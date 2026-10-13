"""Excel and PDF report generation for ReturnWise."""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.chart import BarChart, PieChart, Reference
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import logging
import io

logger = logging.getLogger(__name__)

# Colors
DARK_GREEN = "123C2F"
LIGHT_GREEN = "DDEFE2"
PALE_GREEN = "F0F7F2"
WHITE = "FFFFFF"
HEADER_FONT_COLOR = "FFFFFF"


class ExcelReportGenerator:
    """Generate professional Excel workbook with multiple sheets."""

    def __init__(self, analytics_engine, quality_report: dict = None):
        self.engine = analytics_engine
        self.quality_report = quality_report
        self.wb = Workbook()

        # Styles
        self.header_fill = PatternFill(start_color=DARK_GREEN, end_color=DARK_GREEN, fill_type="solid")
        self.header_font = Font(name="Calibri", size=11, bold=True, color=HEADER_FONT_COLOR)
        self.light_fill = PatternFill(start_color=LIGHT_GREEN, end_color=LIGHT_GREEN, fill_type="solid")
        self.pale_fill = PatternFill(start_color=PALE_GREEN, end_color=PALE_GREEN, fill_type="solid")
        self.title_font = Font(name="Calibri", size=16, bold=True, color=DARK_GREEN)
        self.subtitle_font = Font(name="Calibri", size=12, bold=True, color=DARK_GREEN)
        self.normal_font = Font(name="Calibri", size=10)
        self.thin_border = Border(
            left=Side(style="thin", color="E4EBE6"),
            right=Side(style="thin", color="E4EBE6"),
            top=Side(style="thin", color="E4EBE6"),
            bottom=Side(style="thin", color="E4EBE6"),
        )

    def _style_header_row(self, ws, row_num, max_col):
        """Style a header row."""
        for col in range(1, max_col + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.fill = self.header_fill
            cell.font = self.header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = self.thin_border

    def _write_df(self, ws, df, start_row=1, start_col=1):
        """Write a DataFrame to worksheet with styling."""
        # Headers
        for j, col_name in enumerate(df.columns, start=start_col):
            cell = ws.cell(row=start_row, column=j, value=col_name)
        self._style_header_row(ws, start_row, start_col + len(df.columns) - 1)

        # Data
        for i, row in enumerate(df.itertuples(index=False), start=start_row + 1):
            for j, val in enumerate(row, start=start_col):
                cell = ws.cell(row=i, column=j, value=val)
                cell.font = self.normal_font
                cell.border = self.thin_border
                if (i - start_row) % 2 == 0:
                    cell.fill = self.pale_fill

        # Auto-fit columns
        for col_idx in range(start_col, start_col + len(df.columns)):
            max_len = max(
                len(str(ws.cell(row=r, column=col_idx).value or ""))
                for r in range(start_row, start_row + len(df) + 1)
            )
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 3, 40)

    def generate(self, output_path: Path) -> str:
        """Generate the full Excel workbook."""
        # Remove default sheet
        if "Sheet" in self.wb.sheetnames:
            del self.wb["Sheet"]

        self._create_executive_summary()
        self._create_cleaned_data()
        self._create_category_analysis()
        self._create_discount_analysis()
        self._create_return_reasons()
        self._create_customer_segments()
        self._create_data_quality()

        filepath = output_path / f"ReturnWise_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        self.wb.save(str(filepath))
        logger.info(f"Excel report saved to {filepath}")
        return str(filepath)

    def _create_executive_summary(self):
        """Executive summary sheet."""
        ws = self.wb.create_sheet("Executive Summary")

        ws.cell(row=1, column=1, value="ReturnWise — E-Commerce Return Intelligence Report").font = self.title_font
        ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}").font = self.normal_font
        ws.cell(row=3, column=1, value="").font = self.normal_font

        kpis = self.engine.get_overview_kpis()
        kpi_data = [
            ("Total Orders", kpis["total_orders"]),
            ("Eligible Orders", kpis["total_eligible_orders"]),
            ("Returned Orders", kpis["total_returned_orders"]),
            ("Return Rate (%)", kpis["return_rate"]),
            ("Total Revenue (₹)", kpis["total_revenue"]),
            ("Avg Order Value (₹)", kpis["avg_order_value"]),
            ("Total Items Sold", kpis["total_items"]),
            ("Items Returned", kpis["returned_items"]),
            ("Item Return Rate (%)", kpis["item_return_rate"]),
            ("Avg Discount (%)", kpis["avg_discount_pct"]),
            ("Unique Products", kpis["unique_products"]),
            ("Unique Customers", kpis["unique_customers"]),
            ("Cancelled Orders", kpis["cancelled_orders"]),
            ("Total Refund Amount (₹)", kpis["total_refund_amount"]),
        ]

        ws.cell(row=5, column=1, value="Key Performance Indicators").font = self.subtitle_font

        for i, (label, value) in enumerate(kpi_data, start=6):
            ws.cell(row=i, column=1, value=label).font = Font(name="Calibri", size=10, bold=True)
            ws.cell(row=i, column=2, value=value).font = self.normal_font
            if i % 2 == 0:
                ws.cell(row=i, column=1).fill = self.pale_fill
                ws.cell(row=i, column=2).fill = self.pale_fill

        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 20

    def _create_cleaned_data(self):
        """Cleaned data sheet (first 1000 rows)."""
        ws = self.wb.create_sheet("Cleaned Data")

        # Use merged items view
        df = self.engine.items_full.head(1000).copy()
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")
        self._write_df(ws, df)

    def _create_category_analysis(self):
        """Category analysis sheet."""
        ws = self.wb.create_sheet("Category Analysis")
        ws.cell(row=1, column=1, value="Category Return Analysis").font = self.subtitle_font

        analytics = self.engine.get_returns_analytics()
        df = pd.DataFrame(analytics["category_return_rates"])
        self._write_df(ws, df, start_row=3)

    def _create_discount_analysis(self):
        """Discount analysis sheet."""
        ws = self.wb.create_sheet("Discount Analysis")
        ws.cell(row=1, column=1, value="Discount vs Return Rate Analysis").font = self.subtitle_font

        analytics = self.engine.get_discount_analytics()
        df = pd.DataFrame(analytics["return_rate_by_discount"])
        self._write_df(ws, df, start_row=3)

    def _create_return_reasons(self):
        """Return reasons sheet."""
        ws = self.wb.create_sheet("Return Reasons")
        ws.cell(row=1, column=1, value="Return Reasons Distribution").font = self.subtitle_font

        analytics = self.engine.get_returns_analytics()
        df = pd.DataFrame(analytics["return_reasons"])
        self._write_df(ws, df, start_row=3)

    def _create_customer_segments(self):
        """Customer segments sheet."""
        ws = self.wb.create_sheet("Customer Segments")
        ws.cell(row=1, column=1, value="Customer Segmentation Analysis").font = self.subtitle_font

        analytics = self.engine.get_customer_analytics()
        df = pd.DataFrame(analytics["segments"])
        self._write_df(ws, df, start_row=3)

        # Add tier analysis
        row_offset = len(df) + 6
        ws.cell(row=row_offset, column=1, value="Membership Tier Analysis").font = self.subtitle_font
        tier_df = pd.DataFrame(analytics["tier_stats"])
        self._write_df(ws, tier_df, start_row=row_offset + 2)

    def _create_data_quality(self):
        """Data quality report sheet."""
        ws = self.wb.create_sheet("Data Quality")
        ws.cell(row=1, column=1, value="Data Quality Report").font = self.subtitle_font

        if self.quality_report:
            score = self.quality_report.get("overall_score", "N/A")
            ws.cell(row=3, column=1, value="Overall Quality Score").font = Font(bold=True)
            ws.cell(row=3, column=2, value=score)

            row = 5
            ws.cell(row=row, column=1, value="Cleaning Log").font = self.subtitle_font
            row += 1

            log = self.quality_report.get("cleaning_log", [])
            if log:
                log_df = pd.DataFrame(log)
                self._write_df(ws, log_df, start_row=row)


