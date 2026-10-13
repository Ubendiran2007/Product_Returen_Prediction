"""Return Risk Lab — ML model training and evaluation."""
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    classification_report
)
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class ReturnPredictor:
    """Train and evaluate return prediction models."""

    NUMERIC_FEATURES = [
        "discount_percentage", "line_total", "total_amount", "quantity",
        "margin_percentage", "item_count_in_order", "total_quantity_in_order",
        "customer_age", "customer_order_frequency",
        "customer_historical_return_rate", "product_historical_return_rate",
        "category_return_rate", "order_month", "order_day_of_week",
    ]

    BINARY_FEATURES = [
        "has_discount", "has_shipping_fee", "is_multi_item_order", "is_weekend_order",
    ]

    CATEGORICAL_FEATURES = [
        "category", "payment_method", "membership_tier", "gender", "region",
    ]

    def __init__(self):
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.models = {}
        self.results = {}
        self.feature_names = []

    def prepare_data(self, feature_matrix: pd.DataFrame, test_size: float = 0.2):
        """Prepare data for model training with time-aware split."""
        df = feature_matrix.copy()

        # Use available features
        numeric_cols = [c for c in self.NUMERIC_FEATURES if c in df.columns]
        binary_cols = [c for c in self.BINARY_FEATURES if c in df.columns]
        cat_cols = [c for c in self.CATEGORICAL_FEATURES if c in df.columns]

        # Encode categorical features
        encoded_cat_cols = []
        for col in cat_cols:
            le = LabelEncoder()
            df[f"{col}_encoded"] = le.fit_transform(df[col].fillna("Unknown").astype(str))
            self.label_encoders[col] = le
            encoded_cat_cols.append(f"{col}_encoded")

        self.feature_names = numeric_cols + binary_cols + encoded_cat_cols
        X = df[self.feature_names].fillna(0)
        y = df["is_returned"]

        # Time-aware split: use last 20% by date as test
        df_sorted = df.sort_values("order_date")
        split_idx = int(len(df_sorted) * (1 - test_size))

        X_train = X.iloc[:split_idx]
        X_test = X.iloc[split_idx:]
        y_train = y.iloc[:split_idx]
        y_test = y.iloc[split_idx:]

        # Scale numeric features
        X_train_scaled = X_train.copy()
        X_test_scaled = X_test.copy()

        if numeric_cols:
            X_train_scaled[numeric_cols] = self.scaler.fit_transform(X_train[numeric_cols])
            X_test_scaled[numeric_cols] = self.scaler.transform(X_test[numeric_cols])

        return X_train_scaled, X_test_scaled, y_train, y_test

    def train_models(self, X_train, X_test, y_train, y_test) -> dict:
        """Train multiple models and evaluate them."""

        model_configs = {
            "logistic_regression": LogisticRegression(
                max_iter=1000, random_state=42, class_weight="balanced"
            ),
            "random_forest": RandomForestClassifier(
                n_estimators=100, max_depth=10, random_state=42,
                class_weight="balanced", n_jobs=-1
            ),
            "gradient_boosting": GradientBoostingClassifier(
                n_estimators=100, max_depth=5, random_state=42,
                learning_rate=0.1
            ),
        }

        results = {}

        for name, model in model_configs.items():
            logger.info(f"Training {name}...")
            try:
                model.fit(X_train, y_train)
                self.models[name] = model

                # Predictions
                y_pred = model.predict(X_test)
                y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None

                # Metrics
                metrics = {
                    "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
                    "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
                    "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
                    "f1_score": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
                }

                if y_prob is not None:
                    metrics["roc_auc"] = round(float(roc_auc_score(y_test, y_prob)), 4)
                    metrics["pr_auc"] = round(float(average_precision_score(y_test, y_prob)), 4)

                # Confusion matrix
                cm = confusion_matrix(y_test, y_pred)
                metrics["confusion_matrix"] = {
                    "true_negative": int(cm[0][0]),
                    "false_positive": int(cm[0][1]),
                    "false_negative": int(cm[1][0]),
                    "true_positive": int(cm[1][1]),
                }

                # Feature importance
                if hasattr(model, "feature_importances_"):
                    importances = model.feature_importances_
                elif hasattr(model, "coef_"):
                    importances = np.abs(model.coef_[0])
                else:
                    importances = np.zeros(len(self.feature_names))

                importance_list = sorted(
                    zip(self.feature_names, importances.tolist()),
                    key=lambda x: x[1], reverse=True
                )
                metrics["feature_importance"] = [
                    {"feature": f, "importance": round(float(i), 4)}
                    for f, i in importance_list
                ]

                results[name] = metrics
                logger.info(f"{name} — F1: {metrics['f1_score']}, ROC-AUC: {metrics.get('roc_auc', 'N/A')}")

            except Exception as e:
                logger.error(f"Error training {name}: {e}")
                results[name] = {"error": str(e)}

        self.results = results

        # Training metadata
        metadata = {
            "trained_at": datetime.utcnow().isoformat(),
            "train_size": len(X_train),
            "test_size": len(X_test),
            "features_used": self.feature_names,
            "num_features": len(self.feature_names),
            "target_distribution": {
                "train": {
                    "returned": int(y_train.sum()),
                    "not_returned": int(len(y_train) - y_train.sum()),
                    "return_rate": round(float(y_train.mean() * 100), 2),
                },
                "test": {
                    "returned": int(y_test.sum()),
                    "not_returned": int(len(y_test) - y_test.sum()),
                    "return_rate": round(float(y_test.mean() * 100), 2),
                },
            },
            "split_method": "time-aware (last 20% by order date)",
            "models": results,
        }

        return metadata

    def get_risk_scores(self, feature_matrix: pd.DataFrame, model_name: str = "random_forest") -> list:
        """Generate risk scores for items using a trained model."""
        model = self.models.get(model_name)
        if model is None:
            return []

        feature_cols = [c for c in self.feature_names if c in feature_matrix.columns]
        X = feature_matrix[feature_cols].fillna(0)

        # Scale numeric features
        numeric_cols = [c for c in self.NUMERIC_FEATURES if c in feature_cols]
        if numeric_cols:
            X_scaled = X.copy()
            X_scaled[numeric_cols] = self.scaler.transform(X[numeric_cols])
        else:
            X_scaled = X

        probs = model.predict_proba(X_scaled)[:, 1]

        return [
            {
                "order_item_id": str(row.get("order_item_id", "")),
                "product_name": str(row.get("product_name", "")),
                "category": str(row.get("category", "")),
                "risk_score": round(float(prob), 4),
                "risk_level": "High" if prob > 0.5 else ("Medium" if prob > 0.25 else "Low"),
            }
            for (_, row), prob in zip(feature_matrix.iterrows(), probs)
        ]
