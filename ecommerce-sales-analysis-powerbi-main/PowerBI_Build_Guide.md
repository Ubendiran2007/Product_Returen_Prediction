# Power BI Dashboard — Build Guide
### E-Commerce & Sales Analytics: Customer Behavior, Revenue Trends, Product Returns

This guide walks you through building the Power BI report from the five CSV files
(`customers.csv`, `products.csv`, `orders.csv`, `order_items.csv`, `returns.csv`).
Follow it top to bottom in Power BI Desktop — roughly 15–20 minutes.

---

## 1. Import the data

1. Power BI Desktop → **Get Data → Text/CSV**.
2. Import all five files: `customers.csv`, `products.csv`, `orders.csv`, `order_items.csv`, `returns.csv`.
3. In Power Query Editor, set correct data types before loading:
   - `orders[order_date]`, `returns[return_date]`, `customers[signup_date]` → **Date**
   - `orders[total_amount]`, `orders[order_subtotal]`, `orders[shipping_fee]` → **Decimal Number**
   - `order_items[unit_price]`, `order_items[line_total]`, `order_items[discount_pct]` → **Decimal Number**
   - `products[unit_cost]`, `products[unit_price]`, `products[margin_pct]` → **Decimal Number**
   - `returns[refund_amount]` → **Decimal Number**
   - Everything else (IDs, names, category, status) → **Text**
4. **Close & Apply.**

## 2. Create a Date table (for proper time-intelligence)

Model view → **New Table**:

```
DateTable = 
CALENDAR ( DATE(2024,1,1), DATE(2025,12,31) )
```

Add columns to it:

```
Year = YEAR(DateTable[Date])
MonthNum = MONTH(DateTable[Date])
MonthName = FORMAT(DateTable[Date], "MMM YYYY")
Quarter = "Q" & FORMAT(DateTable[Date], "Q") & " " & YEAR(DateTable[Date])
```

Mark it as a Date table: select `DateTable` → Table tools → **Mark as Date Table** → pick `Date`.

## 3. Build the data model (relationships)

Go to Model view and connect (drag between fields):

| From | To | Cardinality |
|---|---|---|
| `orders[customer_id]` | `customers[customer_id]` | Many → One |
| `order_items[order_id]` | `orders[order_id]` | Many → One |
| `order_items[product_id]` | `products[product_id]` | Many → One |
| `returns[order_id]` | `orders[order_id]` | Many → One |
| `returns[product_id]` | `products[product_id]` | Many → One |
| `returns[customer_id]` | `customers[customer_id]` | Many → One |
| `orders[order_date]` | `DateTable[Date]` | Many → One |

This gives a **star schema**: `orders` and `order_items` as fact tables, `customers` / `products` /
`DateTable` as dimensions, with `returns` as a secondary fact table.

> Tip: set the relationship from `orders[order_date]` to `DateTable[Date]` as the **active** one
> so all your revenue-trend visuals filter correctly by the calendar.

## 4. Core DAX measures

Create a new **Measures table** (Home → Enter Data → empty table named `_Measures`) and add these:

```DAX
Total Revenue = 
CALCULATE(
    SUM(orders[total_amount]),
    orders[order_status] IN {"Delivered","Returned"}
)

Total Orders = 
CALCULATE(
    DISTINCTCOUNT(orders[order_id]),
    orders[order_status] IN {"Delivered","Returned"}
)

Avg Order Value = DIVIDE([Total Revenue], [Total Orders])

Total Refunds = SUM(returns[refund_amount])

Return Count = COUNTROWS(returns)

Return Rate % = DIVIDE([Return Count], COUNTROWS(orders))

Refunds % of Revenue = DIVIDE([Total Refunds], [Total Revenue])

Total Customers = DISTINCTCOUNT(customers[customer_id])

Product Revenue = 
CALCULATE(
    SUM(order_items[line_total]),
    orders[order_status] IN {"Delivered","Returned"}
)

Units Sold = 
CALCULATE(
    SUM(order_items[quantity]),
    orders[order_status] IN {"Delivered","Returned"}
)

MoM Revenue Growth % = 
VAR CurrMonth = [Total Revenue]
VAR PrevMonth = CALCULATE([Total Revenue], DATEADD(DateTable[Date], -1, MONTH))
RETURN DIVIDE(CurrMonth - PrevMonth, PrevMonth)

Repeat Customers = 
CALCULATE(
    DISTINCTCOUNT(orders[customer_id]),
    FILTER(
        VALUES(orders[customer_id]),
        CALCULATE(DISTINCTCOUNT(orders[order_id])) > 1
    )
)

Repeat Customer % = DIVIDE([Repeat Customers], [Total Customers])

Customer Lifetime Value = DIVIDE([Total Revenue], [Total Customers])
```

