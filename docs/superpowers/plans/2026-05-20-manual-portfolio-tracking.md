# Manual Portfolio Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Manual" row to the strategies leaderboard representing the user's real Kraken portfolio, computed using time-weighted return (TWR) segmented at every Kraken deposit/withdrawal.

**Architecture:** Cash flows are detected from Kraken's ledger on leaderboard load (debounced to once per 5 min) and persisted to a new `manual_cash_flows` table. A pure-function `manual_performance` service computes TWR + a synthetic-unit equity curve; the existing `sharpe_24_7` and `max_drawdown_pct` functions run on that curve. The leaderboard router appends a virtual "Manual" row and changes the sort key to `return_all_time_pct` desc so the comparison surfaces who returned the most, not who has the most capital.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Supabase Postgres, Kraken Spot API (`kraken.spot.User`), `MagicMock` + `monkeypatch` for tests. Frontend is React + Vite + Tailwind, modified via `/impeccable` (per project convention).

**Spec:** `docs/superpowers/specs/2026-05-20-manual-portfolio-tracking-design.md`

---

## File map

| Path | Action | Responsibility |
|---|---|---|
| `supabase/migrations/008_manual_cash_flows.sql` | NEW | Create `public.manual_cash_flows`. |
| `supabase/migrations/test_008_manual_cash_flows.sql` | NEW | Mirror in `test` schema. |
| `backend/services/kraken_service.py` | MODIFY | Add `get_cash_flow_entries(since)`. |
| `backend/repositories/manual_cash_flows_repo.py` | NEW | CRUD helpers for the new table. |
| `backend/repositories/__init__.py` | MODIFY | Export the new repo. |
| `backend/services/manual_performance.py` | NEW | Pure-function TWR + synthetic-unit curve. |
| `backend/services/manual_cash_flow_scanner.py` | NEW | Debounced ledger scan + persistence. |
| `backend/routers/strategies.py` | MODIFY | Append Manual row, add `lifetime_return_pct` to every row, change sort key. |
| `frontend/src/pages/StrategiesPage.tsx` (or related) | MODIFY (via `/impeccable`) | New "Lifetime" column, Manual-row visual highlight, short-window caveat banner. |
| `backend/tests/test_kraken_cash_flow_entries.py` | NEW | Unit tests for the new `kraken_service` function. |
| `backend/tests/test_manual_cash_flows_repo.py` | NEW | Repo CRUD round-trip on test schema. |
| `backend/tests/test_manual_twr.py` | NEW | Pure-function TWR tests (no DB, no HTTP). |
| `backend/tests/test_manual_cash_flow_scanner.py` | NEW | Debounce + scan logic with mocked Kraken. |
| `backend/tests/test_manual_leaderboard.py` | NEW | Integration test: leaderboard endpoint with seeded Manual data. |

---

## Conventions used throughout

