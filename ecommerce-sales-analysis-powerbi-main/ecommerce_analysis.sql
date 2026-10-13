/* ============================================================================
   E-COMMERCE & SALES ANALYSIS
   Customer Purchasing Behavior | Revenue Trends | Product Returns
   Dialect: Written in ANSI SQL, verified on SQLite. Notes below mark the
   1-2 line swap needed for MySQL / PostgreSQL / SQL Server where syntax differs.
   ============================================================================ */


/* ============================================================================
   1. SCHEMA
   ============================================================================ */

DROP TABLE IF EXISTS customers;
CREATE TABLE customers (
    customer_id         TEXT PRIMARY KEY,
    first_name          TEXT,
    last_name           TEXT,
    email                TEXT,
    city                 TEXT,
    country              TEXT,
    region               TEXT,
    signup_date          DATE,
    acquisition_channel  TEXT,
    age                  INTEGER,
    gender               TEXT,
    membership_tier      TEXT
);

DROP TABLE IF EXISTS products;
CREATE TABLE products (
    product_id    TEXT PRIMARY KEY,
    product_name  TEXT,
    category      TEXT,
    unit_cost     REAL,
    unit_price    REAL,
    margin_pct    REAL
);

DROP TABLE IF EXISTS orders;
CREATE TABLE orders (
    order_id        TEXT PRIMARY KEY,
    customer_id     TEXT REFERENCES customers(customer_id),
    order_date      DATE,
    payment_method  TEXT,
    order_status    TEXT,      -- Delivered | Returned | Cancelled | Refunded
    shipping_fee    REAL,
    order_subtotal  REAL,
    total_amount    REAL
);

DROP TABLE IF EXISTS order_items;
CREATE TABLE order_items (
    order_item_id  TEXT PRIMARY KEY,
    order_id       TEXT REFERENCES orders(order_id),
    product_id     TEXT REFERENCES products(product_id),
    quantity       INTEGER,
    unit_price     REAL,
    discount_pct   REAL,
    line_total     REAL
);

DROP TABLE IF EXISTS returns;
CREATE TABLE returns (
    return_id       TEXT PRIMARY KEY,
    order_id        TEXT REFERENCES orders(order_id),
    order_item_id   TEXT REFERENCES order_items(order_item_id),
    product_id      TEXT REFERENCES products(product_id),
    customer_id     TEXT REFERENCES customers(customer_id),
    return_date     DATE,
    return_reason   TEXT,
    refund_amount   REAL
);

/* Load customers.csv, products.csv, orders.csv, order_items.csv, returns.csv
   into these tables using your DB's bulk-load tool, e.g.:
   MySQL:      LOAD DATA INFILE ...
   Postgres:   \copy customers FROM 'customers.csv' CSV HEADER
   SQL Server: BULK INSERT ... 
   Or load via Power BI / Excel Power Query directly from the CSVs, skipping
   this step entirely, if you don't have a DB server running. */


/* ============================================================================
   2. REVENUE TRENDS
   ============================================================================ */

-- 2.1 Monthly revenue, orders, and average order value (successful orders only)
SELECT
    strftime('%Y-%m', order_date)              AS order_month,   -- MySQL: DATE_FORMAT(order_date,'%Y-%m') | Postgres: TO_CHAR(order_date,'YYYY-MM')
    COUNT(DISTINCT order_id)                    AS total_orders,
    ROUND(SUM(total_amount), 2)                 AS total_revenue,
    ROUND(SUM(total_amount) * 1.0 / COUNT(DISTINCT order_id), 2) AS avg_order_value
FROM orders
WHERE order_status IN ('Delivered','Returned')   -- revenue-generating orders (returned still billed until refund)
GROUP BY order_month
ORDER BY order_month;


-- 2.2 Month-over-month revenue growth %
WITH monthly AS (
    SELECT strftime('%Y-%m', order_date) AS order_month,
           SUM(total_amount) AS revenue
    FROM orders
    WHERE order_status IN ('Delivered','Returned')
    GROUP BY order_month
)
SELECT
    order_month,
    revenue,
    LAG(revenue) OVER (ORDER BY order_month) AS prev_month_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY order_month)) * 100.0
        / NULLIF(LAG(revenue) OVER (ORDER BY order_month), 0)
    , 2) AS mom_growth_pct
FROM monthly
ORDER BY order_month;


