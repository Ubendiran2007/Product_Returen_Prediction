import json
from pathlib import Path

notebook = {
    'cells': [
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '# ReturnWise — E-Commerce Return Intelligence Platform\n',
                '## Exploratory Data Analysis & Predictive Modeling\n',
                '\n',
                'This notebook performs end-to-end data auditing, exploratory data analysis (EDA), statistical validation, and predictive modeling for the ReturnWise platform.\n',
                '\n',
                '### Objectives:\n',
                '1. **Inspect Raw Datasets**: Schema validation, missing values, duplicate detection.\n',
                '2. **Exploratory Data Analysis**: Univariate and bivariate analysis of returns across categories, delivery delays, discounts, and payment methods.\n',
                '3. **Customer Behavior**: Segmentation and return frequency analysis.\n',
                '4. **Feature Engineering**: Deriving leakage-free predictive signals.\n',
                '5. **Model Evaluation**: Baseline comparison across Logistic Regression, Random Forest, and Gradient Boosting.\n'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': 1,
            'metadata': {},
            'outputs': [],
            'source': [
                'import sys\n',
                'from pathlib import Path\n',
                'import pandas as pd\n',
                'import numpy as np\n',
                'import matplotlib.pyplot as plt\n',
                'import seaborn as sns\n',
                '\n',
                '# Set plot styles\n',
                'sns.set_theme(style="whitegrid", palette="muted")\n',
                'plt.rcParams["figure.figsize"] = (12, 6)\n',
                'plt.rcParams["font.size"] = 11\n',
                '\n',
                '# Paths\n',
                'DATA_DIR = Path("../data/processed")\n',
                'if not DATA_DIR.exists():\n',
                '    DATA_DIR = Path("../data/raw")\n',
                'print(f"Using data directory: {DATA_DIR.resolve()}")\n'
            ]
        },
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '## 1. Load Cleaned Datasets\n'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': 2,
            'metadata': {},
            'outputs': [],
            'source': [
                'customers = pd.read_csv(DATA_DIR / "customers_cleaned.csv" if (DATA_DIR / "customers_cleaned.csv").exists() else DATA_DIR / "customers.csv")\n',
                'orders = pd.read_csv(DATA_DIR / "orders_cleaned.csv" if (DATA_DIR / "orders_cleaned.csv").exists() else DATA_DIR / "orders.csv")\n',
                'order_items = pd.read_csv(DATA_DIR / "order_items_cleaned.csv" if (DATA_DIR / "order_items_cleaned.csv").exists() else DATA_DIR / "order_items.csv")\n',
                'products = pd.read_csv(DATA_DIR / "products_cleaned.csv" if (DATA_DIR / "products_cleaned.csv").exists() else DATA_DIR / "products.csv")\n',
                'returns = pd.read_csv(DATA_DIR / "returns_cleaned.csv" if (DATA_DIR / "returns_cleaned.csv").exists() else DATA_DIR / "returns.csv")\n',
                '\n',
                'print("Dataset Shapes:")\n',
                'print(f"- Customers:   {customers.shape}")\n',
                'print(f"- Orders:      {orders.shape}")\n',
                'print(f"- Order Items: {order_items.shape}")\n',
                'print(f"- Products:    {products.shape}")\n',
                'print(f"- Returns:     {returns.shape}")\n'
            ]
        },
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '## 2. Return Rate Analysis by Category\n'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': 3,
            'metadata': {},
            'outputs': [],
            'source': [
                '# Merge item data with product info and return status\n',
                'items_prod = order_items.merge(products, on="product_id", how="left")\n',
                'return_ids = set(returns["order_id"].unique())\n',
                'items_prod["is_returned"] = items_prod["order_id"].isin(return_ids).astype(int)\n',
                '\n',
                'cat_summary = items_prod.groupby("category").agg(\n',
                '    total_items=("order_item_id", "count"),\n',
                '    returned_items=("is_returned", "sum"),\n',
                ').reset_index()\n',
                'cat_summary["return_rate_pct"] = (cat_summary["returned_items"] / cat_summary["total_items"]) * 100\n',
                'cat_summary = cat_summary.sort_values("return_rate_pct", ascending=False)\n',
                '\n',
                'plt.figure(figsize=(10, 5))\n',
                'sns.barplot(data=cat_summary, x="category", y="return_rate_pct", palette="Blues_r")\n',
                'plt.title("Return Rate (%) by Product Category", fontsize=14, fontweight="bold")\n',
                'plt.xlabel("Category")\n',
                'plt.ylabel("Return Rate (%)")\n',
                'plt.xticks(rotation=20)\n',
                'for i, row in cat_summary.reset_index().iterrows():\n',
                '    plt.text(i, row["return_rate_pct"] + 0.1, f"{row[\'return_rate_pct\']:.1f}%", ha="center")\n',
                'plt.tight_layout()\n',
                'plt.show()\n'
            ]
        },
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '## 3. Top Return Reasons\n'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': 4,
            'metadata': {},
            'outputs': [],
            'source': [
                'reason_counts = returns["return_reason"].value_counts().reset_index()\n',
                'reason_counts.columns = ["Reason", "Count"]\n',
                'reason_counts["Share (%)"] = (reason_counts["Count"] / reason_counts["Count"].sum()) * 100\n',
                '\n',
                'plt.figure(figsize=(10, 5))\n',
                'sns.barplot(data=reason_counts, x="Share (%)", y="Reason", palette="viridis")\n',
                'plt.title("Breakdown of Return Reasons (% of Total Returns)", fontsize=14, fontweight="bold")\n',
                'plt.xlabel("Percentage (%)")\n',
                'plt.ylabel("Return Reason")\n',
                'plt.tight_layout()\n',
                'plt.show()\n'
            ]
        },
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '## 4. Discount Impact on Return Propensity\n'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': 5,
            'metadata': {},
            'outputs': [],
            'source': [
                'items_prod["discount_tier"] = pd.cut(\n',
                '    items_prod["discount_pct"],\n',
                '    bins=[-0.01, 0.001, 0.05, 0.10, 0.15, 0.25],\n',
                '    labels=["0% (No Discount)", "1-5%", "6-10%", "11-15%", "16-20%"]\n',
                ')\n',
                'disc_stats = items_prod.groupby("discount_tier", observed=True).agg(\n',
                '    total=("order_item_id", "count"),\n',
                '    returned=("is_returned", "sum")\n',
                ').reset_index()\n',
                'disc_stats["return_rate"] = (disc_stats["returned"] / disc_stats["total"]) * 100\n',
                '\n',
                'plt.figure(figsize=(9, 4))\n',
                'sns.lineplot(data=disc_stats, x="discount_tier", y="return_rate", marker="o", color="#4F46E5", linewidth=2.5)\n',
                'plt.title("Return Rate across Discount Tiers", fontsize=14, fontweight="bold")\n',
                'plt.xlabel("Discount Tier")\n',
                'plt.ylabel("Return Rate (%)")\n',
                'plt.tight_layout()\n',
                'plt.show()\n'
            ]
        },
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '## 5. Machine Learning Modeling & Leakage Prevention\n'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': 6,
            'metadata': {},
            'outputs': [],
            'source': [
                'import sys\n',
                'sys.path.insert(0, str(Path("../backend").resolve()))\n',
                'from app.features.engineer import FeatureEngineer\n',
                'from app.models.predictor import ReturnPredictor\n',
                '\n',
                'fe = FeatureEngineer(orders, order_items, products, customers, returns)\n',
                'res = fe.generate_features()\n',
                'feature_matrix = res["feature_matrix"]\n',
                '\n',
                'predictor = ReturnPredictor()\n',
                'X_train, X_test, y_train, y_test = predictor.prepare_data(feature_matrix)\n',
                'model_res = predictor.train_models(X_train, X_test, y_train, y_test)\n',
                '\n',
                'print("Model Evaluation Summary:")\n',
                'for name, m in model_res["models"].items():\n',
                '    print(f"{name.upper()}: ROC-AUC = {m[\'roc_auc\']:.4f}, F1 = {m[\'f1\']:.4f}, Accuracy = {m[\'accuracy\']:.4f}")\n'
            ]
        }
    ],
    'metadata': {
        'kernelspec': {
            'display_name': 'Python 3',
            'language': 'python',
            'name': 'python3'
        },
        'language_info': {
            'name': 'python',
            'version': '3.11'
        }
    },
    'nbformat': 4,
    'nbformat_minor': 4
}

out_path = Path(r"e:\E-COMMERCE RETURN INSIGHT\returnwise\notebooks\return_analysis.ipynb")
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=2)

print("Successfully written return_analysis.ipynb")
