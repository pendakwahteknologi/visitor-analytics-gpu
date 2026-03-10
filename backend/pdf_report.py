"""Generate a visitor statistics PDF report using ReportLab."""

import io
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)


def _summary_table(stats: Dict) -> Table:
    """Build a summary table for a stats period."""
    ag = stats.get("age_groups", {})
    data = [
        ["Metric", "Count"],
        ["Total Visitors", str(stats.get("total_visitors", 0))],
        ["Male", str(stats.get("male", 0))],
        ["Female", str(stats.get("female", 0))],
        ["Unknown Gender", str(stats.get("unknown", 0))],
        ["Children (0\u201312)", str(ag.get("Children", 0))],
        ["Teens (13\u201317)", str(ag.get("Teens", 0))],
        ["Young Adults (18\u201330)", str(ag.get("Young Adults", 0))],
        ["Adults (31\u201350)", str(ag.get("Adults", 0))],
        ["Seniors (51+)", str(ag.get("Seniors", 0))],
    ]
    table = Table(data, colWidths=[120 * mm, 40 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _daily_table(daily_rows: List[Dict]) -> Table:
    """Build a daily breakdown table."""
    header = ["Date", "Total", "Male", "Female", "Unknown", "Children", "Teens", "Young Adults", "Adults", "Seniors"]
    data = [header]
    for row in daily_rows:
        ag = row.get("age_groups", {})
        data.append([
            row["date"],
            str(row.get("total_visitors", 0)),
            str(row.get("male", 0)),
            str(row.get("female", 0)),
            str(row.get("unknown", 0)),
            str(ag.get("Children", 0)),
            str(ag.get("Teens", 0)),
            str(ag.get("Young Adults", 0)),
            str(ag.get("Adults", 0)),
            str(ag.get("Seniors", 0)),
        ])

    col_widths = [22 * mm] + [16 * mm] * 9
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def generate_visitor_report(
    today: Dict,
    weekly: Dict,
    monthly: Dict,
    alltime: Dict,
    weekly_daily: List[Dict],
    monthly_daily: List[Dict],
    generated_at: str,
) -> bytes:
    """Generate a complete visitor report PDF and return as bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=16,
        spaceAfter=8,
    )
    subsection_style = ParagraphStyle(
        "SubSection",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#475569"),
        spaceBefore=4,
        spaceAfter=4,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#94a3b8"),
        alignment=1,
    )

    elements = []

    # Header
    elements.append(Paragraph("Aneka Walk Visitor Report", title_style))
    elements.append(Paragraph(f"Generated: {generated_at}", subtitle_style))
    elements.append(Spacer(1, 4 * mm))

    # Today
    elements.append(Paragraph("Today's Statistics", section_style))
    elements.append(_summary_table(today))

    # Weekly
    elements.append(Paragraph("This Week", section_style))
    elements.append(_summary_table(weekly))
    if weekly_daily:
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph("Daily Breakdown \u2014 This Week", subsection_style))
        elements.append(_daily_table(weekly_daily))

    # Monthly
    elements.append(Paragraph("This Month", section_style))
    elements.append(_summary_table(monthly))
    if monthly_daily:
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph("Daily Breakdown \u2014 This Month", subsection_style))
        elements.append(_daily_table(monthly_daily))

    # All-Time
    elements.append(Paragraph("All-Time Statistics", section_style))
    elements.append(_summary_table(alltime))

    # Footer
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph("Bahagian Transformasi Digital", footer_style))

    doc.build(elements)
    return buf.getvalue()
