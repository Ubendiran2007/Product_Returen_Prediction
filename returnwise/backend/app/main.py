"""ReturnWise FastAPI Backend — Main Application."""
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from datetime import datetime
import pandas as pd
import logging
import shutil
import os

from app.core.config import settings
from app.db.mongodb import get_db, check_connection, setup_indexes, drop_all_collections
from app.preprocessing.cleaner import DataCleaner
from app.analytics.engine import AnalyticsEngine
from app.features.engineer import FeatureEngineer
from app.models.predictor import ReturnPredictor
from app.reports.generator import ExcelReportGenerator, PDFReportGenerator

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ReturnWise API",
    description="E-Commerce Return Intelligence Platform",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global state ───────────────────────────────────────────────────────────────
_analytics_engine = None
_quality_report = None
_feature_result = None
_model_result = None
_predictor = None


def _get_engine() -> AnalyticsEngine:
    """Get or initialize the analytics engine."""
    global _analytics_engine
    if _analytics_engine is None:
        processed = settings.processed_path
        if (processed / "orders_cleaned.csv").exists():
            _analytics_engine = AnalyticsEngine(processed_path=processed)
        else:
            # Auto-clean raw data first
            cleaner = DataCleaner(settings.raw_path, processed)
            result = cleaner.run_full_pipeline()
            global _quality_report
            _quality_report = result["quality_report"]
            _analytics_engine = AnalyticsEngine(data=result["cleaned_data"])
            _save_to_mongo(result)
    return _analytics_engine


def _save_to_mongo(result: dict):
    """Save data to MongoDB."""
    try:
        if not check_connection():
            logger.warning("MongoDB not available — skipping database save")
            return

        db = get_db()
        setup_indexes()

        # Clear existing data
        for coll in ["orders", "order_items", "products", "customers", "returns"]:
            db[coll].delete_many({})

        # Insert cleaned data
        for name, df in result["cleaned_data"].items():
            records = df.copy()
            for col in records.columns:
                if pd.api.types.is_datetime64_any_dtype(records[col]):
                    records[col] = records[col].dt.strftime("%Y-%m-%d")
            docs = records.to_dict("records")
            if docs:
                db[name].insert_many(docs)
                logger.info(f"Inserted {len(docs)} records into {name}")

        # Save quality report
        if result.get("quality_report"):
            db.data_quality_reports.insert_one({
                **result["quality_report"],
                "created_at": datetime.utcnow().isoformat(),
            })

        # Save dataset metadata
        db.datasets.update_one(
            {"name": "ecommerce_returns"},
            {"$set": {
                "name": "ecommerce_returns",
                "status": "processed",
                "tables": list(result["cleaned_data"].keys()),
                "total_records": sum(len(df) for df in result["cleaned_data"].values()),
                "imported_at": datetime.utcnow().isoformat(),
            }},
            upsert=True
        )

        logger.info("Data saved to MongoDB successfully")
    except Exception as e:
        logger.error(f"Error saving to MongoDB: {e}")


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    mongo_ok = check_connection()
    raw_files = list(settings.raw_path.glob("*.csv")) if settings.raw_path.exists() else []
    processed_files = list(settings.processed_path.glob("*.csv"))
    return {
        "status": "healthy",
        "mongodb": "connected" if mongo_ok else "disconnected",
        "raw_files": len(raw_files),
        "processed_files": len(processed_files),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Dataset ────────────────────────────────────────────────────────────────────

@app.get("/api/datasets")
def get_datasets():
    raw_files = []
    if settings.raw_path.exists():
        for f in settings.raw_path.glob("*.csv"):
            df = pd.read_csv(f)
            raw_files.append({
                "name": f.name,
                "rows": len(df),
                "columns": len(df.columns),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })

    processed_files = []
    for f in settings.processed_path.glob("*.csv"):
        df = pd.read_csv(f)
        processed_files.append({
            "name": f.name,
            "rows": len(df),
            "columns": len(df.columns),
            "size_kb": round(f.stat().st_size / 1024, 1),
        })

    return {"raw": raw_files, "processed": processed_files}


@app.post("/api/datasets/upload")
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported")

    if file.size and file.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB}MB")

    safe_name = file.filename.replace("..", "").replace("/", "_").replace("\\", "_")
    dest = settings.raw_path / safe_name
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"message": f"Uploaded {safe_name}", "path": str(dest)}


