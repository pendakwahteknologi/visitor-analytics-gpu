"""Generate a visitor statistics PDF report using ReportLab."""

import io
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    KeepTogether,
    HRFlowable,
)
from reportlab.pdfgen import canvas

# -- Colour palette ----------------------------------------------------------
NAVY = colors.HexColor("#0f172a")
DARK_SLATE = colors.HexColor("#1e293b")
SLATE = colors.HexColor("#334155")
MID_GREY = colors.HexColor("#64748b")
LIGHT_GREY = colors.HexColor("#94a3b8")
ZEBRA_LIGHT = colors.HexColor("#f8fafc")
BORDER_LIGHT = colors.HexColor("#e2e8f0")
ACCENT_BLUE = colors.HexColor("#2563eb")
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN_L = 18 * mm
MARGIN_R = 18 * mm
MARGIN_T = 22 * mm
MARGIN_B = 22 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R


# -- Page template with header/footer ----------------------------------------

def _header_footer(canvas_obj: canvas.Canvas, doc):
    """Draw header line and footer on every page."""
    canvas_obj.saveState()

    # Header line
    canvas_obj.setStrokeColor(ACCENT_BLUE)
    canvas_obj.setLineWidth(2)
    canvas_obj.line(MARGIN_L, PAGE_H - MARGIN_T + 6 * mm,
                    PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 6 * mm)

    # Header text - left
    canvas_obj.setFont("Helvetica-Bold", 8)
    canvas_obj.setFillColor(DARK_SLATE)
    canvas_obj.drawString(MARGIN_L, PAGE_H - MARGIN_T + 8 * mm,
                          "ANEKA WALK  |  VISITOR ANALYTICS REPORT")

    # Header text - right (date)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(MID_GREY)
    date_text = getattr(doc, '_report_date', '')
    canvas_obj.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 8 * mm,
                               date_text)

    # Footer line
    canvas_obj.setStrokeColor(BORDER_LIGHT)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(MARGIN_L, MARGIN_B - 6 * mm,
                    PAGE_W - MARGIN_R, MARGIN_B - 6 * mm)

    # Footer left
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.setFillColor(LIGHT_GREY)
    canvas_obj.drawString(MARGIN_L, MARGIN_B - 10 * mm,
                          "Bahagian Transformasi Digital  |  Shah Alam")

    # Footer right - page number
    canvas_obj.drawRightString(PAGE_W - MARGIN_R, MARGIN_B - 10 * mm,
                               f"Page {canvas_obj.getPageNumber()}")

    canvas_obj.restoreState()


# -- Styles -------------------------------------------------------------------

def _get_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "RptTitle", parent=base["Title"],
            fontSize=22, leading=26,
            textColor=NAVY, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "RptSub", parent=base["Normal"],
            fontSize=10, textColor=MID_GREY, spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "RptSection", parent=base["Heading2"],
            fontSize=13, leading=16,
            textColor=NAVY,
            spaceBefore=10, spaceAfter=6,
            borderPadding=(0, 0, 2, 0),
        ),
        "subsection": ParagraphStyle(
            "RptSubsection", parent=base["Normal"],
            fontSize=9, textColor=MID_GREY,
            spaceBefore=6, spaceAfter=4,
        ),
        "kpi_value": ParagraphStyle(
            "KpiVal", parent=base["Normal"],
            fontSize=20, leading=24,
            textColor=NAVY, alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        ),
        "kpi_label": ParagraphStyle(
            "KpiLbl", parent=base["Normal"],
            fontSize=8, leading=10,
            textColor=MID_GREY, alignment=TA_CENTER,
        ),
    }


# -- KPI cards row (the big numbers at top) -----------------------------------

def _kpi_cards(today: Dict, weekly: Dict, monthly: Dict, alltime: Dict,
               styles: dict) -> Table:
    """Row of 4 KPI highlight cards."""
    cards_data = [
        ("Today", today),
        ("This Week", weekly),
        ("This Month", monthly),
        ("All Time", alltime),
    ]

    header_row = []
    value_row = []
    sub_row = []
    for label, stats in cards_data:
        header_row.append(Paragraph(label.upper(), styles["kpi_label"]))
        value_row.append(Paragraph(
            f"{stats.get('total_visitors', 0):,}", styles["kpi_value"]
        ))
        sub_row.append(Paragraph("unique persons", styles["kpi_label"]))

    card_w = CONTENT_W / 4
    table = Table([header_row, value_row, sub_row], colWidths=[card_w] * 4,
                  rowHeights=[14, 30, 12])
    table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, BORDER_LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, -1), ZEBRA_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
    ]))
    return table


# -- Compact summary table (gender + age side by side) ------------------------

