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
