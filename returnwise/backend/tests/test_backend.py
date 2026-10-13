"""Comprehensive automated tests for ReturnWise backend."""
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
import pandas as pd
import numpy as np

from app.core.config import settings
from app.preprocessing.cleaner import DataCleaner
from app.analytics.engine import AnalyticsEngine
from app.features.engineer import FeatureEngineer
from app.models.predictor import ReturnPredictor
from app.reports.generator import ExcelReportGenerator, PDFReportGenerator
from app.db.mongodb import get_db, check_connection


def test_cleaner_and_csv_parsing():
    """Verify raw CSV parsing, validation, and cleaning."""
    cleaner = DataCleaner(settings.raw_path, settings.processed_path)
    res = cleaner.run_full_pipeline()
    
    assert "cleaned_data" in res
    assert "quality_report" in res
    cleaned = res["cleaned_data"]
    
    for key in ["customers", "orders", "order_items", "products", "returns"]:
        assert key in cleaned
        assert len(cleaned[key]) > 0
        assert not cleaned[key].empty


def test_data_quality_report():
    """Verify data quality issues detection and report structure."""
    cleaner = DataCleaner(settings.raw_path, settings.processed_path)
    res = cleaner.run_full_pipeline()
    qr = res["quality_report"]
    
    assert "before" in qr
    assert "after" in qr
    assert "cleaning_log" in qr
    assert "overall_score" in qr
    assert isinstance(qr["cleaning_log"], list)
    assert qr["overall_score"] >= 80.0


def test_analytics_engine_calculations():
    """Verify KPIs, return-rate, discount, and category calculations."""
    engine = AnalyticsEngine(processed_path=settings.processed_path)
    
    # 1. Overview KPIs
    kpis = engine.get_overview_kpis()
    assert "total_orders" in kpis
    assert "return_rate" in kpis
    assert 0 <= kpis["return_rate"] <= 100
    assert kpis["total_orders"] > 0
    
    # 2. Returns Analytics
    returns_data = engine.get_returns_analytics()
    assert "return_reasons" in returns_data
    assert "monthly_trends" in returns_data
    
    # 3. Product Analytics
    prod_data = engine.get_product_analytics()
    assert "products" in prod_data
    assert "category_summary" in prod_data
    
    # 4. Discount Analytics
    disc_data = engine.get_discount_analytics()
    assert "return_rate_by_discount" in disc_data
    assert "discount_distribution" in disc_data


def test_customer_and_seller_analytics():
    """Verify customer segmentation and seller benchmarking."""
    engine = AnalyticsEngine(processed_path=settings.processed_path)
    
    cust = engine.get_customer_analytics()
    assert "customers" in cust
    assert "segments" in cust
    assert "region_stats" in cust
    
    seller = engine.get_seller_analytics()
    assert "category_performance" in seller
    assert "note" in seller


def test_feature_engineering_and_no_leakage():
    """Verify feature engineering calculations and data leakage prevention."""
    engine = AnalyticsEngine(processed_path=settings.processed_path)
    fe = FeatureEngineer(
        engine.orders,
        engine.order_items,
        engine.products,
        engine.customers,
        engine.returns
    )
    result = fe.generate_features()
    
    assert "feature_matrix" in result
    df = result["feature_matrix"]
    
    # Target column must exist
    assert "is_returned" in df.columns
    # Ensure post-purchase return details are NOT leaky features
    leakage_cols = ["refund_amount", "returned_quantity", "return_processed_at"]
    for col in leakage_cols:
        assert col not in df.columns


def test_machine_learning_pipeline():
    """Verify predictor model training, scoring, and metrics."""
    engine = AnalyticsEngine(processed_path=settings.processed_path)
    fe = FeatureEngineer(
        engine.orders,
        engine.order_items,
        engine.products,
        engine.customers,
        engine.returns
    )
    feat_res = fe.generate_features()
    
    predictor = ReturnPredictor()
    X_train, X_test, y_train, y_test = predictor.prepare_data(feat_res["feature_matrix"])
    train_res = predictor.train_models(X_train, X_test, y_train, y_test)
    
    assert "models" in train_res
    assert "logistic_regression" in train_res["models"]
    assert "random_forest" in train_res["models"]
    lr_metrics = train_res["models"]["logistic_regression"]
    assert "f1" in lr_metrics or "roc_auc" in lr_metrics


def test_reports_generation():
    """Verify Excel and PDF file exports."""
    engine = AnalyticsEngine(processed_path=settings.processed_path)
    cleaner = DataCleaner(settings.raw_path, settings.processed_path)
    res = cleaner.run_full_pipeline()
    qr = res["quality_report"]
    
    excel_gen = ExcelReportGenerator(engine, qr)
    excel_path = excel_gen.generate(settings.reports_path)
    assert Path(excel_path).exists()
    assert Path(excel_path).stat().st_size > 0
    
    pdf_gen = PDFReportGenerator(engine, qr)
    pdf_path = pdf_gen.generate(settings.reports_path)
    assert Path(pdf_path).exists()
    assert Path(pdf_path).stat().st_size > 0


def test_mongodb_connection():
    """Verify MongoDB connectivity and collections."""
    conn = check_connection()
    assert conn is True
    db = get_db()
    assert db is not None
    collections = db.list_collection_names()
    assert len(collections) > 0
