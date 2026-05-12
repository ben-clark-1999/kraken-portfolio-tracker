"""Detect recurring outflow subscriptions from the UP transaction log.

Pure-Python heuristic. See docs/superpowers/specs/2026-05-12-recurring-charges-design.md
for the algorithm and thresholds.
"""

import re
from collections import defaultdict
from statistics import median, stdev
from typing import Literal

# Card-network prefixes that should be stripped before grouping.
_PREFIX_RE = re.compile(r"^(sq|py|tpg|paypal)\s*\*\s*", re.IGNORECASE)
# Whitespace-bounded 3-12 digit numeric token (store ID, terminal ID).
# Replaces a trailing-only regex because UP embeds store numbers mid-string
# (e.g. "COLES 0382 BONDI" → "coles bondi").
_INTERIOR_DIGITS_RE = re.compile(r"(?:^|\s)\d{3,12}(?=\s|$)")
# Pure-digit merchant string after other strips → empty.
_ALL_DIGITS_RE = re.compile(r"^\d+$")
# Collapse whitespace.
_WS_RE = re.compile(r"\s+")


def normalise(description: str) -> str:
    """Normalise a UP merchant string to group similar transactions.

    Lowercases, strips card-network prefixes, takes the part after any
    asterisk separator, removes whitespace-bounded 3-12 digit numeric
    tokens (store/terminal IDs), and collapses whitespace.
    """
    s = description.strip().lower()
    if not s:
        return ""
    s = _PREFIX_RE.sub("", s)
    if "*" in s:
        s = s.split("*", 1)[1].strip()
    s = _INTERIOR_DIGITS_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    if _ALL_DIGITS_RE.match(s):
        return ""
    return s


# ---------------------------------------------------------------------------
# Cadence / CV / monthly-equivalent helpers
# ---------------------------------------------------------------------------

Cadence = Literal["weekly", "fortnightly", "monthly", "yearly"]

# (name, target_days, tolerance) — first match wins
CADENCE_BUCKETS: list[tuple[Cadence, int, int]] = [
    ("weekly", 7, 1),
    ("fortnightly", 14, 2),
    ("monthly", 30, 2),
    ("yearly", 366, 6),
]

# Days in one cycle (for next-expected and active-filter math).
CADENCE_DAYS: dict[Cadence, int] = {
    "weekly": 7,
    "fortnightly": 14,
    "monthly": 30,
    "yearly": 365,
}

# Months per cycle (for monthly-equivalent computation).
CYCLES_PER_MONTH: dict[Cadence, float] = {
    "weekly": 4.345,         # 52.17 / 12
    "fortnightly": 2.1725,   # 52.17 / 24  (= half of weekly rate)
    "monthly": 1.0,
    "yearly": 1 / 12,
}

INTERVAL_CONSISTENCY_THRESHOLD = 0.80
MAX_CV = 0.15
MIN_OCCURRENCES_SUB_YEARLY = 3
MIN_OCCURRENCES_YEARLY = 2


def classify_cadence(intervals_days: list[int]) -> Cadence | None:
    """Return the dominant cadence bucket if ≥80% of intervals match it."""
    if not intervals_days:
        return None
    counts: dict[Cadence, int] = defaultdict(int)
    for interval in intervals_days:
        for name, target, tolerance in CADENCE_BUCKETS:
            if abs(interval - target) <= tolerance:
                counts[name] += 1
                break
    if not counts:
        return None
    best_name, best_count = max(counts.items(), key=lambda x: x[1])
    if best_count / len(intervals_days) >= INTERVAL_CONSISTENCY_THRESHOLD:
        return best_name
    return None


def compute_cv(amounts: list[float]) -> float:
    """Coefficient of variation = stddev / median.

    Returns 0.0 for single-element lists or zero medians (caller treats
    a zero median as a skip condition separately)."""
    if len(amounts) < 2:
        return 0.0
    med = median(amounts)
    if med == 0:
        return 0.0
    return stdev(amounts) / med


def monthly_equivalent(amount: float, cadence: Cadence) -> float:
    """Convert a per-cycle amount to its monthly-equivalent cost."""
    return amount * CYCLES_PER_MONTH[cadence]
