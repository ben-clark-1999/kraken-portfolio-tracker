"""Australian financial year helper.

The AU FY runs July 1 → June 30. A date in [Jul 1 YYYY, Jun 30 YYYY+1]
belongs to FY 'YYYY-YY' (e.g. '2025-26').
"""

from datetime import date


def financial_year_from(d: date) -> str:
    """Return the AU financial year string (e.g. '2025-26') for a given date."""
    if d.month >= 7:
        start = d.year
    else:
        start = d.year - 1
    end_short = (start + 1) % 100
    return f"{start}-{end_short:02d}"