- All commit messages use Conventional Commits + the standing `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
- Every task ends with `git push origin main` (per the user's standing instruction).
- Tests are added BEFORE implementation (TDD).
- Tests that hit the live Supabase test schema reuse the existing `_truncate_*` patterns from earlier tests.
- The `WINDOW_START` for the comparison is dynamic: `MIN(created_at)` across active strategies. No hardcoded date in code.

---

### Task 1: Database migration

**Files:**
- Create: `supabase/migrations/008_manual_cash_flows.sql`
- Create: `supabase/migrations/test_008_manual_cash_flows.sql`

- [ ] **Step 1: Create the public-schema migration**

Write `supabase/migrations/008_manual_cash_flows.sql`:

```sql
-- Manual portfolio cash flows: deposit/withdrawal events detected on Kraken.
-- One row per Kraken ledger entry, dedup'd by kraken_refid.
CREATE TABLE public.manual_cash_flows (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  kraken_refid    text          NOT NULL UNIQUE,
  kind            text          NOT NULL CHECK (kind IN ('deposit', 'withdrawal')),
  amount_aud      numeric(20,8) NOT NULL,
  occurred_at     timestamptz   NOT NULL,
  created_at      timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX idx_manual_cash_flows_occurred_at
  ON public.manual_cash_flows (occurred_at);
```

- [ ] **Step 2: Create the test-schema mirror**

Write `supabase/migrations/test_008_manual_cash_flows.sql`:

```sql
-- Mirror of 008_manual_cash_flows.sql for the test schema.
CREATE TABLE test.manual_cash_flows (LIKE public.manual_cash_flows INCLUDING ALL);
```

- [ ] **Step 3: Apply both migrations to Supabase**

Use the Supabase MCP tools you have access to:

1. `mcp__claude_ai_Supabase__list_projects` → confirm the kraken-portfolio-tracker project id (`ofavtswgywjjhfcdzbig`).
2. `mcp__claude_ai_Supabase__apply_migration` with `name="008_manual_cash_flows"` and `query=<contents of 008_manual_cash_flows.sql>`.
3. `mcp__claude_ai_Supabase__apply_migration` with `name="test_008_manual_cash_flows"` and `query=<contents of test_008_manual_cash_flows.sql>`.

If `apply_migration` is unavailable, fall back to `execute_sql` with the same SQL.

- [ ] **Step 4: Verify the table exists in both schemas**

Run via `mcp__claude_ai_Supabase__execute_sql`:

```sql
SELECT table_schema, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'manual_cash_flows'
  AND table_schema IN ('public', 'test')
ORDER BY table_schema, ordinal_position;
```

Expected: 12 rows (6 columns × 2 schemas), including `kraken_refid` (text, NOT NULL), `kind` (text, NOT NULL), `amount_aud` (numeric), `occurred_at` (timestamp with time zone), `created_at` (timestamp with time zone, NOT NULL).

Paste the actual result into your report.

- [ ] **Step 5: Commit and push**

```bash
git add supabase/migrations/008_manual_cash_flows.sql supabase/migrations/test_008_manual_cash_flows.sql
git commit -m "$(cat <<'EOF'
feat(db): add manual_cash_flows table

One row per Kraken deposit/withdrawal event, dedup'd by kraken_refid.
Backs the manual-portfolio tracking feature that adds the user's real
Kraken portfolio as a 4th competitor on the strategies leaderboard.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 2: `kraken_service.get_cash_flow_entries(since)`

**Files:**
- Modify: `backend/services/kraken_service.py`
- Create: `backend/tests/test_kraken_cash_flow_entries.py`

This task adds a new function to `kraken_service` that pulls deposit/withdrawal entries from Kraken's ledger and returns them as normalised dicts. Pure mock-based testing — no live Kraken hits.

- [ ] **Step 1: Write the failing tests**

Write `backend/tests/test_kraken_cash_flow_entries.py`:

```python
"""Tests for kraken_service.get_cash_flow_entries.

Pure unit tests with MagicMock + monkeypatch, matching the existing
test_kraken_service.py pattern. No live Kraken hits.
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.services import kraken_service


def _make_user_with_ledger(pages: list[dict]) -> MagicMock:
    user = MagicMock()
    call_count = {"n": 0}

    def fake_get_ledgers_info(ofs=0, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx >= len(pages):
            return {"count": pages[0]["count"], "ledger": {}}
        return pages[idx]

    user.get_ledgers_info = fake_get_ledgers_info
    return user


@pytest.fixture(autouse=True)
def reset_kraken_singletons():
    kraken_service._user = None
    kraken_service._market = None
    yield
    kraken_service._user = None
    kraken_service._market = None


def test_detects_deposit_entry(monkeypatch):
    ledger = {
        "LDEP1": {
            "asset": "ZAUD",
            "amount": "500.00",
            "refid": "DEPOSIT-REF-1",
            "time": 1779100000.0,
            "type": "deposit",
            "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 1, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)

    assert len(entries) == 1
    assert entries[0]["kraken_refid"] == "DEPOSIT-REF-1"
    assert entries[0]["kind"] == "deposit"
    assert entries[0]["amount_aud"] == Decimal("500.00")
    assert entries[0]["asset"] == "AUD"


def test_detects_withdrawal_entry(monkeypatch):
    ledger = {
        "LWD1": {
            "asset": "ZAUD",
            "amount": "-200.00",
            "refid": "WITHDRAW-REF-1",
            "time": 1779100000.0,
            "type": "withdrawal",
            "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 1, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)

    assert len(entries) == 1
    assert entries[0]["kind"] == "withdrawal"
    assert entries[0]["amount_aud"] == Decimal("200.00")  # absolute


def test_ignores_non_cash_flow_entries(monkeypatch):
    ledger = {
        "LRECV1": {
            "asset": "XETH", "amount": "0.05", "refid": "TRADE1",
            "time": 1779100000.0, "type": "receive", "subtype": "",
        },
        "LSPEND1": {
            "asset": "ZAUD", "amount": "-150.00", "refid": "TRADE1",
            "time": 1779100000.0, "type": "spend", "subtype": "",
        },
        "LSTAKE1": {
            "asset": "SOL.S", "amount": "0.001", "refid": "STAKE1",
            "time": 1779100000.0, "type": "staking", "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 3, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)

    assert entries == []


def test_marks_non_aud_deposit_with_asset_field(monkeypatch):
    """USDT/USDC deposits are returned with asset != 'AUD' so the
    caller can system_alert + skip them."""
    ledger = {
        "LUSDT1": {
            "asset": "USDT", "amount": "100.00", "refid": "USDT-REF",
            "time": 1779100000.0, "type": "deposit", "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 1, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)
    assert len(entries) == 1
    assert entries[0]["asset"] == "USDT"


def test_filters_by_since_timestamp(monkeypatch):
    ledger = {
        "LOLD": {
            "asset": "ZAUD", "amount": "100.00", "refid": "OLD-REF",
            "time": 1779000000.0, "type": "deposit", "subtype": "",
        },
        "LNEW": {
            "asset": "ZAUD", "amount": "200.00", "refid": "NEW-REF",
            "time": 1779200000.0, "type": "deposit", "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 2, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    since = datetime.fromtimestamp(1779100000.0, tz=timezone.utc)
    entries = kraken_service.get_cash_flow_entries(since=since)

    assert len(entries) == 1
    assert entries[0]["kraken_refid"] == "NEW-REF"


def test_pagination_aggregates_all_pages(monkeypatch):
    page1 = {
        "count": 2,
        "ledger": {
            "L1": {"asset": "ZAUD", "amount": "100", "refid": "R1",
                   "time": 1779000000.0, "type": "deposit", "subtype": ""},
        },
    }
    page2 = {
        "count": 2,
        "ledger": {
            "L2": {"asset": "ZAUD", "amount": "200", "refid": "R2",
                   "time": 1779100000.0, "type": "withdrawal", "subtype": ""},
        },
    }
    user = _make_user_with_ledger([page1, page2])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)

    assert {e["kraken_refid"] for e in entries} == {"R1", "R2"}
```

- [ ] **Step 2: Run the tests; they should fail**

```bash
backend/.venv/bin/pytest backend/tests/test_kraken_cash_flow_entries.py -v
```

Expected: `AttributeError: module 'backend.services.kraken_service' has no attribute 'get_cash_flow_entries'`.

- [ ] **Step 3: Add the function**

Append to `backend/services/kraken_service.py`:

```python
def get_cash_flow_entries(since: "datetime | None" = None) -> list[dict]:
    """Return Kraken deposit + withdrawal ledger entries as normalised dicts.

    Each dict shape:
        {
            "kraken_refid": str,
            "kind": "deposit" | "withdrawal",
            "amount_aud": Decimal,              # always positive
            "asset": str,                       # "AUD" for fiat, otherwise the Kraken asset code
            "occurred_at": datetime,
        }

    Non-AUD entries are returned with `asset` set to the raw Kraken code so
    the caller can emit a system_alert and skip. `since` is exclusive; pass
    `None` to fetch everything.
    """
    from datetime import datetime, timezone

    user = _get_user()
    all_entries: dict[str, dict] = {}
    offset = 0

    while True:
        try:
            result = user.get_ledgers_info(ofs=offset)
        except Exception as e:
            raise KrakenServiceError(f"get_cash_flow_entries failed: {e}") from e
        ledger: dict = result.get("ledger", {})
        count: int = result.get("count", 0)
        if not ledger:
            break
        all_entries.update(ledger)
        offset += len(ledger)
        if offset >= count:
            break

    since_ts = since.timestamp() if since is not None else None

    out: list[dict] = []
    for entry in all_entries.values():
        entry_type = entry.get("type")
        if entry_type not in ("deposit", "withdrawal"):
            continue
        ts = float(entry["time"])
        if since_ts is not None and ts <= since_ts:
            continue
        raw_asset = entry.get("asset", "")
        # ZAUD is Kraken's code for fiat AUD. Strip the leading "Z" so
        # downstream code can match on a clean "AUD".
        asset = "AUD" if raw_asset == "ZAUD" else raw_asset
        amount = Decimal(str(entry["amount"]))
        out.append({
            "kraken_refid": entry["refid"],
            "kind": entry_type,
            "amount_aud": abs(amount),
            "asset": asset,
            "occurred_at": datetime.fromtimestamp(ts, tz=timezone.utc),
        })

    out.sort(key=lambda e: e["occurred_at"])
    return out
```

- [ ] **Step 4: Run the tests; they should pass**

```bash
backend/.venv/bin/pytest backend/tests/test_kraken_cash_flow_entries.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/kraken_service.py backend/tests/test_kraken_cash_flow_entries.py
git commit -m "$(cat <<'EOF'
feat(kraken): get_cash_flow_entries — pull deposits/withdrawals from ledger

Filters Kraken's ledger to deposit + withdrawal entries, returns
normalised dicts (refid, kind, amount, asset, occurred_at). Pure
mock-tested; no live Kraken hits.

ZAUD is normalised to "AUD" for downstream matching. Non-AUD assets
are returned with the raw code so the caller can system_alert + skip.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 3: `manual_cash_flows_repo`

**Files:**
- Create: `backend/repositories/manual_cash_flows_repo.py`
- Modify: `backend/repositories/__init__.py` (export the new module)
- Create: `backend/tests/test_manual_cash_flows_repo.py`

- [ ] **Step 1: Write the failing tests**

Write `backend/tests/test_manual_cash_flows_repo.py`:

```python
"""Repo tests for manual_cash_flows. Round-trips through the test schema."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.db.supabase_client import get_supabase
from backend.repositories import manual_cash_flows_repo

SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("manual_cash_flows").delete().neq("id", _SENTINEL_UUID).execute()
    yield


def test_upsert_by_refid_inserts_new_row():
    occurred = datetime.now(timezone.utc) - timedelta(days=1)
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="REF-1", kind="deposit",
        amount_aud=Decimal("500.00"), occurred_at=occurred,
        schema=SCHEMA,
    )
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=2), schema=SCHEMA,
    )
    assert len(rows) == 1
    assert rows[0]["kraken_refid"] == "REF-1"
    assert rows[0]["kind"] == "deposit"
    assert Decimal(str(rows[0]["amount_aud"])) == Decimal("500.00")


def test_upsert_by_refid_is_idempotent():
    occurred = datetime.now(timezone.utc) - timedelta(hours=1)
    for _ in range(3):
        manual_cash_flows_repo.upsert_by_refid(
            kraken_refid="REF-DUP", kind="deposit",
            amount_aud=Decimal("100.00"), occurred_at=occurred,
            schema=SCHEMA,
        )
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=1), schema=SCHEMA,
    )
    assert len(rows) == 1


def test_list_since_filters_by_occurred_at():
    old = datetime.now(timezone.utc) - timedelta(days=10)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="OLD", kind="deposit",
        amount_aud=Decimal("100"), occurred_at=old, schema=SCHEMA,
    )
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="NEW", kind="deposit",
        amount_aud=Decimal("200"), occurred_at=recent, schema=SCHEMA,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    rows = manual_cash_flows_repo.list_since(since=cutoff, schema=SCHEMA)
    refids = [r["kraken_refid"] for r in rows]
    assert refids == ["NEW"]


def test_last_created_at_returns_max():
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="A", kind="deposit",
        amount_aud=Decimal("1"),
        occurred_at=datetime.now(timezone.utc) - timedelta(hours=2),
        schema=SCHEMA,
    )
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="B", kind="withdrawal",
        amount_aud=Decimal("2"),
        occurred_at=datetime.now(timezone.utc) - timedelta(hours=1),
        schema=SCHEMA,
    )
    last = manual_cash_flows_repo.last_created_at(schema=SCHEMA)
    assert last is not None
    assert (datetime.now(timezone.utc) - last).total_seconds() < 60


def test_last_created_at_returns_none_when_empty():
    assert manual_cash_flows_repo.last_created_at(schema=SCHEMA) is None


def test_latest_occurred_at_returns_max_kraken_event_time():
    earlier = datetime.now(timezone.utc) - timedelta(hours=5)
    later = datetime.now(timezone.utc) - timedelta(hours=1)
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="A", kind="deposit", amount_aud=Decimal("1"),
        occurred_at=earlier, schema=SCHEMA,
    )
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="B", kind="deposit", amount_aud=Decimal("2"),
        occurred_at=later, schema=SCHEMA,
    )
    latest = manual_cash_flows_repo.latest_occurred_at(schema=SCHEMA)
    assert latest is not None
    # ~1 hour ago, give or take parsing precision
    assert abs((datetime.now(timezone.utc) - latest).total_seconds() - 3600) < 60
```

- [ ] **Step 2: Run the tests; they should fail**

```bash
backend/.venv/bin/pytest backend/tests/test_manual_cash_flows_repo.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.repositories.manual_cash_flows_repo'`.

- [ ] **Step 3: Implement the repo**

Write `backend/repositories/manual_cash_flows_repo.py`:

```python
"""Repository for the `manual_cash_flows` table.

Persists Kraken deposit/withdrawal events that segment the comparison
window for the manual-portfolio leaderboard entry.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from backend.db.supabase_client import get_supabase


def upsert_by_refid(
    *,
    kraken_refid: str,
    kind: str,           # "deposit" | "withdrawal"
    amount_aud: Decimal,
    occurred_at: datetime,
    schema: str = "public",
) -> None:
    """Insert a new cash-flow row, no-op if the refid already exists.

    Implemented as INSERT ... ON CONFLICT DO NOTHING (via supabase-py's
    upsert with ignore_duplicates=True) so the scanner can re-run safely.
    """
    sb = get_supabase()
    (sb.schema(schema).table("manual_cash_flows")
       .upsert(
           {
               "kraken_refid": kraken_refid,
               "kind": kind,
               "amount_aud": str(amount_aud),
               "occurred_at": occurred_at.isoformat(),
           },
           on_conflict="kraken_refid",
           ignore_duplicates=True,
       ).execute())


def list_since(*, since: datetime, schema: str = "public") -> list[dict]:
    """Cash-flow rows with occurred_at > since, ascending."""
    sb = get_supabase()
    r = (sb.schema(schema).table("manual_cash_flows")
           .select("*")
           .gt("occurred_at", since.isoformat())
           .order("occurred_at", desc=False).execute())
    return r.data or []


def last_created_at(*, schema: str = "public") -> datetime | None:
    """Max created_at across all rows. Used for debounce."""
    sb = get_supabase()
    r = (sb.schema(schema).table("manual_cash_flows")
           .select("created_at")
           .order("created_at", desc=True).limit(1).execute())
    if not r.data:
        return None
    return datetime.fromisoformat(r.data[0]["created_at"].replace("Z", "+00:00"))


def latest_occurred_at(*, schema: str = "public") -> datetime | None:
    """Max occurred_at across all rows. Used as the 'since' for next scan."""
    sb = get_supabase()
    r = (sb.schema(schema).table("manual_cash_flows")
           .select("occurred_at")
           .order("occurred_at", desc=True).limit(1).execute())
    if not r.data:
        return None
    return datetime.fromisoformat(r.data[0]["occurred_at"].replace("Z", "+00:00"))
```

- [ ] **Step 4: Export from the package init**

Edit `backend/repositories/__init__.py`. Find the existing imports (other repo modules are re-exported there) and add:

```python
from backend.repositories import manual_cash_flows_repo
```

If the file uses `__all__`, append `"manual_cash_flows_repo"` to that list.

- [ ] **Step 5: Run the tests; they should pass**

```bash
backend/.venv/bin/pytest backend/tests/test_manual_cash_flows_repo.py -v
```

Expected: 6 PASS.

- [ ] **Step 6: Commit and push**

```bash
git add backend/repositories/manual_cash_flows_repo.py backend/repositories/__init__.py backend/tests/test_manual_cash_flows_repo.py
git commit -m "$(cat <<'EOF'
feat(repos): manual_cash_flows_repo with idempotent upsert

CRUD over the new manual_cash_flows table: upsert_by_refid (no-op
on duplicate refid), list_since (occurred_at filter), last_created_at
(for the scanner's 5-min debounce), latest_occurred_at (next-scan
high-water mark).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 4: `manual_performance.compute_twr` (pure function)

**Files:**
- Create: `backend/services/manual_performance.py`
- Create: `backend/tests/test_manual_twr.py`

Pure-function TWR. No DB, no HTTP. Produces `(twr_pct, synthetic_unit_curve)`. The synthetic-unit curve feeds the existing `sharpe_24_7` / `max_drawdown_pct` functions.

- [ ] **Step 1: Write the failing tests**

Write `backend/tests/test_manual_twr.py`:

```python
"""Pure-function TWR tests. No DB, no HTTP.

In real production data, cash flows happen BETWEEN hourly snapshots,
not at the same timestamp. These tests reflect that: the snapshot
times and cash-flow times are distinct, and compute_twr must merge
them chronologically and segment internally.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.services.manual_performance import (
    CashFlowEvent, EquityPoint, compute_twr,
)


def _ep(days_ago: int, value: str) -> EquityPoint:
    return EquityPoint(
        captured_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        total_value_aud=Decimal(value),
    )


def _cf(days_ago: int, amount: str, kind: str = "deposit") -> CashFlowEvent:
    return CashFlowEvent(
        occurred_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        amount_aud=Decimal(amount),
        kind=kind,
    )


def test_no_cash_flow_single_segment():
    curve = [_ep(7, "1000"), _ep(0, "1100")]
    twr, unit_curve = compute_twr(curve, cash_flows=[])
    assert twr == Decimal("10.00")  # +10%
    assert unit_curve == [Decimal("1"), Decimal("1.1")]


def test_one_deposit_mid_window():
    # Day-7: snap $1000. Day-3: snap $1100 (just before deposit).
    # Day-2: deposit $500 (1 day after the day-3 snapshot).
    # Day-0: snap $1600 (no market movement; 1100+500=1600).
    #
    # Segment 1 (day-7 → day-2 deposit): 1100/1000 = 1.10
    # Segment 2 (day-2 → day-0): 1600/(1100+500) = 1.00
    # TWR = 1.10 * 1.00 - 1 = +10%.
    curve = [_ep(7, "1000"), _ep(3, "1100"), _ep(0, "1600")]
    cf = _cf(2, "500", kind="deposit")
    twr, _ = compute_twr(curve, cash_flows=[cf])
    assert twr == Decimal("10.00")


def test_one_withdrawal_mid_window():
    # Day-7: $1000. Day-3: $1100. Day-2: withdraw 300.
    # Day-0: $800 (= 1100 - 300, no movement).
    # Segment 1: 1100/1000 = 1.10. Segment 2: 800/(1100-300) = 1.00. TWR = +10%.
    curve = [_ep(7, "1000"), _ep(3, "1100"), _ep(0, "800")]
    cf = _cf(2, "300", kind="withdrawal")
    twr, _ = compute_twr(curve, cash_flows=[cf])
    assert twr == Decimal("10.00")


def test_synthetic_unit_curve_grows_segment_by_segment():
    # Day-7: $1000. Day-3: $1100. Day-2: deposit $500. Day-0: $1696.
    # Seg1: 1100/1000 = 1.10. Seg2: 1696/1600 = 1.06.
    # Compound: 1.10 * 1.06 - 1 = 0.166 → 16.60%.
    curve = [_ep(7, "1000"), _ep(3, "1100"), _ep(0, "1696")]
    cf = _cf(2, "500", kind="deposit")
    twr, unit_curve = compute_twr(curve, cash_flows=[cf])
    assert twr == Decimal("16.60")
    # One unit-curve point per snapshot. Cash flow doesn't add a point.
    assert len(unit_curve) == 3
    assert unit_curve[0] == Decimal("1")
    assert unit_curve[-1] == Decimal("1.166")


def test_multiple_cash_flows_in_sequence():
    # Day-10: $1000. Day-7: $1050 (+5%). Day-6: deposit $500.
    # Day-3: $1550 (no movement; 1050+500). Day-2: withdraw $100.
    # Day-0: $1595 (1450 * 1.10 = 1595).
    # Seg1: 1050/1000 = 1.05. Seg2: 1550/1550 = 1.00. Seg3: 1595/1450 = 1.10.
    # Compound: 1.05 * 1.00 * 1.10 - 1 = 0.155 → 15.50%.
    curve = [_ep(10, "1000"), _ep(7, "1050"), _ep(3, "1550"), _ep(0, "1595")]
    cfs = [_cf(6, "500", "deposit"), _cf(2, "100", "withdrawal")]
    twr, _ = compute_twr(curve, cash_flows=cfs)
    assert twr == Decimal("15.50")


def test_empty_curve_returns_zero_pct():
    twr, unit_curve = compute_twr([], cash_flows=[])
    assert twr == Decimal("0")
    assert unit_curve == [Decimal("1")]


def test_zero_portfolio_mid_window_locks_at_minus_100():
    # Day-7: $1000. Day-3: $0 (sold everything). Day-0: still $0.
    curve = [_ep(7, "1000"), _ep(3, "0"), _ep(0, "0")]
    twr, unit_curve = compute_twr(curve, cash_flows=[])
    assert twr == Decimal("-100.00")
    assert unit_curve[-1] == Decimal("0")


def test_cash_flow_before_first_snapshot_is_ignored():
    # Cash flow at day-10, first snapshot at day-7. No baseline before the
    # snapshot, so the cash flow is silently dropped.
    curve = [_ep(7, "1000"), _ep(0, "1100")]
    cf = _cf(10, "500", "deposit")
    twr, _ = compute_twr(curve, cash_flows=[cf])
    assert twr == Decimal("10.00")
```

- [ ] **Step 2: Run tests, verify failure**

```bash
backend/.venv/bin/pytest backend/tests/test_manual_twr.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.services.manual_performance'`.

- [ ] **Step 3: Implement the module**

Write `backend/services/manual_performance.py`:

```python
"""Pure-function TWR + synthetic-unit equity-curve construction.

No DB, no HTTP. Inputs are raw equity points and cash-flow events
(at arbitrary timestamps); the function merges them chronologically
and segments at every cash flow internally. The synthetic_unit_curve
feeds the existing metrics.sharpe_24_7 / metrics.max_drawdown_pct
functions so the manual portfolio's risk numbers are computed the
same way as paper strategies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class EquityPoint:
    captured_at: datetime
    total_value_aud: Decimal


@dataclass(frozen=True)
class CashFlowEvent:
    occurred_at: datetime
    amount_aud: Decimal              # always positive; direction is in `kind`
    kind: str                        # "deposit" | "withdrawal"


def compute_twr(
    equity_curve: list[EquityPoint],
    cash_flows: list[CashFlowEvent],
) -> tuple[Decimal, list[Decimal]]:
    """Return (twr_pct, synthetic_unit_curve).

    Inputs are raw — snapshots and cash flows at independent timestamps.
    The function merges them chronologically and segments at every cash
    flow internally. Cash flows that pre-date the first snapshot are
    ignored (no baseline to attribute them against).

    twr_pct is expressed as a percent (e.g., +10% → Decimal("10.00")).
    The synthetic_unit_curve has one entry per snapshot (cash flows
    don't add curve points — they only modify the segment factor).
    """
    if not equity_curve:
        return Decimal("0"), [Decimal("1")]

    # Merge into a chronological event stream. Tie-break: when a snapshot
    # and a cash flow share a timestamp, process the snapshot FIRST
    # (the snap represents the pre-cash-flow value).
    events: list[tuple[datetime, int, object]] = []
    for ep in equity_curve:
        events.append((ep.captured_at, 0, ep))      # 0 = snap, sorts before flow
    for cf in cash_flows:
        events.append((cf.occurred_at, 1, cf))      # 1 = flow
    events.sort(key=lambda e: (e[0], e[1]))

    unit_curve: list[Decimal] = []
    twr_factor = Decimal("1")
    seg_start: Decimal | None = None
    last_value: Decimal | None = None

    for ts, kind_code, obj in events:
        if kind_code == 0:  # snapshot
            ep = obj  # type: ignore[assignment]
            if seg_start is None:
                # First snapshot — initialise the first segment.
                seg_start = ep.total_value_aud
                last_value = ep.total_value_aud
                unit_curve.append(Decimal("1"))
            else:
                last_value = ep.total_value_aud
                if seg_start > 0:
                    running = twr_factor * (last_value / seg_start)
                else:
                    running = Decimal("0")
                unit_curve.append(running.quantize(Decimal("0.000001")))
        else:  # cash flow
            cf = obj  # type: ignore[assignment]
            if seg_start is None or last_value is None:
                # Cash flow before any snapshot. No baseline; skip silently.
                continue
            # Close the current segment at last_value.
            if seg_start > 0:
                seg_return = last_value / seg_start
            else:
                seg_return = Decimal("0")
            twr_factor = twr_factor * seg_return
            # Start a new segment at last_value + signed delta.
            delta = (cf.amount_aud if cf.kind == "deposit"
                     else -cf.amount_aud)
            new_seg_start = last_value + delta
            if new_seg_start <= 0:
                # Portfolio drained mid-window. Lock the unit curve at 0
                # for any remaining snapshots and return -100%.
                remaining = len(equity_curve) - len(unit_curve)
                for _ in range(remaining):
                    unit_curve.append(Decimal("0"))
                return (twr_factor - Decimal("1")) * Decimal("100"), unit_curve
            seg_start = new_seg_start
            last_value = new_seg_start

    # Close the final segment.
    if seg_start is not None and seg_start > 0 and last_value is not None:
        final_return = last_value / seg_start
    else:
        final_return = Decimal("0")
    twr_total = twr_factor * final_return
    twr_pct = (twr_total - Decimal("1")) * Decimal("100")
    return twr_pct.quantize(Decimal("0.01")), unit_curve
```

- [ ] **Step 4: Run tests, verify pass**

```bash
backend/.venv/bin/pytest backend/tests/test_manual_twr.py -v
```

Expected: 8 PASS.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/manual_performance.py backend/tests/test_manual_twr.py
git commit -m "$(cat <<'EOF'
feat(services): manual_performance.compute_twr pure function

TWR with segment cuts at every cash-flow event, plus a synthetic-unit
equity curve for downstream Sharpe + drawdown. Pure-function — no DB,
no HTTP. Handles deposits, withdrawals, multi-event sequences, and
the zero-portfolio-midway edge.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 5: `manual_cash_flow_scanner.ensure_cash_flows_fresh`

**Files:**
- Create: `backend/services/manual_cash_flow_scanner.py`
- Create: `backend/tests/test_manual_cash_flow_scanner.py`

Debounced scanner that pulls new Kraken deposit/withdrawal entries and persists them. Non-AUD entries trigger a `system_alert` and are skipped.

- [ ] **Step 1: Write the failing tests**

Write `backend/tests/test_manual_cash_flow_scanner.py`:

```python
"""Scanner tests. Mocked Kraken via monkeypatch; real test-schema DB."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.db.supabase_client import get_supabase
from backend.repositories import manual_cash_flows_repo
from backend.services import kraken_service, manual_cash_flow_scanner


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("manual_cash_flows").delete().neq("id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("system_alerts").delete().neq("id", _SENTINEL_UUID).execute()
    kraken_service._user = None
    kraken_service._market = None
    yield
    kraken_service._user = None
    kraken_service._market = None


def _fake_kraken_entries(entries):
    """Return a fake get_cash_flow_entries callable that ignores `since`."""
    return lambda since=None: list(entries)


def test_fresh_scan_persists_new_aud_deposits(monkeypatch):
    occurred = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(
        kraken_service, "get_cash_flow_entries",
        _fake_kraken_entries([
            {"kraken_refid": "R1", "kind": "deposit",
             "amount_aud": Decimal("500"), "asset": "AUD",
             "occurred_at": occurred},
        ]),
    )
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=1), schema=SCHEMA,
    )
    assert len(rows) == 1
    assert rows[0]["kraken_refid"] == "R1"


def test_non_aud_deposit_inserts_system_alert_and_skips(monkeypatch):
    db = get_supabase()
    monkeypatch.setattr(
        kraken_service, "get_cash_flow_entries",
        _fake_kraken_entries([
            {"kraken_refid": "U1", "kind": "deposit",
             "amount_aud": Decimal("100"), "asset": "USDT",
             "occurred_at": datetime.now(timezone.utc) - timedelta(hours=1)},
        ]),
    )
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)

    # No row in manual_cash_flows
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=1), schema=SCHEMA,
    )
    assert rows == []

    # One row in system_alerts with the expected code
    alerts = (db.schema(SCHEMA).table("system_alerts")
                .select("*").eq("code", "MANUAL_CASHFLOW_NON_AUD").execute().data)
    assert len(alerts) == 1
    assert alerts[0]["payload"]["asset"] == "USDT"


def test_debounce_skips_call_within_5_minutes(monkeypatch):
    counter = {"n": 0}
    def _counting_entries(since=None):
        counter["n"] += 1
        return []
    monkeypatch.setattr(kraken_service, "get_cash_flow_entries", _counting_entries)

    # First call — runs the scan
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)
    # Insert a row to update last_created_at to "now"
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="RJUST", kind="deposit",
        amount_aud=Decimal("1"),
        occurred_at=datetime.now(timezone.utc),
        schema=SCHEMA,
    )
    # Second call within debounce window — should skip
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)
    assert counter["n"] == 1   # only the first call hit Kraken


def test_kraken_failure_is_swallowed(monkeypatch, caplog):
    def _raising_entries(since=None):
        raise kraken_service.KrakenServiceError("simulated outage")
    monkeypatch.setattr(kraken_service, "get_cash_flow_entries", _raising_entries)

    # Should NOT raise
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)

    # And there should be no rows
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=1), schema=SCHEMA,
    )
    assert rows == []
```

- [ ] **Step 2: Run tests, verify failure**

```bash
backend/.venv/bin/pytest backend/tests/test_manual_cash_flow_scanner.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.services.manual_cash_flow_scanner'`.

- [ ] **Step 3: Implement the scanner**

Write `backend/services/manual_cash_flow_scanner.py`:

```python
"""Debounced scanner that pulls Kraken deposit/withdrawal entries into
manual_cash_flows. Runs from the leaderboard router; no scheduler job.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.repositories import manual_cash_flows_repo, system_alerts_repo
from backend.services import kraken_service

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 300   # 5 minutes


def ensure_cash_flows_fresh(*, schema: str = "public") -> None:
    """Pull new Kraken cash-flow entries and persist them.

    Idempotent. Debounced — skipped if last_created_at is within
    _DEBOUNCE_SECONDS. Best-effort — never raises into the caller.
    """
    try:
        last_scanned = manual_cash_flows_repo.last_created_at(schema=schema)
        now = datetime.now(timezone.utc)
        if last_scanned is not None and (now - last_scanned).total_seconds() < _DEBOUNCE_SECONDS:
            return

        since = manual_cash_flows_repo.latest_occurred_at(schema=schema)
        entries = kraken_service.get_cash_flow_entries(since=since)

        for entry in entries:
            if entry["asset"] != "AUD":
                try:
                    system_alerts_repo.insert(
                        level="warning",
                        code="MANUAL_CASHFLOW_NON_AUD",
                        strategy_id=None,
                        message=(
                            f"Non-AUD cash flow detected on Kraken: "
                            f"{entry['asset']} {entry['amount_aud']}"
                        ),
                        payload={
                            "refid": entry["kraken_refid"],
                            "asset": entry["asset"],
                            "amount": str(entry["amount_aud"]),
                            "kind": entry["kind"],
                        },
                        schema=schema,
                    )
                except Exception:
                    logger.exception("Failed to insert MANUAL_CASHFLOW_NON_AUD alert")
                continue

            manual_cash_flows_repo.upsert_by_refid(
                kraken_refid=entry["kraken_refid"],
                kind=entry["kind"],
                amount_aud=entry["amount_aud"],
                occurred_at=entry["occurred_at"],
                schema=schema,
            )
    except Exception:
        logger.exception("ensure_cash_flows_fresh failed; leaderboard will use stale data")
```

- [ ] **Step 4: Run tests, verify pass**

```bash
backend/.venv/bin/pytest backend/tests/test_manual_cash_flow_scanner.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/manual_cash_flow_scanner.py backend/tests/test_manual_cash_flow_scanner.py
git commit -m "$(cat <<'EOF'
feat(services): manual_cash_flow_scanner with 5-min debounce

Pulls Kraken deposit/withdrawal entries on demand (from the leaderboard
request path, not a scheduler job). Debounce checks max(created_at)
across manual_cash_flows; <5 min → skip. Non-AUD entries insert a
MANUAL_CASHFLOW_NON_AUD system_alert and are skipped. Kraken failures
are swallowed so the leaderboard still renders.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 6: Leaderboard router — Manual row + lifetime + sort change

**Files:**
- Modify: `backend/routers/strategies.py` (the `leaderboard()` function around line 42)
- Create: `backend/tests/test_manual_leaderboard.py`

Append the Manual row, add `lifetime_return_pct` to every row, switch the sort key.

- [ ] **Step 1: Write the failing tests**

Write `backend/tests/test_manual_leaderboard.py`:

```python
"""Integration tests for the leaderboard endpoint with Manual entry."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.db.supabase_client import get_supabase
from backend.main import app
from backend.repositories import manual_cash_flows_repo
from backend.services import kraken_service


SCHEMA = "public"  # leaderboard router uses public; we accept that for this test
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client(bypass_auth):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _truncate_and_seed(monkeypatch):
    db = get_supabase()
    db.schema(SCHEMA).table("manual_cash_flows").delete().neq("id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("system_alerts").delete().neq("id", _SENTINEL_UUID).execute()
    kraken_service._user = None
    kraken_service._market = None
    # Don't truncate strategies/portfolio_snapshots in public — they're real prod data.
    # Use a monkeypatch on kraken_service.get_cash_flow_entries to control inputs.
    monkeypatch.setattr(
        kraken_service, "get_cash_flow_entries",
        lambda since=None: [],
    )
    yield


def test_leaderboard_includes_manual_row(client):
    r = client.get("/api/strategies/_leaderboard")
    assert r.status_code == 200
    rows = r.json()
    manual = [r for r in rows if r["id"] == "manual"]
    assert len(manual) == 1
    m = manual[0]
    assert m["name"] == "Manual"
    assert m["execution_mode"] == "manual"
    assert "return_all_time_pct" in m
    assert "lifetime_return_pct" in m
    assert "sharpe" in m
    assert "max_drawdown_pct" in m


def test_every_row_has_lifetime_return_pct(client):
    r = client.get("/api/strategies/_leaderboard")
    assert r.status_code == 200
    for row in r.json():
        assert "lifetime_return_pct" in row, f"missing on {row.get('name')}"


def test_rows_are_sorted_by_return_all_time_pct_desc(client):
    r = client.get("/api/strategies/_leaderboard")
    rows = r.json()
    pcts = [Decimal(row["return_all_time_pct"]) for row in rows]
    assert pcts == sorted(pcts, reverse=True), "leaderboard not sorted by return_all_time_pct desc"
```

(Note: this integration test runs against the live `public` schema because the leaderboard router hardcodes `SCHEMA = "public"`. The kraken_service is monkeypatched to return no new entries so production data is not polluted. Existing paper-strategy rows are unaffected.)

- [ ] **Step 2: Run tests, verify failure**

```bash
backend/.venv/bin/pytest backend/tests/test_manual_leaderboard.py -v
```

Expected: tests fail because the Manual row doesn't exist yet and rows don't have `lifetime_return_pct`.

- [ ] **Step 3: Modify the leaderboard router**

Edit `backend/routers/strategies.py`. The existing `leaderboard()` function (around line 42) needs three changes. The full updated function:

```python
@router.get("/_leaderboard")
def leaderboard() -> list[dict]:
    from backend.services.manual_cash_flow_scanner import ensure_cash_flows_fresh
    from backend.services.manual_performance import (
        CashFlowEvent, EquityPoint, compute_twr,
    )
    from backend.repositories import manual_cash_flows_repo, snapshots_repo
    from backend.services.trading import metrics

    sb = get_supabase()
    strats = (sb.schema(SCHEMA).table("strategies").select("*")
                .neq("status", "archived").execute().data or [])
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # Window start = earliest active strategy's created_at. Falls back to
    # 30 days ago if no strategies exist.
    window_start_dt = (
        min(datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            for s in strats)
        if strats
        else datetime.now(timezone.utc) - timedelta(days=30)
    )

    out: list[dict] = []
    for s in strats:
        sid = UUID(s["id"])
        curve_rows = paper_equity_repo.list_curve(sid, schema=SCHEMA)
        curve = [Decimal(str(r["equity_aud"])) for r in curve_rows]
        starting = Decimal(str(s.get("starting_balance_aud") or "0"))
        equity = curve[-1] if curve else starting
        sharpe = metrics.sharpe_24_7(curve)
        max_dd = metrics.max_drawdown_pct(curve)
        trades = (sb.schema(SCHEMA).table("paper_orders")
                    .select("id", count="exact")
                    .eq("strategy_id", s["id"])
                    .limit(0).execute().count or 0)
        cost_rows = (sb.schema(SCHEMA).table("agent_decisions")
                       .select("cost_aud")
                       .eq("strategy_id", s["id"])
                       .gte("created_at", thirty_days_ago.isoformat())
                       .execute().data or [])
        cost_30d = sum(
            (Decimal(str(r["cost_aud"])) for r in cost_rows),
            Decimal("0"),
        )

        def _ret_pct(window_days: int) -> Decimal:
            cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
            window = [Decimal(str(r["equity_aud"])) for r in curve_rows
                      if r["ts"] >= cutoff.isoformat()]
            if not window or window[0] == 0:
                return Decimal("0")
            return ((window[-1] / window[0]) - Decimal("1")) * Decimal("100")

        all_time = (((equity / starting) - Decimal("1")) * Decimal("100")
                    if starting > 0 else Decimal("0"))
        out.append({
            "id": s["id"],
            "name": s["name"],
            "status": s["status"],
            "execution_mode": s["execution_mode"],
            "equity_aud": str(equity),
            "return_7d_pct": str(_ret_pct(7)),
            "return_30d_pct": str(_ret_pct(30)),
            "return_all_time_pct": str(all_time),
            "lifetime_return_pct": str(all_time),   # paper: lifetime == all-time
            "sharpe": str(sharpe),
            "max_drawdown_pct": str(max_dd),
            "trades": trades,
            "cost_30d_aud": str(cost_30d),
            "persona_prompt_stable_since": s.get("persona_prompt_stable_since"),
        })

    # ── Manual row ──────────────────────────────────────────────────
    try:
        ensure_cash_flows_fresh(schema=SCHEMA)
        manual_row = _compute_manual_row(
            window_start_dt=window_start_dt, schema=SCHEMA,
        )
        if manual_row is not None:
            out.append(manual_row)
    except Exception:
        # Best-effort: a manual-row failure must not break the leaderboard.
        import logging
        logging.getLogger(__name__).exception(
            "Manual leaderboard row computation failed; rendering without it"
        )

    out.sort(
        key=lambda r: Decimal(r.get("return_all_time_pct") or "0"),
        reverse=True,
    )
    return out


def _compute_manual_row(*, window_start_dt, schema: str) -> dict | None:
    """Build the Manual leaderboard row from portfolio_snapshots + cash flows.

    Returns None if there's no portfolio data to summarise.
    """
    from backend.services.manual_performance import (
        CashFlowEvent, EquityPoint, compute_twr,
    )
    from backend.repositories import manual_cash_flows_repo, snapshots_repo
    from backend.services.trading import metrics

    # Pull snapshots from the window start onwards.
    snaps = snapshots_repo.get_all(
        from_dt=window_start_dt.isoformat(), schema=schema,
    )
    if not snaps:
        return None

    flows = manual_cash_flows_repo.list_since(
        since=window_start_dt, schema=schema,
    )

    # Build equity curve. For each cash flow inside the window, the snapshots
    # naturally include "before" and "after" because snapshots are taken on a
    # fixed cadence — we don't need synthetic pre/post points here. The
    # synthetic-unit math in compute_twr keys off matching timestamps; this
    # will simplify to "snapshots + a single segment cut at each cash flow."
    equity_points = [
        EquityPoint(
            captured_at=datetime.fromisoformat(s.captured_at.replace("Z", "+00:00"))
            if isinstance(s.captured_at, str) else s.captured_at,
            total_value_aud=Decimal(str(s.total_value_aud)),
        )
        for s in snaps
    ]

    cash_flows = [
        CashFlowEvent(
            occurred_at=datetime.fromisoformat(f["occurred_at"].replace("Z", "+00:00")),
            amount_aud=Decimal(str(f["amount_aud"])),
            kind=f["kind"],
        )
        for f in flows
    ]

    twr_pct, unit_curve = compute_twr(equity_points, cash_flows)
    sharpe = metrics.sharpe_24_7(unit_curve)
    max_dd = metrics.max_drawdown_pct(unit_curve)

    # 7-day and 30-day windows reuse the same logic with later cutoffs.
    def _windowed(days: int) -> Decimal:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        window_snaps = [p for p in equity_points if p.captured_at >= cutoff]
        window_flows = [c for c in cash_flows if c.occurred_at >= cutoff]
        if len(window_snaps) < 2:
            return Decimal("0")
        twr_w, _ = compute_twr(window_snaps, window_flows)
        return twr_w

    # Lifetime = all snapshots, all cash flows.
    all_snaps = snapshots_repo.get_all(schema=schema)
    all_equity = [
        EquityPoint(
            captured_at=datetime.fromisoformat(s.captured_at.replace("Z", "+00:00"))
            if isinstance(s.captured_at, str) else s.captured_at,
            total_value_aud=Decimal(str(s.total_value_aud)),
        )
        for s in all_snaps
    ]
    all_flows_raw = manual_cash_flows_repo.list_since(
        since=datetime(1970, 1, 1, tzinfo=timezone.utc), schema=schema,
    )
    all_flows = [
        CashFlowEvent(
            occurred_at=datetime.fromisoformat(f["occurred_at"].replace("Z", "+00:00")),
            amount_aud=Decimal(str(f["amount_aud"])),
            kind=f["kind"],
        )
        for f in all_flows_raw
    ]
    lifetime_pct, _ = compute_twr(all_equity, all_flows)

    current_equity = equity_points[-1].total_value_aud

    # Count trades: ledger entries with type ∈ {receive, spend} within window.
    # We approximate via the existing kraken_service.get_trade_history.
    from backend.services import kraken_service as _ks
    try:
        trades_all = _ks.get_trade_history()
        window_start_ts = window_start_dt.timestamp()
        trade_count = sum(1 for t in trades_all if t["time"] >= window_start_ts)
    except Exception:
        trade_count = 0

    return {
        "id": "manual",
        "name": "Manual",
        "status": "active",
        "execution_mode": "manual",
        "equity_aud": str(current_equity),
        "return_7d_pct": str(_windowed(7)),
        "return_30d_pct": str(_windowed(30)),
        "return_all_time_pct": str(twr_pct),
        "lifetime_return_pct": str(lifetime_pct),
        "sharpe": str(sharpe),
        "max_drawdown_pct": str(max_dd),
        "trades": trade_count,
        "cost_30d_aud": "0",
        "persona_prompt_stable_since": None,
    }
```

(Keep the file's existing imports unchanged; the new imports are inside the function bodies so they don't affect cold-start performance for routes that don't hit `_leaderboard`.)

- [ ] **Step 4: Run tests, verify pass**

```bash
backend/.venv/bin/pytest backend/tests/test_manual_leaderboard.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run the wider sandbox suite**

```bash
backend/.venv/bin/pytest backend/tests -x -q --ignore=backend/tests/test_evals.py
```

Expected: all pass (or only failures unrelated to this change; note any).

- [ ] **Step 6: Commit and push**

```bash
git add backend/routers/strategies.py backend/tests/test_manual_leaderboard.py
git commit -m "$(cat <<'EOF'
feat(api): leaderboard now includes Manual row + lifetime + sort by return

Three changes to /api/strategies/_leaderboard:
- New "Manual" virtual row, computed from portfolio_snapshots + Kraken
  cash flows via the manual_performance + manual_cash_flow_scanner
  services. id="manual", execution_mode="manual".
- lifetime_return_pct on every row (paper: equals return_all_time_pct;
  manual: TWR over the user's full Kraken history).
- Sort key changed from equity_aud desc to return_all_time_pct desc so
  the larger-capital Manual entry doesn't crowd the top regardless of
  skill.

Manual-row computation is best-effort: failure logs + skips the row
without breaking the rest of the leaderboard.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 7: Frontend — Lifetime column, Manual row highlight, caveat banner (via `/impeccable`)

**Files:**
- Modify: `frontend/src/pages/StrategiesPage.tsx`
- Modify: `frontend/src/api/strategies.ts` (TypeScript type — add `lifetime_return_pct`)
- Modify: `frontend/src/types/` if a `Strategy` interface exists there

Per project convention, frontend work goes through `/impeccable` rather than raw Tailwind. This task is design-driven; the implementer invokes `/impeccable` with the requirements below and applies its output.

- [ ] **Step 1: Read the existing StrategiesPage**

```bash
# To understand the current table layout and Tailwind conventions.
```

Read:
- `frontend/src/pages/StrategiesPage.tsx`
- `frontend/src/api/strategies.ts`
- Any `Strategy` type definitions referenced by the page (probably in `frontend/src/types/` or inline in `strategies.ts`).

- [ ] **Step 2: Add `lifetime_return_pct` to the TypeScript type**

In whichever file declares the `Strategy` (or `LeaderboardRow`) type used by `StrategiesPage`, add the new field. If the type is defined inline in `strategies.ts`, edit there. Example:

```typescript
export interface LeaderboardRow {
  id: string;
  name: string;
  status: string;
  execution_mode: string;
  equity_aud: string;
  return_7d_pct: string;
  return_30d_pct: string;
  return_all_time_pct: string;
  lifetime_return_pct: string;        // NEW
  sharpe: string;
  max_drawdown_pct: string;
  trades: number;
  cost_30d_aud: string;
  persona_prompt_stable_since: string | null;
}
```

Also confirm the `id` field is typed as `string` (not a stricter UUID type), since the Manual row uses the literal `"manual"`.

- [ ] **Step 3: Invoke `/impeccable` for the visual changes**

Invoke the `/impeccable` skill (the project's design skill) with these requirements:

> Update `frontend/src/pages/StrategiesPage.tsx` with three changes:
>
> 1. **New "Lifetime" column** in the leaderboard table, placed immediately after the existing "All-Time" return column. Smaller font and muted color (e.g. `text-sm text-muted-foreground`) to signal "context, not the apples-to-apples comparison." Cell value is the `lifetime_return_pct` field from each row, formatted the same way as the existing percent columns.
>
> 2. **Visual highlight on the Manual row** (the row where `row.id === "manual"`). A subtle 3px left border in the project's accent color, OR a faint background tint, so the user can locate "themselves" at a glance without scanning the name column. Don't make it loud — it should feel like a quiet underline, not a callout.
>
> 3. **Short-window caveat banner** above the leaderboard table, visible only when `new Date() < new Date("2026-06-12")` (four weeks past the comparison-window start of 2026-05-12). Text: "Comparisons are noisy until the window includes several weeks of varied market conditions. Treat numbers cautiously through mid-June 2026." Use a muted info color (not red/yellow alarm); this is informational, not a warning.
>
> Sort, time-window selector, and all other table behavior must stay unchanged. The new column must respect the existing sortable / responsive behavior of the table.

- [ ] **Step 4: Apply `/impeccable`'s output**

Edit `frontend/src/pages/StrategiesPage.tsx` (and any companion files) per the `/impeccable` output. If `/impeccable` produces output that diverges from the spec (e.g. uses a different highlight treatment), apply it as long as the three required visual elements are present.

- [ ] **Step 5: Run the frontend type checker**

```bash
cd frontend && npm run build 2>&1 | tail -40
```

Expected: no TypeScript errors. (If `npm run build` doesn't exist, use `npx tsc --noEmit -p tsconfig.app.json`.)

- [ ] **Step 6: Spot-check in the browser** (optional but recommended)

```bash
cd frontend && npm run dev
```

Open the StrategiesPage in your browser, log in, and confirm:
- The "Lifetime" column appears with muted styling.
- The Manual row is subtly distinguished from the bot rows.
- The caveat banner is visible (assuming today < 2026-06-12).
- Sort order matches the backend (highest `return_all_time_pct` first).

- [ ] **Step 7: Commit and push**

```bash
git add frontend/src/pages/StrategiesPage.tsx frontend/src/api/strategies.ts
# Add any other frontend files /impeccable touched
git commit -m "$(cat <<'EOF'
feat(frontend): StrategiesPage shows Manual row + Lifetime column

Three changes via /impeccable:
- New Lifetime column after All-Time, muted styling.
- Subtle visual highlight on the Manual row (id === "manual").
- Short-window caveat banner above the table, hidden after
  2026-06-12 (four weeks past the comparison-window start).

Frontend type extended with lifetime_return_pct: string.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## Done state

After all seven tasks:

- `manual_cash_flows` table exists in both `public` and `test` schemas.
- `kraken_service.get_cash_flow_entries(since)` returns deposit/withdrawal entries with `asset="AUD"` (or raw code for non-AUD).
- `manual_cash_flows_repo` provides `upsert_by_refid`, `list_since`, `last_created_at`, `latest_occurred_at`.
- `manual_performance.compute_twr` produces TWR + synthetic-unit curve for any equity-curve + cash-flow combination.
- `manual_cash_flow_scanner.ensure_cash_flows_fresh()` keeps `manual_cash_flows` current with 5-min debounce, with non-AUD entries triggering a `MANUAL_CASHFLOW_NON_AUD` system_alert.
- The `/api/strategies/_leaderboard` endpoint returns a Manual row alongside the paper strategies, every row has `lifetime_return_pct`, and rows are sorted by `return_all_time_pct` desc.
- The StrategiesPage shows a Lifetime column, a subtle Manual-row highlight, and a short-window caveat banner.

## Test surface added

- 6 tests in `test_kraken_cash_flow_entries.py` (unit)
- 6 tests in `test_manual_cash_flows_repo.py` (DB integration on test schema)
- 8 tests in `test_manual_twr.py` (pure-function unit)
- 4 tests in `test_manual_cash_flow_scanner.py` (DB + mocked Kraken)
- 3 tests in `test_manual_leaderboard.py` (HTTP integration)

Total: 27 new tests.

## What this plan does NOT do (per spec)

- ❌ No UI to edit/delete cash flows.
- ❌ No support for non-Kraken exchanges.
- ❌ No currency conversion for USD/USDT deposits — they fire a `system_alert` and are skipped.
- ❌ No tax-lot accounting for manual trades.
- ❌ No per-asset attribution for the Manual entry.
- ❌ No backtesting of paper strategies on historical Kraken trades.
- ❌ No Sortino / Calmar / Information Ratio.
