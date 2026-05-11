# Recurring Charges (Subscriptions) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect recurring outflow subscriptions from the existing `up_transactions` table and surface them on the UP page + via a new MCP tool.

**Architecture:** Pure-Python heuristic in `backend/services/up_recurring_service.py`. No new DB tables, no caching, no schedule. Algorithm: normalise merchant string → group → cadence-classify intervals (weekly/fortnightly/monthly/yearly) → require ≥80% interval consistency + CV ≤ 0.15 on amounts → drop if last charge > 2 cycles old. One new REST endpoint, one new MCP tool, one new React component.

**Tech Stack:** Python 3.13 (statistics, re, datetime), pydantic, FastAPI, supabase-py, FastMCP, React 19 + TypeScript + Tailwind.

**Spec:** `docs/superpowers/specs/2026-05-12-recurring-charges-design.md`.

---

## Part 1 — Foundations

### Task 1: Add `RecurringCharge` Pydantic model

**Files:**
- Modify: `backend/models/up.py`
- Test: `backend/tests/test_up_recurring_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_recurring_model.py`:

```python
from datetime import datetime, timezone
from backend.models.up import RecurringCharge


def test_recurring_charge_construction():
    rc = RecurringCharge(
        name="Spotify",
        sample_description="SPOTIFY P0123ABC",
        cadence="monthly",
        median_amount=11.99,
        last_charged_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        next_expected_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
        occurrence_count=5,
        monthly_equivalent=11.99,
    )
    assert rc.cadence == "monthly"
    assert rc.median_amount == 11.99


def test_recurring_charge_rejects_unknown_cadence():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RecurringCharge(
            name="Bad", sample_description="x", cadence="quarterly",
            median_amount=1.0,
            last_charged_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            next_expected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            occurrence_count=2, monthly_equivalent=1.0,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_recurring_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'RecurringCharge'`.

- [ ] **Step 3: Add the model**

Append to `backend/models/up.py`:

```python
from typing import Literal


class RecurringCharge(BaseModel):
    """A recurring outflow subscription detected from the transaction log."""
    name: str
    sample_description: str
    cadence: Literal["weekly", "fortnightly", "monthly", "yearly"]
    median_amount: float  # positive — outflow magnitude
    last_charged_at: datetime
    next_expected_at: datetime
    occurrence_count: int
    monthly_equivalent: float  # cadence-normalised cost for sorting + aggregation
```

(`BaseModel` and `datetime` are already imported at the top of the file from earlier tasks. `Literal` is the only new import.)

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_recurring_model.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/models/up.py backend/tests/test_up_recurring_model.py
git commit -m "feat(models): RecurringCharge pydantic model"
git push
```

---

### Task 2: Implement merchant-string normaliser

**Files:**
- Create: `backend/services/up_recurring_service.py`
- Test: `backend/tests/test_up_recurring_normaliser.py`

The normaliser is the single biggest precision lever. Test it first against a fixture of real-shaped UP merchant strings.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_recurring_normaliser.py`:

```python
import pytest
from backend.services.up_recurring_service import normalise


# Real-shaped UP merchant strings (anonymised) and what they should
# normalise to so they group together.
@pytest.mark.parametrize("raw,expected", [
    # Plain merchant — no change
    ("Spotify", "spotify"),
    ("Netflix", "netflix"),
    # Trailing store/terminal numbers
    ("COLES 0382 BONDI", "coles bondi"),
    ("WOOLWORTHS 1234567", "woolworths"),
    ("ANYTIME FITNESS 567890", "anytime fitness"),
    # Card-network prefixes
    ("SQ *PINOS BARBER SHOP", "pinos barber shop"),
    ("PY *SUSHI HUB", "sushi hub"),
    ("PAYPAL *ADOBE INC", "adobe inc"),
    ("TPG *SPOTIFY", "spotify"),
    # Generic asterisk pattern
    ("ABC *COMPANY NAME", "company name"),
    # Whitespace + case
    ("  spotify  ", "spotify"),
    ("Spotify   AU", "spotify au"),
    # Edge: empty after strip
    ("", ""),
    # Edge: only digits
    ("12345678", ""),
    # Real Apple-shaped
    ("APPLE.COM/BILL ITUNES.COM", "apple.com/bill itunes.com"),
])
def test_normalise(raw: str, expected: str):
    assert normalise(raw) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_recurring_normaliser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.up_recurring_service'`.

