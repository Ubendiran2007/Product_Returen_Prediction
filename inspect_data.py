import pandas as pd
import os

base = r'e:\E-COMMERCE RETURN INSIGHT\ecommerce-sales-analysis-powerbi-main'
files = ['customers.csv', 'order_items.csv', 'orders.csv', 'products.csv', 'returns.csv']

for f in files:
    path = os.path.join(base, f)
    sep = "=" * 80
    print(f"\n{sep}")
    print(f"FILE: {f}")
    print(sep)
    df = pd.read_csv(path)
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nData types:")
    print(df.dtypes.to_string())
    print(f"\nMissing values:")
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)
    found_missing = False
    for col in df.columns:
        if missing[col] > 0:
            print(f"  {col}: {missing[col]} ({missing_pct[col]}%)")
            found_missing = True
    if not found_missing:
        print("  None")
    print(f"\nDuplicates: {df.duplicated().sum()}")
    print(f"\nFirst 3 rows:")
    print(df.head(3).to_string())
    
    # Unique values for categorical columns
    print(f"\nUnique values per column:")
    for col in df.columns:
        nunique = df[col].nunique()
        print(f"  {col}: {nunique}", end="")
        if nunique <= 20 and df[col].dtype == 'object':
            vals = df[col].dropna().unique().tolist()
            print(f"  -> {vals}")
        else:
            print()
    
    # Numeric stats
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    if numeric_cols:
        print(f"\nNumeric statistics:")
        print(df[numeric_cols].describe().to_string())
