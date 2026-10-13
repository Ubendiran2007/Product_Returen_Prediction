"""Data cleaning and preprocessing pipeline for ReturnWise."""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class DataCleaner:
    """Reusable data-cleaning pipeline for e-commerce return data."""

    def __init__(self, raw_path: Path, processed_path: Path):
        self.raw_path = raw_path
        self.processed_path = processed_path
        self.cleaning_log = []
        self.quality_before = {}
        self.quality_after = {}

    def _log_action(self, table: str, issue: str, affected: int, action: str, reason: str):
        """Record each cleaning operation."""
        entry = {
            "table": table,
            "issue": issue,
            "affected_records": affected,
            "action": action,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.cleaning_log.append(entry)
        logger.info(f"[{table}] {issue}: {affected} records — {action}")

    def load_raw_data(self) -> dict:
        """Load all raw CSV files."""
        data = {}
        files = {
            "customers": "customers.csv",
            "orders": "orders.csv",
            "order_items": "order_items.csv",
            "products": "products.csv",
            "returns": "returns.csv",
        }
        for key, filename in files.items():
            path = self.raw_path / filename
            if path.exists():
                data[key] = pd.read_csv(path)
                logger.info(f"Loaded {key}: {len(data[key])} rows")
            else:
                logger.warning(f"File not found: {path}")
        return data

    def compute_quality_metrics(self, data: dict, label: str) -> dict:
        """Compute data quality metrics for all tables."""
        metrics = {}
        for name, df in data.items():
            total_cells = df.shape[0] * df.shape[1]
            missing_cells = df.isnull().sum().sum()
            missing_by_col = {}
            for col in df.columns:
                mc = int(df[col].isnull().sum())
                if mc > 0:
                    missing_by_col[col] = {
                        "count": mc,
                        "percentage": round(mc / len(df) * 100, 2)
                    }
            metrics[name] = {
                "rows": len(df),
                "columns": len(df.columns),
                "total_cells": total_cells,
                "missing_cells": int(missing_cells),
                "missing_percentage": round(missing_cells / total_cells * 100, 2) if total_cells > 0 else 0,
                "missing_by_column": missing_by_col,
                "duplicates": int(df.duplicated().sum()),
                "column_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
            }
        return metrics

    def clean_customers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean customers data."""
        original_len = len(df)

        # Remove exact duplicates
        dupes = df.duplicated().sum()
        if dupes > 0:
            df = df.drop_duplicates()
            self._log_action("customers", "exact_duplicates", dupes, "removed", "Identical rows")

        # Remove duplicate customer_ids (keep first)
        id_dupes = df.duplicated(subset=["customer_id"]).sum()
        if id_dupes > 0:
            df = df.drop_duplicates(subset=["customer_id"], keep="first")
            self._log_action("customers", "duplicate_customer_id", id_dupes, "kept_first", "Duplicate primary key")

        # Validate and parse signup_date
        df["signup_date"] = pd.to_datetime(df["signup_date"], errors="coerce")
        invalid_dates = df["signup_date"].isnull().sum()
        if invalid_dates > 0:
            self._log_action("customers", "invalid_signup_date", int(invalid_dates), "set_to_null", "Unparseable dates")

        # Validate age range
        invalid_age = ((df["age"] < 13) | (df["age"] > 120)).sum()
        if invalid_age > 0:
            self._log_action("customers", "suspicious_age", int(invalid_age), "flagged", "Age outside 13-120 range")

        # Standardize text fields
        for col in ["city", "country", "region", "gender", "membership_tier", "acquisition_channel"]:
            if col in df.columns:
                df[col] = df[col].str.strip()

        self._log_action("customers", "cleaning_complete", original_len - len(df), "summary", f"From {original_len} to {len(df)} rows")
        return df

    def clean_orders(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean orders data."""
        original_len = len(df)

        # Remove exact duplicates
        dupes = df.duplicated().sum()
        if dupes > 0:
            df = df.drop_duplicates()
            self._log_action("orders", "exact_duplicates", dupes, "removed", "Identical rows")

        # Remove duplicate order_ids
        id_dupes = df.duplicated(subset=["order_id"]).sum()
        if id_dupes > 0:
            df = df.drop_duplicates(subset=["order_id"], keep="first")
            self._log_action("orders", "duplicate_order_id", id_dupes, "kept_first", "Duplicate primary key")

        # Parse order_date
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
        invalid_dates = df["order_date"].isnull().sum()
        if invalid_dates > 0:
            self._log_action("orders", "invalid_order_date", int(invalid_dates), "set_to_null", "Unparseable dates")

        # Validate numeric fields
        neg_shipping = (df["shipping_fee"] < 0).sum()
        if neg_shipping > 0:
            df.loc[df["shipping_fee"] < 0, "shipping_fee"] = 0
            self._log_action("orders", "negative_shipping_fee", int(neg_shipping), "set_to_zero", "Negative shipping not valid")

        neg_subtotal = (df["order_subtotal"] <= 0).sum()
        if neg_subtotal > 0:
            self._log_action("orders", "non_positive_subtotal", int(neg_subtotal), "flagged", "Subtotal should be positive")

        # Standardize order_status
        df["order_status"] = df["order_status"].str.strip()

        self._log_action("orders", "cleaning_complete", original_len - len(df), "summary", f"From {original_len} to {len(df)} rows")
        return df

    def clean_order_items(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean order items data."""
        original_len = len(df)

        dupes = df.duplicated().sum()
        if dupes > 0:
            df = df.drop_duplicates()
            self._log_action("order_items", "exact_duplicates", dupes, "removed", "Identical rows")

        id_dupes = df.duplicated(subset=["order_item_id"]).sum()
        if id_dupes > 0:
            df = df.drop_duplicates(subset=["order_item_id"], keep="first")
            self._log_action("order_items", "duplicate_order_item_id", id_dupes, "kept_first", "Duplicate primary key")

        # Validate quantity
        invalid_qty = (df["quantity"] <= 0).sum()
        if invalid_qty > 0:
            self._log_action("order_items", "non_positive_quantity", int(invalid_qty), "flagged", "Quantity must be positive")

        # Validate unit_price
        neg_price = (df["unit_price"] <= 0).sum()
        if neg_price > 0:
            self._log_action("order_items", "non_positive_unit_price", int(neg_price), "flagged", "Price must be positive")

        # Validate discount_pct range (0-1)
        bad_disc = ((df["discount_pct"] < 0) | (df["discount_pct"] > 1)).sum()
        if bad_disc > 0:
            self._log_action("order_items", "discount_out_of_range", int(bad_disc), "flagged", "Discount outside 0-100%")

        # Validate line_total calculation
        expected_total = df["quantity"] * df["unit_price"] * (1 - df["discount_pct"])
        diff = (df["line_total"] - expected_total).abs()
        mismatched = (diff > 0.02).sum()  # allow 2-cent rounding
        if mismatched > 0:
            self._log_action("order_items", "line_total_mismatch", int(mismatched), "flagged", "line_total != qty * price * (1 - discount)")

        self._log_action("order_items", "cleaning_complete", original_len - len(df), "summary", f"From {original_len} to {len(df)} rows")
        return df

    def clean_products(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean products data."""
        original_len = len(df)

        dupes = df.duplicated().sum()
        if dupes > 0:
            df = df.drop_duplicates()
            self._log_action("products", "exact_duplicates", dupes, "removed", "Identical rows")

        # Standardize category
        df["category"] = df["category"].str.strip()

        # Flag negative margins (but don't remove — could be legitimate loss-leaders)
        neg_margin = (df["margin_pct"] < 0).sum()
        if neg_margin > 0:
            self._log_action("products", "negative_margin", int(neg_margin), "flagged", "Product sold below cost — may be legitimate")

        # Validate cost < price (mostly)
        cost_gt_price = (df["unit_cost"] > df["unit_price"]).sum()
        if cost_gt_price > 0:
            self._log_action("products", "cost_exceeds_price", int(cost_gt_price), "flagged", "Unit cost > unit price for some products")

        self._log_action("products", "cleaning_complete", original_len - len(df), "summary", f"From {original_len} to {len(df)} rows")
        return df

    def clean_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean returns data."""
        original_len = len(df)

        dupes = df.duplicated().sum()
        if dupes > 0:
            df = df.drop_duplicates()
            self._log_action("returns", "exact_duplicates", dupes, "removed", "Identical rows")

        id_dupes = df.duplicated(subset=["return_id"]).sum()
        if id_dupes > 0:
            df = df.drop_duplicates(subset=["return_id"], keep="first")
            self._log_action("returns", "duplicate_return_id", id_dupes, "kept_first", "Duplicate primary key")

        # Parse return_date
        df["return_date"] = pd.to_datetime(df["return_date"], errors="coerce")
        invalid_dates = df["return_date"].isnull().sum()
        if invalid_dates > 0:
            self._log_action("returns", "invalid_return_date", int(invalid_dates), "set_to_null", "Unparseable dates")

        # Standardize return_reason
        df["return_reason"] = df["return_reason"].str.strip()

        # Validate refund_amount
        neg_refund = (df["refund_amount"] <= 0).sum()
        if neg_refund > 0:
            self._log_action("returns", "non_positive_refund", int(neg_refund), "flagged", "Refund should be positive")

        self._log_action("returns", "cleaning_complete", original_len - len(df), "summary", f"From {original_len} to {len(df)} rows")
        return df

    def run_full_pipeline(self) -> dict:
        """Execute the complete cleaning pipeline."""
        self.cleaning_log = []

        # Load raw data
        raw_data = self.load_raw_data()
        if not raw_data:
            return {"error": "No data files found"}

        # Compute quality before
        self.quality_before = self.compute_quality_metrics(raw_data, "before")

        # Clean each table
        cleaned = {}
        cleaned["customers"] = self.clean_customers(raw_data["customers"].copy())
        cleaned["orders"] = self.clean_orders(raw_data["orders"].copy())
        cleaned["order_items"] = self.clean_order_items(raw_data["order_items"].copy())
        cleaned["products"] = self.clean_products(raw_data["products"].copy())
        cleaned["returns"] = self.clean_returns(raw_data["returns"].copy())

        # Cross-table validation
        # Check for orphaned returns (return order_id not in orders)
        valid_order_ids = set(cleaned["orders"]["order_id"])
        orphaned_returns = (~cleaned["returns"]["order_id"].isin(valid_order_ids)).sum()
        if orphaned_returns > 0:
            self._log_action("returns", "orphaned_returns", int(orphaned_returns), "flagged", "Return references non-existent order")

        # Check for orphaned order_items
        orphaned_items = (~cleaned["order_items"]["order_id"].isin(valid_order_ids)).sum()
        if orphaned_items > 0:
            self._log_action("order_items", "orphaned_order_items", int(orphaned_items), "flagged", "Order item references non-existent order")

        # Compute quality after
        self.quality_after = self.compute_quality_metrics(cleaned, "after")

        # Save cleaned data
        for name, df in cleaned.items():
            save_df = df.copy()
            # Convert datetime columns to string for CSV
            for col in save_df.columns:
                if pd.api.types.is_datetime64_any_dtype(save_df[col]):
                    save_df[col] = save_df[col].dt.strftime("%Y-%m-%d")
            save_df.to_csv(self.processed_path / f"{name}_cleaned.csv", index=False)
            logger.info(f"Saved cleaned {name}: {len(save_df)} rows")

        # Build quality report
        quality_report = {
            "before": self.quality_before,
            "after": self.quality_after,
            "cleaning_log": self.cleaning_log,
            "overall_score": self._compute_quality_score(cleaned),
            "timestamp": datetime.utcnow().isoformat(),
        }

        return {
            "cleaned_data": cleaned,
            "quality_report": quality_report,
            "cleaning_log": self.cleaning_log,
        }

    def _compute_quality_score(self, data: dict) -> float:
        """
        Compute an overall data quality score (0-100) based on:
        - Completeness (no missing values): 40 points
        - Uniqueness (no duplicates): 20 points
        - Consistency (valid ranges, matching keys): 20 points
        - Validity (correct types, parseable dates): 20 points
        """
        score = 0.0
        total_cells = sum(df.shape[0] * df.shape[1] for df in data.values())
        missing_cells = sum(df.isnull().sum().sum() for df in data.values())
        total_rows = sum(len(df) for df in data.values())
        total_dupes = sum(df.duplicated().sum() for df in data.values())

        # Completeness (40 points)
        if total_cells > 0:
            completeness = 1 - (missing_cells / total_cells)
            score += completeness * 40

        # Uniqueness (20 points)
        if total_rows > 0:
            uniqueness = 1 - (total_dupes / total_rows)
            score += uniqueness * 20

        # Consistency (20 points) — based on cleaning log issues
        issue_count = len([l for l in self.cleaning_log if l["action"] == "flagged"])
        consistency = max(0, 1 - (issue_count / 20))  # up to 20 issues = 0 score
        score += consistency * 20

        # Validity (20 points) — based on type correctness
        validity_issues = len([l for l in self.cleaning_log if "invalid" in l["issue"]])
        validity = max(0, 1 - (validity_issues / 10))
        score += validity * 20

        return round(score, 1)