@app.get("/api/datasets/profile")
def profile_dataset():
    """Get dataset profiling information."""
    engine = _get_engine()
    tables = {
        "orders": engine.orders,
        "order_items": engine.order_items,
        "products": engine.products,
        "customers": engine.customers,
        "returns": engine.returns,
    }
    profiles = {}
    for name, df in tables.items():
        col_profiles = []
        for col in df.columns:
            col_profiles.append({
                "name": col,
                "type": str(df[col].dtype),
                "missing": int(df[col].isnull().sum()),
                "missing_pct": round(df[col].isnull().sum() / len(df) * 100, 2),
                "unique": int(df[col].nunique()),
                "sample_values": [str(v) for v in df[col].dropna().head(5).tolist()],
            })
        profiles[name] = {
            "rows": len(df),
            "columns": len(df.columns),
            "column_profiles": col_profiles,
        }
    return profiles


@app.post("/api/datasets/clean")
def clean_dataset():
    """Run or re-run the cleaning pipeline."""
    global _analytics_engine, _quality_report
    cleaner = DataCleaner(settings.raw_path, settings.processed_path)
    result = cleaner.run_full_pipeline()
    _quality_report = result["quality_report"]
    _analytics_engine = AnalyticsEngine(data=result["cleaned_data"])
    _save_to_mongo(result)
    return {
        "message": "Data cleaned successfully",
        "quality_score": _quality_report["overall_score"],
        "cleaning_actions": len(_quality_report["cleaning_log"]),
    }


# ── Overview ───────────────────────────────────────────────────────────────────

@app.get("/api/overview")
def get_overview(
    date_from: str = None, date_to: str = None,
    category: str = None, region: str = None,
    status: str = None, payment_method: str = None
):
    engine = _get_engine()
    filters = {k: v for k, v in {
        "date_from": date_from, "date_to": date_to,
        "category": category, "region": region,
        "status": status, "payment_method": payment_method,
    }.items() if v}
    kpis = engine.get_overview_kpis(filters or None)
    charts = engine.get_overview_charts(filters or None)
    filter_opts = engine.get_filter_options()
    return {"kpis": kpis, "charts": charts, "filters": filter_opts}


# ── Analytics ──────────────────────────────────────────────────────────────────

@app.get("/api/analytics/returns")
def get_returns_analytics(category: str = None, date_from: str = None, date_to: str = None, region: str = None):
    engine = _get_engine()
    filters = {k: v for k, v in {"category": category, "date_from": date_from, "date_to": date_to, "region": region}.items() if v}
    return engine.get_returns_analytics(filters or None)


@app.get("/api/analytics/categories")
def get_category_analytics(category: str = None):
    engine = _get_engine()
    filters = {"category": category} if category else None
    return engine.get_product_analytics(filters)


@app.get("/api/analytics/discounts")
def get_discount_analytics(category: str = None):
    engine = _get_engine()
    filters = {"category": category} if category else None
    return engine.get_discount_analytics(filters)


@app.get("/api/analytics/delivery")
def get_delivery_analytics():
    return {
        "available": False,
        "message": "Delivery analysis is unavailable. The dataset does not contain delivery date fields "
                   "(promised_delivery_date, actual_delivery_date) or courier information. "
                   "To enable delivery insights, please provide a dataset with delivery tracking data.",
        "required_fields": ["promised_delivery_date", "actual_delivery_date", "courier_name"],
    }


@app.get("/api/analytics/customers")
def get_customer_analytics(region: str = None, date_from: str = None, date_to: str = None):
    engine = _get_engine()
    filters = {k: v for k, v in {"region": region, "date_from": date_from, "date_to": date_to}.items() if v}
    return engine.get_customer_analytics(filters or None)


