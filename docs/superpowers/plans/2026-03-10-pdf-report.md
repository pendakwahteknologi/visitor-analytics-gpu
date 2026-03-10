# PDF Report Feature Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Download Report" button to the dashboard that generates a server-side PDF containing Today, This Week, This Month, and All-Time visitor statistics with daily breakdown tables.

**Architecture:** New `backend/pdf_report.py` module generates PDF using ReportLab. New `GET /stats/export/pdf` endpoint in `main.py` calls it. `DataStorage` gains a `get_daily_range()` method to fetch per-day rows for breakdown tables. Frontend adds a download button next to the existing Reset button.

**Tech Stack:** ReportLab (reportlab~=4.1), Python, FastAPI

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/pdf_report.py` | Create | PDF generation logic (ReportLab) |
| `backend/data_storage.py` | Modify (lines 286-290) | Add `get_daily_range()` public method |
| `backend/main.py` | Modify (lines 467-475) | Add `/stats/export/pdf` endpoint |
| `frontend/index.html` | Modify (lines 193-197) | Add download button next to reset |
| `static/js/app.js` | Modify (lines 23, 112-113) | Add click handler for download |
| `requirements.txt` | Modify | Add `reportlab~=4.1` |
| `tests/test_pdf_report.py` | Create | Unit tests for PDF generation |
| `tests/test_api.py` | Modify | Integration test for PDF endpoint |

---

## Task 1: Add `get_daily_range()` to DataStorage

**Files:**
- Modify: `backend/data_storage.py:286-290`
- Test: `tests/test_data_storage.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_data_storage.py`, add:

```python
def test_get_daily_range(tmp_path):
    """get_daily_range returns per-day dicts for a date range."""
    ds = DataStorage(data_dir=str(tmp_path))
    ds.save_current_stats(10, 5, 4, {"Children": 1, "Teens": 2, "Young Adults": 3, "Adults": 2, "Seniors": 1, "Unknown": 1}, unknown_count=1)
    today = ds._get_today_key()
    rows = ds.get_daily_range(today, today)
    assert len(rows) == 1
    assert rows[0]["date"] == today
    assert rows[0]["total_visitors"] == 10
    assert rows[0]["male"] == 5
    assert rows[0]["female"] == 4
    assert rows[0]["unknown"] == 1
    assert rows[0]["age_groups"]["Children"] == 1


