# Phone Push Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fire one phone push notification (ntfy.sh) per strategy buy/sell decision, gated by a per-strategy `notify_enabled` flag (default false), idempotent via a `notified_at` column on `agent_decisions`.

**Architecture:** A new `backend/services/notifications/` package exposes `maybe_notify(...)` and is called from `backend/services/trading/decision_writer.py:write_agent_decision` after the row is inserted. The notification path is best-effort: failures log a `system_alert` and never raise into the trading loop.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `httpx==0.28.1` (already in deps), `respx==0.23.1` for HTTP mocking in tests (already in deps), Supabase Postgres, ntfy.sh public broker.

**Spec:** `docs/superpowers/specs/2026-05-19-push-notifications-design.md`

---

## File map

| Path | Action | Responsibility |
|---|---|---|
| `supabase/migrations/007_push_notifications.sql` | NEW | Add `notify_enabled` and `notified_at` to public schema. |
| `supabase/migrations/test_007_push_notifications.sql` | NEW | Same columns on test schema. |
| `backend/config/settings.py` | MODIFY | Add `ntfy_topic`, `ntfy_url_base`, `frontend_url`. |
| `backend/models/trading.py` | MODIFY | Add `notify_enabled: bool = False` to `StrategyRow`. |
| `backend/services/notifications/__init__.py` | NEW | Package init; re-export `maybe_notify`. |
| `backend/services/notifications/payload.py` | NEW | Pure-function notification body rendering. |
| `backend/services/notifications/service.py` | NEW | `maybe_notify`, ntfy POST + retry + system_alert on failure. |
| `backend/repositories/agent_decisions_repo.py` | MODIFY | Add `mark_notified(decision_id, schema)`. |
| `backend/services/trading/decision_writer.py` | MODIFY | Call `notifications.maybe_notify(...)` after insert. |
| `backend/tests/test_notification_payload.py` | NEW | Unit tests for payload rendering. |
| `backend/tests/test_notification_service.py` | NEW | Unit + service tests with `respx`. |
| `backend/tests/test_trading_decision_writer.py` | MODIFY | Integration: writer fans out to notify when enabled. |
| `README.md` | MODIFY | Add phone-app setup section. |

---

## Conventions used throughout