@app.get("/api/analytics/sellers")
def get_seller_analytics(category: str = None):
    engine = _get_engine()
    filters = {"category": category} if category else None
    return engine.get_seller_analytics(filters)


# ── Data Quality ───────────────────────────────────────────────────────────────

@app.get("/api/data-quality")
def get_data_quality():
    global _quality_report
    _get_engine()  # Ensure data is loaded
    if _quality_report:
        return _quality_report
    # If no quality report yet, run cleaning
    cleaner = DataCleaner(settings.raw_path, settings.processed_path)
    result = cleaner.run_full_pipeline()
    _quality_report = result["quality_report"]
    return _quality_report


# ── Data Explorer ──────────────────────────────────────────────────────────────

@app.get("/api/data-explorer")
def explore_data(
    table: str = "orders",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    sort_by: str = None,
    sort_order: str = "asc",
    search: str = None,
):
    engine = _get_engine()
    return engine.get_data_explorer(table, page, page_size, sort_by, sort_order, search)


# ── Feature Engineering ────────────────────────────────────────────────────────

@app.post("/api/features/generate")
def generate_features():
    global _feature_result
    engine = _get_engine()
    fe = FeatureEngineer(
        engine.orders, engine.order_items, engine.products,
        engine.customers, engine.returns
    )
    result = fe.generate_features()

    # Store feature matrix for ML
    _feature_result = result

    # Save to processed
    fm = result["feature_matrix"].copy()
    for col in fm.columns:
        if pd.api.types.is_datetime64_any_dtype(fm[col]):
            fm[col] = fm[col].dt.strftime("%Y-%m-%d")
        if hasattr(fm[col], "cat"):
            fm[col] = fm[col].astype(str)
    fm.to_csv(settings.processed_path / "feature_matrix.csv", index=False)

    return {
        "feature_stats": result["feature_stats"],
        "feature_catalog": result["feature_catalog"],
        "total_records": result["total_records"],
        "total_features": result["total_features"],
        "target_distribution": result["target_distribution"],
    }


@app.get("/api/features")
def get_features():
    if _feature_result:
        return {
            "feature_stats": _feature_result["feature_stats"],
            "feature_catalog": _feature_result["feature_catalog"],
            "total_records": _feature_result["total_records"],
            "total_features": _feature_result["total_features"],
            "target_distribution": _feature_result["target_distribution"],
        }
    raise HTTPException(404, "Features not generated yet. POST /api/features/generate first.")


# ── ML Models ──────────────────────────────────────────────────────────────────

@app.post("/api/models/train")
def train_models():
    global _model_result, _predictor
    if _feature_result is None:
        raise HTTPException(400, "Generate features first: POST /api/features/generate")

    predictor = ReturnPredictor()
    X_train, X_test, y_train, y_test = predictor.prepare_data(_feature_result["feature_matrix"])
    result = predictor.train_models(X_train, X_test, y_train, y_test)

    _model_result = result
    _predictor = predictor

    # Save to MongoDB if available
    try:
        if check_connection():
            db = get_db()
            db.model_runs.insert_one({
                **result,
                "created_at": datetime.utcnow().isoformat(),
            })
    except Exception as e:
        logger.warning(f"Could not save model results to MongoDB: {e}")

    return result


@app.get("/api/models/results")
def get_model_results():
    if _model_result:
        return _model_result
    raise HTTPException(404, "No models trained yet. POST /api/models/train first.")


@app.get("/api/models/risk-scores")
def get_risk_scores(limit: int = Query(50, ge=10, le=500)):
    if _predictor is None or _feature_result is None:
        raise HTTPException(400, "Train models first")
    scores = _predictor.get_risk_scores(_feature_result["feature_matrix"].head(limit))
    return {"scores": scores, "model": "random_forest", "total": len(scores)}


# ── Recommendations ───────────────────────────────────────────────────────────