-- 2.3 Revenue by product category
SELECT
    p.category,
    COUNT(DISTINCT oi.order_id)         AS orders_count,
    SUM(oi.quantity)                    AS units_sold,
    ROUND(SUM(oi.line_total), 2)        AS category_revenue,
    ROUND(SUM(oi.line_total) * 100.0 / SUM(SUM(oi.line_total)) OVER (), 2) AS pct_of_total_revenue
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
JOIN orders  o  ON o.order_id   = oi.order_id
WHERE o.order_status IN ('Delivered','Returned')
GROUP BY p.category
ORDER BY category_revenue DESC;


-- 2.4 Top 10 products by revenue
SELECT
    p.product_name,
    p.category,
    SUM(oi.quantity)             AS units_sold,
    ROUND(SUM(oi.line_total), 2) AS product_revenue,
    ROUND(AVG(oi.discount_pct)*100, 1) AS avg_discount_pct
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
JOIN orders  o  ON o.order_id   = oi.order_id
WHERE o.order_status IN ('Delivered','Returned')
GROUP BY p.product_name, p.category
ORDER BY product_revenue DESC
LIMIT 10;


-- 2.5 Revenue by region and acquisition channel
SELECT
    c.region,
    c.acquisition_channel,
    COUNT(DISTINCT o.order_id)   AS orders_count,
    ROUND(SUM(o.total_amount),2) AS revenue
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status IN ('Delivered','Returned')
GROUP BY c.region, c.acquisition_channel
ORDER BY c.region, revenue DESC;


/* ============================================================================
   3. CUSTOMER PURCHASING BEHAVIOR
   ============================================================================ */

-- 3.1 RFM segmentation (Recency, Frequency, Monetary)
-- Anchor date = day after the last order in the dataset
WITH last_date AS (
    SELECT DATE(MAX(order_date), '+1 day') AS anchor_date FROM orders
),
customer_orders AS (
    SELECT
        o.customer_id,
        MAX(o.order_date)                     AS last_order_date,
        COUNT(DISTINCT o.order_id)             AS frequency,
        SUM(o.total_amount)                    AS monetary
    FROM orders o
    WHERE o.order_status IN ('Delivered','Returned')
    GROUP BY o.customer_id
),
rfm_base AS (
    SELECT
        co.customer_id,
        CAST(julianday((SELECT anchor_date FROM last_date)) - julianday(co.last_order_date) AS INTEGER) AS recency_days,
        co.frequency,
        co.monetary
    FROM customer_orders co
),
rfm_scored AS (
    SELECT
        customer_id, recency_days, frequency, monetary,
        NTILE(4) OVER (ORDER BY recency_days DESC) AS r_score,   -- higher = more recent
        NTILE(4) OVER (ORDER BY frequency ASC)     AS f_score,
        NTILE(4) OVER (ORDER BY monetary ASC)      AS m_score
    FROM rfm_base
)
SELECT
    customer_id, recency_days, frequency, ROUND(monetary,2) AS monetary,
    r_score, f_score, m_score,
    (r_score + f_score + m_score) AS rfm_total,
    CASE
        WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Champions'
        WHEN r_score >= 3 AND f_score <= 2                  THEN 'New / Promising'
        WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3 THEN 'At Risk (High Value)'
        WHEN r_score <= 2 AND f_score <= 2                  THEN 'Lost / Dormant'
        ELSE 'Regular'
    END AS customer_segment
FROM rfm_scored
ORDER BY rfm_total DESC;


-- 3.2 Repeat vs one-time purchase customers
WITH order_counts AS (
    SELECT customer_id, COUNT(DISTINCT order_id) AS n_orders
    FROM orders
    WHERE order_status IN ('Delivered','Returned')
    GROUP BY customer_id
)
SELECT
    CASE WHEN n_orders = 1 THEN 'One-Time' ELSE 'Repeat' END AS customer_type,
    COUNT(*) AS customer_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct_of_customers
FROM order_counts
GROUP BY customer_type;


-- 3.3 Customer Lifetime Value (CLV) by acquisition channel & membership tier
SELECT
    c.acquisition_channel,
    c.membership_tier,
    COUNT(DISTINCT c.customer_id)          AS customers,
    ROUND(SUM(o.total_amount),2)           AS total_revenue,
    ROUND(SUM(o.total_amount) / COUNT(DISTINCT c.customer_id), 2) AS avg_clv
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_status IN ('Delivered','Returned')
GROUP BY c.acquisition_channel, c.membership_tier
ORDER BY avg_clv DESC;