- All commit messages use Conventional Commits + the standing co-author trailer.
- Every task ends with `git push origin main` (per the user's standing instruction).
- Tests are added BEFORE implementation (TDD).
- Tests that hit the live Supabase test schema reuse the existing `_truncate_paper_tables` pattern from `backend/tests/test_trading_decision_writer.py`.

---

### Task 1: Apply database migration

**Files:**
- Create: `supabase/migrations/007_push_notifications.sql`
- Create: `supabase/migrations/test_007_push_notifications.sql`

- [ ] **Step 1: Create the public-schema migration**

Write `supabase/migrations/007_push_notifications.sql`:

```sql
-- Phone push notifications: per-strategy opt-in flag and per-decision
-- idempotency timestamp.
ALTER TABLE public.strategies
  ADD COLUMN IF NOT EXISTS notify_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE public.agent_decisions
  ADD COLUMN IF NOT EXISTS notified_at timestamptz NULL;
```

(No new index. The idempotency UPDATE in Task 5 filters by `id` first — the existing PK index handles it.)

- [ ] **Step 2: Create the test-schema migration**

Write `supabase/migrations/test_007_push_notifications.sql`:

```sql
-- Mirror of 007_push_notifications.sql for the `test` schema.
-- `test.strategies` and `test.agent_decisions` were created with
-- CREATE TABLE ... (LIKE public.<x> INCLUDING ALL) in earlier migrations,
-- which does NOT auto-propagate later ALTERs. Apply the same changes.
ALTER TABLE test.strategies
  ADD COLUMN IF NOT EXISTS notify_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE test.agent_decisions
  ADD COLUMN IF NOT EXISTS notified_at timestamptz NULL;
```

- [ ] **Step 3: Apply the migrations**

Both files need to be run against your Supabase project. The simplest path is the Supabase dashboard SQL editor:

1. Open the SQL editor for the project.
2. Paste the contents of `007_push_notifications.sql`, run.
3. Paste the contents of `test_007_push_notifications.sql`, run.

(If you have the `supabase` CLI configured locally with `db push` set up, use that instead — the project's existing migrations were applied via the dashboard historically, so the CLI path is optional.)

- [ ] **Step 4: Verify the columns exist**

Run in the SQL editor:

```sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_schema IN ('public', 'test')
  AND table_name IN ('strategies', 'agent_decisions')
  AND column_name IN ('notify_enabled', 'notified_at')
ORDER BY table_schema, table_name, column_name;
```

Expected output: four rows. `notify_enabled` (boolean, default `false`) on both `public.strategies` and `test.strategies`. `notified_at` (timestamp with time zone, no default) on both `public.agent_decisions` and `test.agent_decisions`.

- [ ] **Step 5: Commit and push**

```bash
git add supabase/migrations/007_push_notifications.sql supabase/migrations/test_007_push_notifications.sql
git commit -m "$(cat <<'EOF'
feat(db): add notify_enabled + notified_at columns for push notifications

Two ALTER migrations adding the per-strategy opt-in flag and per-decision
idempotency timestamp described in the push-notifications spec. Partial
index on notified_at IS NULL keeps retry lookups cheap.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 2: Extend `StrategyRow` with `notify_enabled`

**Files:**
- Modify: `backend/models/trading.py` (StrategyRow class around line 179)
- Test: extension of an existing test file — see Step 1 below

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_trading_decision_writer.py`:

```python
def test_strategy_row_loads_notify_enabled_default_false():
    from backend.repositories import strategies_repo
    sid = _seed_dca_strategy()
    strat = strategies_repo.get(sid, schema=SCHEMA)
    assert strat.notify_enabled is False


def test_strategy_row_loads_notify_enabled_when_true():
    from backend.repositories import strategies_repo
    sid = _seed_dca_strategy()
    db = get_supabase()
    db.schema(SCHEMA).table("strategies").update(
        {"notify_enabled": True}
    ).eq("id", sid).execute()
    strat = strategies_repo.get(sid, schema=SCHEMA)
    assert strat.notify_enabled is True
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py::test_strategy_row_loads_notify_enabled_default_false backend/tests/test_trading_decision_writer.py::test_strategy_row_loads_notify_enabled_when_true -v
```

Expected: FAIL with `AttributeError: 'StrategyRow' object has no attribute 'notify_enabled'` (or pydantic validation error).

- [ ] **Step 3: Add the field to `StrategyRow`**

In `backend/models/trading.py`, find the `StrategyRow` class (around line 179). Add `notify_enabled: bool = False` between `dry_run` and `persona_prompt_stable_since`:

```python
class StrategyRow(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    execution_mode: Literal["llm_agent", "deterministic"]
    persona_key: str | None = None
    deterministic_config: DeterministicConfig | None = None
    starting_balance_aud: Decimal = Decimal("1000")
    trigger_config: dict = {}
    risk_caps: RiskCaps = RiskCaps()
    kill_criteria: KillCriteria = KillCriteria()
    model_preference: str | None = None
    status: Literal["active", "paused", "archived"] = "active"
    dry_run: bool = False
    notify_enabled: bool = False
    persona_prompt_stable_since: datetime | None = None
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py::test_strategy_row_loads_notify_enabled_default_false backend/tests/test_trading_decision_writer.py::test_strategy_row_loads_notify_enabled_when_true -v
```

Expected: PASS, both tests.

- [ ] **Step 5: Run the whole `test_trading_decision_writer.py` to confirm no regression**

```bash
backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py -v
```

Expected: all tests pass (including the existing two).

- [ ] **Step 6: Commit and push**

```bash
git add backend/models/trading.py backend/tests/test_trading_decision_writer.py
git commit -m "$(cat <<'EOF'
feat(models): add StrategyRow.notify_enabled, default false

Lets the notification layer (next commits) read the per-strategy
opt-in flag without an extra table.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 3: Add settings entries

**Files:**
- Modify: `backend/config/settings.py`

- [ ] **Step 1: Add the three fields to `Settings`**

In `backend/config/settings.py`, add three fields to the `Settings` class with safe defaults. The full updated class:

```python
from pathlib import Path
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    kraken_api_key: str
    kraken_api_secret: str
    supabase_url: str
    supabase_key: str
    supabase_db_url: str = ""
    anthropic_api_key: str = ""
    app_password_hash: str
    jwt_secret: str
    kraken_live_tests: bool = False
    up_pat: str
    ntfy_topic: str = ""
    ntfy_url_base: str = "https://ntfy.sh"
    frontend_url: str = ""

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


settings = Settings()
```

Defaults make the feature dormant when not configured: `ntfy_topic == ""` → notifications skipped silently, `frontend_url == ""` → no click-through link in the body.

- [ ] **Step 2: Verify settings load without error**

```bash
backend/.venv/bin/python -c "from backend.config import settings; print('ntfy_url_base len:', len(settings.ntfy_url_base))"
```

Expected: prints `ntfy_url_base len: 14` (the length of `https://ntfy.sh`). Do **not** print the topic or full settings object — keep secrets out of stdout per project convention.

- [ ] **Step 3: Commit and push**

```bash
git add backend/config/settings.py
git commit -m "$(cat <<'EOF'
feat(config): add ntfy_topic, ntfy_url_base, frontend_url

All three default to empty/public-broker so the notification layer
ships dormant until NTFY_TOPIC is set on Railway.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 4: Notification payload renderer (pure functions)

**Files:**
- Create: `backend/services/notifications/__init__.py`
- Create: `backend/services/notifications/payload.py`
- Test: `backend/tests/test_notification_payload.py`

This task implements the rendering of title + body from a normalized payload. Pure functions, no DB, no HTTP. Reasoning context is locked in here so the service layer (Task 6) can stay thin.

- [ ] **Step 1: Create the package init (empty for now)**

Write `backend/services/notifications/__init__.py`:

```python
"""Push-notification fan-out from the trading-decision write path."""
__all__: list[str] = []
```

Task 6 will replace this with the `maybe_notify` re-export once `service.py` exists. Keeping it empty now means tests in this task can import `backend.services.notifications.payload` without dragging in (yet-nonexistent) `service.py`.

- [ ] **Step 2: Write failing tests for the renderer**

Write `backend/tests/test_notification_payload.py`:

```python
"""Tests for the pure rendering layer of the notification service.

These cover every body-content branch from the spec table without
touching the DB or the network.
"""
from decimal import Decimal

from backend.services.notifications.payload import (
    NotificationLeg, NotificationContext, render_payload,
)


def _leg(side: str = "buy", pair: str = "ETH/AUD",
         notional: str = "100", mid: str | None = "3450",
         alloc_before: str = "18", alloc_after: str = "23") -> NotificationLeg:
    return NotificationLeg(
        side=side, pair=pair,
        notional_aud=Decimal(notional),
        mid=(Decimal(mid) if mid is not None else None),
        allocation_after_pct=Decimal(alloc_after),
        allocation_before_pct=Decimal(alloc_before),
    )


def _ctx(strategy_name: str = "Trend-Follower",
         execution_mode: str = "llm_agent",
         confidence: str | None = "medium",
         strategy_id: str = "00000000-0000-0000-0000-000000000abc",
         frontend_url: str = "https://app.example.com") -> NotificationContext:
    return NotificationContext(
        strategy_name=strategy_name,
        execution_mode=execution_mode,
        strategy_id=strategy_id,
        confidence=confidence,
        frontend_url=frontend_url,
    )


def test_single_leg_buy_with_full_context():
    out = render_payload([_leg()], _ctx())
    assert out["title"] == "BUY ETH/AUD — Trend-Follower"
    assert "100 AUD @ ~$3450 (mid)" in out["message"]
    assert "ETH allocation after: 23% (was 18%)" in out["message"]
    assert "Confidence: medium" in out["message"]
    assert out["click"] == "https://app.example.com/strategies/00000000-0000-0000-0000-000000000abc"
    assert "buy" in out["tags"] and "eth_aud" in out["tags"]


def test_single_leg_sell_renders_sell_title():
    out = render_payload([_leg(side="sell")], _ctx())
    assert out["title"].startswith("SELL ETH/AUD")
    assert "sell" in out["tags"]


def test_single_leg_missing_mid_omits_price_line():
    out = render_payload([_leg(mid=None)], _ctx())
    assert "@" not in out["message"]
    assert "100 AUD" in out["message"]


def test_single_leg_missing_confidence_renders_em_dash():
    out = render_payload([_leg()], _ctx(confidence=None))
    assert "Confidence: —" in out["message"]


def test_deterministic_strategy_omits_confidence_line():
    ctx = _ctx(execution_mode="deterministic", confidence=None,
               strategy_name="DCA-Baseline")
    out = render_payload([_leg()], ctx)
    assert "Confidence" not in out["message"]


def test_multi_leg_uses_rebalance_title_and_lists_legs():
    # DCA rebalance: four BUY legs. AUD is the cash side, not a tradable pair.
    legs = [_leg(pair="ETH/AUD", notional="500"),
            _leg(pair="SOL/AUD", notional="250", mid="140"),
            _leg(pair="LINK/AUD", notional="150", mid="22"),
            _leg(pair="ADA/AUD", notional="100", mid="0.45")]
    ctx = _ctx(strategy_name="DCA-Baseline", execution_mode="deterministic",
               confidence=None)
    out = render_payload(legs, ctx)
    assert out["title"] == "DCA-Baseline — 4 orders"
    assert out["message"].count("BUY") == 4
    # Compact form: base asset only, not the full pair.
    assert "BUY ETH" in out["message"]
    assert "BUY ADA" in out["message"]
    assert "Source: DCA-Baseline (deterministic)" in out["message"]
    assert "rebalance" in out["tags"]


def test_multi_leg_over_cap_truncates_to_four_and_appends_more():
    legs = [_leg(pair=f"PAIR{i}/AUD") for i in range(7)]
    out = render_payload(legs, _ctx(strategy_name="Many", execution_mode="deterministic"))
    assert out["title"] == "Many — 7 orders"
    assert "… +3 more" in out["message"]
    visible_buy_lines = [
        ln for ln in out["message"].splitlines() if ln.startswith("BUY")
    ]
    assert len(visible_buy_lines) == 4


def test_empty_legs_returns_none():
    assert render_payload([], _ctx()) is None


def test_click_omitted_when_frontend_url_blank():
    out = render_payload([_leg()], _ctx(frontend_url=""))
    assert out["click"] == ""
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
backend/.venv/bin/pytest backend/tests/test_notification_payload.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.notifications.payload'`.

- [ ] **Step 4: Implement the renderer**

Write `backend/services/notifications/payload.py`:

```python
"""Pure-function rendering of ntfy notification payloads.

No DB, no HTTP. Inputs are normalised dataclasses; output is a dict
matching ntfy's JSON-publish schema (https://ntfy.sh/docs/publish/).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Side = Literal["buy", "sell"]
MAX_VISIBLE_LEGS = 4


@dataclass(frozen=True)
class NotificationLeg:
    side: Side
    pair: str                       # e.g. "ETH/AUD"
    notional_aud: Decimal
    mid: Decimal | None             # None if book unavailable / stale
    allocation_before_pct: Decimal  # 0-100
    allocation_after_pct: Decimal   # 0-100


@dataclass(frozen=True)
class NotificationContext:
    strategy_name: str
    execution_mode: str             # "llm_agent" | "deterministic"
    strategy_id: str
    confidence: str | None          # "high" | "medium" | "low" | None
    frontend_url: str               # "" → no click URL


def _format_mid(leg: NotificationLeg) -> str:
    if leg.mid is None:
        return ""
    # 4 sig figs is enough — phone screen is small.
    return f" @ ~${leg.mid:.0f} (mid)" if leg.mid >= 100 else f" @ ~${leg.mid:.2f} (mid)"


def _pair_tag(pair: str) -> str:
    return pair.lower().replace("/", "_")


def _format_single_leg(leg: NotificationLeg, ctx: NotificationContext) -> dict:
    base_asset = leg.pair.split("/")[0]
    lines: list[str] = [
        f"{leg.notional_aud:.0f} AUD{_format_mid(leg)}",
        f"{base_asset} allocation after: "
        f"{leg.allocation_after_pct:.0f}% (was {leg.allocation_before_pct:.0f}%)",
    ]
    if ctx.execution_mode == "llm_agent":
        lines.append(f"Confidence: {ctx.confidence or '—'}")
    return {
        "title": f"{leg.side.upper()} {leg.pair} — {ctx.strategy_name}",
        "message": "\n".join(lines),
        "tags": [leg.side, _pair_tag(leg.pair)],
        "click": (
            f"{ctx.frontend_url}/strategies/{ctx.strategy_id}"
            if ctx.frontend_url else ""
        ),
    }


def _format_multi_leg(
    legs: list[NotificationLeg], ctx: NotificationContext,
) -> dict:
    visible = legs[:MAX_VISIBLE_LEGS]
    overflow = len(legs) - len(visible)
    lines: list[str] = []
    for leg in visible:
        base_asset = leg.pair.split("/")[0]
        # Compact line: SIDE ASSET   N AUD @ ~$P
        mid_part = _format_mid(leg).strip()
        lines.append(
            f"{leg.side.upper()} {base_asset:<5} "
            f"{leg.notional_aud:>4.0f} AUD"
            + (f" {mid_part}" if mid_part else "")
        )
    if overflow > 0:
        lines.append(f"… +{overflow} more")
    lines.append(f"Source: {ctx.strategy_name} ({ctx.execution_mode})")
    return {
        "title": f"{ctx.strategy_name} — {len(legs)} orders",
        "message": "\n".join(lines),
        "tags": ["rebalance"],
        "click": (
            f"{ctx.frontend_url}/strategies/{ctx.strategy_id}"
            if ctx.frontend_url else ""
        ),
    }


def render_payload(
    legs: list[NotificationLeg], ctx: NotificationContext,
) -> dict | None:
    """Return an ntfy-publish-shaped dict, or None if there are no legs.

    The caller is expected to add `topic` separately before POSTing.
    """
    if not legs:
        return None
    if len(legs) == 1:
        return _format_single_leg(legs[0], ctx)
    return _format_multi_leg(legs, ctx)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
backend/.venv/bin/pytest backend/tests/test_notification_payload.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 6: Commit and push**

```bash
git add backend/services/notifications/__init__.py backend/services/notifications/payload.py backend/tests/test_notification_payload.py
git commit -m "$(cat <<'EOF'
feat(notifications): pure-function ntfy payload renderer

Title/body/tags/click rendering for single-leg and multi-leg
decisions, including the four-leg cap with overflow indicator,
missing-mid omission, and the confidence-line conditional for
LLM vs deterministic strategies.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 5: `mark_notified` on the agent_decisions repo

**Files:**
- Modify: `backend/repositories/agent_decisions_repo.py`
- Test: append to `backend/tests/test_trading_decision_writer.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_trading_decision_writer.py`:

```python
def test_mark_notified_sets_timestamp_when_null():
    from backend.repositories import agent_decisions_repo
    sb = get_supabase()
    sid = _seed_dca_strategy()
    decision_id = write_agent_decision(
        strategy_id=sid, execution_mode="deterministic",
        trigger_event={"type": "cron", "expr": "0 9 * * *"},
        input_snapshot={}, persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[], agent_output=None, latency_ms=1, error=None,
        schema=SCHEMA,
    )

    result = agent_decisions_repo.mark_notified(decision_id, schema=SCHEMA)
    assert result is True
    row = (sb.schema(SCHEMA).table("agent_decisions")
             .select("notified_at").eq("id", decision_id).execute().data[0])
    assert row["notified_at"] is not None


def test_mark_notified_is_idempotent_when_already_set():
    from backend.repositories import agent_decisions_repo
    sb = get_supabase()
    sid = _seed_dca_strategy()
    decision_id = write_agent_decision(
        strategy_id=sid, execution_mode="deterministic",
        trigger_event={"type": "cron", "expr": "0 9 * * *"},
        input_snapshot={}, persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[], agent_output=None, latency_ms=1, error=None,
        schema=SCHEMA,
    )
    assert agent_decisions_repo.mark_notified(decision_id, schema=SCHEMA) is True
    first = (sb.schema(SCHEMA).table("agent_decisions")
               .select("notified_at").eq("id", decision_id).execute().data[0]["notified_at"])
    # Second call: no-op, returns False.
    assert agent_decisions_repo.mark_notified(decision_id, schema=SCHEMA) is False
    second = (sb.schema(SCHEMA).table("agent_decisions")
                .select("notified_at").eq("id", decision_id).execute().data[0]["notified_at"])
    assert first == second
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py::test_mark_notified_sets_timestamp_when_null backend/tests/test_trading_decision_writer.py::test_mark_notified_is_idempotent_when_already_set -v
```

Expected: FAIL with `AttributeError: module 'backend.repositories.agent_decisions_repo' has no attribute 'mark_notified'`.

- [ ] **Step 3: Add the function**

Append to `backend/repositories/agent_decisions_repo.py`:

```python
def mark_notified(decision_id: str, schema: str = "public") -> bool:
    """Set notified_at = now() iff currently NULL. Returns True if the
    update changed a row (i.e. this is the first notify), False if the
    decision was already notified.
    """
    from datetime import datetime, timezone
    sb = get_supabase()
    r = (sb.schema(schema).table("agent_decisions")
           .update({"notified_at": datetime.now(timezone.utc).isoformat()})
           .eq("id", decision_id)
           .is_("notified_at", "null")
           .execute())
    return bool(r.data)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py::test_mark_notified_sets_timestamp_when_null backend/tests/test_trading_decision_writer.py::test_mark_notified_is_idempotent_when_already_set -v
```

Expected: both PASS.

- [ ] **Step 5: Commit and push**

```bash
git add backend/repositories/agent_decisions_repo.py backend/tests/test_trading_decision_writer.py
git commit -m "$(cat <<'EOF'
feat(repos): agent_decisions.mark_notified is idempotent

UPDATE ... WHERE notified_at IS NULL returns no rows on the
second call. The service layer uses this to make retries safe.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 6: `NotificationService.maybe_notify` (assembly + HTTP)

**Files:**
- Create: `backend/services/notifications/service.py`
- Modify: `backend/services/notifications/__init__.py` (re-export `maybe_notify`)
- Test: `backend/tests/test_notification_service.py`

This task wires the payload renderer to the strategy/positions/executor reads and the ntfy HTTP POST, with retry + system_alert on failure.

- [ ] **Step 1: Write the failing tests**

Write `backend/tests/test_notification_service.py`:

```python
"""Tests for NotificationService.maybe_notify.

We test against real Supabase test-schema rows (positions, strategies,
agent_decisions) and fake the ntfy HTTP layer with respx so the suite
stays hermetic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import respx

from backend.db.supabase_client import get_supabase
from backend.repositories import agent_decisions_repo
from backend.services.notifications import service as notif


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    for table in ("paper_fills", "paper_orders", "agent_decisions", "system_alerts"):
        db.schema(SCHEMA).table(table).delete().neq("id", _SENTINEL_UUID).execute()
    for table in ("paper_positions", "paper_equity_snapshots"):
        db.schema(SCHEMA).table(table).delete().neq("strategy_id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()
    yield


def _seed_strategy(notify_enabled: bool, name: str = "trend",
                   execution_mode: str = "llm_agent") -> str:
    db = get_supabase()
    payload = {
        "name": f"{name}-{uuid4()}",
        "execution_mode": execution_mode,
        "starting_balance_aud": "1000",
        "trigger_config": {"triggers": [{"type": "cron", "expr": "0 9 * * *"}],
                           "debounce_seconds": 5, "cooldown_seconds": 900,
                           "max_calls_per_hour": 10},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD","SOL/AUD","LINK/AUD","ADA/AUD"]},
        "notify_enabled": notify_enabled,
    }
    if execution_mode == "deterministic":
        payload["deterministic_config"] = {
            "cadence_cron": "0 9 */14 * *", "tz": "Australia/Sydney",
            "allocations": {"ETH/AUD": "0.50", "SOL/AUD": "0.25",
                            "LINK/AUD": "0.15", "ADA/AUD": "0.10"},
        }
    r = db.schema(SCHEMA).table("strategies").insert(payload).execute()
    sid = r.data[0]["id"]
    db.schema(SCHEMA).table("paper_positions").insert([
        {"strategy_id": sid, "asset": "AUD", "qty": "800",
         "avg_cost_aud": "1", "lots_jsonb": []},
        {"strategy_id": sid, "asset": "ETH", "qty": "0.052",
         "avg_cost_aud": "3450", "lots_jsonb": []},
    ]).execute()
    return sid


def _seed_decision(sid: str, *, tool_calls: list[dict],
                   agent_output: str | None = None) -> str:
    return agent_decisions_repo.insert(
        strategy_id=sid, execution_mode="llm_agent",
        trigger_event={"type": "cron", "expr": "0 9 * * *"},
        input_snapshot={}, persona_prompt_hash=None, model="claude-haiku-4-5",
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=tool_calls, agent_output=agent_output,
        latency_ms=1, error=None, schema=SCHEMA,
    )


def _mock_books() -> dict:
    class _Lvl:
        def __init__(self, p, q): self.price, self.qty = Decimal(p), Decimal(q)
    class _Book:
        ts = datetime.now(timezone.utc)
        bids = [_Lvl("3449", "1")]
        asks = [_Lvl("3451", "1")]
        def mid(self): return Decimal("3450")
        def age_seconds(self, _): return 0
    return {"ETH/AUD": _Book()}


@pytest.mark.asyncio
async def test_no_notify_when_flag_false():
    sid = _seed_strategy(notify_enabled=False)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<rationale>x</rationale>\n<confidence>medium</confidence>")
    with respx.mock(base_url="https://ntfy.sh") as router:
        route = router.post("/test-topic").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>medium</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="test-topic", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        assert route.call_count == 0


@pytest.mark.asyncio
async def test_no_notify_when_topic_blank():
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<confidence>medium</confidence>")
    with respx.mock(base_url="https://ntfy.sh") as router:
        route = router.post("/").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>medium</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        assert route.call_count == 0


@pytest.mark.asyncio
async def test_happy_path_single_leg_posts_and_marks_notified():
    sb = get_supabase()
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<rationale>x</rationale>\n<confidence>high</confidence>")
    with respx.mock(base_url="https://ntfy.sh") as router:
        route = router.post("/topic-abc").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>high</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="topic-abc", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        assert route.call_count == 1
        body = route.calls.last.request.read().decode()
        assert "BUY ETH/AUD" in body
        assert "Confidence: high" in body
    row = (sb.schema(SCHEMA).table("agent_decisions")
             .select("notified_at").eq("id", decision_id).execute().data[0])
    assert row["notified_at"] is not None


@pytest.mark.asyncio
async def test_retries_once_then_alerts_on_persistent_failure():
    sb = get_supabase()
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<confidence>low</confidence>")
    with respx.mock(base_url="https://ntfy.sh") as router:
        route = router.post("/topic-abc").mock(return_value=httpx.Response(500))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>low</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="topic-abc", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        # One initial attempt + one retry.
        assert route.call_count == 2
    alerts = (sb.schema(SCHEMA).table("system_alerts")
                .select("*").eq("code", "PUSH_NOTIFY_FAILED").execute().data)
    assert len(alerts) == 1
    assert alerts[0]["payload"]["decision_id"] == decision_id


@pytest.mark.asyncio
async def test_idempotent_when_already_notified():
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<confidence>medium</confidence>")
    # Pre-mark as notified.
    agent_decisions_repo.mark_notified(decision_id, schema=SCHEMA)
    with respx.mock(base_url="https://ntfy.sh") as router:
        route = router.post("/topic-abc").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>medium</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="topic-abc", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        assert route.call_count == 0


@pytest.mark.asyncio
async def test_ignores_non_place_paper_order_tool_calls():
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[
        {"tool": "get_market_snapshot", "args": {"pair": "ETH/AUD"}},
        {"tool": "get_my_paper_state", "args": {}},
    ])
    with respx.mock(base_url="https://ntfy.sh") as router:
        route = router.post("/topic-abc").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[
                {"tool": "get_market_snapshot", "args": {"pair": "ETH/AUD"}},
                {"tool": "get_my_paper_state", "args": {}},
            ],
            agent_output=None, schema=SCHEMA, books=_mock_books(),
            ntfy_topic="topic-abc", ntfy_url_base="https://ntfy.sh",
            frontend_url="",
        )
        assert route.call_count == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
backend/.venv/bin/pytest backend/tests/test_notification_service.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.notifications.service'`.

- [ ] **Step 3: Implement `service.py`**

Write `backend/services/notifications/service.py`:

```python
"""Notification orchestration: assemble payload, POST to ntfy, mark notified.

Best-effort: failures emit a system_alert but never raise into the
caller (write_agent_decision). Designed so the trading loop is never
blocked by a phone-broker outage.
"""
from __future__ import annotations

import asyncio
import logging
import re
from decimal import Decimal
from typing import Iterable
from uuid import UUID

import httpx

from backend.repositories import (
    agent_decisions_repo, paper_positions_repo, strategies_repo,
    system_alerts_repo,
)
from backend.services.notifications.payload import (
    NotificationContext, NotificationLeg, render_payload,
)

logger = logging.getLogger(__name__)

_CONFIDENCE_RE = re.compile(
    r"<confidence>\s*(high|medium|low)\s*</confidence>", re.IGNORECASE
)
_PLACE_PAPER_ORDER = "place_paper_order"
_REQUEST_TIMEOUT_S = 5.0
_RETRY_BACKOFF_S = 1.0


def _extract_confidence(agent_output: str | None) -> str | None:
    if not agent_output:
        return None
    match = _CONFIDENCE_RE.search(agent_output)
    return match.group(1).lower() if match else None


def _filter_legs(tool_calls: Iterable[dict]) -> list[dict]:
    legs: list[dict] = []
    for c in tool_calls or []:
        if c.get("tool") != _PLACE_PAPER_ORDER:
            continue
        args = c.get("args") or {}
        side = args.get("side")
        if side not in ("buy", "sell"):
            continue
        legs.append(args)
    return legs


def _resolve_mid(books: dict, pair: str) -> Decimal | None:
    book = books.get(pair) if books else None
    if book is None:
        return None
    # Match the freshness gate used in the executor's market path.
    try:
        if not book.bids or not book.asks:
            return None
        from datetime import datetime, timezone
        if book.age_seconds(datetime.now(timezone.utc)) > 5:
            return None
        return book.mid()
    except Exception:
        return None


def _build_leg(
    args: dict, *, current_positions: dict, total_notional_aud: Decimal,
    books: dict,
) -> NotificationLeg:
    pair = args["pair"]
    side = args["side"]
    notional = Decimal(str(args["notional_aud"]))
    mid = _resolve_mid(books, pair)
    base_asset = pair.split("/")[0]
    asset_qty = Decimal(str(current_positions.get(base_asset, {}).get("qty", "0")))
    avg_cost = Decimal(str(current_positions.get(base_asset, {}).get("avg_cost_aud", "0")))
    before_aud = asset_qty * (mid or avg_cost)
    delta = notional if side == "buy" else -notional
    after_aud = before_aud + delta
    new_total = total_notional_aud + (delta if side == "buy" else Decimal("0"))
    def _pct(n: Decimal, d: Decimal) -> Decimal:
        return (n / d * Decimal("100")) if d > 0 else Decimal("0")
    return NotificationLeg(
        side=side, pair=pair, notional_aud=notional, mid=mid,
        allocation_before_pct=_pct(before_aud, total_notional_aud),
        allocation_after_pct=_pct(after_aud, new_total or total_notional_aud),
    )


async def _post_with_retry(
    *, url: str, json_body: dict, decision_id: str, schema: str,
) -> None:
    attempts = 0
    last_err: str | None = None
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
        for attempts in (1, 2):
            try:
                r = await client.post(url, json=json_body)
                if 200 <= r.status_code < 300:
                    return
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as exc:
                last_err = repr(exc)
            if attempts == 1:
                await asyncio.sleep(_RETRY_BACKOFF_S)
    # Both attempts failed.
    try:
        system_alerts_repo.insert(
            level="warning", code="PUSH_NOTIFY_FAILED",
            strategy_id=None,
            message="Push notification failed after retry",
            payload={"decision_id": decision_id, "error": last_err or "unknown"},
            schema=schema,
        )
    except Exception:
        logger.exception("Failed to insert PUSH_NOTIFY_FAILED alert")


async def maybe_notify(
    *,
    decision_id: str,
    strategy_id: UUID | str,
    tool_calls: list[dict] | None,
    agent_output: str | None,
    schema: str = "public",
    books: dict | None = None,
    ntfy_topic: str | None = None,
    ntfy_url_base: str | None = None,
    frontend_url: str | None = None,
) -> None:
    """Send one ntfy notification for `decision_id` if eligible.

    Eligibility (all must hold):
    - `ntfy_topic` resolves to a non-empty string.
    - The strategy has `notify_enabled = True`.
    - `tool_calls` contains at least one `place_paper_order` with a
       buy/sell side.
    - The decision has `notified_at IS NULL` (idempotency guard).

    All arguments after `decision_id` are passed in by the caller so
    this function stays trivially testable; defaults are resolved
    against `backend.config.settings` when None.
    """
    try:
        from backend.config import settings as _settings
        topic = ntfy_topic if ntfy_topic is not None else _settings.ntfy_topic
        url_base = ntfy_url_base if ntfy_url_base is not None else _settings.ntfy_url_base
        fe_url = frontend_url if frontend_url is not None else _settings.frontend_url

        if not topic:
            return

        legs_args = _filter_legs(tool_calls or [])
        if not legs_args:
            return

        strat = strategies_repo.get(UUID(str(strategy_id)), schema=schema)
        if strat is None or not strat.notify_enabled:
            return

        # Resolve books from caller, or fall back to the executor singleton.
        if books is None:
            from backend.services.trading import strategy_loop
            ex = getattr(strategy_loop, "_current_executor", None)
            books = (getattr(ex, "_books", {}) if ex is not None else {}) or {}

        positions = paper_positions_repo.get_all(
            UUID(str(strategy_id)), schema=schema,
        )
        # Total notional ≈ sum(qty * mid_or_avg) over non-AUD + AUD cash.
        total = Decimal("0")
        for asset, row in positions.items():
            qty = Decimal(str(row.get("qty", "0")))
            if asset == "AUD":
                total += qty
                continue
            pair = f"{asset}/AUD"
            mid = _resolve_mid(books, pair) or Decimal(str(row.get("avg_cost_aud", "0")))
            total += qty * mid

        legs = [
            _build_leg(a, current_positions=positions,
                       total_notional_aud=total, books=books)
            for a in legs_args
        ]

        ctx = NotificationContext(
            strategy_name=strat.name,
            execution_mode=strat.execution_mode,
            strategy_id=str(strategy_id),
            confidence=_extract_confidence(agent_output),
            frontend_url=fe_url or "",
        )
        payload = render_payload(legs, ctx)
        if payload is None:
            return

        # Atomic-ish: only POST if we successfully claim the decision.
        if not agent_decisions_repo.mark_notified(decision_id, schema=schema):
            return

        url = f"{url_base.rstrip('/')}/{topic}"
        await _post_with_retry(
            url=url, json_body=payload,
            decision_id=decision_id, schema=schema,
        )
    except Exception as exc:
        logger.exception("maybe_notify failed unexpectedly")
        try:
            system_alerts_repo.insert(
                level="warning", code="PUSH_NOTIFY_FAILED",
                strategy_id=None,
                message=f"maybe_notify raised: {exc!r}",
                payload={"decision_id": decision_id, "error": repr(exc)},
                schema=schema,
            )
        except Exception:
            logger.exception("Also failed to insert outer-catch system_alert")
```

- [ ] **Step 4: Re-export from the package init**

Update `backend/services/notifications/__init__.py`:

```python
"""Push-notification fan-out from the trading-decision write path."""
from backend.services.notifications.service import maybe_notify

__all__ = ["maybe_notify"]
```

- [ ] **Step 5: Patch `system_alerts_repo.insert` to accept `schema`**

The test schema needs to receive alerts. Check `backend/repositories/system_alerts_repo.py` — `insert` already accepts a `schema` kwarg with default `"public"`, so no change needed. (Verify by reading the file; it does as of the spec date.)

- [ ] **Step 6: Run the tests to verify they pass**

```bash
backend/.venv/bin/pytest backend/tests/test_notification_service.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 7: Run the full notifications + decision-writer suite**

```bash
backend/.venv/bin/pytest backend/tests/test_notification_payload.py backend/tests/test_notification_service.py backend/tests/test_trading_decision_writer.py -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 8: Commit and push**

```bash
git add backend/services/notifications/service.py backend/services/notifications/__init__.py backend/tests/test_notification_service.py
git commit -m "$(cat <<'EOF'
feat(notifications): NotificationService.maybe_notify with ntfy POST + retry

Best-effort orchestration: filters tool_calls to buy/sell legs,
reads strategy + positions, resolves current mid from the executor's
local books, claims the decision via mark_notified (idempotency),
then POSTs to ntfy with one retry. Persistent failures emit a
PUSH_NOTIFY_FAILED system_alert; nothing raises into the caller.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 7: Wire `maybe_notify` into the decision write path

**Files:**
- Modify: `backend/services/trading/decision_writer.py`
- Test: append to `backend/tests/test_trading_decision_writer.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_trading_decision_writer.py`:

```python
@pytest.mark.asyncio
async def test_write_agent_decision_invokes_notify_when_enabled():
    import httpx, respx
    from backend.db.supabase_client import get_supabase as _gs
    sid = _seed_dca_strategy()
    _gs().schema(SCHEMA).table("strategies").update(
        {"notify_enabled": True}
    ).eq("id", sid).execute()

    with respx.mock(base_url="https://ntfy.sh") as router:
        route = router.post("/wire-topic").mock(return_value=httpx.Response(200))
        write_agent_decision(
            strategy_id=sid, execution_mode="llm_agent",
            trigger_event={"type": "cron", "expr": "0 9 * * *"},
            input_snapshot={}, persona_prompt_hash=None,
            model="claude-haiku-4-5",
            input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy",
                                  "notional_aud": "100"}}],
            agent_output="<confidence>medium</confidence>",
            latency_ms=1, error=None, schema=SCHEMA,
            _notify_overrides={
                "ntfy_topic": "wire-topic",
                "ntfy_url_base": "https://ntfy.sh",
                "frontend_url": "https://app.example.com",
            },
        )
        # Notification fanout is async fire-and-forget; allow loop to drain.
        import asyncio
        await asyncio.sleep(0.05)
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_write_agent_decision_does_not_notify_when_disabled():
    import httpx, respx
    sid = _seed_dca_strategy()
    # notify_enabled defaults to False — leave it alone.
    with respx.mock(base_url="https://ntfy.sh") as router:
        route = router.post("/wire-topic").mock(return_value=httpx.Response(200))
        write_agent_decision(
            strategy_id=sid, execution_mode="llm_agent",
            trigger_event={"type": "cron", "expr": "0 9 * * *"},
            input_snapshot={}, persona_prompt_hash=None,
            model="claude-haiku-4-5",
            input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy",
                                  "notional_aud": "100"}}],
            agent_output="<confidence>medium</confidence>",
            latency_ms=1, error=None, schema=SCHEMA,
            _notify_overrides={"ntfy_topic": "wire-topic",
                               "ntfy_url_base": "https://ntfy.sh",
                               "frontend_url": ""},
        )
        import asyncio
        await asyncio.sleep(0.05)
        assert route.call_count == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py::test_write_agent_decision_invokes_notify_when_enabled backend/tests/test_trading_decision_writer.py::test_write_agent_decision_does_not_notify_when_disabled -v
```

Expected: FAIL with `TypeError: write_agent_decision() got an unexpected keyword argument '_notify_overrides'` (or similar, depending on which assertion fails first).

- [ ] **Step 3: Modify `decision_writer.py`**

Replace `backend/services/trading/decision_writer.py` entirely:

```python
"""Thin wrapper around agent_decisions_repo for the strategy loop.

Also the seam where push notifications fan out on a freshly inserted
decision (spec: docs/superpowers/specs/2026-05-19-push-notifications-design.md).
The fan-out is best-effort and runs as a fire-and-forget task so the
caller never waits on the phone broker.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.repositories.agent_decisions_repo import insert as _insert

logger = logging.getLogger(__name__)


def write_agent_decision(
    *, _notify_overrides: dict[str, Any] | None = None, **kwargs,
) -> str:
    decision_id = _insert(**kwargs)
    _schedule_notify(decision_id, kwargs, _notify_overrides)
    return decision_id


def _schedule_notify(
    decision_id: str,
    kwargs: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> None:
    """Fire-and-forget notification. Never raises."""
    try:
        from backend.services.notifications import maybe_notify
    except Exception:
        logger.exception("Notification import failed; skipping")
        return

    overrides = overrides or {}
    coro = maybe_notify(
        decision_id=decision_id,
        strategy_id=kwargs.get("strategy_id"),
        tool_calls=kwargs.get("tool_calls") or [],
        agent_output=kwargs.get("agent_output"),
        schema=kwargs.get("schema", "public"),
        ntfy_topic=overrides.get("ntfy_topic"),
        ntfy_url_base=overrides.get("ntfy_url_base"),
        frontend_url=overrides.get("frontend_url"),
    )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running loop — caller is a sync test or boot path.
        # Run to completion synchronously rather than dropping the task.
        try:
            asyncio.run(coro)
        except Exception:
            logger.exception("Notify failed in sync path")
```

- [ ] **Step 4: Run the new tests**

```bash
backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py::test_write_agent_decision_invokes_notify_when_enabled backend/tests/test_trading_decision_writer.py::test_write_agent_decision_does_not_notify_when_disabled -v
```

Expected: both PASS.

- [ ] **Step 5: Run the whole decision-writer + sandbox suite**

```bash
backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py backend/tests/test_notification_payload.py backend/tests/test_notification_service.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run a wider smoke suite**

```bash
backend/.venv/bin/pytest backend/tests -x -q --ignore=backend/tests/test_evals.py
```

Expected: pass (or only failures unrelated to this change — note any in the commit message).

- [ ] **Step 7: Commit and push**

```bash
git add backend/services/trading/decision_writer.py backend/tests/test_trading_decision_writer.py
git commit -m "$(cat <<'EOF'
feat(trading): fan out push notifications from write_agent_decision

The writer now schedules maybe_notify as a fire-and-forget task on
the running event loop (or, in sync test paths, runs it inline).
Errors are caught at every layer so the trading loop never sees a
notification failure.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

### Task 8: README phone-setup section + end-to-end smoke

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Generate a topic name**

In a terminal (the value will be set on Railway, not committed):

```bash
backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Copy the output; you'll paste it into Railway env as `NTFY_TOPIC` and into the ntfy app as your subscribed topic.

- [ ] **Step 2: Add the README section**

Append to `README.md`:

```markdown

## Phone push notifications

The backend optionally pushes a phone notification each time a strategy with `notify_enabled = true` emits a buy/sell decision. Delivery uses the free ntfy.sh public broker — no account, no per-notification cost.

### Setup

1. Install the official ntfy app (search "ntfy" on the iOS App Store or Google Play; icon is a yellow speech bubble).
2. Generate a topic name:
   ```bash
   backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(24))"
   ```
3. On Railway, set three env vars:
   - `NTFY_TOPIC` — the value from step 2.
   - `NTFY_URL_BASE` — leave as `https://ntfy.sh` unless self-hosting.
   - `FRONTEND_URL` — your deployed frontend origin (used for the tap-through link).
4. In the ntfy app, tap **+ → Subscribe to topic**, paste the same topic name, leave the server as default.

### Enabling a strategy

Notifications are off by default for every strategy. To enable one (via the Supabase SQL editor):

```sql
UPDATE strategies
   SET notify_enabled = true
 WHERE name = '<your strategy name>';
```

Switch back off the same way (`= false`). Only one strategy at a time is supported by design — flip the previous one off first.

### What's in the notification

For a single-leg decision: `BUY ETH/AUD — <strategy name>` with notional, mid price, allocation-after-trade, and (for LLM strategies) the confidence tag.

For a multi-leg decision (e.g. DCA rebalance): one notification listing up to four legs, with a `… +N more` indicator if a rebalance ever exceeds four. The notification is informational; you act on it manually on Kraken.

### Security note

The topic name is the only auth on ntfy — anyone who knows it can read or write. Don't share the value, don't commit it, and treat it like an API token. The notification body deliberately omits balances and total portfolio value; leak ceiling is "Ben's bot is interested in ETH right now."
```

- [ ] **Step 3: Optional manual end-to-end smoke**

Pick one of your existing test-schema strategies, flip `notify_enabled = true` in Supabase, set the three env vars in a local `.env`, restart the backend, and trigger a decision (e.g. wait for the DCA cron or call the deterministic path manually). The phone should buzz within a few seconds. Flip the strategy back off afterwards.

This is not part of CI — it requires a real phone and the real broker, and it's the kind of one-time verification you'd want before flipping a production strategy.

- [ ] **Step 4: Commit and push**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: README section for push-notification phone setup

Covers app install, topic generation, Railway env vars, enabling a
strategy from the SQL editor, and the security note on topic-name
secrecy. Also documents the one-strategy-at-a-time convention.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## Done state

After all eight tasks:

- `notify_enabled` is a per-strategy column, defaulting to false.
- A single ntfy POST fires per `agent_decisions` row that contains buy/sell `place_paper_order` calls — only if the strategy has the flag on.
- Idempotency: `agent_decisions.notified_at` is the claim. Retries cannot duplicate sends.
- Failures alert via `system_alerts.code = 'PUSH_NOTIFY_FAILED'` and never raise.
- New tests cover: pure-function payload rendering, service-layer retry/alert/idempotency, end-to-end wire-up from the decision writer.
- README documents phone setup, enable/disable flow, and the topic-secrecy security note.

## What this plan does NOT do (per spec)

- No tap-to-execute. No UI toggle for `notify_enabled` (manual SQL flip).
- No quiet-hours, no digest mode, no confidence filter.
- No live-Kraken executor. When that arrives, the notification hook moves from `decision_writer` to a post-fill seam on `LiveKrakenExecutor` — the `NotificationService` interface is unchanged. Out of scope for this plan.
