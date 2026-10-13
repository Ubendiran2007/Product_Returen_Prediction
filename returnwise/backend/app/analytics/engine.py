"""Analytics engine for ReturnWise — all calculations from real data."""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """Compute all analytics from cleaned data."""

    def __init__(self, data: dict = None, processed_path: Path = None):
        """Initialize with either in-memory data or path to processed CSVs."""
        if data:
            self.orders = data.get("orders")
            self.order_items = data.get("order_items")
            self.products = data.get("products")
            self.customers = data.get("customers")
            self.returns = data.get("returns")
        elif processed_path:
            self._load_from_path(processed_path)
        else:
            raise ValueError("Must provide either data dict or processed_path")

        # Build merged datasets
        self._build_merged()

    def _load_from_path(self, path: Path):
        """Load cleaned CSVs."""
        self.orders = pd.read_csv(path / "orders_cleaned.csv")
        self.order_items = pd.read_csv(path / "order_items_cleaned.csv")
        self.products = pd.read_csv(path / "products_cleaned.csv")
        self.customers = pd.read_csv(path / "customers_cleaned.csv")
        self.returns = pd.read_csv(path / "returns_cleaned.csv")

        # Parse dates
        self.orders["order_date"] = pd.to_datetime(self.orders["order_date"], errors="coerce")
        self.returns["return_date"] = pd.to_datetime(self.returns["return_date"], errors="coerce")
        self.customers["signup_date"] = pd.to_datetime(self.customers["signup_date"], errors="coerce")

    def _build_merged(self):
        """Build merged datasets for analytics."""
        # Order items with product info
        self.items_with_products = self.order_items.merge(
            self.products[["product_id", "product_name", "category", "unit_cost", "margin_pct"]],
            on="product_id", how="left"
        )

        # Mark returned items
        returned_item_ids = set(self.returns["order_item_id"])
        self.items_with_products["is_returned"] = self.items_with_products["order_item_id"].isin(returned_item_ids)

        # Items with order info
        self.items_full = self.items_with_products.merge(
            self.orders[["order_id", "customer_id", "order_date", "order_status", "payment_method", "shipping_fee"]],
            on="order_id", how="left"
        )

        # Items with return details (for returned items)
        self.returned_items = self.items_full[self.items_full["is_returned"]].merge(
            self.returns[["order_item_id", "return_date", "return_reason", "refund_amount"]],
            on="order_item_id", how="left"
        )

    # ── Overview KPIs ──────────────────────────────────────────────────────────

    def get_overview_kpis(self, filters: dict = None) -> dict:
        """Compute overview dashboard KPIs."""
        orders = self._apply_order_filters(self.orders, filters)
        items = self._apply_item_filters(self.items_full, filters)

        total_orders = len(orders)
        returned_order_ids = set(self.returns["order_id"])

        # Filter returned orders based on current filter context
        returned_orders = orders[orders["order_id"].isin(returned_order_ids)]
        total_returned = len(returned_orders)

        # Eligible orders: Delivered + Returned + Refunded (not Cancelled)
        eligible_statuses = ["Delivered", "Returned", "Refunded"]
        eligible_orders = orders[orders["order_status"].isin(eligible_statuses)]
        total_eligible = len(eligible_orders)

        returned_eligible = eligible_orders[eligible_orders["order_id"].isin(returned_order_ids)]
        return_rate = (len(returned_eligible) / total_eligible * 100) if total_eligible > 0 else 0

        total_revenue = float(orders["total_amount"].sum())
        avg_order_value = float(orders["total_amount"].mean()) if total_orders > 0 else 0

        # Item-level stats
        total_items = len(items)
        returned_items_count = int(items["is_returned"].sum())
        item_return_rate = (returned_items_count / total_items * 100) if total_items > 0 else 0

        avg_discount = float(items["discount_pct"].mean() * 100)

        # Unique counts
        unique_products = int(items["product_id"].nunique())
        unique_customers = int(orders["customer_id"].nunique())
        unique_categories = int(self.products["category"].nunique())

        # Cancelled orders
        cancelled = len(orders[orders["order_status"] == "Cancelled"])
        cancellation_rate = (cancelled / total_orders * 100) if total_orders > 0 else 0

        return {
            "total_orders": total_orders,
            "total_eligible_orders": total_eligible,
            "total_returned_orders": len(returned_eligible),
            "return_rate": round(return_rate, 2),
            "total_revenue": round(total_revenue, 2),
            "avg_order_value": round(avg_order_value, 2),
            "total_items": total_items,
            "returned_items": returned_items_count,
            "item_return_rate": round(item_return_rate, 2),
            "avg_discount_pct": round(avg_discount, 2),
            "unique_products": unique_products,
            "unique_customers": unique_customers,
            "unique_categories": unique_categories,
            "cancelled_orders": cancelled,
            "cancellation_rate": round(cancellation_rate, 2),
            "total_refund_amount": round(float(self.returns["refund_amount"].sum()), 2),
        }

    # ── Returns Analytics ──────────────────────────────────────────────────────

    def get_returns_analytics(self, filters: dict = None) -> dict:
        """Comprehensive return analysis."""
        items = self._apply_item_filters(self.items_full, filters)

        # Return rate by category
        cat_stats = items.groupby("category").agg(
            total_items=("order_item_id", "count"),
            returned_items=("is_returned", "sum"),
            total_revenue=("line_total", "sum"),
        ).reset_index()
        cat_stats["return_rate"] = (cat_stats["returned_items"] / cat_stats["total_items"] * 100).round(2)
        cat_stats = cat_stats.sort_values("return_rate", ascending=False)

        # Return reasons distribution
        reasons = self.returns["return_reason"].value_counts().reset_index()
        reasons.columns = ["reason", "count"]
        reasons["percentage"] = (reasons["count"] / reasons["count"].sum() * 100).round(2)

        # Returns over time (monthly)
        returns_copy = self.returns.copy()
        returns_copy["month"] = returns_copy["return_date"].dt.to_period("M").astype(str)
        monthly_returns = returns_copy.groupby("month").size().reset_index(name="return_count")

        # Orders over time for comparison
        orders_copy = self.orders.copy()
        orders_copy["month"] = orders_copy["order_date"].dt.to_period("M").astype(str)
        monthly_orders = orders_copy.groupby("month").size().reset_index(name="order_count")

        monthly_merged = monthly_orders.merge(monthly_returns, on="month", how="left").fillna(0)
        monthly_merged["return_count"] = monthly_merged["return_count"].astype(int)
        monthly_merged["return_rate"] = (monthly_merged["return_count"] / monthly_merged["order_count"] * 100).round(2)

        # Discount vs returns
        items_disc = items.copy()
        bins = [0, 0.001, 0.05, 0.10, 0.15, 0.20, 1.0]
        labels = ["No discount", "1-5%", "6-10%", "11-15%", "16-20%", ">20%"]
        items_disc["discount_range"] = pd.cut(items_disc["discount_pct"], bins=bins, labels=labels, include_lowest=True)

        disc_stats = items_disc.groupby("discount_range", observed=True).agg(
            total=("order_item_id", "count"),
            returned=("is_returned", "sum"),
        ).reset_index()
        disc_stats["return_rate"] = (disc_stats["returned"] / disc_stats["total"] * 100).round(2)

        # Returned vs non-returned comparison
        returned_items = items[items["is_returned"]]
        non_returned = items[~items["is_returned"]]

        comparison = {
            "returned": {
                "count": int(len(returned_items)),
                "avg_price": round(float(returned_items["unit_price"].mean()), 2) if len(returned_items) > 0 else 0,
                "avg_discount": round(float(returned_items["discount_pct"].mean() * 100), 2) if len(returned_items) > 0 else 0,
                "avg_line_total": round(float(returned_items["line_total"].mean()), 2) if len(returned_items) > 0 else 0,
                "avg_quantity": round(float(returned_items["quantity"].mean()), 2) if len(returned_items) > 0 else 0,
            },
            "non_returned": {
                "count": int(len(non_returned)),
                "avg_price": round(float(non_returned["unit_price"].mean()), 2) if len(non_returned) > 0 else 0,
                "avg_discount": round(float(non_returned["discount_pct"].mean() * 100), 2) if len(non_returned) > 0 else 0,
                "avg_line_total": round(float(non_returned["line_total"].mean()), 2) if len(non_returned) > 0 else 0,
                "avg_quantity": round(float(non_returned["quantity"].mean()), 2) if len(non_returned) > 0 else 0,
            },
        }

        return {
            "category_return_rates": cat_stats.to_dict("records"),
            "return_reasons": reasons.to_dict("records"),
            "monthly_trends": monthly_merged.to_dict("records"),
            "discount_return_rates": disc_stats.to_dict("records"),
            "returned_vs_non_returned": comparison,
        }

    # ── Product Intelligence ───────────────────────────────────────────────────

    def get_product_analytics(self, filters: dict = None, min_sample: int = 5) -> dict:
        """Product-level return analysis."""
        items = self._apply_item_filters(self.items_full, filters)

        # Product-level stats
        prod_stats = items.groupby(["product_id", "product_name", "category"]).agg(
            total_sold=("order_item_id", "count"),
            total_returned=("is_returned", "sum"),
            total_quantity=("quantity", "sum"),
            total_revenue=("line_total", "sum"),
            avg_discount=("discount_pct", "mean"),
            avg_price=("unit_price", "first"),
        ).reset_index()
        prod_stats["return_rate"] = (prod_stats["total_returned"] / prod_stats["total_sold"] * 100).round(2)
        prod_stats["avg_discount"] = (prod_stats["avg_discount"] * 100).round(2)
        prod_stats["total_revenue"] = prod_stats["total_revenue"].round(2)
        prod_stats["avg_price"] = prod_stats["avg_price"].round(2)

        # Flag products with enough samples and high return rate
        prod_stats["has_min_sample"] = prod_stats["total_sold"] >= min_sample
        prod_stats["is_high_return"] = (prod_stats["return_rate"] > 10) & (prod_stats["has_min_sample"])

        prod_stats = prod_stats.sort_values("return_rate", ascending=False)

        # Category summary
        cat_summary = items.groupby("category").agg(
            total_products=("product_id", "nunique"),
            total_sold=("order_item_id", "count"),
            total_returned=("is_returned", "sum"),
            total_revenue=("line_total", "sum"),
        ).reset_index()
        cat_summary["return_rate"] = (cat_summary["total_returned"] / cat_summary["total_sold"] * 100).round(2)
        cat_summary["total_revenue"] = cat_summary["total_revenue"].round(2)
        cat_summary = cat_summary.sort_values("return_rate", ascending=False)

        # Return reasons by category
        returned_with_reason = self.returned_items.copy()
        if filters and filters.get("category"):
            returned_with_reason = returned_with_reason[returned_with_reason["category"] == filters["category"]]

        cat_reasons = returned_with_reason.groupby(["category", "return_reason"]).size().reset_index(name="count")

        return {
            "products": prod_stats.to_dict("records"),
            "category_summary": cat_summary.to_dict("records"),
            "category_return_reasons": cat_reasons.to_dict("records"),
            "min_sample_size": min_sample,
            "total_products": int(self.products.shape[0]),
        }

    # ── Customer Segmentation ─────────────────────────────────────────────────

    def get_customer_analytics(self, filters: dict = None) -> dict:
        """Customer-level analytics and segmentation."""
        orders = self._apply_order_filters(self.orders, filters)
        returned_order_ids = set(self.returns["order_id"])

        # Customer-level aggregation
        cust_stats = orders.groupby("customer_id").agg(
            total_orders=("order_id", "count"),
            total_spent=("total_amount", "sum"),
            avg_order_value=("total_amount", "mean"),
            first_order=("order_date", "min"),
            last_order=("order_date", "max"),
        ).reset_index()

        # Count returned orders per customer
        orders_returned = orders[orders["order_id"].isin(returned_order_ids)]
        return_counts = orders_returned.groupby("customer_id")["order_id"].count().reset_index()
        return_counts.columns = ["customer_id", "returned_orders"]

        cust_stats = cust_stats.merge(return_counts, on="customer_id", how="left")
        cust_stats["returned_orders"] = cust_stats["returned_orders"].fillna(0).astype(int)
        cust_stats["return_rate"] = (cust_stats["returned_orders"] / cust_stats["total_orders"] * 100).round(2)
        cust_stats["total_spent"] = cust_stats["total_spent"].round(2)
        cust_stats["avg_order_value"] = cust_stats["avg_order_value"].round(2)

        # Add customer demographics
        cust_stats = cust_stats.merge(
            self.customers[["customer_id", "region", "country", "city", "gender", "age", "membership_tier", "acquisition_channel"]],
            on="customer_id", how="left"
        )

        # Segments based on business rules
        def segment_customer(row):
            if row["returned_orders"] == 0:
                if row["total_orders"] >= 10:
                    return "Loyal No-Return"
                return "Standard"
            elif row["return_rate"] > 50:
                return "High Return Risk"
            elif row["return_rate"] > 25:
                return "Moderate Return Risk"
            elif row["total_orders"] >= 10:
                return "Active with Returns"
            else:
                return "Occasional Returner"

        cust_stats["segment"] = cust_stats.apply(segment_customer, axis=1)

        # Segment summary
        seg_summary = cust_stats.groupby("segment").agg(
            customer_count=("customer_id", "count"),
            avg_orders=("total_orders", "mean"),
            avg_return_rate=("return_rate", "mean"),
            avg_spent=("total_spent", "mean"),
        ).reset_index()
        seg_summary = seg_summary.round(2)

        # Region analysis
        region_stats = cust_stats.groupby("region").agg(
            customers=("customer_id", "count"),
            avg_return_rate=("return_rate", "mean"),
            total_spent=("total_spent", "sum"),
        ).reset_index().round(2)

        # Membership tier analysis
        tier_stats = cust_stats.groupby("membership_tier").agg(
            customers=("customer_id", "count"),
            avg_return_rate=("return_rate", "mean"),
            avg_orders=("total_orders", "mean"),
            avg_spent=("total_spent", "mean"),
        ).reset_index().round(2)

        # Gender analysis
        gender_stats = cust_stats.groupby("gender").agg(
            customers=("customer_id", "count"),
            avg_return_rate=("return_rate", "mean"),
            avg_spent=("total_spent", "mean"),
        ).reset_index().round(2)

        # Repeat vs first-time
        repeat = cust_stats[cust_stats["total_orders"] > 1]
        first_time = cust_stats[cust_stats["total_orders"] == 1]

        repeat_vs_first = {
            "repeat": {
                "count": int(len(repeat)),
                "avg_return_rate": round(float(repeat["return_rate"].mean()), 2) if len(repeat) > 0 else 0,
                "avg_orders": round(float(repeat["total_orders"].mean()), 2) if len(repeat) > 0 else 0,
                "avg_spent": round(float(repeat["total_spent"].mean()), 2) if len(repeat) > 0 else 0,
            },
            "first_time": {
                "count": int(len(first_time)),
                "avg_return_rate": round(float(first_time["return_rate"].mean()), 2) if len(first_time) > 0 else 0,
                "avg_orders": 1,
                "avg_spent": round(float(first_time["total_spent"].mean()), 2) if len(first_time) > 0 else 0,
            }
        }

        return {
            "customers": cust_stats.sort_values("return_rate", ascending=False).head(100).to_dict("records"),
            "total_customers": int(len(cust_stats)),
            "segments": seg_summary.to_dict("records"),
            "region_stats": region_stats.to_dict("records"),
            "tier_stats": tier_stats.to_dict("records"),
            "gender_stats": gender_stats.to_dict("records"),
            "repeat_vs_first_time": repeat_vs_first,
        }

    # ── Seller/Category Performance (No seller field — use category as proxy) ─

    def get_seller_analytics(self, filters: dict = None) -> dict:
        """
        Since the dataset has no seller field, we provide category-level performance
        analysis as a proxy. The UI will explain this adaptation.
        """
        items = self._apply_item_filters(self.items_full, filters)

        cat_perf = items.groupby("category").agg(
            total_orders=("order_id", "nunique"),
            total_items=("order_item_id", "count"),
            returned_items=("is_returned", "sum"),
            total_revenue=("line_total", "sum"),
            avg_discount=("discount_pct", "mean"),
            unique_products=("product_id", "nunique"),
        ).reset_index()
        cat_perf["return_rate"] = (cat_perf["returned_items"] / cat_perf["total_items"] * 100).round(2)
        cat_perf["avg_discount"] = (cat_perf["avg_discount"] * 100).round(2)
        cat_perf["total_revenue"] = cat_perf["total_revenue"].round(2)
        cat_perf = cat_perf.sort_values("total_revenue", ascending=False)

        # Return reasons by category
        reasons_by_cat = self.returned_items.groupby(["category", "return_reason"]).size().reset_index(name="count")

        # Payment method distribution by category
        payment_by_cat = items.groupby(["category", "payment_method"]).size().reset_index(name="count")

        return {
            "category_performance": cat_perf.to_dict("records"),
            "return_reasons_by_category": reasons_by_cat.to_dict("records"),
            "payment_by_category": payment_by_cat.to_dict("records"),
            "note": "Seller-level analysis is unavailable as the dataset does not contain seller identifiers. Category-level performance is shown as an alternative.",
        }

    # ── Data Explorer ──────────────────────────────────────────────────────────

    def get_data_explorer(self, table: str, page: int = 1, page_size: int = 50,
                          sort_by: str = None, sort_order: str = "asc",
                          search: str = None, columns: list = None) -> dict:
        """Paginated data exploration."""
        table_map = {
            "orders": self.orders,
            "order_items": self.order_items,
            "products": self.products,
            "customers": self.customers,
            "returns": self.returns,
            "items_full": self.items_full,
        }

        df = table_map.get(table)
        if df is None:
            return {"error": f"Table '{table}' not found"}

        df = df.copy()

        # Search across all string columns
        if search:
            mask = pd.Series([False] * len(df))
            for col in df.select_dtypes(include=["object"]).columns:
                mask |= df[col].str.contains(search, case=False, na=False)
            df = df[mask]

        # Select columns
        if columns:
            valid_cols = [c for c in columns if c in df.columns]
            if valid_cols:
                df = df[valid_cols]

        # Sort
        if sort_by and sort_by in df.columns:
            df = df.sort_values(sort_by, ascending=(sort_order == "asc"))

        total_rows = len(df)
        total_pages = max(1, (total_rows + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        start = (page - 1) * page_size
        end = start + page_size
        page_data = df.iloc[start:end]

        # Convert datetime to string for JSON
        result_df = page_data.copy()
        for col in result_df.columns:
            if pd.api.types.is_datetime64_any_dtype(result_df[col]):
                result_df[col] = result_df[col].dt.strftime("%Y-%m-%d")

        # Column metadata
        col_info = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            missing = int(df[col].isnull().sum())
            col_info.append({
                "name": col,
                "type": dtype,
                "missing": missing,
                "missing_pct": round(missing / total_rows * 100, 2) if total_rows > 0 else 0,
            })

        return {
            "data": result_df.fillna("").to_dict("records"),
            "columns": col_info,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_rows": total_rows,
                "total_pages": total_pages,
            },
            "available_tables": list(table_map.keys()),
        }

    # ── Filter helpers ─────────────────────────────────────────────────────────

    def _apply_order_filters(self, df: pd.DataFrame, filters: dict = None) -> pd.DataFrame:
        """Apply filters to orders dataframe."""
        if not filters:
            return df
        df = df.copy()
        if filters.get("date_from"):
            df = df[df["order_date"] >= pd.to_datetime(filters["date_from"])]
        if filters.get("date_to"):
            df = df[df["order_date"] <= pd.to_datetime(filters["date_to"])]
        if filters.get("status"):
            df = df[df["order_status"] == filters["status"]]
        if filters.get("payment_method"):
            df = df[df["payment_method"] == filters["payment_method"]]
        return df

    def _apply_item_filters(self, df: pd.DataFrame, filters: dict = None) -> pd.DataFrame:
        """Apply filters to items dataframe."""
        if not filters:
            return df
        df = df.copy()
        if filters.get("category"):
            df = df[df["category"] == filters["category"]]
        if filters.get("product_id"):
            df = df[df["product_id"] == filters["product_id"]]
        if filters.get("date_from") and "order_date" in df.columns:
            df = df[df["order_date"] >= pd.to_datetime(filters["date_from"])]
        if filters.get("date_to") and "order_date" in df.columns:
            df = df[df["order_date"] <= pd.to_datetime(filters["date_to"])]
        if filters.get("region") and "customer_id" in df.columns:
            region_custs = self.customers[self.customers["region"] == filters["region"]]["customer_id"]
            df = df[df["customer_id"].isin(region_custs)]
        return df

    # ── Discount Analysis ──────────────────────────────────────────────────────

    def get_discount_analytics(self, filters: dict = None) -> dict:
        """Detailed discount analysis."""
        items = self._apply_item_filters(self.items_full, filters)

        # Discount distribution
        disc_dist = items["discount_pct"].value_counts().sort_index().reset_index()
        disc_dist.columns = ["discount_pct", "count"]
        disc_dist["discount_label"] = (disc_dist["discount_pct"] * 100).astype(int).astype(str) + "%"

        # Return rate by discount level
        disc_return = items.groupby("discount_pct").agg(
            total=("order_item_id", "count"),
            returned=("is_returned", "sum"),
            avg_price=("unit_price", "mean"),
            avg_line_total=("line_total", "mean"),
        ).reset_index()
        disc_return["return_rate"] = (disc_return["returned"] / disc_return["total"] * 100).round(2)
        disc_return["discount_label"] = (disc_return["discount_pct"] * 100).astype(int).astype(str) + "%"
        disc_return["avg_price"] = disc_return["avg_price"].round(2)
        disc_return["avg_line_total"] = disc_return["avg_line_total"].round(2)

        # Discount by category
        disc_cat = items.groupby(["category", "discount_pct"]).agg(
            total=("order_item_id", "count"),
            returned=("is_returned", "sum"),
        ).reset_index()
        disc_cat["return_rate"] = (disc_cat["returned"] / disc_cat["total"] * 100).round(2)
        disc_cat["discount_label"] = (disc_cat["discount_pct"] * 100).astype(int).astype(str) + "%"

        return {
            "discount_distribution": disc_dist.to_dict("records"),
            "return_rate_by_discount": disc_return.to_dict("records"),
            "discount_by_category": disc_cat.to_dict("records"),
        }

    # ── Overview Charts Data ───────────────────────────────────────────────────

    def get_overview_charts(self, filters: dict = None) -> dict:
        """Get all chart data for the overview dashboard."""
        items = self._apply_item_filters(self.items_full, filters)

        # Return rate by category (bar chart)
        cat_return = items.groupby("category").agg(
            total=("order_item_id", "count"),
            returned=("is_returned", "sum"),
        ).reset_index()
        cat_return["return_rate"] = (cat_return["returned"] / cat_return["total"] * 100).round(2)

        # Return reasons (pie chart)
        reasons = self.returns["return_reason"].value_counts().reset_index()
        reasons.columns = ["reason", "count"]

        # Monthly trend
        orders_copy = self.orders.copy()
        orders_copy["month"] = orders_copy["order_date"].dt.to_period("M").astype(str)
        returned_order_ids = set(self.returns["order_id"])
        orders_copy["is_returned"] = orders_copy["order_id"].isin(returned_order_ids)

        monthly = orders_copy.groupby("month").agg(
            total_orders=("order_id", "count"),
            returned_orders=("is_returned", "sum"),
            revenue=("total_amount", "sum"),
        ).reset_index()
        monthly["return_rate"] = (monthly["returned_orders"] / monthly["total_orders"] * 100).round(2)
        monthly["revenue"] = monthly["revenue"].round(2)

        # Payment method distribution
        payment_dist = self.orders["payment_method"].value_counts().reset_index()
        payment_dist.columns = ["method", "count"]

        # Order status distribution
        status_dist = self.orders["order_status"].value_counts().reset_index()
        status_dist.columns = ["status", "count"]

        return {
            "category_return_rates": cat_return.to_dict("records"),
            "return_reasons": reasons.to_dict("records"),
            "monthly_trends": monthly.to_dict("records"),
            "payment_distribution": payment_dist.to_dict("records"),
            "status_distribution": status_dist.to_dict("records"),
        }

    # ── Filter Options ─────────────────────────────────────────────────────────

    def get_filter_options(self) -> dict:
        """Get available filter options from data."""
        return {
            "categories": sorted(self.products["category"].unique().tolist()),
            "regions": sorted(self.customers["region"].unique().tolist()),
            "countries": sorted(self.customers["country"].unique().tolist()),
            "payment_methods": sorted(self.orders["payment_method"].unique().tolist()),
            "order_statuses": sorted(self.orders["order_status"].unique().tolist()),
            "membership_tiers": sorted(self.customers["membership_tier"].unique().tolist()),
            "return_reasons": sorted(self.returns["return_reason"].unique().tolist()),
            "date_range": {
                "min": self.orders["order_date"].min().strftime("%Y-%m-%d") if not self.orders["order_date"].isnull().all() else None,
                "max": self.orders["order_date"].max().strftime("%Y-%m-%d") if not self.orders["order_date"].isnull().all() else None,
            },
        }