### RFM helper measures (for a Customer Segments page)

```DAX
Customer Recency (Days) = 
VAR LastOrder = CALCULATE(MAX(orders[order_date]), ALLEXCEPT(customers, customers[customer_id]))
VAR AnchorDate = MAX(orders[order_date]) + 1
RETURN DATEDIFF(LastOrder, AnchorDate, DAY)

Customer Frequency = 
CALCULATE(DISTINCTCOUNT(orders[order_id]), orders[order_status] IN {"Delivered","Returned"})

Customer Monetary = 
CALCULATE(SUM(orders[total_amount]), orders[order_status] IN {"Delivered","Returned"})
```

Build the actual **Champions / At Risk / Lost / Regular** segment as a calculated column on
`customers` using `RANKX` + these measures, or keep the pre-computed segmentation from the
`Customer_Segments` tab in the Excel workbook and import it as a sixth table if you'd rather
not rebuild RFM logic in DAX.

## 5. Report pages to build

**Page 1 — Executive Overview**
- Card visuals: Total Revenue, Total Orders, Avg Order Value, Return Rate %, Total Customers
- Line chart: `Total Revenue` by `DateTable[MonthName]`
- Column chart: `Total Orders` by `DateTable[MonthName]`
- Slicers: `DateTable[Year]`, `customers[region]`

**Page 2 — Revenue & Product Performance**
- Donut chart: `Product Revenue` by `products[category]`
- Bar chart: Top 10 `products[product_name]` by `Product Revenue` (use a Top N filter)
- Table: category, units sold, revenue, avg discount %
- Matrix: revenue by `customers[region]` × `customers[acquisition_channel]`

**Page 3 — Customer Behavior**
- Scatter chart: Frequency vs Monetary, sized by Recency, colored by segment
- Bar chart: customer count by segment (Champions / Regular / At Risk / Lost / New)
- Bar chart: `Customer Lifetime Value` by `acquisition_channel` and `membership_tier`
- Table: repeat vs one-time customer split

**Page 4 — Returns Analysis**
- KPI cards: Return Rate %, Refunds % of Revenue, Total Refunds
- Bar chart: return count by `returns[return_reason]`
- Bar chart: return rate % by `products[category]`
- Table: Top 10 most-returned products with refund value
- Line chart: monthly refund value vs monthly revenue (dual-axis) — shows whether returns are
  outpacing sales growth

## 6. Formatting tips

- Use a consistent color theme (View → Themes) — pick one accent color for "good" (revenue,
  repeat customers) and one warning color (red/orange) for returns/refunds visuals.
- Add a report-level tooltip page for product drill-through: right-click a product → **Drill through**.
- Publish to Power BI Service and set a scheduled refresh if you connect this to a live source
  later (e.g., a database instead of static CSVs).

## 7. What to say about this project in interviews

- You modeled a **star schema** (fact: orders/order_items/returns; dimensions: customers/products/date).
- You built **RFM segmentation** to identify high-value vs at-risk customers — a real retention lever.
- You separated **gross revenue** (includes shipping) from **product revenue** (line items only) —
  a distinction interviewers like to probe on, and shows you understand what's actually being measured.
- You used **DAX time intelligence** (`DATEADD`) for MoM growth instead of hardcoding month offsets.