-- 3.4 Purchase frequency distribution (how many customers ordered N times)
WITH order_counts AS (
    SELECT customer_id, COUNT(DISTINCT order_id) AS n_orders
    FROM orders
    WHERE order_status IN ('Delivered','Returned')
    GROUP BY customer_id
)
SELECT n_orders AS times_purchased, COUNT(*) AS num_customers
FROM order_counts
GROUP BY n_orders
ORDER BY n_orders;


-- 3.5 Preferred payment method by region
SELECT
    c.region,
    o.payment_method,
    COUNT(*) AS order_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY c.region), 1) AS pct_within_region
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.region, o.payment_method
ORDER BY c.region, order_count DESC;


/* ============================================================================
   4. PRODUCT RETURNS ANALYSIS
   ============================================================================ */

-- 4.1 Overall return rate
SELECT
    COUNT(DISTINCT o.order_id)                                           AS total_orders,
    COUNT(DISTINCT r.order_id)                                           AS returned_orders,
    ROUND(COUNT(DISTINCT r.order_id) * 100.0 / COUNT(DISTINCT o.order_id), 2) AS return_rate_pct
FROM orders o
LEFT JOIN returns r ON r.order_id = o.order_id;


-- 4.2 Return rate by category
SELECT
    p.category,
    SUM(oi.quantity)                                   AS units_sold,
    COUNT(DISTINCT r.return_id)                        AS units_returned,
    ROUND(COUNT(DISTINCT r.return_id) * 100.0 / SUM(oi.quantity), 2) AS return_rate_pct,
    ROUND(SUM(r.refund_amount), 2)                     AS total_refund_value
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
LEFT JOIN returns r ON r.order_item_id = oi.order_item_id
GROUP BY p.category
ORDER BY return_rate_pct DESC;


-- 4.3 Top 10 most-returned products
SELECT
    p.product_name,
    p.category,
    COUNT(r.return_id)             AS times_returned,
    ROUND(SUM(r.refund_amount), 2) AS total_refunded
FROM returns r
JOIN products p ON p.product_id = r.product_id
GROUP BY p.product_name, p.category
ORDER BY times_returned DESC
LIMIT 10;


-- 4.4 Return reasons breakdown
SELECT
    return_reason,
    COUNT(*) AS return_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct_of_returns,
    ROUND(SUM(refund_amount), 2) AS total_refund_value
FROM returns
GROUP BY return_reason
ORDER BY return_count DESC;


-- 4.5 Monthly return trend vs revenue (are returns growing faster than sales?)
WITH monthly_revenue AS (
    SELECT strftime('%Y-%m', order_date) AS ym, SUM(total_amount) AS revenue
    FROM orders WHERE order_status IN ('Delivered','Returned')
    GROUP BY ym
),
monthly_returns AS (
    SELECT strftime('%Y-%m', return_date) AS ym, COUNT(*) AS returns_count,
           SUM(refund_amount) AS refund_value
    FROM returns
    GROUP BY ym
)
SELECT
    mr.ym AS month,
    mr2.revenue,
    mr.returns_count,
    ROUND(mr.refund_value, 2) AS refund_value,
    ROUND(mr.refund_value * 100.0 / NULLIF(mr2.revenue,0), 2) AS refund_pct_of_revenue
FROM monthly_returns mr
JOIN monthly_revenue mr2 ON mr2.ym = mr.ym
ORDER BY month;


-- 4.6 Customers with the highest return frequency (possible serial returners)
SELECT
    r.customer_id,
    c.first_name || ' ' || c.last_name AS customer_name,
    COUNT(*)                       AS total_returns,
    ROUND(SUM(r.refund_amount), 2) AS total_refunded
FROM returns r
JOIN customers c ON c.customer_id = r.customer_id
GROUP BY r.customer_id, customer_name
ORDER BY total_returns DESC
LIMIT 10;


/* ============================================================================
   5. EXECUTIVE SUMMARY QUERY (single-row KPI snapshot)
   ============================================================================ */
SELECT
    (SELECT COUNT(*) FROM orders) AS total_orders,
    (SELECT COUNT(*) FROM customers) AS total_customers,
    (SELECT ROUND(SUM(total_amount),2) FROM orders WHERE order_status IN ('Delivered','Returned')) AS gross_revenue,
    (SELECT ROUND(SUM(refund_amount),2) FROM returns) AS total_refunds,
    (SELECT ROUND(AVG(total_amount),2) FROM orders WHERE order_status IN ('Delivered','Returned')) AS avg_order_value,
    (SELECT ROUND(COUNT(DISTINCT order_id)*100.0/(SELECT COUNT(*) FROM orders),2) FROM returns) AS return_rate_pct;
