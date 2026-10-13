"""Feature engineering module for ReturnWise."""
import pandas as pd
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Build features from cleaned data for analysis and ML."""

    # Feature catalog — what each feature means and requires
    FEATURE_CATALOG = [
        {
            "name": "discount_percentage",
            "description": "Discount applied to the order item as a percentage (0-20%)",
            "source_columns": ["discount_pct"],
            "transformation": "discount_pct * 100",
            "missing_handling": "Fill with 0 (no discount)",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "line_total",
            "description": "Total value of the order line after discount",
            "source_columns": ["quantity", "unit_price", "discount_pct"],
            "transformation": "quantity * unit_price * (1 - discount_pct)",
            "missing_handling": "Computed from components",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "order_value",
            "description": "Total order amount including shipping",
            "source_columns": ["total_amount"],
            "transformation": "Direct from orders table",
            "missing_handling": "Exclude if missing",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "has_discount",
            "description": "Binary indicator: whether a discount was applied",
            "source_columns": ["discount_pct"],
            "transformation": "1 if discount_pct > 0 else 0",
            "missing_handling": "0 (assume no discount)",
            "type": "binary",
            "leakage_safe": True,
        },
        {
            "name": "item_count_in_order",
            "description": "Number of distinct items in the same order",
            "source_columns": ["order_id", "order_item_id"],
            "transformation": "Count of order_item_id per order_id",
            "missing_handling": "1 (single item order)",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "total_quantity_in_order",
            "description": "Total quantity of all items in the order",
            "source_columns": ["order_id", "quantity"],
            "transformation": "Sum of quantity per order_id",
            "missing_handling": "Use item quantity",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "is_multi_item_order",
            "description": "Whether the order contains multiple items",
            "source_columns": ["order_id", "order_item_id"],
            "transformation": "1 if item_count_in_order > 1 else 0",
            "missing_handling": "0",
            "type": "binary",
            "leakage_safe": True,
        },
        {
            "name": "customer_order_frequency",
            "description": "Total number of historical orders by the customer (before this order)",
            "source_columns": ["customer_id", "order_id", "order_date"],
            "transformation": "Cumulative count of orders per customer, ordered by date",
            "missing_handling": "1 for first order",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "customer_historical_return_rate",
            "description": "Customer's return rate from all previous orders (before current order)",
            "source_columns": ["customer_id", "order_id", "order_date", "is_returned"],
            "transformation": "Expanding mean of is_returned, shifted by 1 to prevent leakage",
            "missing_handling": "0 for first order (no history)",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "product_historical_return_rate",
            "description": "Product's historical return rate from prior orders",
            "source_columns": ["product_id", "order_date", "is_returned"],
            "transformation": "Expanding mean of is_returned for product, shifted by 1",
            "missing_handling": "Overall mean return rate",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "category_return_rate",
            "description": "Historical return rate for the product category",
            "source_columns": ["category", "order_date", "is_returned"],
            "transformation": "Expanding mean of is_returned for category, shifted by 1",
            "missing_handling": "Overall mean return rate",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "price_tier",
            "description": "Price bucket: Low (<500), Medium (500-2000), High (2000-5000), Premium (>5000)",
            "source_columns": ["unit_price"],
            "transformation": "Binning by price thresholds",
            "missing_handling": "Unknown",
            "type": "categorical",
            "leakage_safe": True,
        },
        {
            "name": "order_month",
            "description": "Month of the order (1-12)",
            "source_columns": ["order_date"],
            "transformation": "order_date.month",
            "missing_handling": "Exclude if date missing",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "order_day_of_week",
            "description": "Day of week of the order (0=Monday, 6=Sunday)",
            "source_columns": ["order_date"],
            "transformation": "order_date.dayofweek",
            "missing_handling": "Exclude if date missing",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "is_weekend_order",
            "description": "Whether the order was placed on a weekend",
            "source_columns": ["order_date"],
            "transformation": "1 if dayofweek >= 5 else 0",
            "missing_handling": "0",
            "type": "binary",
            "leakage_safe": True,
        },
        {
            "name": "customer_age",
            "description": "Age of the customer",
            "source_columns": ["age"],
            "transformation": "Direct from customers table",
            "missing_handling": "Median age",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "margin_percentage",
            "description": "Product profit margin percentage",
            "source_columns": ["margin_pct"],
            "transformation": "margin_pct * 100",
            "missing_handling": "Category median",
            "type": "numeric",
            "leakage_safe": True,
        },
        {
            "name": "has_shipping_fee",
            "description": "Whether the order has a shipping fee",
            "source_columns": ["shipping_fee"],
            "transformation": "1 if shipping_fee > 0 else 0",
            "missing_handling": "0",
            "type": "binary",
            "leakage_safe": True,
        },
    ]

    def __init__(self, orders, order_items, products, customers, returns):
        self.orders = orders.copy()
        self.order_items = order_items.copy()
        self.products = products.copy()
        self.customers = customers.copy()
        self.returns = returns.copy()

        # Parse dates
        if self.orders["order_date"].dtype == "object":
            self.orders["order_date"] = pd.to_datetime(self.orders["order_date"], errors="coerce")
        if self.returns["return_date"].dtype == "object":
            self.returns["return_date"] = pd.to_datetime(self.returns["return_date"], errors="coerce")

    def generate_features(self) -> dict:
        """Generate all features and return feature matrix with metadata."""
        # Start with order_items merged with products and orders
        df = self.order_items.merge(
            self.products[["product_id", "product_name", "category", "unit_cost", "margin_pct"]],
            on="product_id", how="left"
        )
        df = df.merge(
            self.orders[["order_id", "customer_id", "order_date", "order_status",
                         "payment_method", "shipping_fee", "total_amount"]],
            on="order_id", how="left"
        )
        df = df.merge(
            self.customers[["customer_id", "age", "gender", "region", "country", "membership_tier"]],
            on="customer_id", how="left"
        )

        # Mark returned items
        returned_ids = set(self.returns["order_item_id"])
        df["is_returned"] = df["order_item_id"].isin(returned_ids).astype(int)

        # Sort by date for time-aware features
        df = df.sort_values("order_date").reset_index(drop=True)

        # ── Generate features ──

        # Basic features
        df["discount_percentage"] = df["discount_pct"] * 100
        df["has_discount"] = (df["discount_pct"] > 0).astype(int)
        df["margin_percentage"] = df["margin_pct"] * 100
        df["has_shipping_fee"] = (df["shipping_fee"] > 0).astype(int)

        # Order complexity
        item_counts = df.groupby("order_id")["order_item_id"].transform("count")
        df["item_count_in_order"] = item_counts
        df["total_quantity_in_order"] = df.groupby("order_id")["quantity"].transform("sum")
        df["is_multi_item_order"] = (df["item_count_in_order"] > 1).astype(int)

        # Time features
        df["order_month"] = df["order_date"].dt.month
        df["order_day_of_week"] = df["order_date"].dt.dayofweek
        df["is_weekend_order"] = (df["order_day_of_week"] >= 5).astype(int)
        df["order_quarter"] = df["order_date"].dt.quarter

        # Price tier
        bins = [0, 500, 2000, 5000, float("inf")]
        labels = ["Low", "Medium", "High", "Premium"]
        df["price_tier"] = pd.cut(df["unit_price"], bins=bins, labels=labels)

        # Customer age
        df["customer_age"] = df["age"]

        # ── Time-aware historical features (prevent leakage) ──

        # Customer historical return rate (using expanding window, shifted)
        df_sorted = df.sort_values(["customer_id", "order_date"])
        df["customer_historical_return_rate"] = (
            df_sorted.groupby("customer_id")["is_returned"]
            .transform(lambda x: x.expanding().mean().shift(1))
            .fillna(0) * 100
        )

        # Customer order frequency (cumulative count)
        df["customer_order_frequency"] = (
            df_sorted.groupby("customer_id")["order_id"]
            .transform(lambda x: range(1, len(x) + 1))
        )

        # Product historical return rate
        df_sorted2 = df.sort_values(["product_id", "order_date"])
        overall_rate = df["is_returned"].mean()
        df["product_historical_return_rate"] = (
            df_sorted2.groupby("product_id")["is_returned"]
            .transform(lambda x: x.expanding().mean().shift(1))
            .fillna(overall_rate) * 100
        )

        # Category historical return rate
        df_sorted3 = df.sort_values(["category", "order_date"])
        df["category_return_rate"] = (
            df_sorted3.groupby("category")["is_returned"]
            .transform(lambda x: x.expanding().mean().shift(1))
            .fillna(overall_rate) * 100
        )

        # Feature metadata
        generated_features = []
        feature_columns = [
            "discount_percentage", "has_discount", "line_total", "total_amount",
            "margin_percentage", "has_shipping_fee", "item_count_in_order",
            "total_quantity_in_order", "is_multi_item_order", "order_month",
            "order_day_of_week", "is_weekend_order", "order_quarter",
            "customer_age", "customer_order_frequency",
            "customer_historical_return_rate", "product_historical_return_rate",
            "category_return_rate", "quantity",
        ]

        for col in feature_columns:
            if col in df.columns:
                stats = df[col].describe()
                generated_features.append({
                    "name": col,
                    "min": round(float(stats.get("min", 0)), 4),
                    "max": round(float(stats.get("max", 0)), 4),
                    "mean": round(float(stats.get("mean", 0)), 4),
                    "std": round(float(stats.get("std", 0)), 4),
                    "missing": int(df[col].isnull().sum()),
                    "sample_values": [round(float(v), 4) for v in df[col].dropna().head(5).tolist()],
                })

        return {
            "feature_matrix": df,
            "feature_stats": generated_features,
            "feature_catalog": self.FEATURE_CATALOG,
            "total_records": len(df),
            "total_features": len(feature_columns),
            "target_column": "is_returned",
            "target_distribution": {
                "returned": int(df["is_returned"].sum()),
                "not_returned": int((1 - df["is_returned"]).sum()),
                "return_rate": round(float(df["is_returned"].mean() * 100), 2),
            },
        }
