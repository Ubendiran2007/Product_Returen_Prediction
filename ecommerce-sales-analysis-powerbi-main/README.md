# E-Commerce & Sales Analytics Project
### Customer Purchasing Behavior · Revenue Trends · Product Returns

A portfolio-ready project using **SQL + Excel + Power BI** on a realistic synthetic
e-commerce dataset (600 customers, 50 products, 8,000 orders, ~16,400 order line items,
883 returns, spanning Jan 2024–Dec 2025).

## What's included

| File | Purpose |
|---|---|
| `customers.csv`, `products.csv`, `orders.csv`, `order_items.csv`, `returns.csv` | Raw dataset (5-table relational structure) |
| `ecommerce_analysis.sql` | Schema (DDL) + 17 analysis queries: revenue trends, RFM customer segmentation, CLV, returns analysis |
| `ecommerce_dashboard.xlsx` | Excel workbook — raw data tables + a live, formula-driven dashboard (KPIs, charts, RFM segments, category performance, return analysis). Zero hardcoded numbers — every KPI recalculates if you edit the raw data. |
| `PowerBI_Build_Guide.md` | Step-by-step guide to build the same analysis as an interactive Power BI report: data model, relationships, and 15+ DAX measures |

## Data model

```
customers ──┬── orders ──┬── order_items ── products
            │            │
            └── returns ─┴──(order_id, product_id)
```

- **customers**: demographics, region, signup date, acquisition channel, membership tier
- **products**: 6 categories, 50 SKUs, cost/price/margin
- **orders**: order-level status (Delivered/Returned/Cancelled/Refunded), payment method, totals
- **order_items**: line-item detail (qty, discount, line total)
- **returns**: linked to the specific order item returned, with reason and refund amount

## How to use each tool

**SQL** — Load the 5 CSVs into any relational DB (MySQL/Postgres/SQL Server/SQLite) using the
schema in `ecommerce_analysis.sql`, then run the queries. They're organized into four sections:
revenue trends, customer behavior (RFM), product returns, and an executive KPI snapshot.

**Excel** — Open `ecommerce_dashboard.xlsx`. Start on the **Dashboard** tab for headline KPIs,
then explore `Revenue_Trend`, `Category_Performance`, `Customer_Segments`, and `Returns_Analysis`.
Raw data lives in the last five tabs. All summary tabs use live `SUMIFS`/`SUMPRODUCT`/`INDEX-MATCH`
formulas against the raw tables — change a value in `Orders` and the dashboard updates.

**Power BI** — Follow `PowerBI_Build_Guide.md` to import the CSVs, build the star-schema model,
add the DAX measures, and lay out four report pages (Overview, Revenue & Products, Customer
Behavior, Returns).

## Key findings baked into the data (worth highlighting on a resume/portfolio)

- Revenue is seasonal — Nov/Dec (festive season) and Jun/Jul (mid-year sale) run well above
  baseline months, useful for a "seasonality & demand planning" narrative.
- ~11% of orders result in a return; return rates vary meaningfully by category — good material
  for a "which categories drive avoidable refund cost" finding.
- Customer value is concentrated (Pareto-style) — a small share of customers drive a
  disproportionate share of repeat revenue, which is exactly what the RFM segmentation surfaces.

## Suggested next steps if you want to extend this

- Add a cohort retention analysis (% of each signup-month cohort still ordering N months later).
- Build a simple churn-risk score from the RFM "At Risk" segment.
- Swap the static CSVs for a live database connection in Power BI and set up scheduled refresh.


https://www.linkedin.com/in/mohammed-sahil-873605394/
mohammedsahil0116@gmail.com
