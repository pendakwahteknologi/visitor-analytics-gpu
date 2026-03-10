# PDF Report Feature — Design

## Overview

A "Download Report" button on the dashboard generates a server-side PDF via a new `/stats/export/pdf` endpoint. The PDF contains four sections (Today, This Week, This Month, All-Time), each with summary stats and a daily breakdown table.

## Backend

### New Endpoint

`GET /stats/export/pdf` (auth required)

- Fetches today's stats, weekly, monthly, and all-time from `DataStorage`
- Fetches daily rows for the week and month periods for breakdown tables
- Generates PDF using ReportLab and returns as `application/pdf`
- Filename: `Visitor_Report_YYYY-MM-DD.pdf`

### New Dependency

`reportlab~=4.1` added to `requirements.txt`

### PDF Layout (single file, ~2-3 pages)

1. **Header** — "Aneka Walk Visitor Report", generated date/time
2. **Today section** — summary table (total, male, female, unknown, age groups)
3. **This Week section** — summary + daily breakdown table (7 rows)
4. **This Month section** — summary + daily breakdown table (up to 31 rows)
5. **All-Time section** — summary table only
6. **Footer** — "Bahagian Transformasi Digital" on each page

## Frontend

### Dashboard Change

Add a download button next to the existing Reset button on the "Today's Visitors" card. Clicking it triggers `window.location.href = 'stats/export/pdf'` (relative URL, works behind Nginx).

## Files Changed

- `backend/main.py` — new `/stats/export/pdf` endpoint
- `backend/data_storage.py` — add helper to get daily rows for a date range if needed
- `frontend/index.html` — download button next to reset
- `static/js/app.js` — click handler for download
- `requirements.txt` — add `reportlab~=4.1`
- `tests/test_api.py` — new test for the PDF endpoint
