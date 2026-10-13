import pandas as pd
import os

base = r'e:\E-COMMERCE RETURN INSIGHT\ecommerce-sales-analysis-powerbi-main'

# Key categorical values
orders = pd.read_csv(os.path.join(base, 'orders.csv'))
products = pd.read_csv(os.path.join(base, 'products.csv'))
returns = pd.read_csv(os.path.join(base, 'returns.csv'))
customers = pd.read_csv(os.path.join(base, 'customers.csv'))
order_items = pd.read_csv(os.path.join(base, 'order_items.csv'))

print("=== ORDER STATUS VALUES ===")
print(orders['order_status'].value_counts().to_string())

print("\n=== PAYMENT METHODS ===")
print(orders['payment_method'].value_counts().to_string())

print("\n=== PRODUCT CATEGORIES ===")
print(products['category'].value_counts().to_string())

print("\n=== RETURN REASONS ===")
print(returns['return_reason'].value_counts().to_string())

print("\n=== CUSTOMER REGIONS ===")
print(customers['region'].value_counts().to_string())

print("\n=== CUSTOMER COUNTRIES ===")
print(customers['country'].value_counts().to_string())

print("\n=== MEMBERSHIP TIERS ===")
print(customers['membership_tier'].value_counts().to_string())

print("\n=== ACQUISITION CHANNELS ===")
print(customers['acquisition_channel'].value_counts().to_string())

print("\n=== GENDER ===")
print(customers['gender'].value_counts().to_string())

print("\n=== DISCOUNT PCT VALUES ===")
print(order_items['discount_pct'].value_counts().sort_index().to_string())

print("\n=== QUANTITY VALUES ===")
print(order_items['quantity'].value_counts().sort_index().to_string())

print("\n=== SHIPPING FEE VALUES ===")
print(orders['shipping_fee'].value_counts().sort_index().to_string())

# Join validation
print("\n=== JOIN VALIDATION ===")
# Check if all return order_ids exist in orders
return_orders = set(returns['order_id'].unique())
all_orders = set(orders['order_id'].unique())
unmatched = return_orders - all_orders
print(f"Return order_ids not in orders: {len(unmatched)}")

# Check if all return order_item_ids exist in order_items
return_ois = set(returns['order_item_id'].unique())
all_ois = set(order_items['order_item_id'].unique())
unmatched_oi = return_ois - all_ois
print(f"Return order_item_ids not in order_items: {len(unmatched_oi)}")

# Check if all return customer_ids exist in customers
return_custs = set(returns['customer_id'].unique())
all_custs = set(customers['customer_id'].unique())
unmatched_cust = return_custs - all_custs
print(f"Return customer_ids not in customers: {len(unmatched_cust)}")

# Check order_items -> orders join
oi_orders = set(order_items['order_id'].unique())
unmatched_oi_o = oi_orders - all_orders
print(f"Order_item order_ids not in orders: {len(unmatched_oi_o)}")

# Orders -> customers join
order_custs = set(orders['customer_id'].unique())
unmatched_o_c = order_custs - all_custs
print(f"Order customer_ids not in customers: {len(unmatched_o_c)}")

# Date range analysis
print("\n=== DATE RANGES ===")
orders['order_date'] = pd.to_datetime(orders['order_date'])
print(f"Order dates: {orders['order_date'].min()} to {orders['order_date'].max()}")
returns['return_date'] = pd.to_datetime(returns['return_date'])
print(f"Return dates: {returns['return_date'].min()} to {returns['return_date'].max()}")
customers['signup_date'] = pd.to_datetime(customers['signup_date'])
print(f"Signup dates: {customers['signup_date'].min()} to {customers['signup_date'].max()}")

# Check returns vs delivered orders
delivered_orders = orders[orders['order_status'] == 'Delivered']['order_id']
returned_order_ids = returns['order_id']
returns_from_delivered = returned_order_ids.isin(delivered_orders).sum()
print(f"\n=== RETURNS FROM DELIVERED ORDERS ===")
print(f"Returns from Delivered orders: {returns_from_delivered} / {len(returns)}")
returns_from_non_delivered = (~returned_order_ids.isin(delivered_orders)).sum()
print(f"Returns from non-Delivered orders: {returns_from_non_delivered}")

# Check which statuses returned orders have
return_order_statuses = orders[orders['order_id'].isin(return_orders)]['order_status'].value_counts()
print(f"\nOrder status of returned orders:")
print(return_order_statuses.to_string())

# Product names
print("\n=== ALL PRODUCTS ===")
print(products[['product_id', 'product_name', 'category', 'unit_price']].to_string())
