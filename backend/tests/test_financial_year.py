from datetime import date

import pytest

from backend.utils.financial_year import financial_year_from


@pytest.mark.parametrize("input_date,expected", [
    # Standard mid-year dates
    (date(2025, 8, 15), "2025-26"),
    (date(2025, 12, 31), "2025-26"),
    (date(2026, 1, 1), "2025-26"),
    (date(2026, 5, 30), "2025-26"),
    # Boundary: July 1 (FY starts)
    (date(2025, 7, 1), "2025-26"),
    # Boundary: June 30 (FY ends)
    (date(2026, 6, 30), "2025-26"),
    # Next FY starts July 1
    (date(2026, 7, 1), "2026-27"),
    # Distant past
    (date(2000, 7, 1), "2000-01"),
    (date(2000, 6, 30), "1999-00"),
    # Leap year (Feb 29 in FY 2023-24)
    (date(2024, 2, 29), "2023-24"),
    # Year ending in 99 → 00 short suffix
    (date(1999, 7, 1), "1999-00"),
    (date(2099, 7, 1), "2099-00"),
])
def test_financial_year_from_returns_expected(input_date: date, expected: str) -> None:
    assert financial_year_from(input_date) == expected