def _summary_block(stats: Dict) -> Table:
    """Gender and age summary as two side-by-side mini-tables."""
    total = stats.get("total_visitors", 0)
    male = stats.get("male", 0)
    female = stats.get("female", 0)
    unknown = stats.get("unknown", 0)
    ag = stats.get("age_groups", {})

    def pct(v):
        return f"({v / total * 100:.0f}%)" if total > 0 else ""

    gender_data = [
        ["Gender", "Count", ""],
        ["Male", str(male), pct(male)],
        ["Female", str(female), pct(female)],
        ["Unknown", str(unknown), pct(unknown)],
    ]

    age_data = [
        ["Age Group", "Count", ""],
        ["Children (0\u201312)", str(ag.get("Children", 0)), pct(ag.get("Children", 0))],
        ["Teens (13\u201317)", str(ag.get("Teens", 0)), pct(ag.get("Teens", 0))],
        ["Young Adults (18\u201330)", str(ag.get("Young Adults", 0)), pct(ag.get("Young Adults", 0))],
        ["Adults (31\u201350)", str(ag.get("Adults", 0)), pct(ag.get("Adults", 0))],
        ["Seniors (51+)", str(ag.get("Seniors", 0)), pct(ag.get("Seniors", 0))],
    ]

    mini_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_SLATE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("TEXTCOLOR", (2, 1), (2, -1), LIGHT_GREY),
        ("FONTSIZE", (2, 1), (2, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ZEBRA_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ])

    half_w = CONTENT_W / 2 - 3 * mm
    gender_t = Table(gender_data, colWidths=[half_w * 0.50, half_w * 0.28, half_w * 0.22])
    gender_t.setStyle(mini_style)

    age_t = Table(age_data, colWidths=[half_w * 0.50, half_w * 0.28, half_w * 0.22])
    age_t.setStyle(mini_style)

    wrapper = Table([[gender_t, age_t]], colWidths=[half_w + 2 * mm, half_w + 2 * mm])
    wrapper.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return wrapper


# -- Daily breakdown table (compact) ------------------------------------------

def _daily_table(daily_rows: List[Dict]) -> Table:
    """Daily breakdown table with compact columns."""
    header = ["Date", "Persons", "Male", "Female", "Unk",
              "Child", "Teen", "Y.Adult", "Adult", "Senior"]
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

    date_w = 22 * mm
    num_w = (CONTENT_W - date_w) / 9
    col_widths = [date_w] + [num_w] * 9

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_SLATE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ZEBRA_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


# -- Section divider ----------------------------------------------------------

def _section_divider():
    return HRFlowable(
        width="100%", thickness=0.5,
        color=BORDER_LIGHT,
        spaceBefore=8, spaceAfter=4,
    )


# -- Build a section (title + summary + optional daily) -----------------------

def _build_section(title: str, stats: Dict, daily_rows: List[Dict],
                   styles: dict, show_total: bool = True) -> list:
    """Build a complete section with summary and optional daily table."""
    elements = []
    elements.append(_section_divider())

    total = stats.get("total_visitors", 0)
    if show_total:
        section_title = f"{title}  <font size='10' color='#{MID_GREY.hexval()[2:]}'>" \
                        f"&mdash;  {total:,} unique persons</font>"
    else:
        section_title = title

    elements.append(Paragraph(section_title, styles["section"]))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_summary_block(stats))

    if daily_rows:
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph("Daily Breakdown", styles["subsection"]))
        elements.append(_daily_table(daily_rows))

    return elements


# -- Main entry point ---------------------------------------------------------

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

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        title="Aneka Walk Visitor Report",
        author="Bahagian Transformasi Digital",
    )
    doc._report_date = generated_at

    frame = Frame(
        MARGIN_L, MARGIN_B,
        CONTENT_W, PAGE_H - MARGIN_T - MARGIN_B,
        id="main",
    )
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame], onPage=_header_footer),
    ])

    styles = _get_styles()
    elements = []

    # Title block
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph("Visitor Analytics Report", styles["title"]))
    elements.append(Paragraph(
        f"Aneka Walk, Shah Alam  &bull;  Generated {generated_at}",
        styles["subtitle"],
    ))
    elements.append(Spacer(1, 4 * mm))

    # KPI highlight cards
    elements.append(_kpi_cards(today, weekly, monthly, alltime, styles))
    elements.append(Spacer(1, 2 * mm))

    # Today section (keep together — it's small)
    today_section = _build_section("Today", today, [], styles)
    elements.append(KeepTogether(today_section))

    # Weekly section
    weekly_section = _build_section("This Week", weekly, weekly_daily, styles)
    elements.extend(weekly_section)

    # Monthly section
    monthly_section = _build_section("This Month", monthly, monthly_daily, styles)
    elements.extend(monthly_section)

    # All-time section (keep together — no daily breakdown)
    alltime_section = _build_section("All Time", alltime, [], styles)
    elements.append(KeepTogether(alltime_section))

    doc.build(elements)
    return buf.getvalue()
