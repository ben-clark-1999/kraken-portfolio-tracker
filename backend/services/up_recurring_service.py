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

# Intervals must mostly fall in the same cadence bucket. Strict greater-than
# so 60% exactly fails (test_classify_fails_at_60_percent_consistency relies
# on this boundary). Real-world UP data has noise (one-off charges from a
# recurring merchant, missed/early cycles) — 80% was too strict to detect
# obvious weekly/monthly subs in production data.
INTERVAL_CONSISTENCY_THRESHOLD = 0.60
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
    if best_count / len(intervals_days) > INTERVAL_CONSISTENCY_THRESHOLD:
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


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402 — after constants

from backend.db.supabase_client import get_supabase
from backend.models.up import RecurringCharge


def _title_case(s: str) -> str:
    """Title-case but preserve all-caps acronyms up to 4 chars."""
    return " ".join(
        w if w.isupper() and len(w) <= 4 else w.title()
        for w in s.split()
    )


# Sub-yearly cadences detect on a recent window so paused-then-resumed subs
# (e.g., gym membership during a year of travel) still register as active.
# Yearly cadences need full history to find the ≥2 charges 12 months apart.
RECENT_LOOKBACK_DAYS = 200


def _intervals(timestamps: list[datetime]) -> list[int]:
    return [(timestamps[i + 1] - timestamps[i]).days for i in range(len(timestamps) - 1)]


def find_recurring(schema: str = "public") -> list[RecurringCharge]:
    """Detect recurring outflow subscriptions.

    See docs/superpowers/specs/2026-05-12-recurring-charges-design.md.
    """
    db = get_supabase()
    # Supabase PostgREST has a server-side max-rows=1000 cap that overrides
    # client .limit(); paginate via .range() to fetch the full outflow history.
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        page = (
            db.schema(schema).table("up_transactions")
            .select("description,amount_value,created_at")
            .lt("amount_value", 0)
            .order("created_at", desc=False)
            .range(offset, offset + page_size - 1)
            .execute().data
        )
        if not page:
            break
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    # Group by normalised description.
    groups: dict[str, list[tuple[datetime, float, str]]] = defaultdict(list)
    for r in rows:
        norm = normalise(r["description"])
        if not norm:
            continue
        ts = datetime.fromisoformat(r["created_at"])
        amt = abs(float(r["amount_value"]))
        groups[norm].append((ts, amt, r["description"]))

    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=RECENT_LOOKBACK_DAYS)
    out: list[RecurringCharge] = []

    for norm, full_entries in groups.items():
        if len(full_entries) < 2:
            continue
        full_entries.sort(key=lambda x: x[0])

        # Try the recent window first — handles paused subs that resumed.
        recent = [e for e in full_entries if e[0] >= recent_cutoff]
        cadence: Cadence | None = None
        entries: list[tuple[datetime, float, str]] = []
        if len(recent) >= 2:
            cad_recent = classify_cadence(_intervals([e[0] for e in recent]))
            if cad_recent is not None and cad_recent != "yearly":
                cadence = cad_recent
                entries = recent

        # Fall back to full history (catches yearly).
        if cadence is None:
            cad_full = classify_cadence(_intervals([e[0] for e in full_entries]))
            if cad_full == "yearly":
                cadence = cad_full
                entries = full_entries

        if cadence is None:
            continue
        timestamps = [e[0] for e in entries]
        amounts = [e[1] for e in entries]

        min_occ = MIN_OCCURRENCES_YEARLY if cadence == "yearly" else MIN_OCCURRENCES_SUB_YEARLY
        if len(entries) < min_occ:
            continue

        med = median(amounts)
        if med <= 0:
            continue
        if compute_cv(amounts) > MAX_CV:
            continue

        last_charged = timestamps[-1]
        if now - last_charged > timedelta(days=2 * CADENCE_DAYS[cadence]):
            continue

        next_expected = last_charged + timedelta(days=CADENCE_DAYS[cadence])
        out.append(RecurringCharge(
            name=_title_case(norm),
            sample_description=entries[-1][2],
            cadence=cadence,
            median_amount=round(med, 2),
            last_charged_at=last_charged,
            next_expected_at=next_expected,
            occurrence_count=len(entries),
            monthly_equivalent=round(monthly_equivalent(med, cadence), 2),
        ))

    out.sort(key=lambda r: r.monthly_equivalent, reverse=True)
    return out