@app.get("/api/recommendations")
def get_recommendations():
    engine = _get_engine()
    kpis = engine.get_overview_kpis()
    analytics = engine.get_returns_analytics()
    discount = engine.get_discount_analytics()
    customer = engine.get_customer_analytics()
    product = engine.get_product_analytics()

    recommendations = []

    # Category recommendations
    cats = analytics["category_return_rates"]
    if cats:
        top = cats[0]
        recommendations.append({
            "id": 1,
            "title": f"Investigate High Returns in {top['category']}",
            "finding": f"{top['category']} has the highest return rate at {top['return_rate']}%",
            "metric": f"{int(top['returned_items'])} returned out of {int(top['total_items'])} items",
            "sample_size": int(top["total_items"]),
            "interpretation": "This category significantly exceeds the overall return rate, suggesting systematic quality or expectation issues",
            "action": "Audit product listings, quality standards, and customer feedback for this category",
            "expected_impact": "Medium — could reduce overall returns by 1-3% if addressed",
            "evidence_strength": "Strong",
            "follow_up_kpi": f"Monthly return rate for {top['category']}",
            "category": "category",
            "priority": "high",
        })

    # Return reasons
    reasons = analytics["return_reasons"]
    if reasons:
        top_reason = reasons[0]
        recommendations.append({
            "id": 2,
            "title": f"Address '{top_reason['reason']}' — Top Return Reason",
            "finding": f"'{top_reason['reason']}' accounts for {top_reason['percentage']}% of all returns",
            "metric": f"{top_reason['count']} returns with this reason",
            "sample_size": int(top_reason["count"]),
            "interpretation": "The most frequent return reason represents a key area for operational improvement",
            "action": "Implement specific measures to address this return reason (e.g., better descriptions, quality checks, price matching)",
            "expected_impact": "High — addressing the top reason could reduce returns significantly",
            "evidence_strength": "Strong",
            "follow_up_kpi": f"Monthly count of '{top_reason['reason']}' returns",
            "category": "operations",
            "priority": "high",
        })

    # Discount analysis
    disc_rates = discount["return_rate_by_discount"]
    if len(disc_rates) > 1:
        max_disc = max(disc_rates, key=lambda x: x["return_rate"])
        min_disc = min(disc_rates, key=lambda x: x["return_rate"])
        recommendations.append({
            "id": 3,
            "title": "Discount Strategy Review",
            "finding": f"Return rate varies from {min_disc['return_rate']}% ({min_disc['discount_label']}) to {max_disc['return_rate']}% ({max_disc['discount_label']})",
            "metric": f"Highest return rate at {max_disc['discount_label']} discount level",
            "sample_size": int(max_disc["total"]),
            "interpretation": "The relationship between discounts and returns is observational — correlation does not imply causation",
            "action": "Monitor return rates by discount tier and investigate if specific discount levels attract return-prone purchases",
            "expected_impact": "Low to Medium — depends on causal relationship",
            "evidence_strength": "Moderate — observational correlation",
            "follow_up_kpi": "Return rate by discount range (monthly)",
            "category": "pricing",
            "priority": "medium",
        })

    # Customer segments
    segments = customer.get("segments", [])
    high_risk_seg = [s for s in segments if "High" in s.get("segment", "")]
    if high_risk_seg:
        seg = high_risk_seg[0]
        recommendations.append({
            "id": 4,
            "title": "High-Risk Customer Segment Intervention",
            "finding": f"{int(seg['customer_count'])} customers in 'High Return Risk' segment with avg return rate {seg['avg_return_rate']}%",
            "metric": f"Average {seg['avg_orders']} orders, avg spend ₹{seg['avg_spent']:.0f}",
            "sample_size": int(seg["customer_count"]),
            "interpretation": "A subset of customers consistently returns a high proportion of orders",
            "action": "Implement targeted communication, product recommendations, and sizing guides for these customers",
            "expected_impact": "Medium — personalized interventions can reduce repeat returns",
            "evidence_strength": "Strong",
            "follow_up_kpi": "Return rate of high-risk segment over time",
            "category": "customer",
            "priority": "medium",
        })

    # Refund cost
    recommendations.append({
        "id": 5,
        "title": "Return Cost Optimization",
        "finding": f"Total refund amount is ₹{kpis['total_refund_amount']:,.2f} across {kpis['returned_items']} returned items",
        "metric": f"Average refund per item: ₹{kpis['total_refund_amount'] / max(kpis['returned_items'], 1):,.2f}",
        "sample_size": kpis["returned_items"],
        "interpretation": "Returns represent a significant cost center that could be reduced through targeted interventions",
        "action": "Prioritize return reduction in high-value categories and address top return reasons",
        "expected_impact": "High — direct financial impact from reduced refunds",
        "evidence_strength": "Strong — based on actual refund data",
        "follow_up_kpi": "Monthly total refund amount and return rate",
        "category": "finance",
        "priority": "high",
    })

    # Product quality
    products = product.get("products", [])
    high_return_prods = [p for p in products if p.get("is_high_return") and p.get("has_min_sample")]
    if high_return_prods:
        recommendations.append({
            "id": 6,
            "title": f"{len(high_return_prods)} Products with Elevated Return Rates",
            "finding": f"{len(high_return_prods)} products have return rates above 10% with sufficient sample sizes",
            "metric": f"Highest: {high_return_prods[0]['product_name']} at {high_return_prods[0]['return_rate']}%",
            "sample_size": int(high_return_prods[0]["total_sold"]),
            "interpretation": "These products consistently underperform on returns, suggesting quality or description issues",
            "action": "Review product listings, customer reviews, and quality for flagged products",
            "expected_impact": "Medium — focused improvements on specific products",
            "evidence_strength": "Strong — minimum sample size applied",
            "follow_up_kpi": "Monthly return rate per product",
            "category": "product",
            "priority": "medium",
        })

    return {"recommendations": recommendations, "total": len(recommendations)}