- [ ] **Step 3: Implement the normaliser**

Create `backend/services/up_recurring_service.py`:

```python
"""Detect recurring outflow subscriptions from the UP transaction log.

Pure-Python heuristic. See docs/superpowers/specs/2026-05-12-recurring-charges-design.md
for the algorithm and thresholds.
"""

import re

# Card-network prefixes that should be stripped before grouping.
_PREFIX_RE = re.compile(r"^(sq|py|tpg|paypal)\s*\*\s*", re.IGNORECASE)
# Trailing 6-12 digit numeric suffix (store ID, terminal ID).
_TRAILING_DIGITS_RE = re.compile(r"\s+\d{6,12}\s*$")
# Pure-digit merchant string after other strips → empty.
_ALL_DIGITS_RE = re.compile(r"^\d+$")
# Collapse whitespace.
_WS_RE = re.compile(r"\s+")


def normalise(description: str) -> str:
    """Normalise a UP merchant string to group similar transactions.

    Lowercases, strips card-network prefixes, takes the part after any
    asterisk separator, removes trailing 6-12 digit numeric suffixes,
    and collapses whitespace.
    """
    s = description.strip().lower()
    s = _PREFIX_RE.sub("", s)
    if "*" in s:
        s = s.split("*", 1)[1].strip()
    s = _TRAILING_DIGITS_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    if _ALL_DIGITS_RE.match(s):
        return ""
    return s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_recurring_normaliser.py -v`
Expected: PASS (15 parametrized cases).

If any case fails, adjust the regex incrementally. Don't broaden the patterns blindly — every change to the normaliser is a precision/recall tradeoff.

- [ ] **Step 5: Commit**

```bash
git add backend/services/up_recurring_service.py backend/tests/test_up_recurring_normaliser.py
git commit -m "feat(up): merchant-string normaliser for recurring detection"
git push
```

---

## Part 2 — Algorithm

### Task 3: Cadence + CV + active-filter helpers

**Files:**
- Modify: `backend/services/up_recurring_service.py`
- Test: `backend/tests/test_up_recurring_helpers.py`

These are pure functions — easy to unit-test with no DB.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_recurring_helpers.py`:

```python
from backend.services.up_recurring_service import (
    classify_cadence, compute_cv, monthly_equivalent, CADENCE_DAYS,
)


# classify_cadence ---------------------------------------------------------

def test_classify_monthly():
    # 5 monthly intervals all ~30 days
    assert classify_cadence([29, 30, 31, 30, 30]) == "monthly"


def test_classify_weekly():
    assert classify_cadence([7, 7, 8, 7, 7]) == "weekly"


def test_classify_fortnightly():
    assert classify_cadence([14, 13, 15, 14]) == "fortnightly"


def test_classify_yearly_single_interval():
    # 2 yearly transactions = 1 interval; ≥80% trivially holds
    assert classify_cadence([365]) == "yearly"


def test_classify_returns_none_when_intervals_dont_cluster():
    # Mix of 7, 30, 60 — no dominant bucket
    assert classify_cadence([7, 30, 60, 5, 90]) is None


def test_classify_tolerates_one_outlier_in_five():
    # 4/5 monthly, 1 outlier — 80% threshold passes
    assert classify_cadence([30, 30, 30, 30, 7]) == "monthly"


def test_classify_fails_at_60_percent_consistency():
    # 3/5 monthly = 60% — below the 80% threshold
    assert classify_cadence([30, 30, 30, 7, 7]) is None


def test_classify_returns_none_for_empty():
    assert classify_cadence([]) is None


# compute_cv --------------------------------------------------------------

def test_cv_zero_for_identical_amounts():
    assert compute_cv([10.0, 10.0, 10.0]) == 0.0


def test_cv_positive_for_varying_amounts():
    cv = compute_cv([10.0, 12.0, 14.0])
    assert 0.1 < cv < 0.3


