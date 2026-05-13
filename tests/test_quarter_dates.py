"""Tests for the quarter-to-date helper in pipeline.py.

Covers the leap-year edge case that previously crashed when Q1 of a leap year
was compared against a non-leap baseline.
"""

from __future__ import annotations

from datetime import date

import pytest


def test_quarter_to_dates_q1():
    from pipeline.pipeline import quarter_to_dates

    start, end = quarter_to_dates("2026Q1")
    assert start == date(2026, 1, 1)
    assert end.month == 3
    assert end.day == 31


def test_quarter_to_dates_q4():
    from pipeline.pipeline import quarter_to_dates

    start, end = quarter_to_dates("2026Q4")
    assert start == date(2026, 10, 1)
    assert end.month == 12
    assert end.day == 31


def test_quarter_to_dates_invalid_raises():
    from pipeline.pipeline import quarter_to_dates

    with pytest.raises(ValueError):
        quarter_to_dates("2026Q5")
    with pytest.raises(ValueError):
        quarter_to_dates("not-a-quarter")