# ── Reports ────────────────────────────────────────────────────────────────────

@app.post("/api/reports/excel")
def generate_excel_report():
    engine = _get_engine()
    generator = ExcelReportGenerator(engine, _quality_report)
    filepath = generator.generate(settings.reports_path)
    return FileResponse(filepath, filename=Path(filepath).name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/reports/pdf")
def generate_pdf_report():
    engine = _get_engine()
    generator = PDFReportGenerator(engine, _quality_report, _model_result)
    filepath = generator.generate(settings.reports_path)
    return FileResponse(filepath, filename=Path(filepath).name, media_type="application/pdf")


@app.get("/api/reports/csv/{table}")
def export_csv(table: str):
    engine = _get_engine()
    table_map = {
        "orders": engine.orders,
        "order_items": engine.order_items,
        "products": engine.products,
        "customers": engine.customers,
        "returns": engine.returns,
    }
    df = table_map.get(table)
    if df is None:
        raise HTTPException(404, f"Table '{table}' not found")

    filepath = settings.reports_path / f"{table}_export.csv"
    export = df.copy()
    for col in export.columns:
        if pd.api.types.is_datetime64_any_dtype(export[col]):
            export[col] = export[col].dt.strftime("%Y-%m-%d")
    export.to_csv(filepath, index=False)
    return FileResponse(filepath, filename=f"{table}_export.csv", media_type="text/csv")


# ── Settings / Filters ─────────────────────────────────────────────────────────

@app.get("/api/filters")
def get_filter_options():
    engine = _get_engine()
    return engine.get_filter_options()


@app.get("/api/settings")
def get_settings():
    return {
        "database": {
            "connected": check_connection(),
            "name": settings.MONGODB_DB,
        },
        "data_paths": {
            "raw": str(settings.raw_path),
            "processed": str(settings.processed_path),
            "reports": str(settings.reports_path),
        },
        "dataset_status": {
            "raw_files": len(list(settings.raw_path.glob("*.csv"))) if settings.raw_path.exists() else 0,
            "processed_files": len(list(settings.processed_path.glob("*.csv"))),
        },
    }


# ── Init on startup ───────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("ReturnWise API starting up...")
    if settings.raw_path.exists() and list(settings.raw_path.glob("*.csv")):
        try:
            _get_engine()
            logger.info("Analytics engine initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing engine on startup: {e}")