def test_cv_zero_for_single_value():
    # No variation possible
    assert compute_cv([5.0]) == 0.0


def test_cv_zero_when_median_is_zero():
    # Avoid division by zero — caller treats as "skip"
    assert compute_cv([0.0, 0.0]) == 0.0


# monthly_equivalent ------------------------------------------------------

def test_monthly_eq_monthly_passthrough():
    assert monthly_equivalent(11.99, "monthly") == 11.99


def test_monthly_eq_yearly_divides_by_twelve():
    assert round(monthly_equivalent(99.0, "yearly"), 2) == 8.25


def test_monthly_eq_weekly():
    # 4.345 weeks per month average
    assert round(monthly_equivalent(10.0, "weekly"), 2) == 43.45


def test_monthly_eq_fortnightly():
    # ~2.173 fortnights per month
    assert round(monthly_equivalent(20.0, "fortnightly"), 2) == 43.45


# CADENCE_DAYS ------------------------------------------------------------

def test_cadence_days_complete():
    assert set(CADENCE_DAYS.keys()) == {"weekly", "fortnightly", "monthly", "yearly"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_recurring_helpers.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the helpers**

Append to `backend/services/up_recurring_service.py`:

```python
from collections import defaultdict
from statistics import median, stdev
from typing import Literal

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
    "fortnightly": 2.173,    # 26.09 / 12
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_recurring_helpers.py -v`
Expected: PASS (15 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/up_recurring_service.py backend/tests/test_up_recurring_helpers.py
git commit -m "feat(up): cadence/CV/monthly-equivalent helpers for recurring detection"
git push
```

---

### Task 4: `find_recurring` orchestrator

**Files:**
- Modify: `backend/services/up_recurring_service.py`
- Test: `backend/tests/test_up_recurring_service.py`

The orchestrator stitches the helpers together against a real DB (the test schema). Uses synthetic fixtures.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_recurring_service.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount, UpTransaction
from backend.repositories import up_accounts_repo, up_transactions_repo
from backend.services.up_recurring_service import find_recurring

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _seed():
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    up_accounts_repo.upsert_many([UpAccount(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)
    yield


def _tx(id: str, amount: float, days_ago: int, description: str = "Spotify"):
    """Build a transaction `days_ago` days before now, with a fixed amount."""
    base = datetime.now(timezone.utc).replace(microsecond=0)
    when = base - timedelta(days=days_ago)
    return UpTransaction(
        id=id,
        account_id="acct-1",
        status="SETTLED",
        description=description,
        amount_value=-abs(amount),  # outflow
        category_id=None,
        parent_category_id=None,
        created_at=when,
        settled_at=when,
    )


def test_detects_5_monthly_netflix():
    txs = [_tx(f"n{i}", 16.99, 30 * i, "Netflix") for i in range(5)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)

    results = find_recurring(schema=SCHEMA)

    assert len(results) == 1
    r = results[0]
    assert r.name.lower().startswith("netflix")
    assert r.cadence == "monthly"
    assert r.median_amount == 16.99
    assert r.occurrence_count == 5
    assert r.monthly_equivalent == 16.99


def test_detects_weekly_audible():
    txs = [_tx(f"a{i}", 4.99, 7 * i, "Audible") for i in range(4)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)

    results = find_recurring(schema=SCHEMA)
    assert len(results) == 1
    assert results[0].cadence == "weekly"


def test_detects_yearly_with_two_charges():
    txs = [_tx("y0", 99.0, 0, "Apple iCloud"),
           _tx("y1", 99.0, 365, "Apple iCloud")]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)

    results = find_recurring(schema=SCHEMA)
    assert len(results) == 1
    r = results[0]
    assert r.cadence == "yearly"
    assert round(r.monthly_equivalent, 2) == 8.25


def test_skips_only_two_monthly_charges():
    # 2 monthly charges — below MIN_OCCURRENCES_SUB_YEARLY (=3)
    txs = [_tx("s0", 11.99, 0, "Spotify"),
           _tx("s1", 11.99, 30, "Spotify")]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_skips_high_cv_amounts():
    # Same merchant, monthly cadence, wildly varying amounts → CV > 0.15
    amounts = [10, 50, 100, 30, 200]
    txs = [_tx(f"v{i}", a, 30 * i, "Coles") for i, a in enumerate(amounts)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_skips_inactive_subscription():
    # 4 monthly charges but the most recent is 4 months old (> 2 cycles)
    txs = [_tx(f"d{i}", 9.99, 30 * i + 120, "Old Sub") for i in range(4)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_skips_mixed_cadence_cluster():
    # Mix of intervals — 30, 7, 60, 14, 90 — no dominant bucket
    days = [0, 30, 37, 97, 111, 201]
    txs = [_tx(f"m{i}", 10.0, d, "Sporadic") for i, d in enumerate(days)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_ignores_inflows():
    # Positive amounts (income) — should never be candidates
    base = datetime.now(timezone.utc).replace(microsecond=0)
    txs = [
        UpTransaction(
            id=f"i{i}", account_id="acct-1", status="SETTLED",
            description="Salary", amount_value=2000.0,  # POSITIVE
            category_id=None, parent_category_id=None,
            created_at=base - timedelta(days=30 * i),
            settled_at=base - timedelta(days=30 * i),
        )
        for i in range(5)
    ]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_results_sorted_by_monthly_equivalent_desc():
    # Spotify $11.99/mo, Netflix $16.99/mo, Audible $4.99/wk (~$21.69/mo)
    spotify = [_tx(f"s{i}", 11.99, 30 * i, "Spotify") for i in range(3)]
    netflix = [_tx(f"n{i}", 16.99, 30 * i, "Netflix") for i in range(3)]
    audible = [_tx(f"a{i}", 4.99, 7 * i, "Audible") for i in range(4)]
    up_transactions_repo.upsert_many(spotify + netflix + audible, schema=SCHEMA)

    results = find_recurring(schema=SCHEMA)
    monthly_costs = [r.monthly_equivalent for r in results]
    assert monthly_costs == sorted(monthly_costs, reverse=True)
    assert results[0].name.lower().startswith("audible")  # ~$21.69/mo
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_recurring_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_recurring'`.

- [ ] **Step 3: Implement `find_recurring`**

Append to `backend/services/up_recurring_service.py`:

```python
from datetime import datetime, timedelta, timezone

from backend.db.supabase_client import get_supabase
from backend.models.up import RecurringCharge


def _title_case(s: str) -> str:
    """Title-case but preserve all-caps acronyms up to 4 chars."""
    return " ".join(
        w if w.isupper() and len(w) <= 4 else w.title()
        for w in s.split()
    )


def find_recurring(schema: str = "public") -> list[RecurringCharge]:
    """Detect recurring outflow subscriptions.

    See docs/superpowers/specs/2026-05-12-recurring-charges-design.md.
    """
    db = get_supabase()
    rows = (
        db.schema(schema).table("up_transactions")
        .select("description,amount_value,created_at")
        .lt("amount_value", 0)
        .order("created_at", desc=False)
        .execute().data
    )

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
    out: list[RecurringCharge] = []

    for norm, entries in groups.items():
        if len(entries) < 2:  # need ≥1 interval to classify
            continue
        entries.sort(key=lambda x: x[0])
        timestamps = [e[0] for e in entries]
        amounts = [e[1] for e in entries]

        intervals = [
            (timestamps[i + 1] - timestamps[i]).days
            for i in range(len(timestamps) - 1)
        ]
        cadence = classify_cadence(intervals)
        if cadence is None:
            continue

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_recurring_service.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/up_recurring_service.py backend/tests/test_up_recurring_service.py
git commit -m "feat(up): find_recurring orchestrator + integration tests"
git push
```

---

## Part 3 — API + Agent

### Task 5: REST endpoint

**Files:**
- Modify: `backend/routers/up.py`
- Modify: `backend/tests/test_up_router.py`

- [ ] **Step 1: Append failing test**

Append to `backend/tests/test_up_router.py`:

```python
from datetime import timedelta as _td
from backend.models.up import UpAccount as _UpA, UpTransaction as _UpT


def test_recurring_endpoint(monkeypatch, bypass_auth):
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    # The router calls up_recurring_service.find_recurring(schema=SCHEMA);
    # patching SCHEMA is enough to redirect to the test schema.
    monkeypatch.setattr("backend.routers.up.SCHEMA", SCHEMA)

    up_accounts_repo.upsert_many([_UpA(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)

    base = datetime.now(timezone.utc).replace(microsecond=0)
    txs = [
        _UpT(
            id=f"r{i}", account_id="acct-1", status="SETTLED",
            description="Spotify", amount_value=-11.99,
            category_id=None, parent_category_id=None,
            created_at=base - _td(days=30 * i), settled_at=base - _td(days=30 * i),
        )
        for i in range(4)
    ]
    from backend.repositories import up_transactions_repo as _tx_repo
    _tx_repo.upsert_many(txs, schema=SCHEMA)

    resp = client.get("/api/up/recurring")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["cadence"] == "monthly"
    assert body[0]["name"].lower().startswith("spotify")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_router.py::test_recurring_endpoint -v`
Expected: FAIL with 404 (endpoint doesn't exist).

- [ ] **Step 3: Add the endpoint**

Append to `backend/routers/up.py`:

```python
from backend.services import up_recurring_service


@router.get("/recurring")
async def list_recurring() -> list[dict]:
    charges = up_recurring_service.find_recurring(schema=SCHEMA)
    return [c.model_dump(mode="json") for c in charges]
```

- [ ] **Step 4: Run all router tests to verify**

Run: `backend/.venv/bin/pytest backend/tests/test_up_router.py -v`
Expected: PASS (all existing + new).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/up.py backend/tests/test_up_router.py
git commit -m "feat(api): GET /api/up/recurring"
git push
```

---

### Task 6: MCP tool + agent integration

**Files:**
- Modify: `backend/mcp_server.py`
- Modify: `backend/agent/agent_config.py`
- Modify: `backend/agent/prompts.py`
- Modify: `backend/tests/test_mcp_up_tools.py`
- Modify: `backend/tests/test_mcp_integration.py` (tool-name set)

- [ ] **Step 1: Append failing test**

Append to `backend/tests/test_mcp_up_tools.py`:

```python
from datetime import timedelta as _td2
from backend.models.up import UpAccount as _UpA2, UpTransaction as _UpT2
from backend.repositories import up_accounts_repo as _acc_repo, up_transactions_repo as _tx_repo


def test_get_recurring_charges_includes_monthly_total(monkeypatch):
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()

    import backend.mcp_server as mcp_module
    # The MCP tool calls find_recurring(schema=UP_SCHEMA); patching UP_SCHEMA
    # is enough to redirect reads to the test schema.
    monkeypatch.setattr(mcp_module, "UP_SCHEMA", SCHEMA)

    _acc_repo.upsert_many([_UpA2(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)

    base = datetime.now(timezone.utc).replace(microsecond=0)
    txs = [
        _UpT2(id=f"x{i}", account_id="acct-1", status="SETTLED",
              description="Spotify", amount_value=-11.99,
              category_id=None, parent_category_id=None,
              created_at=base - _td2(days=30 * i), settled_at=base - _td2(days=30 * i))
        for i in range(4)
    ]
    _tx_repo.upsert_many(txs, schema=SCHEMA)

    out = mcp_module.get_recurring_charges()
    assert "Spotify" in out
    assert "monthly" in out.lower()
    assert "11.99" in out
    assert "/month" in out  # the heading line
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_mcp_up_tools.py::test_get_recurring_charges_includes_monthly_total -v`
Expected: FAIL with `AttributeError: module 'backend.mcp_server' has no attribute 'get_recurring_charges'`.

- [ ] **Step 3: Add the MCP tool**

Append to `backend/mcp_server.py` (BEFORE the `if __name__ == "__main__"` block):

```python
from backend.services import up_recurring_service as _up_recurring


@mcp.tool()
def get_recurring_charges() -> str:
    """Detected recurring charges (subscriptions). Returns each subscription's
    cadence, amount, and monthly-equivalent cost, sorted by largest first.
    Includes a total monthly subscription burden at the top."""
    charges = _up_recurring.find_recurring(schema=UP_SCHEMA)
    if not charges:
        return ("No recurring charges detected yet. A subscription needs to "
                "charge regularly with a stable amount before we can spot it "
                "(3 monthly charges, or 2 yearly).")
    total_monthly = sum(c.monthly_equivalent for c in charges)
    lines = [f"Total recurring subscriptions: ${total_monthly:,.2f}/month  ({len(charges)} active)"]
    for c in charges:
        if c.cadence == "yearly":
            extra = f"  (next: {c.next_expected_at.date()}, ~${c.monthly_equivalent:,.2f}/mo)"
            amount_str = f"${c.median_amount:,.2f}"
        else:
            extra = f"  (next: {c.next_expected_at.date()})"
            amount_str = f"${c.median_amount:,.2f}"
        lines.append(f"  - {c.name:24s} {c.cadence:12s} {amount_str}{extra}")
    return "\n".join(lines)
```

- [ ] **Step 4: Add tool to the cash agent's tool subset**

Modify `backend/agent/agent_config.py`. Find the `TOOL_SUBSETS["cash"]` list and append `"get_recurring_charges"`:

```python
    "cash": [
        "get_up_balance",
        "get_up_spending_by_category",
        "get_up_cashflow",
        "get_up_recent_transactions",
        "get_combined_net_worth",
        "get_recurring_charges",
    ],
```

- [ ] **Step 5: Mention the tool in CASH_APPENDIX**

In `backend/agent/prompts.py`, find `CASH_APPENDIX` and add one bullet to the tool list (insert after `get_combined_net_worth`):

```
- get_recurring_charges — detected subscriptions with monthly totals.
```

- [ ] **Step 6: Update integration test tool-name set**

```bash
grep -n "get_up_balance\|tool_names" backend/tests/test_mcp_integration.py | head
```

Find the assertion that compares the loaded MCP tool names to a hardcoded set/list. Add `"get_recurring_charges"` to that collection so it stays in sync. The test will fail otherwise.

- [ ] **Step 7: Run tests to verify**

```bash
backend/.venv/bin/pytest backend/tests/test_mcp_up_tools.py backend/tests/test_mcp_integration.py -v
```
Expected: PASS (all).

- [ ] **Step 8: Commit**

```bash
git add backend/mcp_server.py backend/agent/agent_config.py backend/agent/prompts.py backend/tests/test_mcp_up_tools.py backend/tests/test_mcp_integration.py
git commit -m "feat(mcp): get_recurring_charges tool + cash agent integration"
git push
```

---

## Part 4 — Frontend

### Task 7: Type + API client method

**Files:**
- Modify: `frontend/src/types/up.ts`
- Modify: `frontend/src/api/up.ts`

- [ ] **Step 1: Add the type**

Append to `frontend/src/types/up.ts`:

```typescript
export type RecurringCadence = 'weekly' | 'fortnightly' | 'monthly' | 'yearly'

export interface RecurringCharge {
  name: string
  sample_description: string
  cadence: RecurringCadence
  median_amount: number
  last_charged_at: string
  next_expected_at: string
  occurrence_count: number
  monthly_equivalent: number
}
```

- [ ] **Step 2: Add the fetch function**

Append to `frontend/src/api/up.ts`:

```typescript
import type { RecurringCharge } from '../types/up'

export async function fetchRecurring(): Promise<RecurringCharge[]> {
  const r = await apiFetch('/api/up/recurring')
  if (!r.ok) throw new Error(`recurring: ${r.status}`)
  return r.json()
}
```

(`apiFetch` is already imported at the top of the file.)

- [ ] **Step 3: Verify TS compiles**

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npx tsc -b --noEmit 2>&1 | grep -v "src/pages/CryptoPage\|src/components/SummaryBar"
```
Expected: only pre-existing CryptoPage/SummaryBar errors (unrelated tech debt). No new errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker
git add frontend/src/types/up.ts frontend/src/api/up.ts
git commit -m "feat(frontend): RecurringCharge type + fetchRecurring API client"
git push
```

---

### Task 8: `RecurringList` component

**Files:**
- Create: `frontend/src/components/up/RecurringList.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/up/RecurringList.tsx`:

```tsx
import type { RecurringCharge } from '../../types/up'

interface Props { charges: RecurringCharge[] }

const CADENCE_LABEL: Record<RecurringCharge['cadence'], string> = {
  weekly: 'Weekly',
  fortnightly: 'Fortnightly',
  monthly: 'Monthly',
  yearly: 'Yearly',
}

function fmt(n: number): string {
  return n.toLocaleString('en-AU', { minimumFractionDigits: 2 })
}

function formatNextDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })
}

export default function RecurringList({ charges }: Props) {
  if (charges.length === 0) {
    return (
      <div className="text-sm text-txt-muted">
        No recurring charges detected. A subscription needs to charge regularly
        with a stable amount before we can spot it (3 monthly charges, or 2 yearly).
      </div>
    )
  }

  const totalMonthly = charges.reduce((s, c) => s + c.monthly_equivalent, 0)

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-1">
        <span className="font-mono text-3xl text-txt-primary tabular-nums">
          ${fmt(totalMonthly)}<span className="text-base text-txt-secondary font-normal">/mo</span>
        </span>
        <span className="text-xs font-medium text-txt-muted tabular-nums">
          {charges.length} active
        </span>
      </div>
      <p className="text-xs text-txt-muted mb-4">total recurring</p>

      <ul className="divide-y divide-surface-border">
        {charges.map(c => (
          <li key={c.name + c.cadence} className="grid grid-cols-[1fr_auto] items-baseline gap-x-4 py-2.5">
            <div className="min-w-0">
              <div className="text-sm text-txt-primary truncate">{c.name}</div>
              <div className="text-xs text-txt-muted mt-0.5">
                {CADENCE_LABEL[c.cadence]}
                {c.cadence === 'yearly' && ` $${fmt(c.median_amount)}`}
                {' · next '}
                {formatNextDate(c.next_expected_at)}
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono text-sm text-txt-primary tabular-nums">
                ${fmt(c.monthly_equivalent)}
              </div>
              <div className="text-xs text-txt-muted mt-0.5">
                {c.cadence === 'yearly' ? '/mo equiv' : '/mo'}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 2: Verify TS compiles**

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npx tsc -b --noEmit 2>&1 | grep -v "src/pages/CryptoPage\|src/components/SummaryBar"
```
Expected: only pre-existing errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker
git add frontend/src/components/up/RecurringList.tsx
git commit -m "feat(frontend): RecurringList component"
git push
```

---

### Task 9: Wire `RecurringList` into UpPage

**Files:**
- Modify: `frontend/src/pages/UpPage.tsx`

- [ ] **Step 1: Add the new state, fetch, and section to UpPage**

Modify `frontend/src/pages/UpPage.tsx`. Three changes:

**(a)** Add the import near the other UP component imports:

```tsx
import RecurringList from '../components/up/RecurringList'
```

And to API + types:

```tsx
import {
  fetchAccounts, fetchTransactions, fetchSpendingSummary, fetchRecurring,
} from '../api/up'
import type { UpAccount, UpTransaction, RecurringCharge } from '../types/up'
```

**(b)** Add new state + fetch. Find the existing accounts `useEffect` (the one that depends on `sync?.state` and only fetches accounts) and update it to also fetch recurring charges, since both are range-independent:

```tsx
const [accounts, setAccounts] = useState<UpAccount[]>([])
const [recurring, setRecurring] = useState<RecurringCharge[]>([])
// ... other state ...
const [accountsLoading, setAccountsLoading] = useState(true)
const [recurringLoading, setRecurringLoading] = useState(true)

useEffect(() => {
  let cancelled = false
  setAccountsLoading(true)
  setRecurringLoading(true)
  Promise.all([
    fetchAccounts(),
    fetchRecurring(),
  ]).then(([a, r]) => {
    if (cancelled) return
    setAccounts(a); setAccountsLoading(false)
    setRecurring(r); setRecurringLoading(false)
  }).catch(() => {
    if (cancelled) return
    setAccountsLoading(false); setRecurringLoading(false)
  })
  return () => { cancelled = true }
}, [sync?.state])
```

**(c)** Add a new section between Spending and Transactions in the JSX:

```tsx
<Section title="Subscriptions">
  {recurringLoading ? <Skeleton tall /> : <RecurringList charges={recurring} />}
</Section>
```

Place it AFTER the Spending section and BEFORE the Transactions section.

- [ ] **Step 2: Verify TS compiles**

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npx tsc -b --noEmit 2>&1 | grep -v "src/pages/CryptoPage\|src/components/SummaryBar"
```
Expected: only pre-existing errors.

- [ ] **Step 3: Manual smoke**

Refresh http://localhost:5173/up. Confirm:
- Subscriptions section appears between Spending and Transactions.
- If you have ≥3 charges from a single normalised merchant, they appear with monthly equivalent.
- Loading state shows skeleton, then content.
- Empty state shows the explanatory copy if no recurring detected.

- [ ] **Step 4: Commit**

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker
git add frontend/src/pages/UpPage.tsx
git commit -m "feat(frontend): wire RecurringList into UpPage"
git push
```

---

## Part 5 — Smoke

### Task 10: End-to-end smoke

**Files:** none (manual + a few automated probes)

- [ ] **Step 1: Run the full non-eval test suite**

```bash
backend/.venv/bin/pytest backend/tests -m "not eval" --tb=short 2>&1 | tail -30
```
Expected: all pass.

- [ ] **Step 2: Probe the live endpoint**

(uvicorn is presumed running; if not, start it with `backend/.venv/bin/uvicorn backend.main:app --reload`)

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/up/recurring
```
Expected: `401` (auth gate active — endpoint exists).

- [ ] **Step 3: Inspect detection on real data via Python REPL**

```bash
backend/.venv/bin/python -c "
from backend.services.up_recurring_service import find_recurring
charges = find_recurring()
print(f'detected {len(charges)} recurring charges:')
for c in charges:
    print(f'  {c.name:30s} {c.cadence:12s} \${c.median_amount:>7.2f}  ~\${c.monthly_equivalent:.2f}/mo')
"
```

Eyeball the output. If something obvious is missing (a known subscription you have isn't there), the normaliser likely needs a tweak — investigate that merchant string.

- [ ] **Step 4: Browser walkthrough**

Open `http://localhost:5173/up`. Verify:
- Subscriptions section renders between Spending and Transactions.
- Monthly total + count match what Step 3 printed.
- Each row's name, cadence, and amount look correct.
- Yearly subs (if any) show `/mo equiv` label and the annual amount in the secondary line.

- [ ] **Step 5: Agent walkthrough**

Open the agent chat (currently lives on `/crypto`) and ask: **"What subscriptions am I paying for?"**

Expected: agent classifies as `cash`, calls `get_recurring_charges`, returns the formatted list with monthly total.

- [ ] **Step 6: No commit unless bugs found**

If any bug surfaces, fix and commit with `fix(...)`.

---

## Spec coverage check

| Spec section | Implemented in |
|---|---|
| `RecurringCharge` model | Task 1 |
| Normaliser (`normalise()`) | Task 2 |
| Cadence classifier, CV, monthly-equivalent helpers | Task 3 |
| `find_recurring()` orchestrator (groups, thresholds, active filter, sort) | Task 4 |
| `GET /api/up/recurring` REST endpoint | Task 5 |
| `get_recurring_charges()` MCP tool | Task 6 |
| `TOOL_SUBSETS["cash"]` extension | Task 6 |
| `CASH_APPENDIX` mention | Task 6 |
| Frontend `RecurringCharge` type + `fetchRecurring()` | Task 7 |
| `RecurringList.tsx` component (Layout A) | Task 8 |
| UpPage section (between Spending and Transactions) | Task 9 |
| Loading skeleton + empty state | Tasks 8, 9 |
| Tests (normaliser, helpers, service, router, MCP tool) | Tasks 2, 3, 4, 5, 6 |

All spec requirements covered.

---

## Execution

Plan complete and saved to `docs/superpowers/plans/2026-05-12-recurring-charges.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