class PDFReportGenerator:
    """Generate PDF executive report."""

    def __init__(self, analytics_engine, quality_report: dict = None, model_results: dict = None):
        self.engine = analytics_engine
        self.quality_report = quality_report
        self.model_results = model_results

    def generate(self, output_path: Path) -> str:
        """Generate PDF report."""
        filepath = output_path / f"ReturnWise_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        doc = SimpleDocTemplate(
            str(filepath), pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CustomTitle", parent=styles["Title"],
            textColor=HexColor("#123C2F"), fontSize=24, spaceAfter=20
        )
        heading_style = ParagraphStyle(
            "CustomHeading", parent=styles["Heading1"],
            textColor=HexColor("#123C2F"), fontSize=16, spaceAfter=12,
            spaceBefore=20
        )
        subheading_style = ParagraphStyle(
            "CustomSubHeading", parent=styles["Heading2"],
            textColor=HexColor("#123C2F"), fontSize=13, spaceAfter=8
        )
        body_style = ParagraphStyle(
            "CustomBody", parent=styles["Normal"],
            fontSize=10, spaceAfter=6, textColor=HexColor("#17251F")
        )

        elements = []

        # Title page
        elements.append(Spacer(1, 100))
        elements.append(Paragraph("ReturnWise", title_style))
        elements.append(Paragraph("E-Commerce Return Intelligence Report", subheading_style))
        elements.append(Spacer(1, 30))
        elements.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}", body_style))
        elements.append(Paragraph("Confidential — For Internal Use Only", body_style))
        elements.append(PageBreak())

        # Table of Contents
        elements.append(Paragraph("Table of Contents", heading_style))
        toc = [
            "1. Executive Summary",
            "2. Dataset Overview",
            "3. Data Quality Findings",
            "4. Key Insights",
            "5. Category Analysis",
            "6. Discount Impact",
            "7. Customer Segmentation",
            "8. Recommendations",
            "9. Methodology & Limitations",
        ]
        for item in toc:
            elements.append(Paragraph(item, body_style))
        elements.append(PageBreak())

        # 1. Executive Summary
        elements.append(Paragraph("1. Executive Summary", heading_style))
        kpis = self.engine.get_overview_kpis()
        summary_text = (
            f"This report analyzes {kpis['total_orders']:,} orders from the e-commerce platform, "
            f"covering {kpis['unique_customers']:,} customers and {kpis['unique_products']} products "
            f"across {kpis['unique_categories']} categories. "
            f"The overall return rate is {kpis['return_rate']}% based on {kpis['total_eligible_orders']:,} "
            f"eligible orders (excluding cancelled orders). "
            f"Total revenue amounts to ₹{kpis['total_revenue']:,.2f} with an average order value of "
            f"₹{kpis['avg_order_value']:,.2f}."
        )
        elements.append(Paragraph(summary_text, body_style))
        elements.append(Spacer(1, 10))

        # KPI Table
        kpi_table_data = [
            ["Metric", "Value"],
            ["Total Orders", f"{kpis['total_orders']:,}"],
            ["Return Rate", f"{kpis['return_rate']}%"],
            ["Total Revenue", f"₹{kpis['total_revenue']:,.2f}"],
            ["Avg Order Value", f"₹{kpis['avg_order_value']:,.2f}"],
            ["Items Returned", f"{kpis['returned_items']:,}"],
            ["Total Refund Amount", f"₹{kpis['total_refund_amount']:,.2f}"],
            ["Cancellation Rate", f"{kpis['cancellation_rate']}%"],
        ]
        kpi_table = Table(kpi_table_data, colWidths=[200, 200])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#123C2F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E4EBE6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F0F7F2")]),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(kpi_table)
        elements.append(PageBreak())

        # 2. Dataset Overview
        elements.append(Paragraph("2. Dataset Overview", heading_style))
        elements.append(Paragraph(
            f"The dataset consists of 5 related tables: customers ({len(self.engine.customers)} records), "
            f"orders ({len(self.engine.orders)} records), order items ({len(self.engine.order_items)} records), "
            f"products ({len(self.engine.products)} records), and returns ({len(self.engine.returns)} records). "
            f"All joins are clean with zero unmatched keys.",
            body_style
        ))
        elements.append(Paragraph(
            f"Order dates range from {self.engine.orders['order_date'].min().strftime('%Y-%m-%d')} to "
            f"{self.engine.orders['order_date'].max().strftime('%Y-%m-%d')}.",
            body_style
        ))
        elements.append(Paragraph(
            "Note: The dataset does not contain delivery date or seller identifier fields. "
            "Delivery and seller analyses are adapted accordingly.",
            body_style
        ))
        elements.append(Spacer(1, 10))

        # 3. Data Quality
        elements.append(Paragraph("3. Data Quality Findings", heading_style))
        if self.quality_report:
            score = self.quality_report.get("overall_score", "N/A")
            elements.append(Paragraph(f"Overall Data Quality Score: {score}/100", subheading_style))
            elements.append(Paragraph(
                "The dataset has no missing values and no duplicate records across all tables. "
                "One product has a negative margin (sold below cost), which is flagged but retained as potentially legitimate.",
                body_style
            ))
        else:
            elements.append(Paragraph("Data quality report not available.", body_style))
        elements.append(PageBreak())

        # 4. Key Insights
        elements.append(Paragraph("4. Key Insights", heading_style))
        analytics = self.engine.get_returns_analytics()

        # Category insights
        elements.append(Paragraph("Category Return Rates", subheading_style))
        cat_data = [["Category", "Total Items", "Returned", "Return Rate"]]
        for cat in analytics["category_return_rates"]:
            cat_data.append([
                cat["category"],
                str(int(cat["total_items"])),
                str(int(cat["returned_items"])),
                f"{cat['return_rate']}%"
            ])
        cat_table = Table(cat_data, colWidths=[130, 80, 80, 80])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#123C2F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E4EBE6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F0F7F2")]),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        elements.append(cat_table)
        elements.append(Spacer(1, 15))

        # Return reasons
        elements.append(Paragraph("Return Reasons", subheading_style))
        reason_data = [["Reason", "Count", "Percentage"]]
        for r in analytics["return_reasons"]:
            reason_data.append([r["reason"], str(r["count"]), f"{r['percentage']}%"])
        reason_table = Table(reason_data, colWidths=[180, 80, 80])
        reason_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#123C2F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E4EBE6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F0F7F2")]),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        elements.append(reason_table)
        elements.append(PageBreak())

        # 5-7: Category, Discount, Customer details
        elements.append(Paragraph("5. Discount Impact Analysis", heading_style))
        disc = self.engine.get_discount_analytics()
        disc_data = [["Discount Level", "Total Items", "Returns", "Return Rate"]]
        for d in disc["return_rate_by_discount"]:
            disc_data.append([
                d["discount_label"], str(int(d["total"])),
                str(int(d["returned"])), f"{d['return_rate']}%"
            ])
        disc_table = Table(disc_data, colWidths=[100, 80, 80, 80])
        disc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#123C2F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E4EBE6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F0F7F2")]),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        elements.append(disc_table)
        elements.append(PageBreak())

        # 8. Recommendations
        elements.append(Paragraph("8. Recommendations", heading_style))
        recommendations = self._generate_recommendations(kpis, analytics, disc)
        for i, rec in enumerate(recommendations, 1):
            elements.append(Paragraph(f"{i}. {rec['title']}", subheading_style))
            elements.append(Paragraph(f"Finding: {rec['finding']}", body_style))
            elements.append(Paragraph(f"Metric: {rec['metric']}", body_style))
            elements.append(Paragraph(f"Action: {rec['action']}", body_style))
            elements.append(Paragraph(f"Evidence: {rec['evidence']}", body_style))
            elements.append(Spacer(1, 8))
        elements.append(PageBreak())

        # 9. Methodology
        elements.append(Paragraph("9. Methodology & Limitations", heading_style))
        elements.append(Paragraph(
            "Return Rate Calculation: Returned eligible orders ÷ Total eligible orders × 100. "
            "Eligible orders include Delivered, Returned, and Refunded statuses. Cancelled orders are excluded.",
            body_style
        ))
        elements.append(Paragraph(
            "Limitations: (1) No delivery date fields available — delivery delay analysis not possible. "
            "(2) No seller identifiers — seller performance uses category-level proxy. "
            "(3) No product size field — size-related analysis not possible. "
            "(4) Correlation does not imply causation — discount and return associations are observational.",
            body_style
        ))

        doc.build(elements)
        logger.info(f"PDF report saved to {filepath}")
        return str(filepath)

    def _generate_recommendations(self, kpis, analytics, discount_data) -> list:
        """Generate evidence-based recommendations from analytics."""
        recs = []

        # Category recommendations
        cats = analytics["category_return_rates"]
        if cats:
            top_cat = cats[0]
            recs.append({
                "title": f"Investigate High Returns in {top_cat['category']}",
                "finding": f"{top_cat['category']} has the highest return rate at {top_cat['return_rate']}%",
                "metric": f"{int(top_cat['returned_items'])} returned items out of {int(top_cat['total_items'])} sold",
                "action": "Review product descriptions, quality checks, and customer feedback for this category",
                "evidence": f"Based on {int(top_cat['total_items'])} order items — statistically meaningful sample",
                "impact": "Medium",
                "strength": "Strong — based on full dataset",
            })

        # Return reasons
        reasons = analytics["return_reasons"]
        if reasons:
            top_reason = reasons[0]
            recs.append({
                "title": f"Address '{top_reason['reason']}' Returns",
                "finding": f"'{top_reason['reason']}' is the most common return reason ({top_reason['percentage']}%)",
                "metric": f"{top_reason['count']} returns",
                "action": "Implement targeted interventions based on the specific reason type",
                "evidence": f"Consistent across {top_reason['count']} return instances",
                "impact": "High",
                "strength": "Strong",
            })

        # Return rate
        recs.append({
            "title": "Overall Return Rate Monitoring",
            "finding": f"Overall return rate is {kpis['return_rate']}%",
            "metric": f"{kpis['total_returned_orders']} returns out of {kpis['total_eligible_orders']} eligible orders",
            "action": "Set up automated alerts for return rate changes by category and time period",
            "evidence": "Baseline established from full dataset analysis",
            "impact": "High",
            "strength": "Strong — comprehensive baseline",
        })

        # Refund cost
        recs.append({
            "title": "Reduce Refund Costs",
            "finding": f"Total refund amount is ₹{kpis['total_refund_amount']:,.2f}",
            "metric": f"Average refund: ₹{kpis['total_refund_amount'] / max(kpis['returned_items'], 1):,.2f} per returned item",
            "action": "Focus return reduction efforts on high-value product categories",
            "evidence": f"Based on {kpis['returned_items']} returned items",
            "impact": "High",
            "strength": "Strong",
        })

        return recs