def test_get_daily_range_empty(tmp_path):
    """get_daily_range returns empty list when no data in range."""
    ds = DataStorage(data_dir=str(tmp_path))
    rows = ds.get_daily_range("2020-01-01", "2020-01-07")
    assert rows == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_data_storage.py::test_get_daily_range tests/test_data_storage.py::test_get_daily_range_empty -v`
Expected: FAIL with `AttributeError: 'DataStorage' object has no attribute 'get_daily_range'`

- [ ] **Step 3: Implement `get_daily_range()`**

Add after `get_all_time_stats()` in `backend/data_storage.py` (around line 290):

```python
def get_daily_range(self, start_date: str, end_date: str) -> list[Dict]:
    """Return per-day stats as a list of dicts for the given date range."""
    with self._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_stats WHERE date BETWEEN ? AND ? ORDER BY date",
            (start_date, end_date),
        ).fetchall()
    return [{"date": r["date"], **self._row_to_dict(r)} for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_data_storage.py::test_get_daily_range tests/test_data_storage.py::test_get_daily_range_empty -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/data_storage.py tests/test_data_storage.py
git commit -m "feat: add get_daily_range() to DataStorage for PDF report"
```

---

## Task 2: Install ReportLab dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add reportlab to requirements.txt**

Add before the test dependencies section:

```
reportlab~=4.1
```

- [ ] **Step 2: Install the dependency**

Run: `pip install reportlab~=4.1`

- [ ] **Step 3: Verify installation**

Run: `python -c "from reportlab.lib.pagesizes import A4; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add reportlab for PDF report generation"
```

---

## Task 3: Create PDF generation module

**Files:**
- Create: `backend/pdf_report.py`
- Test: `tests/test_pdf_report.py`

- [ ] **Step 1: Write failing tests for PDF generation**

Create `tests/test_pdf_report.py`:

```python
"""Tests for PDF report generation."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pdf_report import generate_visitor_report


def _make_period_stats(total=100, male=40, female=50, unknown=10):
    return {
        "total_visitors": total,
        "male": male,
        "female": female,
        "unknown": unknown,
        "age_groups": {
            "Children": 5,
            "Teens": 15,
            "Young Adults": 30,
            "Adults": 35,
            "Seniors": 15,
            "Unknown": 0,
        },
    }


def _make_daily_rows(n=3):
    rows = []
    for i in range(n):
        rows.append({
            "date": f"2026-03-{10 - i:02d}",
            "total_visitors": 30 + i,
            "male": 15,
            "female": 12,
            "unknown": 3 + i,
            "age_groups": {
                "Children": 2,
                "Teens": 5,
                "Young Adults": 10,
                "Adults": 10,
                "Seniors": 3 + i,
                "Unknown": 0,
            },
        })
    return rows


def test_generate_pdf_returns_bytes():
    """generate_visitor_report returns non-empty bytes."""
    pdf = generate_visitor_report(
        today=_make_period_stats(),
        weekly=_make_period_stats(),
        monthly=_make_period_stats(),
        alltime=_make_period_stats(),
        weekly_daily=_make_daily_rows(7),
        monthly_daily=_make_daily_rows(10),
        generated_at="2026-03-10 15:30:00",
    )
    assert isinstance(pdf, bytes)
    assert len(pdf) > 500
    assert pdf[:5] == b"%PDF-"


def test_generate_pdf_with_empty_data():
    """PDF generation works with zero stats."""
    empty = _make_period_stats(0, 0, 0, 0)
    pdf = generate_visitor_report(
        today=empty,
        weekly=empty,
        monthly=empty,
        alltime=empty,
        weekly_daily=[],
        monthly_daily=[],
        generated_at="2026-03-10 15:30:00",
    )
    assert isinstance(pdf, bytes)
    assert pdf[:5] == b"%PDF-"


def test_generate_pdf_with_large_monthly():
    """PDF handles a full month of daily rows (31 days)."""
    pdf = generate_visitor_report(
        today=_make_period_stats(),
        weekly=_make_period_stats(),
        monthly=_make_period_stats(),
        alltime=_make_period_stats(),
        weekly_daily=_make_daily_rows(7),
        monthly_daily=_make_daily_rows(31),
        generated_at="2026-03-10 15:30:00",
    )
    assert isinstance(pdf, bytes)
    assert pdf[:5] == b"%PDF-"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pdf_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdf_report'`

- [ ] **Step 3: Implement `backend/pdf_report.py`**

Create `backend/pdf_report.py`:

```python
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
    PageBreak,
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
        ["Children (0–12)", str(ag.get("Children", 0))],
        ["Teens (13–17)", str(ag.get("Teens", 0))],
        ["Young Adults (18–30)", str(ag.get("Young Adults", 0))],
        ["Adults (31–50)", str(ag.get("Adults", 0))],
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
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#94a3b8"),
        alignment=1,  # center
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
        elements.append(Paragraph("Daily Breakdown — This Week", ParagraphStyle(
            "SubSection", parent=styles["Normal"], fontSize=10,
            textColor=colors.HexColor("#475569"), spaceBefore=4, spaceAfter=4,
        )))
        elements.append(_daily_table(weekly_daily))

    # Monthly
    elements.append(Paragraph("This Month", section_style))
    elements.append(_summary_table(monthly))
    if monthly_daily:
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph("Daily Breakdown — This Month", ParagraphStyle(
            "SubSection2", parent=styles["Normal"], fontSize=10,
            textColor=colors.HexColor("#475569"), spaceBefore=4, spaceAfter=4,
        )))
        elements.append(_daily_table(monthly_daily))

    # All-Time
    elements.append(Paragraph("All-Time Statistics", section_style))
    elements.append(_summary_table(alltime))

    # Footer
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph("Bahagian Transformasi Digital", footer_style))

    doc.build(elements)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pdf_report.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pdf_report.py tests/test_pdf_report.py
git commit -m "feat: add PDF report generation module"
```

---

## Task 4: Add `/stats/export/pdf` endpoint

**Files:**
- Modify: `backend/main.py:467-475`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing test for the PDF endpoint**

Add to `tests/test_api.py`:

```python
def test_pdf_export_requires_auth(client):
    """PDF export endpoint requires authentication."""
    response = client.get("/stats/export/pdf")
    assert response.status_code == 401


def test_pdf_export_returns_pdf(client):
    """PDF export returns a valid PDF file."""
    response = client.get(
        "/stats/export/pdf",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers.get("content-disposition", "")
    assert response.content[:5] == b"%PDF-"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py::test_pdf_export_requires_auth tests/test_api.py::test_pdf_export_returns_pdf -v`
Expected: FAIL with 404 (endpoint doesn't exist yet)

- [ ] **Step 3: Add the endpoint to `backend/main.py`**

Add after the CSV export endpoint (line 475), and add the import at the top:

Import (add near other backend imports around line 34):
```python
from pdf_report import generate_visitor_report
```

Endpoint (add after `export_stats`):
```python
@app.get("/stats/export/pdf", dependencies=[Depends(require_auth)])
async def export_pdf():
    """Export a comprehensive PDF report of all visitor statistics."""
    today = data_storage.get_today_stats()
    weekly = data_storage.get_weekly_stats()
    monthly = data_storage.get_monthly_stats()
    alltime = data_storage.get_all_time_stats()

    weekly_daily = data_storage.get_daily_range(
        weekly.get("start_date", ""), weekly.get("end_date", "")
    )
    monthly_daily = data_storage.get_daily_range(
        monthly.get("start_date", ""), monthly.get("end_date", "")
    )

    now = datetime.now()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    filename = f"Visitor_Report_{now.strftime('%Y-%m-%d')}.pdf"

    pdf_bytes = generate_visitor_report(
        today=today,
        weekly=weekly,
        monthly=monthly,
        alltime=alltime,
        weekly_daily=weekly_daily,
        monthly_daily=monthly_daily,
        generated_at=generated_at,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py::test_pdf_export_requires_auth tests/test_api.py::test_pdf_export_returns_pdf -v`
Expected: Both PASS

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat: add /stats/export/pdf endpoint"
```

---

## Task 5: Add download button to dashboard

**Files:**
- Modify: `frontend/index.html:193-197`
- Modify: `static/js/app.js:23,112-113`

- [ ] **Step 1: Add download button to HTML**

In `frontend/index.html`, find the reset button (line 193-197):

```html
                        <button id="btn-reset-stats" class="btn-icon-only" title="Reset Today's Statistics">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                        </button>
```

Replace with:

```html
                        <div style="display: flex; gap: 0.5rem;">
                            <button id="btn-download-report" class="btn-icon-only" title="Download PDF Report">
                                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                            </button>
                            <button id="btn-reset-stats" class="btn-icon-only" title="Reset Today's Statistics">
                                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                            </button>
                        </div>
```

- [ ] **Step 2: Add DOM reference and click handler in `static/js/app.js`**

Add DOM element reference after `this.btnResetStats` (around line 23):

```javascript
this.btnDownloadReport = document.getElementById('btn-download-report');
```

Add click handler in `bindEvents()` (after the reset button listener, around line 113):

```javascript
this.btnDownloadReport.addEventListener('click', () => this.downloadReport());
```

Add the method (after `resetStats()`, around line 415):

```javascript
downloadReport() {
    window.location.href = 'stats/export/pdf';
}
```

- [ ] **Step 3: Verify manually**

Run: `python -m pytest tests/ -v` to ensure all existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html static/js/app.js
git commit -m "feat: add Download Report button to dashboard"
```

---

## Task 6: Update documentation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update README.md**

Add `/stats/export/pdf` to the API Endpoints table:

```
| `/stats/export/pdf` | GET | Yes | Download comprehensive PDF report |
```

- [ ] **Step 2: Update CHANGELOG.md**

Add under the `[4.1.0]` entry or create a new version entry:

```
- **PDF Report Download** — new `/stats/export/pdf` endpoint generates a multi-section PDF with today, weekly, monthly, and all-time stats including daily breakdown tables
- Added "Download Report" button to dashboard next to Reset button
- Added `reportlab~=4.1` dependency
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (77 existing + 5 new = 82)

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: add PDF report feature to README and CHANGELOG"
```
