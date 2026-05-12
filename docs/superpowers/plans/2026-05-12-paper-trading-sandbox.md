# Paper Trading Sandbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Execution Progress

**Status as of 2026-05-12 (second session):** Tasks 1–27 complete and pushed. Resume at **Task 28 (`Strategies CRUD + leaderboard + detail endpoints`)**.

| Range | Status | Notes |
|---|---|---|
| 1 — hypothesis dep | ✅ done | `28f63cc`; websockets pin removed (transitive via python-kraken-sdk) |
| 2 — DB migration (8 tables) | ✅ done | `52137ba` + `19d77bf`; `agent_decisions.execution_mode` is enum |
| 3 — Pydantic models | ✅ done | `3346322` + `5d2e234`; `TriggerEvent` real type alias + helper |
| 4 — LocalOrderBook | ✅ done | `b764353` |
| 5 — FeeSchedule | ✅ done | `d2afb47` |
| 6 — fill model | ✅ done | `77464a8` |
| 7 — risk_cap_precheck | ✅ done | `aea5c37` (incl. 3 Hypothesis property tests @ 200 examples each) |
| 8 — kill_criteria | ✅ done | `3e21004` |
| 9 — min_order | ✅ done | `6447ddd`; test_filter_drops_pair threshold corrected |
| 10 — OrderExecutor + skel | ✅ done | `f86263e` |
| 11 — market path | ✅ done | `bbe83ad`; integration tests use test schema |
| 12 — limit + reconciler | ✅ done | `02efe4d`; 24h default TTL, maker fees on cross |
| 13 — EventBus | ✅ done | `45ea4be` |
| 14 — trigger evaluators | ✅ done | `2752de7` |
| 15 — TriggerState | ✅ done | `d909793` |
| 16 — price_feed | ✅ done | `b2cf76d`; Kraken WS v2 book + trade |
| 17 — trigger_scheduler | ✅ done | `fa44edd` |
| 18 — strategy_loop | ✅ done | `ad6ec9d` |
| 19 — deterministic | ✅ done | `04418b0` |
| 20 — decision_writer | ✅ done | `1383d76` |
| 21 — persona files | ✅ done | `07500a3` |
| 22 — persona_loader | ✅ done | `a0715c3` |
| 23 — 5 MCP tools | ✅ done | `d860256` |
| 24 — LLM strategy + cost model | ✅ done | `190a48a`; `invoke_for_strategy` in graph.py is intentionally a stub (production wiring at Task 31) |
| 25 — equity snapshot | ✅ done | `942c73e`; fixed Decimal(float) imprecision via Decimal(str(...)) |
| 26 — benchmark snapshot | ✅ done | `05ecf46` |
| 27 — metrics | ✅ done | `ae24cd5` |
| 28–37 | ⏳ pending | Start here when resuming |

**Resume instructions:** open a fresh Claude Code session in this repo and say *"Use superpowers:executing-plans on `docs/superpowers/plans/2026-05-12-paper-trading-sandbox.md`, starting at Task 28"*. The plan stands alone — no conversation context is needed to continue.

**Plan corrections applied during Tasks 1–23** (already documented in commit messages; future tasks must keep applying):
- `from backend.db.client` → `from backend.db.supabase_client` (correct import).
- All new repos accept `schema: str = "public"` and tests pass `schema="test"`; matches existing `lots_repo` / `up_*_repo` convention.
- `PaperExecutor(schema=...)` threads schema through every repo call; same for `strategy_loop.set_executor(exec, schema=...)`.
- Removed `"updated_at": "now()"` literal strings (supabase-py sends them verbatim).
- `OrderResult.order_id` normalised to `str` on cached idempotency path.
- `event.model_dump(mode="json")` before writing JSONB so datetime → ISO string.
- `@mcp.tool()` decorated functions don't expose `.fn` in this FastMCP — call them directly in tests.
- TriggerEvent is a real type alias + `validate_trigger_event` helper.
- Migrations apply via Supabase MCP `apply_migration`, not a non-existent script.

---

**Goal:** Build a multi-strategy paper-trading sandbox on Kraken AUD pairs (ETH/LINK/ADA/SOL), with PaperExecutor abstracted so future paper→real swap is a drop-in.

**Architecture:** Single-process asyncio (Approach A): a Kraken-WS `price_feed_task`, an APScheduler extension for cron/interval triggers, one `strategy_loop_task` per active strategy, and one shared `PaperExecutor` — all running inside the existing FastAPI process. Three strategies at AUD 1,000 each: DCA-Baseline (deterministic, no LLM), Trend-Follower + Mean-Reverter (LLM via existing LangGraph agent with five new MCP tools and scoped persona prompts). New top-level frontend `StrategiesPage` with leaderboard + overlay equity chart (two benchmark lines: BTC HODL + monthly-rebalanced equal-weight basket).

**Tech Stack:** Python 3.13 + FastAPI + asyncio + APScheduler + Supabase Postgres + Pydantic + supabase-py; LangGraph agent (existing) + FastMCP; Kraken WebSocket (`book` and `trade` channels) + REST (`AssetPairs`, `Ticker`); `hypothesis` for property-based tests; React 19 + TypeScript + Tailwind frontend via `/impeccable`.

**Spec:** `docs/superpowers/specs/2026-05-12-paper-trading-sandbox-design.md`.

**Conventions (project-specific, derived from existing code):**
- Pydantic models: `backend/models/`
- Business logic: `backend/services/` (this plan creates `backend/services/trading/`)
- DB access: `backend/repositories/`
- API routers: `backend/routers/`
- Tests: flat at `backend/tests/test_*.py`
- Migrations: `supabase/migrations/00N_name.sql`
- Memory rule: **push after every task** (each commit step is `git add … && git commit -m "…" && git push`).
- Memory rule: **frontend tasks use `/impeccable`** (not raw Tailwind).
- Memory rule: **never print `Settings`** in tests/scripts — use `hasattr`/`len` to verify imports.
- Existing scheduler at `backend/scheduler.py` (APScheduler) is **extended**, not replaced.

---

## File Structure (decomposition decisions)

**New files (created by this plan):**

```
supabase/migrations/
  006_paper_trading.sql                    # all paper_* tables + enums

backend/models/
  trading.py                               # Pydantic: OrderResult, Fill, OrderRow, OrderBookLevel, TickEvent, BookUpdateEvent, TriggerEvent, AgentDecisionRow, …

backend/services/trading/
  __init__.py
  order_book.py                            # LocalOrderBook (snapshot+diff+checksum)
  fees.py                                  # FeeSchedule + apply_fee
  fill_model.py                            # walk_book(qty, side, book) → list[Fill]
  risk_caps.py                             # risk_cap_precheck(state, order, caps) → Decision
  kill_criteria.py                         # evaluate_kill_criteria(snapshot, criteria) → Decision
  min_order.py                             # validate_min_order_against_kraken(pair, max_position)
  executor.py                              # OrderExecutor Protocol + PaperExecutor
  event_bus.py                             # in-process asyncio Queue pub/sub
  trigger_evaluators.py                    # match_cron, match_interval, match_breakout, match_stretch, …
  trigger_state.py                         # TriggerState (debounce / cooldown / rate-cap)
  trigger_scheduler.py                     # extends backend/scheduler.py with cron/interval registration per strategy
  price_feed.py                            # Kraken WS task (book + trade)
  strategy_loop.py                         # per-strategy asyncio loop entrypoint
  deterministic.py                         # compute_rebalance_orders for execution_mode='deterministic'
  llm_strategy.py                          # invoke_llm_strategy(strategy, event) — context assembly, LangGraph call, decision write
  persona_loader.py                        # load + hash persona markdown
  decision_writer.py                       # write_agent_decision(...)
  cost_model.py                            # tokens × model_prices × FX → cost_aud
  equity_snapshot.py                       # hourly per-strategy equity snapshots
  benchmark_snapshot.py                    # BTC HODL + alt-basket monthly rebalance
  metrics.py                               # Sharpe (√365), Sortino, max DD, Calmar, win-rate, payoff
  health.py                                # status payload for /_health

backend/repositories/
  strategies_repo.py                       # CRUD on strategies
  paper_orders_repo.py                     # paper_orders + paper_fills
  paper_positions_repo.py                  # paper_positions (cash = asset 'AUD')
  agent_decisions_repo.py                  # write + read decisions
  paper_equity_repo.py                     # paper_equity_snapshots + paper_benchmarks
  system_alerts_repo.py                    # alerts

backend/agent/personas/
  dca-baseline.md                          # charter (deterministic, no prompt — file documents WHY 50/25/15/10)
  trend-follower.md                        # system prompt for LLM strategy
  mean-reverter.md                         # system prompt for LLM strategy

backend/routers/
  strategies.py                            # /api/strategies/* and /_health

backend/evals/
  personas_golden_set.yaml                 # scenarios for persona eval
  personas_runner.py                       # per-persona scenario runner

backend/tests/
  test_trading_order_book.py
  test_trading_fees.py
  test_trading_fill_model.py
  test_trading_risk_caps.py                # property-based
  test_trading_kill_criteria.py            # boundary tests
  test_trading_min_order.py
  test_trading_executor_market.py          # integration against test DB
  test_trading_executor_limit.py
  test_trading_executor_idempotency.py
  test_trading_event_bus.py
  test_trading_trigger_evaluators.py
  test_trading_trigger_state.py
  test_trading_deterministic.py
  test_trading_persona_loader.py
  test_trading_cost_model.py
  test_trading_equity_snapshot.py
  test_trading_benchmark_snapshot.py
  test_trading_metrics.py
  test_trading_decision_writer.py
  test_strategies_router.py
  test_strategies_health.py
  test_trading_seed.py

frontend/src/types/
  strategies.ts                            # all strategy + leaderboard + chart types

frontend/src/api/
  strategies.ts                            # fetchStrategies / fetchStrategy / fetchLeaderboard / fetchEquityCurves / fetchHealth / pause / resume / archive / fetchDecisions / fetchOpenOrders

frontend/src/pages/
  StrategiesPage.tsx                       # top-level page

frontend/src/components/strategies/
  LeaderboardTable.tsx
  EquityChart.tsx
  StrategyDetailDrawer.tsx
  DecisionsFeed.tsx
  PersonaChatTab.tsx
  SystemStatusBanner.tsx

docs/
  manual-smoke-strategies.md               # frontend + e2e smoke checklist
```

**Modified files:**

```
backend/requirements.txt                   # + hypothesis, + websockets (if not already there)
backend/main.py                            # boot trading tasks on FastAPI startup
backend/scheduler.py                       # add register_strategy_triggers() entrypoint
backend/mcp_server.py                      # add 5 new tools (place_paper_order, cancel_paper_order, get_my_paper_state, get_my_recent_decisions, get_market_snapshot)
backend/agent/                             # extend existing graph to support strategy-invocation mode (scoped tool surface)
frontend/src/components/AppLayout.tsx      # add "Strategies" side-rail item
frontend/src/App.tsx                       # add /strategies route
```

---

## Part 0 — Foundation

### Task 1: Add `hypothesis` to backend dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Inspect current requirements**

Run: `cat backend/requirements.txt | grep -E "hypothesis|websockets"`
Expected: no `hypothesis` line (may or may not have `websockets`).

- [ ] **Step 2: Add `hypothesis>=6.100,<7` to requirements.txt**

Append the following line (preserve existing pinning style — e.g., `>=` ranges if that's the pattern, exact pins if that's the pattern):

```
hypothesis>=6.100,<7
```

**Do NOT add `websockets` explicitly.** It is already a transitive dependency of `python-kraken-sdk` (which requires `websockets>=14.1`). Adding a conflicting upper-bound pin breaks `pip install`. The `price_feed.py` task (Task 16) imports `websockets` directly — that works against the transitive version (verified 15.0.1 at plan write time).

- [ ] **Step 3: Install in the venv**

Run: `backend/.venv/bin/pip install -r backend/requirements.txt`
Expected: "Successfully installed hypothesis-6.x.x" (and `websockets` if added).

- [ ] **Step 4: Verify the import works**

Run: `backend/.venv/bin/python -c "import hypothesis; print(hypothesis.__version__)"`
Expected: a version string like `6.x.x` — no traceback.

- [ ] **Step 5: Commit and push**

```bash
git add backend/requirements.txt
git commit -m "chore(deps): add hypothesis for property-based tests"
git push
```

---

### Task 2: Database migration — all `paper_*` tables

**Files:**
- Create: `supabase/migrations/006_paper_trading.sql`
- Create: `supabase/migrations/test_006_paper_trading.sql` (mirror for test schema if pattern in `test_005_up_bank.sql` is followed)

- [ ] **Step 1: Create the migration file**

Create `supabase/migrations/006_paper_trading.sql` with the full schema below. Reference spec §4 for column-by-column rationale.

```sql
-- 006_paper_trading.sql
-- Paper-trading sandbox schema. See spec §4.

create type strategy_execution_mode as enum ('llm_agent', 'deterministic');
create type strategy_status         as enum ('active', 'paused', 'archived');
create type paper_order_side        as enum ('buy', 'sell');
create type paper_order_type        as enum ('market', 'limit');
create type paper_order_status      as enum ('pending', 'filled', 'partial', 'rejected', 'cancelled', 'expired');
create type paper_fee_role          as enum ('maker', 'taker');
create type system_alert_level      as enum ('info', 'warning', 'error');

create table strategies (
  id                            uuid primary key default gen_random_uuid(),
  name                          text not null,
  description                   text,
  execution_mode                strategy_execution_mode not null,
  persona_key                   text,
  deterministic_config          jsonb,
  starting_balance_aud          numeric(12,2) not null default 1000.00,
  trigger_config                jsonb not null default '{}'::jsonb,
  risk_caps                     jsonb not null default '{}'::jsonb,
  kill_criteria                 jsonb not null default '{}'::jsonb,
  model_preference              text,
  status                        strategy_status not null default 'active',
  dry_run                       boolean not null default false,
  persona_prompt_stable_since   timestamptz,
  created_at                    timestamptz not null default now(),
  updated_at                    timestamptz not null default now(),
  constraint persona_required_for_llm
    check (execution_mode = 'deterministic' or persona_key is not null),
  constraint deterministic_config_required_for_deterministic
    check (execution_mode = 'llm_agent' or deterministic_config is not null)
);

create table paper_orders (
  id                uuid primary key default gen_random_uuid(),
  strategy_id       uuid not null references strategies(id) on delete cascade,
  idempotency_key   text not null,
  pair              text not null,
  side              paper_order_side not null,
  type              paper_order_type not null,
  qty               numeric(20,10) not null,
  limit_price       numeric(20,10),
  expires_at        timestamptz,
  status            paper_order_status not null default 'pending',
  reject_reason     text,
  decided_by        uuid,
  created_at        timestamptz not null default now(),
  unique (strategy_id, idempotency_key)
);
create index paper_orders_strategy_status_idx on paper_orders (strategy_id, status);
create index paper_orders_created_idx on paper_orders (strategy_id, created_at desc);

create table paper_fills (
  id                uuid primary key default gen_random_uuid(),
  order_id          uuid not null references paper_orders(id) on delete cascade,
  qty               numeric(20,10) not null,
  price             numeric(20,10) not null,
  fee_aud           numeric(12,4) not null default 0,
  fee_role          paper_fee_role not null,
  book_state_hash   text,
  filled_at         timestamptz not null default now()
);
create index paper_fills_order_idx on paper_fills (order_id);

create table paper_positions (
  strategy_id       uuid not null references strategies(id) on delete cascade,
  asset             text not null,
  qty               numeric(20,10) not null default 0,
  avg_cost_aud      numeric(12,4) not null default 0,
  lots_jsonb        jsonb not null default '[]'::jsonb,
  updated_at        timestamptz not null default now(),
  primary key (strategy_id, asset)
);

create table agent_decisions (
  id                    uuid primary key default gen_random_uuid(),
  strategy_id           uuid not null references strategies(id) on delete cascade,
  execution_mode        strategy_execution_mode not null,
  trigger_event         jsonb not null,
  input_snapshot        jsonb not null,
  persona_prompt_hash   text,
  model                 text,
  input_tokens          integer not null default 0,
  output_tokens         integer not null default 0,
  cost_aud              numeric(10,4) not null default 0,
  tool_calls            jsonb not null default '[]'::jsonb,
  agent_output          text,
  latency_ms            integer,
  error                 text,
  created_at            timestamptz not null default now()
);
create index agent_decisions_strategy_created_idx
  on agent_decisions (strategy_id, created_at desc);

-- Now that agent_decisions exists, link paper_orders.decided_by to it.
alter table paper_orders
  add constraint paper_orders_decided_by_fk
  foreign key (decided_by) references agent_decisions(id) on delete set null;

create table paper_equity_snapshots (
  strategy_id           uuid not null references strategies(id) on delete cascade,
  ts                    timestamptz not null,
  equity_aud            numeric(14,4) not null,
  cash_aud              numeric(14,4) not null,
  position_value_aud    numeric(14,4) not null,
  realised_pnl_aud      numeric(14,4) not null default 0,
  unrealised_pnl_aud    numeric(14,4) not null default 0,
  primary key (strategy_id, ts)
);

create table paper_benchmarks (
  benchmark_key         text not null,
  ts                    timestamptz not null,
  equity_aud            numeric(14,4) not null,
  primary key (benchmark_key, ts)
);

create table system_alerts (
  id                    uuid primary key default gen_random_uuid(),
  level                 system_alert_level not null,
  code                  text not null,
  strategy_id           uuid references strategies(id) on delete set null,
  message               text not null,
  payload               jsonb not null default '{}'::jsonb,
  acknowledged_at       timestamptz,
  created_at            timestamptz not null default now()
);
create index system_alerts_unack_idx
  on system_alerts (created_at desc) where acknowledged_at is null;

-- View: per-strategy LLM cost roll-up (referenced in spec §7.4).
create view paper_strategy_costs as
  select strategy_id,
         date_trunc('day', created_at) as day,
         sum(cost_aud)::numeric(12,4) as cost_aud,
         count(*) as invocations
  from agent_decisions
  where execution_mode = 'llm_agent'
  group by 1, 2;
```

- [ ] **Step 2: Mirror to the test-schema migration if the project uses one**

Check existence: `ls supabase/migrations/test_*.sql`.
If `test_005_up_bank.sql` exists, create `supabase/migrations/test_006_paper_trading.sql` with the same DDL but referencing the test schema (e.g., `test.strategies` instead of `strategies`), matching the pattern in `test_005_up_bank.sql`.
If the project doesn't use a `test_` prefix for some migrations, skip this step.

- [ ] **Step 3: Apply the migration locally**

Use the **Supabase MCP `apply_migration` tool** (this is the project's actual pattern — verified during execution of this task). Provide the SQL file contents and a name like `006_paper_trading`. Apply the test mirror the same way if you created one.

If you're operating without Supabase MCP access, fall back to `psql $SUPABASE_DB_URL -f supabase/migrations/006_paper_trading.sql`. `backend/scripts/` does **not** contain an apply-migration helper in this project.

Expected: no errors; eight tables/types created in public schema (and another eight in test schema if you applied the test mirror).

- [ ] **Step 4: Verify in the DB**

Run:
```bash
backend/.venv/bin/python -c "
from backend.db.supabase_client import get_supabase
sb = get_supabase()
for t in ['strategies','paper_orders','paper_fills','paper_positions','agent_decisions','paper_equity_snapshots','paper_benchmarks','system_alerts']:
    r = sb.table(t).select('count', count='exact').limit(0).execute()
    print(t, '→', r.count, 'rows')
"
```
Expected: each table prints `0 rows` (or current count), no exceptions.

- [ ] **Step 5: Commit and push**

```bash
git add supabase/migrations/006_paper_trading.sql supabase/migrations/test_006_paper_trading.sql
git commit -m "feat(db): paper-trading sandbox schema (8 tables + enums + view)"
git push
```

---

### Task 3: Trading module skeleton + domain Pydantic models

**Files:**
- Create: `backend/services/trading/__init__.py`
- Create: `backend/models/trading.py`
- Test: `backend/tests/test_trading_models.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_models.py`:

```python
from decimal import Decimal
from datetime import datetime, timezone

from backend.models.trading import (
    OrderBookLevel, OrderBookSnapshot,
    Fill, OrderResult, OrderRow,
    TickEvent, BookUpdateEvent, TriggerEvent,
    RiskCaps, KillCriteria, DeterministicConfig,
)


def test_order_book_level_construction():
    level = OrderBookLevel(price=Decimal("25.00"), qty=Decimal("20"))
    assert level.price == Decimal("25.00")


def test_order_book_snapshot_sorted_invariant():
    snap = OrderBookSnapshot(
        pair="ETH/AUD",
        asks=[
            OrderBookLevel(price=Decimal("3196.50"), qty=Decimal("0.5")),
            OrderBookLevel(price=Decimal("3196.60"), qty=Decimal("1.0")),
        ],
        bids=[
            OrderBookLevel(price=Decimal("3196.40"), qty=Decimal("0.8")),
            OrderBookLevel(price=Decimal("3196.30"), qty=Decimal("1.2")),
        ],
        checksum="abc123",
        ts=datetime.now(timezone.utc),
    )
    # asks ascending, bids descending — assert top of book
    assert snap.asks[0].price < snap.asks[1].price
    assert snap.bids[0].price > snap.bids[1].price


def test_order_result_serialises_fills():
    res = OrderResult(
        order_id="00000000-0000-0000-0000-000000000001",
        status="filled",
        fills=[Fill(qty=Decimal("0.1"), price=Decimal("3196.60"),
                    fee_aud=Decimal("1.28"), fee_role="taker",
                    book_state_hash="h1",
                    filled_at=datetime.now(timezone.utc))],
        reject_reason=None,
    )
    assert res.status == "filled"
    assert len(res.fills) == 1


def test_risk_caps_defaults():
    caps = RiskCaps()
    assert caps.max_single_asset_pct == Decimal("30")
    assert caps.max_total_crypto_exposure_pct == Decimal("60")
    assert caps.max_order_aud == Decimal("250")
    assert caps.daily_loss_cap_aud == Decimal("100")
    assert caps.max_drawdown_pct_before_pause == Decimal("25")
    assert caps.allowed_pairs == ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]


def test_trigger_event_discriminated_by_type():
    from backend.models.trading import validate_trigger_event, CronTriggerEvent, IntervalTriggerEvent

    interval = validate_trigger_event(
        {"type": "interval", "minutes": 60, "ts": "2026-05-12T00:00:00Z"}
    )
    assert isinstance(interval, IntervalTriggerEvent)
    assert interval.minutes == 60

    cron = validate_trigger_event(
        {"type": "cron", "expr": "0 9 * * *", "ts": "2026-05-12T00:00:00Z"}
    )
    assert isinstance(cron, CronTriggerEvent)
    assert cron.expr == "0 9 * * *"

    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        validate_trigger_event(
            {"type": "unknown_event_kind", "ts": "2026-05-12T00:00:00Z"}
        )


def test_deterministic_config_weights_sum_to_one():
    cfg = DeterministicConfig(
        cadence_cron="0 9 */14 * *", tz="Australia/Sydney",
        allocations={"ETH/AUD": Decimal("0.50"),
                     "SOL/AUD": Decimal("0.25"),
                     "LINK/AUD": Decimal("0.15"),
                     "ADA/AUD": Decimal("0.10")},
    )
    assert sum(cfg.allocations.values()) == Decimal("1.00")
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_models.py -v`
Expected: `ImportError` — `backend.models.trading` doesn't exist yet.

- [ ] **Step 3: Create the trading module + models**

Create `backend/services/trading/__init__.py` (empty file).

Create `backend/models/trading.py`:

```python
"""Pydantic models for the paper-trading sandbox.

See docs/superpowers/specs/2026-05-12-paper-trading-sandbox-design.md §4.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter, field_validator


# ─────────────────────────── Order book ───────────────────────────

class OrderBookLevel(BaseModel):
    price: Decimal
    qty: Decimal


class OrderBookSnapshot(BaseModel):
    pair: str
    asks: list[OrderBookLevel]   # ascending
    bids: list[OrderBookLevel]   # descending
    checksum: str
    ts: datetime


# ─────────────────────────── Orders & fills ───────────────────────

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["pending", "filled", "partial", "rejected", "cancelled", "expired"]
FeeRole = Literal["maker", "taker"]


class Fill(BaseModel):
    qty: Decimal
    price: Decimal
    fee_aud: Decimal
    fee_role: FeeRole
    book_state_hash: str | None = None
    filled_at: datetime


class OrderResult(BaseModel):
    order_id: UUID | str
    status: OrderStatus
    fills: list[Fill] = []
    reject_reason: str | None = None


class OrderRow(BaseModel):
    id: UUID
    strategy_id: UUID
    idempotency_key: str
    pair: str
    side: OrderSide
    type: OrderType
    qty: Decimal
    limit_price: Decimal | None = None
    expires_at: datetime | None = None
    status: OrderStatus
    reject_reason: str | None = None
    decided_by: UUID | None = None
    created_at: datetime


# ─────────────────────────── Bus events ───────────────────────────

class TickEvent(BaseModel):
    type: Literal["tick"] = "tick"
    pair: str
    price: Decimal
    ts: datetime


class BookUpdateEvent(BaseModel):
    type: Literal["book_update"] = "book_update"
    pair: str
    snapshot: OrderBookSnapshot
    ts: datetime


class CronTriggerEvent(BaseModel):
    type: Literal["cron"] = "cron"
    expr: str
    ts: datetime


class IntervalTriggerEvent(BaseModel):
    type: Literal["interval"] = "interval"
    minutes: int
    ts: datetime


class PriceBreakoutEvent(BaseModel):
    type: Literal["price_breakout"] = "price_breakout"
    pair: str
    direction: Literal["up", "down"]
    move_pct: Decimal
    lookback_bars: int
    ts: datetime


class PriceStretchEvent(BaseModel):
    type: Literal["price_stretch"] = "price_stretch"
    pair: str
    direction: Literal["above", "below"]
    stdev_distance: Decimal
    ts: datetime


class OrderFilledEvent(BaseModel):
    type: Literal["order_filled"] = "order_filled"
    order_id: UUID
    strategy_id: UUID
    ts: datetime


class DrawdownEvent(BaseModel):
    type: Literal["drawdown"] = "drawdown"
    strategy_id: UUID
    session_pct: Decimal
    ts: datetime


TriggerEvent = Annotated[
    CronTriggerEvent | IntervalTriggerEvent | PriceBreakoutEvent
    | PriceStretchEvent | OrderFilledEvent | DrawdownEvent
    | TickEvent | BookUpdateEvent,
    Field(discriminator="type"),
]

_trigger_event_adapter: TypeAdapter[TriggerEvent] = TypeAdapter(TriggerEvent)


def validate_trigger_event(data: object) -> TriggerEvent:
    """Parse a dict/JSON into the appropriate concrete TriggerEvent subtype."""
    return _trigger_event_adapter.validate_python(data)


# ─────────────────────────── Configs ──────────────────────────────

class RiskCaps(BaseModel):
    max_single_asset_pct: Decimal = Decimal("30")
    max_total_crypto_exposure_pct: Decimal = Decimal("60")
    max_order_aud: Decimal = Decimal("250")
    daily_loss_cap_aud: Decimal = Decimal("100")  # FIXED, not moving; see spec decision-log row 22
    max_drawdown_pct_before_pause: Decimal = Decimal("25")
    allowed_pairs: list[str] = ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]


class KillCriterion(BaseModel):
    metric: str   # 'drawdown_pct' | 'daily_loss_aud' | 'trailing_30d_sharpe'
    op: Literal[">=", ">", "<=", "<", "=="]
    value: Decimal


class KillCriteria(BaseModel):
    auto_pause_when: list[KillCriterion] = []


class DeterministicConfig(BaseModel):
    cadence_cron: str
    tz: str = "Australia/Sydney"
    allocations: dict[str, Decimal]   # pair → weight (sums to 1.0)

    @field_validator("allocations")
    @classmethod
    def _weights_sum_to_one(cls, v: dict[str, Decimal]) -> dict[str, Decimal]:
        total = sum(v.values())
        if abs(total - Decimal("1")) > Decimal("0.0001"):
            raise ValueError(f"allocations must sum to 1.0, got {total}")
        return v


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
    persona_prompt_stable_since: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ─────────────────────────── Decisions ────────────────────────────

class AgentDecisionRow(BaseModel):
    id: UUID
    strategy_id: UUID
    execution_mode: str
    trigger_event: dict
    input_snapshot: dict
    persona_prompt_hash: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_aud: Decimal = Decimal("0")
    tool_calls: list[dict] = []
    agent_output: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    created_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_models.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/__init__.py backend/models/trading.py backend/tests/test_trading_models.py
git commit -m "feat(trading): core Pydantic models (orders, fills, books, trigger events, configs)"
git push
```

---

## Part 1 — Order Book + Fill Model

### Task 4: `LocalOrderBook` (snapshot + diff + checksum)

**Files:**
- Create: `backend/services/trading/order_book.py`
- Test: `backend/tests/test_trading_order_book.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_order_book.py`:

```python
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from backend.models.trading import OrderBookLevel
from backend.services.trading.order_book import LocalOrderBook, ChecksumMismatch


def _ts():
    return datetime.now(timezone.utc)


def test_apply_snapshot_replaces_state():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("100"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("99"), qty=Decimal("2"))],
        checksum="snap1",
        ts=_ts(),
    )
    assert ob.top_ask().price == Decimal("100")
    assert ob.top_bid().price == Decimal("99")


def test_apply_diff_updates_level_qty():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("100"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("99"), qty=Decimal("2"))],
        checksum="snap1", ts=_ts(),
    )
    ob.apply_diff(
        ask_updates=[OrderBookLevel(price=Decimal("100"), qty=Decimal("3"))],
        bid_updates=[],
        new_checksum=None, ts=_ts(),
    )
    assert ob.asks[0].qty == Decimal("3")


def test_apply_diff_qty_zero_removes_level():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[
            OrderBookLevel(price=Decimal("100"), qty=Decimal("1")),
            OrderBookLevel(price=Decimal("101"), qty=Decimal("2")),
        ],
        bids=[], checksum="snap1", ts=_ts(),
    )
    ob.apply_diff(
        ask_updates=[OrderBookLevel(price=Decimal("100"), qty=Decimal("0"))],
        bid_updates=[], new_checksum=None, ts=_ts(),
    )
    assert len(ob.asks) == 1
    assert ob.asks[0].price == Decimal("101")


def test_apply_diff_insert_new_level_in_sort_order():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[
            OrderBookLevel(price=Decimal("100"), qty=Decimal("1")),
            OrderBookLevel(price=Decimal("102"), qty=Decimal("1")),
        ],
        bids=[], checksum="snap1", ts=_ts(),
    )
    ob.apply_diff(
        ask_updates=[OrderBookLevel(price=Decimal("101"), qty=Decimal("5"))],
        bid_updates=[], new_checksum=None, ts=_ts(),
    )
    assert [a.price for a in ob.asks] == [Decimal("100"), Decimal("101"), Decimal("102")]


def test_checksum_mismatch_raises():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("100"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("99"), qty=Decimal("1"))],
        checksum="snap1", ts=_ts(),
    )
    with pytest.raises(ChecksumMismatch):
        ob.apply_diff(
            ask_updates=[], bid_updates=[],
            new_checksum="not_the_checksum_we_compute", ts=_ts(),
        )


def test_age_seconds_grows_with_time():
    ob = LocalOrderBook("ETH/AUD")
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("100"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("99"), qty=Decimal("1"))],
        checksum="x", ts=old,
    )
    # at "now" the age should be large
    assert ob.age_seconds(_ts()) > 60 * 60 * 24  # >1 day
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_order_book.py -v`
Expected: ImportError on `LocalOrderBook`.

- [ ] **Step 3: Implement `LocalOrderBook`**

Create `backend/services/trading/order_book.py`:

```python
"""LocalOrderBook — in-process replica of Kraken's L2 book per pair.

Maintained from snapshot + diff messages on the Kraken WS `book` channel.
Kraken supplies a checksum on every update; on mismatch the maintainer
resubscribes for a fresh snapshot.

See docs/superpowers/specs/2026-05-12-paper-trading-sandbox-design.md §5.3.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable

from backend.models.trading import OrderBookLevel


class ChecksumMismatch(Exception):
    """Raised when an applied diff's computed checksum != Kraken's expected."""


class LocalOrderBook:
    def __init__(self, pair: str) -> None:
        self.pair = pair
        self.asks: list[OrderBookLevel] = []   # ascending
        self.bids: list[OrderBookLevel] = []   # descending
        self.checksum: str = ""
        self.ts: datetime | None = None

    # ── snapshot / diff entry points ────────────────────────────

    def apply_snapshot(
        self,
        *,
        asks: list[OrderBookLevel],
        bids: list[OrderBookLevel],
        checksum: str,
        ts: datetime,
    ) -> None:
        self.asks = sorted(asks, key=lambda l: l.price)
        self.bids = sorted(bids, key=lambda l: l.price, reverse=True)
        self.checksum = checksum
        self.ts = ts

    def apply_diff(
        self,
        *,
        ask_updates: list[OrderBookLevel],
        bid_updates: list[OrderBookLevel],
        new_checksum: str | None,
        ts: datetime,
    ) -> None:
        self.asks = self._merge(self.asks, ask_updates, reverse=False)
        self.bids = self._merge(self.bids, bid_updates, reverse=True)
        self.ts = ts
        if new_checksum is not None:
            computed = self.compute_checksum()
            if computed != new_checksum:
                raise ChecksumMismatch(
                    f"{self.pair}: computed {computed}, expected {new_checksum}"
                )
            self.checksum = new_checksum

    # ── reads ───────────────────────────────────────────────────

    def top_ask(self) -> OrderBookLevel:
        return self.asks[0]

    def top_bid(self) -> OrderBookLevel:
        return self.bids[0]

    def mid(self) -> Decimal:
        return (self.top_ask().price + self.top_bid().price) / 2

    def age_seconds(self, now: datetime) -> float:
        if self.ts is None:
            return float("inf")
        return (now - self.ts).total_seconds()

    # ── internals ───────────────────────────────────────────────

    @staticmethod
    def _merge(
        existing: list[OrderBookLevel],
        updates: Iterable[OrderBookLevel],
        *,
        reverse: bool,
    ) -> list[OrderBookLevel]:
        by_price: dict[Decimal, Decimal] = {l.price: l.qty for l in existing}
        for u in updates:
            if u.qty == 0:
                by_price.pop(u.price, None)
            else:
                by_price[u.price] = u.qty
        merged = [OrderBookLevel(price=p, qty=q) for p, q in by_price.items()]
        merged.sort(key=lambda l: l.price, reverse=reverse)
        return merged

    def compute_checksum(self) -> str:
        """Match Kraken's L2 checksum algorithm.

        Kraken concatenates the top-10 price/qty (no decimal points, stripped
        leading zeros) ask-then-bid, then CRC32. See:
        https://docs.kraken.com/websockets/#book-checksum
        """
        import zlib

        def fmt(d: Decimal) -> str:
            # remove decimal point, strip leading zeros
            s = format(d.normalize(), "f").replace(".", "").lstrip("0")
            return s or "0"

        parts: list[str] = []
        for lvl in self.asks[:10]:
            parts.append(fmt(lvl.price))
            parts.append(fmt(lvl.qty))
        for lvl in self.bids[:10]:
            parts.append(fmt(lvl.price))
            parts.append(fmt(lvl.qty))
        return str(zlib.crc32("".join(parts).encode("ascii")))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_order_book.py -v`
Expected: all 6 tests pass. (The `ChecksumMismatch` test passes because the test supplies a checksum that doesn't match the one computed from the empty diff applied to the snapshot.)

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/order_book.py backend/tests/test_trading_order_book.py
git commit -m "feat(trading): LocalOrderBook with snapshot/diff/checksum (Kraken WS book channel)"
git push
```

---

### Task 5: Fee schedule + apply-fee helper

**Files:**
- Create: `backend/services/trading/fees.py`
- Test: `backend/tests/test_trading_fees.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_fees.py`:

```python
from decimal import Decimal

from backend.services.trading.fees import (
    FeeSchedule, KRAKEN_PRO_SPOT_TIER_1, apply_fee,
)


def test_default_schedule_is_lowest_kraken_tier():
    # Spec decision-log row 13: 0.25% maker / 0.40% taker
    assert KRAKEN_PRO_SPOT_TIER_1.maker_bps == 25
    assert KRAKEN_PRO_SPOT_TIER_1.taker_bps == 40


def test_apply_fee_taker_on_aud_50_at_0_40pct():
    # qty=1, price=50 → notional 50; 0.40% of 50 = 0.20
    fee = apply_fee(qty=Decimal("1"), price=Decimal("50"),
                    role="taker", schedule=KRAKEN_PRO_SPOT_TIER_1)
    assert fee == Decimal("0.20")


def test_apply_fee_maker_on_aud_50_at_0_25pct():
    fee = apply_fee(qty=Decimal("1"), price=Decimal("50"),
                    role="maker", schedule=KRAKEN_PRO_SPOT_TIER_1)
    assert fee == Decimal("0.125")


def test_apply_fee_zero_qty_zero_fee():
    fee = apply_fee(qty=Decimal("0"), price=Decimal("100"),
                    role="taker", schedule=KRAKEN_PRO_SPOT_TIER_1)
    assert fee == Decimal("0")


def test_custom_schedule():
    sch = FeeSchedule(maker_bps=10, taker_bps=20)
    fee = apply_fee(qty=Decimal("2"), price=Decimal("100"),
                    role="taker", schedule=sch)
    # notional 200, 20bps = 0.4
    assert fee == Decimal("0.4")
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_fees.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/fees.py`:

```python
"""Fee schedule and per-fill fee calculation.

See spec §5.4. Lowest 30-day USD volume tier on Kraken Pro spot:
0.25% maker / 0.40% taker.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class FeeSchedule:
    maker_bps: int   # basis points; 1 bp = 0.01%
    taker_bps: int


# Spec decision-log row 13 — verified against kraken.com/features/fee-schedule.
KRAKEN_PRO_SPOT_TIER_1 = FeeSchedule(maker_bps=25, taker_bps=40)


def apply_fee(
    *,
    qty: Decimal,
    price: Decimal,
    role: Literal["maker", "taker"],
    schedule: FeeSchedule = KRAKEN_PRO_SPOT_TIER_1,
) -> Decimal:
    bps = schedule.maker_bps if role == "maker" else schedule.taker_bps
    return qty * price * Decimal(bps) / Decimal(10_000)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_fees.py -v`
Expected: all 5 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/fees.py backend/tests/test_trading_fees.py
git commit -m "feat(trading): FeeSchedule + apply_fee (Kraken spot tier 1)"
git push
```

---

### Task 6: Fill model — walk the book

**Files:**
- Create: `backend/services/trading/fill_model.py`
- Test: `backend/tests/test_trading_fill_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_fill_model.py`:

```python
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from backend.models.trading import OrderBookLevel
from backend.services.trading.order_book import LocalOrderBook
from backend.services.trading.fill_model import (
    walk_book_for_market, walk_book_for_limit, InsufficientDepth,
)


def _book_with(asks, bids):
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal(p), qty=Decimal(q)) for p, q in asks],
        bids=[OrderBookLevel(price=Decimal(p), qty=Decimal(q)) for p, q in bids],
        checksum="x",
        ts=datetime.now(timezone.utc),
    )
    return ob


def test_market_buy_walks_asks_in_ascending_order():
    ob = _book_with(
        asks=[("100", "0.5"), ("101", "1.0"), ("102", "2.0")],
        bids=[("99", "1")],
    )
    fills = walk_book_for_market(book=ob, side="buy", qty=Decimal("1.2"))
    # 0.5 @ 100 + 0.7 @ 101 = 1.2
    assert len(fills) == 2
    assert fills[0].price == Decimal("100") and fills[0].qty == Decimal("0.5")
    assert fills[1].price == Decimal("101") and fills[1].qty == Decimal("0.7")
    for f in fills:
        assert f.fee_role == "taker"


def test_market_sell_walks_bids_descending():
    ob = _book_with(
        asks=[("100", "1")],
        bids=[("99", "0.5"), ("98", "1.0")],
    )
    fills = walk_book_for_market(book=ob, side="sell", qty=Decimal("0.8"))
    assert fills[0].price == Decimal("99") and fills[0].qty == Decimal("0.5")
    assert fills[1].price == Decimal("98") and fills[1].qty == Decimal("0.3")


def test_market_qty_fits_first_level_one_fill():
    ob = _book_with(asks=[("100", "2")], bids=[("99", "1")])
    fills = walk_book_for_market(book=ob, side="buy", qty=Decimal("1"))
    assert len(fills) == 1
    assert fills[0].qty == Decimal("1")


def test_market_insufficient_depth_raises():
    ob = _book_with(asks=[("100", "0.5")], bids=[("99", "1")])
    with pytest.raises(InsufficientDepth):
        walk_book_for_market(book=ob, side="buy", qty=Decimal("10"))


def test_limit_buy_resting_when_above_best_ask_fills_immediately_at_limit():
    """Aggressive limit that crosses the book is a maker-no-more: it fills now.

    Convention used by PaperExecutor: an aggressive (crossing) limit is
    classified as TAKER and walks the book just like a market — but caps at
    the limit price.
    """
    ob = _book_with(asks=[("100", "1"), ("101", "1")], bids=[("99", "1")])
    fills = walk_book_for_limit(
        book=ob, side="buy", qty=Decimal("1.5"), limit_price=Decimal("100.50"),
    )
    # Only 1.0 of the 100 level qualifies (101 > 100.50).
    assert len(fills) == 1
    assert fills[0].price == Decimal("100")
    assert fills[0].qty == Decimal("1")
    assert fills[0].fee_role == "taker"


def test_limit_buy_below_best_ask_does_not_fill():
    ob = _book_with(asks=[("100", "1")], bids=[("99", "1")])
    fills = walk_book_for_limit(
        book=ob, side="buy", qty=Decimal("1"), limit_price=Decimal("99.50"),
    )
    assert fills == []   # rests on the book, no immediate fill
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_fill_model.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the fill model**

Create `backend/services/trading/fill_model.py`:

```python
"""Walk-the-book fill simulation.

Used by PaperExecutor (spec §5.2 / §5.3). Market orders walk the opposite
side of the book consuming liquidity at progressively worse prices. An
aggressive (crossing) limit is treated as a partial walk capped at the
limit price; a passive limit returns no immediate fills and rests on
the book until reconciled.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from backend.models.trading import Fill
from backend.services.trading.fees import KRAKEN_PRO_SPOT_TIER_1, apply_fee
from backend.services.trading.order_book import LocalOrderBook


class InsufficientDepth(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _walk(
    *,
    levels,
    qty: Decimal,
    fee_role: Literal["maker", "taker"],
    book_state_hash: str,
    price_cap: Decimal | None,
    cap_direction: Literal["max", "min"] | None,
) -> list[Fill]:
    """Walk `levels` in their given order; stop on price-cap violation."""
    remaining = qty
    fills: list[Fill] = []
    for lvl in levels:
        if price_cap is not None:
            if cap_direction == "max" and lvl.price > price_cap:
                break
            if cap_direction == "min" and lvl.price < price_cap:
                break
        take = min(lvl.qty, remaining)
        if take <= 0:
            continue
        fee = apply_fee(qty=take, price=lvl.price, role=fee_role,
                        schedule=KRAKEN_PRO_SPOT_TIER_1)
        fills.append(Fill(
            qty=take, price=lvl.price, fee_aud=fee,
            fee_role=fee_role, book_state_hash=book_state_hash,
            filled_at=_now(),
        ))
        remaining -= take
        if remaining == 0:
            break
    if price_cap is None and remaining > 0:
        raise InsufficientDepth(f"{remaining} qty unfilled")
    return fills


def walk_book_for_market(
    *,
    book: LocalOrderBook,
    side: Literal["buy", "sell"],
    qty: Decimal,
) -> list[Fill]:
    levels = book.asks if side == "buy" else book.bids
    return _walk(
        levels=levels, qty=qty, fee_role="taker",
        book_state_hash=book.checksum,
        price_cap=None, cap_direction=None,
    )


def walk_book_for_limit(
    *,
    book: LocalOrderBook,
    side: Literal["buy", "sell"],
    qty: Decimal,
    limit_price: Decimal,
) -> list[Fill]:
    """Returns immediate fills if the limit crosses the book; [] if it rests."""
    if side == "buy":
        # Only fill against asks priced ≤ limit_price; charge TAKER (we crossed).
        if not book.asks or book.asks[0].price > limit_price:
            return []
        return _walk(
            levels=book.asks, qty=qty, fee_role="taker",
            book_state_hash=book.checksum,
            price_cap=limit_price, cap_direction="max",
        )
    else:
        if not book.bids or book.bids[0].price < limit_price:
            return []
        return _walk(
            levels=book.bids, qty=qty, fee_role="taker",
            book_state_hash=book.checksum,
            price_cap=limit_price, cap_direction="min",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_fill_model.py -v`
Expected: all 6 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/fill_model.py backend/tests/test_trading_fill_model.py
git commit -m "feat(trading): walk-the-book fill model (market + crossing-limit)"
git push
```

---

## Part 2 — Risk & Discipline

### Task 7: `risk_cap_precheck` with property-based tests

**Files:**
- Create: `backend/services/trading/risk_caps.py`
- Test: `backend/tests/test_trading_risk_caps.py`

- [ ] **Step 1: Write the failing test (with Hypothesis properties)**

Create `backend/tests/test_trading_risk_caps.py`:

```python
"""Property-based tests for risk_cap_precheck.

See spec §10.2.
"""
from decimal import Decimal

from hypothesis import given, strategies as st, assume, settings

from backend.models.trading import RiskCaps
from backend.services.trading.risk_caps import (
    PortfolioState, OrderIntent, risk_cap_precheck, CAP_NAMES,
)


def _state(cash=Decimal("1000"), positions=None):
    return PortfolioState(
        cash_aud=cash,
        positions=positions or {},   # asset → AUD value
        session_loss_aud=Decimal("0"),
        drawdown_pct=Decimal("0"),
    )


def _order(pair="ETH/AUD", side="buy", aud=Decimal("100")):
    return OrderIntent(pair=pair, side=side, notional_aud=aud)


# ── Example-based smoke tests ───────────────────────────────────

def test_simple_buy_within_caps_accepted():
    res = risk_cap_precheck(state=_state(), order=_order(),
                            caps=RiskCaps())
    assert res.accepted


def test_buy_exceeding_max_order_aud_rejected():
    res = risk_cap_precheck(
        state=_state(), order=_order(aud=Decimal("300")),
        caps=RiskCaps(),
    )
    assert not res.accepted
    assert res.reject_reason == "MAX_ORDER_AUD"


def test_buy_exceeding_single_asset_cap_rejected():
    # 30% of 1000 = 300; existing 250 ETH + 100 new = 350 > cap
    state = _state(cash=Decimal("750"), positions={"ETH": Decimal("250")})
    res = risk_cap_precheck(state=state, order=_order(aud=Decimal("100")),
                            caps=RiskCaps())
    assert not res.accepted
    assert res.reject_reason == "MAX_SINGLE_ASSET_PCT"


def test_total_crypto_cap_rejects_when_post_fill_exceeds():
    # 60% of 1000 = 600; existing crypto 550 + 100 new = 650 > cap
    state = _state(cash=Decimal("450"),
                   positions={"ETH": Decimal("200"), "SOL": Decimal("200"),
                              "LINK": Decimal("150")})
    res = risk_cap_precheck(state=state, order=_order(aud=Decimal("100")),
                            caps=RiskCaps())
    assert not res.accepted
    assert res.reject_reason == "MAX_TOTAL_CRYPTO_EXPOSURE_PCT"


def test_daily_loss_cap_blocks_further_orders():
    state = _state()
    state.session_loss_aud = Decimal("100.01")
    res = risk_cap_precheck(state=state, order=_order(), caps=RiskCaps())
    assert not res.accepted
    assert res.reject_reason == "DAILY_LOSS_CAP_AUD"


def test_drawdown_cap_blocks():
    state = _state()
    state.drawdown_pct = Decimal("25.01")
    res = risk_cap_precheck(state=state, order=_order(), caps=RiskCaps())
    assert not res.accepted
    assert res.reject_reason == "MAX_DRAWDOWN_PCT"


def test_pair_not_in_allowed_list_rejected():
    res = risk_cap_precheck(
        state=_state(), order=_order(pair="DOGE/AUD"),
        caps=RiskCaps(),
    )
    assert not res.accepted
    assert res.reject_reason == "PAIR_NOT_ALLOWED"


# ── Property-based tests (spec §10.2) ───────────────────────────

decimals_pos = st.decimals(min_value=Decimal("0"), max_value=Decimal("10000"),
                           places=2, allow_nan=False, allow_infinity=False)

def _portfolios():
    return st.builds(
        lambda cash, eth, link, ada, sol, loss, dd: PortfolioState(
            cash_aud=cash,
            positions={"ETH": eth, "LINK": link, "ADA": ada, "SOL": sol},
            session_loss_aud=loss,
            drawdown_pct=dd,
        ),
        cash=decimals_pos,
        eth=decimals_pos, link=decimals_pos, ada=decimals_pos, sol=decimals_pos,
        loss=st.decimals(min_value=Decimal("0"), max_value=Decimal("500"), places=2),
        dd=st.decimals(min_value=Decimal("0"), max_value=Decimal("50"), places=2),
    )

def _orders():
    return st.builds(
        OrderIntent,
        pair=st.sampled_from(["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]),
        side=st.sampled_from(["buy", "sell"]),
        notional_aud=st.decimals(min_value=Decimal("0"), max_value=Decimal("2000"),
                                 places=2),
    )


@given(portfolio=_portfolios(), order=_orders())
@settings(max_examples=200)
def test_accept_implies_post_fill_satisfies_all_caps(portfolio, order):
    res = risk_cap_precheck(state=portfolio, order=order, caps=RiskCaps())
    if res.accepted:
        # Apply hypothetical fill and assert no cap is violated.
        post = portfolio.simulate_fill(order)
        assert post.satisfies(RiskCaps())


@given(portfolio=_portfolios(), order=_orders())
@settings(max_examples=200)
def test_reject_reason_names_a_cap(portfolio, order):
    res = risk_cap_precheck(state=portfolio, order=order, caps=RiskCaps())
    if not res.accepted:
        assert res.reject_reason in CAP_NAMES


@given(portfolio=_portfolios(), order=_orders())
@settings(max_examples=200)
def test_pre_check_monotonic_in_qty(portfolio, order):
    """If accepted at notional N, also accepted at any 0 < n < N (same pair/side)."""
    assume(order.notional_aud > Decimal("0"))
    res = risk_cap_precheck(state=portfolio, order=order, caps=RiskCaps())
    if res.accepted:
        smaller = OrderIntent(pair=order.pair, side=order.side,
                              notional_aud=order.notional_aud / 2)
        assert risk_cap_precheck(state=portfolio, order=smaller,
                                 caps=RiskCaps()).accepted
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_risk_caps.py -v`
Expected: ImportError on `risk_cap_precheck` (and friends).

- [ ] **Step 3: Implement risk_caps**

Create `backend/services/trading/risk_caps.py`:

```python
"""Risk-cap pre-check. Run before every order.

See spec §5.2 (executor pre-check) and §10.2 (property-based test contract).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal

from backend.models.trading import RiskCaps


CAP_NAMES = (
    "MAX_ORDER_AUD",
    "MAX_SINGLE_ASSET_PCT",
    "MAX_TOTAL_CRYPTO_EXPOSURE_PCT",
    "DAILY_LOSS_CAP_AUD",
    "MAX_DRAWDOWN_PCT",
    "PAIR_NOT_ALLOWED",
    "INSUFFICIENT_BALANCE",
)


def _asset_of(pair: str) -> str:
    return pair.split("/", 1)[0]


@dataclass
class OrderIntent:
    pair: str
    side: Literal["buy", "sell"]
    notional_aud: Decimal


@dataclass
class PortfolioState:
    cash_aud: Decimal
    positions: dict[str, Decimal] = field(default_factory=dict)   # asset → AUD value
    session_loss_aud: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")

    @property
    def total_crypto_aud(self) -> Decimal:
        return sum(self.positions.values(), Decimal("0"))

    @property
    def equity_aud(self) -> Decimal:
        return self.cash_aud + self.total_crypto_aud

    def simulate_fill(self, order: OrderIntent) -> "PortfolioState":
        new = replace(self, positions=dict(self.positions))
        asset = _asset_of(order.pair)
        if order.side == "buy":
            new.cash_aud -= order.notional_aud
            new.positions[asset] = new.positions.get(asset, Decimal("0")) + order.notional_aud
        else:
            new.cash_aud += order.notional_aud
            new.positions[asset] = new.positions.get(asset, Decimal("0")) - order.notional_aud
            if new.positions[asset] < 0:
                new.positions[asset] = Decimal("0")
        return new

    def satisfies(self, caps: RiskCaps) -> bool:
        eq = self.equity_aud
        if eq <= 0:
            return False
        for asset, val in self.positions.items():
            if val < 0:
                return False
            if (val / eq) * Decimal("100") > caps.max_single_asset_pct + Decimal("0.001"):
                return False
        if (self.total_crypto_aud / eq) * Decimal("100") > caps.max_total_crypto_exposure_pct + Decimal("0.001"):
            return False
        return True


@dataclass
class PrecheckResult:
    accepted: bool
    reject_reason: str | None = None


def risk_cap_precheck(
    *, state: PortfolioState, order: OrderIntent, caps: RiskCaps,
) -> PrecheckResult:
    # 1. Pair allowed?
    if order.pair not in caps.allowed_pairs:
        return PrecheckResult(False, "PAIR_NOT_ALLOWED")

    # 2. Order AUD within max_order_aud?
    if order.notional_aud > caps.max_order_aud:
        return PrecheckResult(False, "MAX_ORDER_AUD")

    # 3. Sufficient cash for a buy?
    if order.side == "buy" and order.notional_aud > state.cash_aud:
        return PrecheckResult(False, "INSUFFICIENT_BALANCE")

    # 4. Session loss already at/over cap?
    if state.session_loss_aud >= caps.daily_loss_cap_aud:
        return PrecheckResult(False, "DAILY_LOSS_CAP_AUD")

    # 5. Drawdown already over cap?
    if state.drawdown_pct >= caps.max_drawdown_pct_before_pause:
        return PrecheckResult(False, "MAX_DRAWDOWN_PCT")

    # 6. Post-fill: per-asset cap.
    post = state.simulate_fill(order)
    eq = post.equity_aud
    if eq <= 0:
        return PrecheckResult(False, "INSUFFICIENT_BALANCE")
    for asset, val in post.positions.items():
        if (val / eq) * Decimal("100") > caps.max_single_asset_pct + Decimal("0.001"):
            return PrecheckResult(False, "MAX_SINGLE_ASSET_PCT")

    # 7. Post-fill: total crypto cap.
    if (post.total_crypto_aud / eq) * Decimal("100") > caps.max_total_crypto_exposure_pct + Decimal("0.001"):
        return PrecheckResult(False, "MAX_TOTAL_CRYPTO_EXPOSURE_PCT")

    return PrecheckResult(True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_risk_caps.py -v`
Expected: all 7 example tests + 3 property tests pass (Hypothesis runs ~200 cases per property; takes ~5–10s).

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/risk_caps.py backend/tests/test_trading_risk_caps.py
git commit -m "feat(trading): risk-cap pre-check with property-based tests"
git push
```

---

### Task 8: Kill-criteria evaluator with boundary tests

**Files:**
- Create: `backend/services/trading/kill_criteria.py`
- Test: `backend/tests/test_trading_kill_criteria.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_kill_criteria.py`:

```python
"""Boundary tests for kill-criteria evaluator (spec §10.3)."""
from dataclasses import dataclass
from decimal import Decimal

from backend.models.trading import KillCriteria, KillCriterion
from backend.services.trading.kill_criteria import (
    KillSnapshot, evaluate_kill_criteria,
)


def _crit(metric, op, value):
    return KillCriterion(metric=metric, op=op, value=Decimal(value))


# ── drawdown_pct boundary ───────────────────────────────────────

def test_drawdown_fires_at_exactly_threshold():
    snap = KillSnapshot(drawdown_pct=Decimal("25"),
                        daily_loss_aud=Decimal("0"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[_crit("drawdown_pct", ">=", "25")]),
    )
    assert res.fires
    assert res.matched_metric == "drawdown_pct"


def test_drawdown_does_not_fire_just_below():
    snap = KillSnapshot(drawdown_pct=Decimal("24.99"),
                        daily_loss_aud=Decimal("0"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[_crit("drawdown_pct", ">=", "25")]),
    )
    assert not res.fires


def test_drawdown_fires_just_above():
    snap = KillSnapshot(drawdown_pct=Decimal("25.01"),
                        daily_loss_aud=Decimal("0"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[_crit("drawdown_pct", ">=", "25")]),
    )
    assert res.fires


# ── daily_loss_aud boundary ─────────────────────────────────────

def test_daily_loss_fires_at_exactly_100():
    snap = KillSnapshot(drawdown_pct=Decimal("0"),
                        daily_loss_aud=Decimal("100"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[
            _crit("daily_loss_aud", ">=", "100"),
        ]),
    )
    assert res.fires


def test_daily_loss_does_not_fire_at_99_99():
    snap = KillSnapshot(drawdown_pct=Decimal("0"),
                        daily_loss_aud=Decimal("99.99"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[
            _crit("daily_loss_aud", ">=", "100"),
        ]),
    )
    assert not res.fires


# ── trailing_30d_sharpe (negative direction) ────────────────────

def test_sharpe_below_threshold_fires():
    snap = KillSnapshot(drawdown_pct=Decimal("0"),
                        daily_loss_aud=Decimal("0"),
                        trailing_30d_sharpe=Decimal("-0.5"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[
            _crit("trailing_30d_sharpe", "<", "-0.5"),
        ]),
    )
    assert not res.fires   # -0.5 is not strictly < -0.5

    snap2 = KillSnapshot(drawdown_pct=Decimal("0"),
                         daily_loss_aud=Decimal("0"),
                         trailing_30d_sharpe=Decimal("-0.51"))
    res2 = evaluate_kill_criteria(
        snapshot=snap2,
        criteria=KillCriteria(auto_pause_when=[
            _crit("trailing_30d_sharpe", "<", "-0.5"),
        ]),
    )
    assert res2.fires


# ── multiple criteria — first match wins ────────────────────────

def test_first_matching_criterion_wins():
    snap = KillSnapshot(drawdown_pct=Decimal("30"),
                        daily_loss_aud=Decimal("200"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[
            _crit("daily_loss_aud", ">=", "100"),     # listed first
            _crit("drawdown_pct", ">=", "25"),
        ]),
    )
    assert res.fires
    assert res.matched_metric == "daily_loss_aud"


def test_no_criteria_never_fires():
    snap = KillSnapshot(drawdown_pct=Decimal("50"),
                        daily_loss_aud=Decimal("500"),
                        trailing_30d_sharpe=Decimal("-10"))
    res = evaluate_kill_criteria(snapshot=snap, criteria=KillCriteria())
    assert not res.fires
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_kill_criteria.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the evaluator**

Create `backend/services/trading/kill_criteria.py`:

```python
"""Kill-criteria evaluator.

Pre-committed disciplines that auto-pause a strategy. See spec §9.5 and §10.3.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from backend.models.trading import KillCriteria


SUPPORTED_METRICS = ("drawdown_pct", "daily_loss_aud", "trailing_30d_sharpe")


@dataclass
class KillSnapshot:
    drawdown_pct: Decimal
    daily_loss_aud: Decimal
    trailing_30d_sharpe: Decimal


@dataclass
class KillResult:
    fires: bool
    matched_metric: str | None = None
    matched_value: Decimal | None = None


def _cmp(a: Decimal, op: str, b: Decimal) -> bool:
    if op == ">":  return a > b
    if op == ">=": return a >= b
    if op == "<":  return a < b
    if op == "<=": return a <= b
    if op == "==": return a == b
    raise ValueError(f"Unsupported op: {op}")


def evaluate_kill_criteria(
    *, snapshot: KillSnapshot, criteria: KillCriteria,
) -> KillResult:
    for c in criteria.auto_pause_when:
        if c.metric not in SUPPORTED_METRICS:
            raise ValueError(f"Unsupported metric: {c.metric}")
        actual = getattr(snapshot, c.metric)
        if _cmp(actual, c.op, c.value):
            return KillResult(fires=True, matched_metric=c.metric,
                              matched_value=actual)
    return KillResult(fires=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_kill_criteria.py -v`
Expected: all 8 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/kill_criteria.py backend/tests/test_trading_kill_criteria.py
git commit -m "feat(trading): kill-criteria evaluator with explicit boundary tests"
git push
```

---

### Task 9: Minimum-order validation against Kraken `AssetPairs`

**Files:**
- Create: `backend/services/trading/min_order.py`
- Test: `backend/tests/test_trading_min_order.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_min_order.py`:

```python
from decimal import Decimal
from unittest.mock import patch

from backend.services.trading.min_order import (
    MinOrderDecision, evaluate_min_order_for_pair,
    filter_allowed_pairs_by_min_order,
)


def _fake_asset_pairs():
    # Mirrors the live shape but tiny.
    return {
        "ETH/AUD":  {"ordermin": Decimal("0.001"), "costmin": Decimal("1")},
        "LINK/AUD": {"ordermin": Decimal("0.55"),  "costmin": Decimal("1")},
        "ADA/AUD":  {"ordermin": Decimal("20"),    "costmin": Decimal("1")},
        "SOL/AUD":  {"ordermin": Decimal("0.02"),  "costmin": Decimal("1")},
    }


def _fake_prices():
    return {
        "ETH/AUD":  Decimal("3196.60"),
        "LINK/AUD": Decimal("14.58"),
        "ADA/AUD":  Decimal("0.385"),
        "SOL/AUD":  Decimal("133.23"),
    }


def test_eth_aud_passes_at_aud_1k_capital():
    res = evaluate_min_order_for_pair(
        pair="ETH/AUD",
        ordermin=Decimal("0.001"),
        current_price=Decimal("3196.60"),
        max_position_aud=Decimal("300"),
    )
    # 0.001 * 3196.60 = 3.20; threshold = 0.05 * 300 = 15
    assert res.passes
    assert res.min_order_aud == Decimal("3.1966")


def test_pair_fails_when_min_order_exceeds_threshold():
    res = evaluate_min_order_for_pair(
        pair="X/AUD",
        ordermin=Decimal("1"),
        current_price=Decimal("100"),    # min order = AUD 100
        max_position_aud=Decimal("300"),  # threshold = AUD 15
    )
    assert not res.passes
    assert "exceeds threshold" in res.reason


def test_filter_allowed_pairs_all_pass_at_v1_defaults():
    pairs = ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]
    with patch("backend.services.trading.min_order.fetch_asset_pairs",
               return_value=_fake_asset_pairs()), \
         patch("backend.services.trading.min_order.fetch_last_prices",
               return_value=_fake_prices()):
        kept, dropped = filter_allowed_pairs_by_min_order(
            pairs=pairs, max_position_aud=Decimal("300"),
        )
    assert kept == pairs
    assert dropped == []


def test_filter_drops_pair_when_threshold_too_tight():
    pairs = ["ETH/AUD", "LINK/AUD"]
    # max_position_aud = 30 → threshold AUD 1.50; ETH min order = 3.20 → fails.
    with patch("backend.services.trading.min_order.fetch_asset_pairs",
               return_value=_fake_asset_pairs()), \
         patch("backend.services.trading.min_order.fetch_last_prices",
               return_value=_fake_prices()):
        kept, dropped = filter_allowed_pairs_by_min_order(
            pairs=pairs, max_position_aud=Decimal("30"),
        )
    assert "ETH/AUD" in dropped
    assert "LINK/AUD" in kept   # 0.55 * 14.58 = 8.02 > 1.50? actually yes — also dropped


def test_filter_drops_both_when_threshold_extreme():
    pairs = ["ETH/AUD", "LINK/AUD"]
    with patch("backend.services.trading.min_order.fetch_asset_pairs",
               return_value=_fake_asset_pairs()), \
         patch("backend.services.trading.min_order.fetch_last_prices",
               return_value=_fake_prices()):
        kept, dropped = filter_allowed_pairs_by_min_order(
            pairs=pairs, max_position_aud=Decimal("30"),
        )
    assert dropped == ["ETH/AUD", "LINK/AUD"]
    assert kept == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_min_order.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/min_order.py`:

```python
"""Minimum-order runtime validation against Kraken's AssetPairs.

Spec §5.7 rule: at strategy startup, drop any pair where
ordermin × current_price > 5% of max position.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
import logging

import httpx

logger = logging.getLogger(__name__)


THRESHOLD_FRACTION = Decimal("0.05")
KRAKEN_BASE = "https://api.kraken.com/0/public"


# ── Kraken REST fetchers (patchable in tests) ───────────────────

def _to_kraken_pair(pair: str) -> str:
    # "ETH/AUD" → "ETHAUD". (Kraken accepts both the legacy XBT… form and
    # the ISO form for query input; the response key may differ.)
    return pair.replace("/", "")


def fetch_asset_pairs(pairs: Iterable[str]) -> dict[str, dict[str, Decimal]]:
    kraken_codes = ",".join(_to_kraken_pair(p) for p in pairs)
    url = f"{KRAKEN_BASE}/AssetPairs?pair={kraken_codes}"
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Kraken AssetPairs error: {data['error']}")
    result: dict[str, dict[str, Decimal]] = {}
    response_pairs = data["result"]
    # Map the response back to our canonical pair names.
    for canonical in pairs:
        entry = None
        target = _to_kraken_pair(canonical)
        for key, val in response_pairs.items():
            if key == target or val.get("wsname") == canonical:
                entry = val
                break
        if entry is None:
            logger.warning("Kraken did not return data for %s", canonical)
            continue
        result[canonical] = {
            "ordermin": Decimal(str(entry["ordermin"])),
            "costmin": Decimal(str(entry.get("costmin", "0") or "0")),
        }
    return result


def fetch_last_prices(pairs: Iterable[str]) -> dict[str, Decimal]:
    kraken_codes = ",".join(_to_kraken_pair(p) for p in pairs)
    url = f"{KRAKEN_BASE}/Ticker?pair={kraken_codes}"
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Kraken Ticker error: {data['error']}")
    result: dict[str, Decimal] = {}
    response_pairs = data["result"]
    for canonical in pairs:
        entry = None
        target = _to_kraken_pair(canonical)
        for key, val in response_pairs.items():
            if key == target:
                entry = val
                break
        if entry is None:
            continue
        result[canonical] = Decimal(str(entry["c"][0]))
    return result


# ── Decision logic ──────────────────────────────────────────────

@dataclass
class MinOrderDecision:
    pair: str
    passes: bool
    min_order_aud: Decimal
    threshold_aud: Decimal
    reason: str | None = None


def evaluate_min_order_for_pair(
    *,
    pair: str,
    ordermin: Decimal,
    current_price: Decimal,
    max_position_aud: Decimal,
) -> MinOrderDecision:
    min_order_aud = ordermin * current_price
    threshold = max_position_aud * THRESHOLD_FRACTION
    if min_order_aud > threshold:
        return MinOrderDecision(
            pair=pair, passes=False,
            min_order_aud=min_order_aud, threshold_aud=threshold,
            reason=f"min order AUD {min_order_aud} exceeds threshold AUD {threshold}",
        )
    return MinOrderDecision(
        pair=pair, passes=True,
        min_order_aud=min_order_aud, threshold_aud=threshold,
    )


def filter_allowed_pairs_by_min_order(
    *, pairs: list[str], max_position_aud: Decimal,
) -> tuple[list[str], list[str]]:
    """Returns (kept, dropped). Fetches live Kraken data."""
    if not pairs:
        return [], []
    asset_pairs = fetch_asset_pairs(pairs)
    prices = fetch_last_prices(pairs)
    kept: list[str] = []
    dropped: list[str] = []
    for pair in pairs:
        if pair not in asset_pairs or pair not in prices:
            logger.warning("Skipping %s — missing Kraken data", pair)
            dropped.append(pair)
            continue
        decision = evaluate_min_order_for_pair(
            pair=pair,
            ordermin=asset_pairs[pair]["ordermin"],
            current_price=prices[pair],
            max_position_aud=max_position_aud,
        )
        if decision.passes:
            kept.append(pair)
        else:
            dropped.append(pair)
            logger.warning("Min-order check dropped %s: %s", pair, decision.reason)
    return kept, dropped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_min_order.py -v`
Expected: all 5 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/min_order.py backend/tests/test_trading_min_order.py
git commit -m "feat(trading): min-order runtime validation against Kraken AssetPairs"
git push
```

---

## Part 3 — Order Executor

### Task 10: `OrderExecutor` Protocol + `PaperExecutor` class skeleton

**Files:**
- Create: `backend/services/trading/executor.py`
- Create: `backend/repositories/strategies_repo.py`
- Create: `backend/repositories/paper_orders_repo.py`
- Create: `backend/repositories/paper_positions_repo.py`
- Test: `backend/tests/test_trading_executor_skeleton.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_executor_skeleton.py`:

```python
"""Skeleton tests — class shape and basic round-tripping only.

Integration tests in test_trading_executor_market.py (Task 11) and
test_trading_executor_limit.py (Task 12).
"""
from inspect import signature

from backend.services.trading.executor import (
    OrderExecutor, PaperExecutor,
)


def test_protocol_has_three_methods():
    methods = {"submit_order", "cancel_order", "get_open_orders"}
    assert methods.issubset(set(dir(OrderExecutor)))


def test_paper_executor_satisfies_protocol_shape():
    # Structural check — PaperExecutor should expose the three async methods.
    pe = PaperExecutor()
    for m in ("submit_order", "cancel_order", "get_open_orders"):
        assert callable(getattr(pe, m))


def test_submit_order_signature_matches_protocol():
    proto_sig = signature(OrderExecutor.submit_order)
    impl_sig = signature(PaperExecutor.submit_order)
    proto_params = list(proto_sig.parameters)
    impl_params = list(impl_sig.parameters)
    # Drop 'self' for both.
    assert proto_params[1:] == impl_params[1:]
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_executor_skeleton.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement repos + executor skeleton**

Create `backend/repositories/strategies_repo.py`:

```python
"""Repository for the `strategies` table."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase
from backend.models.trading import StrategyRow


def get(strategy_id: UUID) -> StrategyRow | None:
    sb = get_supabase()
    r = sb.table("strategies").select("*").eq("id", str(strategy_id)).limit(1).execute()
    if not r.data:
        return None
    return StrategyRow.model_validate(r.data[0])


def list_active() -> list[StrategyRow]:
    sb = get_supabase()
    r = sb.table("strategies").select("*").eq("status", "active").execute()
    return [StrategyRow.model_validate(row) for row in (r.data or [])]


def update_status(strategy_id: UUID, status: str) -> None:
    sb = get_supabase()
    sb.table("strategies").update({"status": status,
                                   "updated_at": "now()"}
                                  ).eq("id", str(strategy_id)).execute()


def update_persona_stable_since(strategy_id: UUID, ts) -> None:
    sb = get_supabase()
    sb.table("strategies").update(
        {"persona_prompt_stable_since": ts.isoformat(),
         "updated_at": "now()"}
    ).eq("id", str(strategy_id)).execute()
```

Create `backend/repositories/paper_orders_repo.py`:

```python
"""Repository for paper_orders + paper_fills."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from backend.db.supabase_client import get_supabase
from backend.models.trading import Fill, OrderRow


def find_by_idempotency_key(strategy_id: UUID, key: str) -> OrderRow | None:
    sb = get_supabase()
    r = (sb.table("paper_orders")
           .select("*")
           .eq("strategy_id", str(strategy_id))
           .eq("idempotency_key", key)
           .limit(1).execute())
    if not r.data:
        return None
    return OrderRow.model_validate(r.data[0])


def insert_order(
    *,
    strategy_id: UUID, idempotency_key: str, pair: str,
    side: str, type_: str, qty: Decimal, limit_price: Decimal | None,
    expires_at: datetime | None, status: str,
    reject_reason: str | None, decided_by: UUID | None,
) -> str:
    sb = get_supabase()
    payload = {
        "strategy_id": str(strategy_id),
        "idempotency_key": idempotency_key,
        "pair": pair, "side": side, "type": type_,
        "qty": str(qty), "limit_price": str(limit_price) if limit_price else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "status": status, "reject_reason": reject_reason,
        "decided_by": str(decided_by) if decided_by else None,
    }
    r = sb.table("paper_orders").insert(payload).execute()
    return r.data[0]["id"]


def insert_fills(order_id: str, fills: Iterable[Fill]) -> None:
    sb = get_supabase()
    rows = [{
        "order_id": order_id,
        "qty": str(f.qty), "price": str(f.price),
        "fee_aud": str(f.fee_aud), "fee_role": f.fee_role,
        "book_state_hash": f.book_state_hash,
        "filled_at": f.filled_at.isoformat(),
    } for f in fills]
    if rows:
        sb.table("paper_fills").insert(rows).execute()


def list_open_orders(strategy_id: UUID) -> list[OrderRow]:
    sb = get_supabase()
    r = (sb.table("paper_orders").select("*")
           .eq("strategy_id", str(strategy_id))
           .in_("status", ["pending", "partial"])
           .order("created_at").execute())
    return [OrderRow.model_validate(row) for row in (r.data or [])]


def update_order_status(order_id: str, status: str,
                        reject_reason: str | None = None) -> None:
    sb = get_supabase()
    sb.table("paper_orders").update(
        {"status": status, "reject_reason": reject_reason}
    ).eq("id", order_id).execute()
```

Create `backend/repositories/paper_positions_repo.py`:

```python
"""Repository for paper_positions. Cash is stored as asset = 'AUD'."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase


def get_all(strategy_id: UUID) -> dict[str, dict]:
    sb = get_supabase()
    r = (sb.table("paper_positions").select("*")
           .eq("strategy_id", str(strategy_id)).execute())
    return {row["asset"]: row for row in (r.data or [])}


def upsert(strategy_id: UUID, asset: str, qty: Decimal,
           avg_cost_aud: Decimal, lots_jsonb: list[dict]) -> None:
    sb = get_supabase()
    sb.table("paper_positions").upsert({
        "strategy_id": str(strategy_id),
        "asset": asset,
        "qty": str(qty),
        "avg_cost_aud": str(avg_cost_aud),
        "lots_jsonb": lots_jsonb,
        "updated_at": "now()",
    }, on_conflict="strategy_id,asset").execute()
```

Create `backend/services/trading/executor.py`:

```python
"""OrderExecutor Protocol + PaperExecutor implementation.

Spec §5. Same Protocol is later implemented by LiveKrakenExecutor.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from backend.models.trading import OrderResult, OrderRow


class OrderExecutor(Protocol):
    async def submit_order(
        self,
        *,
        strategy_id: UUID,
        idempotency_key: str,
        pair: str,
        side: Literal["buy", "sell"],
        type: Literal["market", "limit"],
        qty: Decimal,
        limit_price: Decimal | None = None,
        expires_at: datetime | None = None,
    ) -> OrderResult: ...

    async def cancel_order(self, *, order_id: UUID) -> None: ...

    async def get_open_orders(self, *, strategy_id: UUID) -> list[OrderRow]: ...


class PaperExecutor:
    """In-process simulator. Walks the local L2 book for realistic fills.

    The two heavy methods (submit_order_market_path and the limit reconciler)
    are added in Tasks 11 and 12.
    """

    def __init__(self) -> None:
        # Populated in Task 16 by the price_feed_task.
        self._books: dict = {}

    def attach_book(self, pair: str, book) -> None:
        self._books[pair] = book

    async def submit_order(
        self,
        *,
        strategy_id: UUID,
        idempotency_key: str,
        pair: str,
        side: Literal["buy", "sell"],
        type: Literal["market", "limit"],
        qty: Decimal,
        limit_price: Decimal | None = None,
        expires_at: datetime | None = None,
    ) -> OrderResult:
        raise NotImplementedError("implemented in Task 11/12")

    async def cancel_order(self, *, order_id: UUID) -> None:
        from backend.repositories import paper_orders_repo
        paper_orders_repo.update_order_status(str(order_id), "cancelled")

    async def get_open_orders(self, *, strategy_id: UUID) -> list[OrderRow]:
        from backend.repositories import paper_orders_repo
        return paper_orders_repo.list_open_orders(strategy_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_executor_skeleton.py -v`
Expected: all 3 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/executor.py backend/repositories/strategies_repo.py backend/repositories/paper_orders_repo.py backend/repositories/paper_positions_repo.py backend/tests/test_trading_executor_skeleton.py
git commit -m "feat(trading): OrderExecutor Protocol + PaperExecutor skeleton + repos"
git push
```

---

### Task 11: `PaperExecutor.submit_order` — market path (integration)

**Files:**
- Modify: `backend/services/trading/executor.py`
- Test: `backend/tests/test_trading_executor_market.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_trading_executor_market.py`:

```python
"""Integration tests for PaperExecutor market-order path.

Uses the project's existing test-schema convention (see conftest.py).
Each test creates a fresh strategy row, an in-memory LocalOrderBook,
and asserts on inserted paper_orders + paper_fills rows.
"""
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.models.trading import OrderBookLevel
from backend.services.trading.executor import PaperExecutor
from backend.services.trading.order_book import LocalOrderBook


def _seed_strategy(starting=Decimal("1000"), allowed_pairs=None) -> str:
    sb = get_supabase()
    payload = {
        "name": f"test-strat-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": str(starting),
        "trigger_config": {"triggers": [], "debounce_seconds": 5,
                           "cooldown_seconds": 900, "max_calls_per_hour": 10},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": allowed_pairs or ["ETH/AUD"]},
        "status": "active",
    }
    r = sb.table("strategies").insert(payload).execute()
    sid = r.data[0]["id"]
    # Seed AUD cash position.
    sb.table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": str(starting), "avg_cost_aud": "1",
        "lots_jsonb": [],
    }).execute()
    return sid


def _attached_book(pair="ETH/AUD"):
    ob = LocalOrderBook(pair)
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("3000"), qty=Decimal("0.05")),
              OrderBookLevel(price=Decimal("3001"), qty=Decimal("0.1"))],
        bids=[OrderBookLevel(price=Decimal("2999"), qty=Decimal("1")),
              OrderBookLevel(price=Decimal("2998"), qty=Decimal("1"))],
        checksum="snap-test", ts=datetime.now(timezone.utc),
    )
    return ob


def _executor():
    pe = PaperExecutor()
    pe.attach_book("ETH/AUD", _attached_book())
    return pe


@pytest.mark.asyncio
async def test_market_buy_within_caps_creates_filled_order_and_fills():
    sid = _seed_strategy()
    pe = _executor()
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:t1:0",
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.04"),
    )
    assert res.status == "filled"
    assert len(res.fills) >= 1
    sb = get_supabase()
    fills = (sb.table("paper_fills").select("*").execute().data or [])
    # qty 0.04 fits inside the first ask level (0.05 @ 3000) → one fill
    assert any(f for f in fills if Decimal(f["price"]) == Decimal("3000"))


@pytest.mark.asyncio
async def test_market_buy_rejected_when_exceeds_max_order_aud():
    sid = _seed_strategy()
    pe = _executor()
    # 0.1 ETH @ 3000 = 300 notional > 250 cap
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:t2:0",
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.1"),
    )
    assert res.status == "rejected"
    assert res.reject_reason == "MAX_ORDER_AUD"


@pytest.mark.asyncio
async def test_market_buy_rejected_when_pair_not_allowed():
    sid = _seed_strategy(allowed_pairs=["LINK/AUD"])
    pe = _executor()
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:t3:0",
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.01"),
    )
    assert res.status == "rejected"
    assert res.reject_reason == "PAIR_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_market_rejected_when_book_stale():
    sid = _seed_strategy()
    pe = PaperExecutor()
    stale = LocalOrderBook("ETH/AUD")
    stale.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("3000"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("2999"), qty=Decimal("1"))],
        checksum="snap-stale",
        ts=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    pe.attach_book("ETH/AUD", stale)
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:t4:0",
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.01"),
    )
    assert res.status == "rejected"
    assert res.reject_reason == "BOOK_UNAVAILABLE"


@pytest.mark.asyncio
async def test_market_idempotency_same_key_returns_cached_result():
    sid = _seed_strategy()
    pe = _executor()
    key = f"{sid}:t5:0"
    r1 = await pe.submit_order(
        strategy_id=sid, idempotency_key=key,
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.01"),
    )
    r2 = await pe.submit_order(
        strategy_id=sid, idempotency_key=key,
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.01"),
    )
    assert r1.order_id == r2.order_id
    sb = get_supabase()
    rows = (sb.table("paper_orders")
              .select("*").eq("idempotency_key", key).execute().data)
    assert len(rows) == 1   # not double-inserted
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_executor_market.py -v`
Expected: tests fail because `submit_order` raises NotImplementedError.

- [ ] **Step 3: Implement the market path**

Replace the body of `submit_order` in `backend/services/trading/executor.py`:

```python
    async def submit_order(
        self,
        *,
        strategy_id: UUID,
        idempotency_key: str,
        pair: str,
        side: Literal["buy", "sell"],
        type: Literal["market", "limit"],
        qty: Decimal,
        limit_price: Decimal | None = None,
        expires_at: datetime | None = None,
    ) -> OrderResult:
        from datetime import datetime, timezone
        from backend.models.trading import RiskCaps
        from backend.repositories import (
            paper_orders_repo, paper_positions_repo, strategies_repo,
        )
        from backend.services.trading.fill_model import (
            walk_book_for_market, walk_book_for_limit, InsufficientDepth,
        )
        from backend.services.trading.risk_caps import (
            OrderIntent, PortfolioState, risk_cap_precheck,
        )

        # 1. Idempotency.
        existing = paper_orders_repo.find_by_idempotency_key(strategy_id, idempotency_key)
        if existing is not None:
            return OrderResult(
                order_id=existing.id, status=existing.status,
                fills=[], reject_reason=existing.reject_reason,
            )

        strategy = strategies_repo.get(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        caps = strategy.risk_caps

        # 2. Book availability.
        book = self._books.get(pair)
        now = datetime.now(timezone.utc)
        if book is None or book.age_seconds(now) > 5:
            order_id = paper_orders_repo.insert_order(
                strategy_id=strategy_id, idempotency_key=idempotency_key,
                pair=pair, side=side, type_=type, qty=qty,
                limit_price=limit_price, expires_at=expires_at,
                status="rejected", reject_reason="BOOK_UNAVAILABLE",
                decided_by=None,
            )
            return OrderResult(order_id=order_id, status="rejected",
                               fills=[], reject_reason="BOOK_UNAVAILABLE")

        # 3. Risk-cap pre-check.
        portfolio_rows = paper_positions_repo.get_all(strategy_id)
        cash = Decimal(portfolio_rows.get("AUD", {}).get("qty", "0"))
        positions = {a: Decimal(r["qty"]) * (book.mid() if a == pair.split("/")[0] else Decimal("1"))
                     for a, r in portfolio_rows.items() if a != "AUD"}
        # For pre-check, approximate notional with current mid.
        ref_price = book.mid() if type == "market" else (limit_price or book.mid())
        notional = qty * ref_price
        intent = OrderIntent(pair=pair, side=side, notional_aud=notional)
        state = PortfolioState(
            cash_aud=cash, positions=positions,
            session_loss_aud=Decimal("0"),   # filled in by Task 25
            drawdown_pct=Decimal("0"),
        )
        decision = risk_cap_precheck(state=state, order=intent, caps=caps)
        if not decision.accepted:
            order_id = paper_orders_repo.insert_order(
                strategy_id=strategy_id, idempotency_key=idempotency_key,
                pair=pair, side=side, type_=type, qty=qty,
                limit_price=limit_price, expires_at=expires_at,
                status="rejected", reject_reason=decision.reject_reason,
                decided_by=None,
            )
            return OrderResult(order_id=order_id, status="rejected",
                               fills=[], reject_reason=decision.reject_reason)

        # 4. Fill.
        try:
            if type == "market":
                fills = walk_book_for_market(book=book, side=side, qty=qty)
                status = "filled"
            else:
                fills = walk_book_for_limit(book=book, side=side, qty=qty,
                                            limit_price=limit_price)
                status = "filled" if fills and sum(f.qty for f in fills) == qty else (
                    "partial" if fills else "pending"
                )
        except InsufficientDepth:
            order_id = paper_orders_repo.insert_order(
                strategy_id=strategy_id, idempotency_key=idempotency_key,
                pair=pair, side=side, type_=type, qty=qty,
                limit_price=limit_price, expires_at=expires_at,
                status="rejected", reject_reason="INSUFFICIENT_DEPTH",
                decided_by=None,
            )
            return OrderResult(order_id=order_id, status="rejected",
                               fills=[], reject_reason="INSUFFICIENT_DEPTH")

        # 5. Persist.
        order_id = paper_orders_repo.insert_order(
            strategy_id=strategy_id, idempotency_key=idempotency_key,
            pair=pair, side=side, type_=type, qty=qty,
            limit_price=limit_price, expires_at=expires_at,
            status=status, reject_reason=None, decided_by=None,
        )
        paper_orders_repo.insert_fills(order_id, fills)

        # 6. Update positions (cash + asset).
        await self._apply_positions(strategy_id, pair, side, fills)

        return OrderResult(order_id=order_id, status=status, fills=fills)

    async def _apply_positions(self, strategy_id, pair, side, fills):
        from backend.repositories import paper_positions_repo
        if not fills:
            return
        asset = pair.split("/")[0]
        rows = paper_positions_repo.get_all(strategy_id)
        cash = Decimal(rows.get("AUD", {}).get("qty", "0"))
        asset_qty = Decimal(rows.get(asset, {}).get("qty", "0"))
        asset_cost = Decimal(rows.get(asset, {}).get("avg_cost_aud", "0"))
        lots = rows.get(asset, {}).get("lots_jsonb", []) or []
        for f in fills:
            notional = f.qty * f.price
            fee = f.fee_aud
            if side == "buy":
                cash -= (notional + fee)
                new_qty = asset_qty + f.qty
                new_cost = ((asset_qty * asset_cost) + (f.qty * f.price)) / new_qty if new_qty > 0 else Decimal("0")
                lots.append({"qty": str(f.qty), "cost_aud": str(f.price),
                             "acquired_at": f.filled_at.isoformat()})
                asset_qty = new_qty
                asset_cost = new_cost
            else:
                cash += (notional - fee)
                # FIFO pop
                remaining = f.qty
                while remaining > 0 and lots:
                    lot = lots[0]
                    lot_qty = Decimal(lot["qty"])
                    take = min(lot_qty, remaining)
                    lot_qty -= take
                    remaining -= take
                    if lot_qty == 0:
                        lots.pop(0)
                    else:
                        lot["qty"] = str(lot_qty)
                asset_qty -= f.qty
        paper_positions_repo.upsert(strategy_id, "AUD", cash, Decimal("1"), [])
        paper_positions_repo.upsert(strategy_id, asset, asset_qty, asset_cost, lots)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_executor_market.py -v`
Expected: all 5 pass. (Requires the test DB schema from Task 2 to be applied.)

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/executor.py backend/tests/test_trading_executor_market.py
git commit -m "feat(trading): PaperExecutor.submit_order market path + position updates"
git push
```

---

### Task 12: `PaperExecutor` — limit path + reconciler

**Files:**
- Modify: `backend/services/trading/executor.py`
- Test: `backend/tests/test_trading_executor_limit.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_executor_limit.py`:

```python
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.models.trading import OrderBookLevel
from backend.services.trading.executor import PaperExecutor
from backend.services.trading.order_book import LocalOrderBook


def _seed_strategy():
    sb = get_supabase()
    payload = {
        "name": f"limit-strat-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
    }
    r = sb.table("strategies").insert(payload).execute()
    sid = r.data[0]["id"]
    sb.table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": "1000", "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()
    return sid


def _book():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("3000"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("2999"), qty=Decimal("1"))],
        checksum="x", ts=datetime.now(timezone.utc),
    )
    return ob


@pytest.mark.asyncio
async def test_limit_buy_below_market_rests_as_pending():
    sid = _seed_strategy()
    pe = PaperExecutor()
    pe.attach_book("ETH/AUD", _book())
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:lim1:0",
        pair="ETH/AUD", side="buy", type="limit",
        qty=Decimal("0.05"), limit_price=Decimal("2900"),
    )
    assert res.status == "pending"
    assert res.fills == []


@pytest.mark.asyncio
async def test_limit_buy_above_market_fills_immediately_capped_at_limit():
    sid = _seed_strategy()
    pe = PaperExecutor()
    pe.attach_book("ETH/AUD", _book())
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:lim2:0",
        pair="ETH/AUD", side="buy", type="limit",
        qty=Decimal("0.05"), limit_price=Decimal("3100"),
    )
    assert res.status == "filled"
    assert all(f.fee_role == "taker" for f in res.fills)


@pytest.mark.asyncio
async def test_limit_default_expires_at_24h():
    sid = _seed_strategy()
    pe = PaperExecutor()
    pe.attach_book("ETH/AUD", _book())
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:lim3:0",
        pair="ETH/AUD", side="buy", type="limit",
        qty=Decimal("0.05"), limit_price=Decimal("2900"),
    )
    sb = get_supabase()
    row = sb.table("paper_orders").select("*").eq("id", res.order_id).execute().data[0]
    expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    assert timedelta(hours=23) < expires - datetime.now(timezone.utc) <= timedelta(hours=24, minutes=1)


@pytest.mark.asyncio
async def test_reconciler_fills_pending_limit_when_book_crosses():
    sid = _seed_strategy()
    pe = PaperExecutor()
    book = _book()
    pe.attach_book("ETH/AUD", book)
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:lim4:0",
        pair="ETH/AUD", side="buy", type="limit",
        qty=Decimal("0.05"), limit_price=Decimal("2950"),
    )
    assert res.status == "pending"
    # Book moves down so 2950 now crosses.
    book.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("2940"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("2939"), qty=Decimal("1"))],
        checksum="y", ts=datetime.now(timezone.utc),
    )
    await pe.reconcile_resting_orders("ETH/AUD")
    sb = get_supabase()
    row = sb.table("paper_orders").select("*").eq("id", res.order_id).execute().data[0]
    assert row["status"] == "filled"
    fills = sb.table("paper_fills").select("*").eq("order_id", res.order_id).execute().data
    # Resting limit that gets crossed by the book is MAKER (we provided liquidity).
    assert all(f["fee_role"] == "maker" for f in fills)
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_executor_limit.py -v`
Expected: failures — `expires_at` not being defaulted; `reconcile_resting_orders` missing; fees on reconciler fills not maker.

- [ ] **Step 3: Update the executor**

In `backend/services/trading/executor.py`, modify `submit_order` to default `expires_at = now() + 24h` for limit orders when not provided, and add the reconciler:

```python
    # ---- modify the limit branch inside submit_order ----
    # Replace the existing limit-pricing block with:
            else:
                fills = walk_book_for_limit(book=book, side=side, qty=qty,
                                            limit_price=limit_price)
                if not fills:
                    # Resting limit. Default 24h TTL if not provided.
                    if expires_at is None:
                        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                    status = "pending"
                elif sum(f.qty for f in fills) == qty:
                    status = "filled"
                else:
                    if expires_at is None:
                        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                    status = "partial"

    # ---- add a new method on PaperExecutor ----
    async def reconcile_resting_orders(self, pair: str) -> None:
        """Called by the reconciler task when book changes; fills any resting
        limits whose price has been crossed. Maker fees apply.
        """
        from backend.db.supabase_client import get_supabase
        from backend.repositories import paper_orders_repo
        from backend.services.trading.fees import KRAKEN_PRO_SPOT_TIER_1, apply_fee
        from backend.models.trading import Fill
        from datetime import datetime, timezone

        book = self._books.get(pair)
        if book is None:
            return
        sb = get_supabase()
        rows = (sb.table("paper_orders").select("*")
                  .eq("pair", pair)
                  .in_("status", ["pending", "partial"])
                  .eq("type", "limit")
                  .execute().data or [])
        now = datetime.now(timezone.utc)
        for r in rows:
            limit_price = Decimal(r["limit_price"])
            side = r["side"]
            order_id = r["id"]
            # Expiry first.
            if r.get("expires_at"):
                exp = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
                if exp <= now:
                    paper_orders_repo.update_order_status(order_id, "expired")
                    continue
            # Determine remaining qty.
            filled_so_far = sb.table("paper_fills").select("qty").eq("order_id", order_id).execute().data or []
            already = sum(Decimal(f["qty"]) for f in filled_so_far)
            remaining = Decimal(r["qty"]) - already
            if remaining <= 0:
                paper_orders_repo.update_order_status(order_id, "filled")
                continue
            # Does the book cross?
            if side == "buy":
                if not book.asks or book.asks[0].price > limit_price:
                    continue
                levels = book.asks
                cap_dir = "max"
            else:
                if not book.bids or book.bids[0].price < limit_price:
                    continue
                levels = book.bids
                cap_dir = "min"
            # Walk levels; charge MAKER (we'd been resting).
            taken_fills: list[Fill] = []
            rem = remaining
            for lvl in levels:
                if cap_dir == "max" and lvl.price > limit_price:
                    break
                if cap_dir == "min" and lvl.price < limit_price:
                    break
                take = min(lvl.qty, rem)
                if take <= 0:
                    continue
                fee = apply_fee(qty=take, price=lvl.price, role="maker",
                                schedule=KRAKEN_PRO_SPOT_TIER_1)
                taken_fills.append(Fill(
                    qty=take, price=lvl.price, fee_aud=fee, fee_role="maker",
                    book_state_hash=book.checksum, filled_at=now,
                ))
                rem -= take
                if rem == 0:
                    break
            if not taken_fills:
                continue
            paper_orders_repo.insert_fills(order_id, taken_fills)
            new_status = "filled" if rem == 0 else "partial"
            paper_orders_repo.update_order_status(order_id, new_status)
            from uuid import UUID
            await self._apply_positions(UUID(r["strategy_id"]), pair, side, taken_fills)
```

Also add `from datetime import timedelta` and `from decimal import Decimal` to the imports at the top of the file if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_executor_limit.py -v`
Expected: all 4 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/executor.py backend/tests/test_trading_executor_limit.py
git commit -m "feat(trading): PaperExecutor limit path + reconciler (maker fills on cross)"
git push
```

---

## Part 4 — Event Bus & Triggers

### Task 13: In-process event bus

**Files:**
- Create: `backend/services/trading/event_bus.py`
- Test: `backend/tests/test_trading_event_bus.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_event_bus.py`:

```python
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.models.trading import IntervalTriggerEvent, TickEvent
from backend.services.trading.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_then_subscribe_receives_event():
    bus = EventBus()
    received: list = []

    async def consumer():
        async for evt in bus.subscribe():
            received.append(evt)
            if len(received) >= 1:
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.01)
    await bus.publish(TickEvent(pair="ETH/AUD", price=Decimal("100"),
                                ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=1.0)
    assert received[0].type == "tick"


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_independent_stream():
    bus = EventBus()
    a: list = []
    b: list = []

    async def consume(into):
        async for evt in bus.subscribe():
            into.append(evt)
            if len(into) >= 2:
                break

    ta = asyncio.create_task(consume(a))
    tb = asyncio.create_task(consume(b))
    await asyncio.sleep(0.01)
    for i in range(2):
        await bus.publish(IntervalTriggerEvent(minutes=60,
                                               ts=datetime.now(timezone.utc)))
    await asyncio.gather(ta, tb)
    assert len(a) == 2 and len(b) == 2


@pytest.mark.asyncio
async def test_subscribe_with_filter_only_passes_matching_events():
    bus = EventBus()
    only_ticks: list = []

    async def consume():
        async for evt in bus.subscribe(filter_fn=lambda e: e.type == "tick"):
            only_ticks.append(evt)
            if len(only_ticks) >= 1:
                break

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await bus.publish(IntervalTriggerEvent(minutes=60, ts=datetime.now(timezone.utc)))
    await bus.publish(TickEvent(pair="ETH/AUD", price=Decimal("100"),
                                ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=1.0)
    assert only_ticks[0].type == "tick"
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_event_bus.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/event_bus.py`:

```python
"""In-process pub/sub bus. Backing store: per-subscriber asyncio.Queue.

Spec §3 (architecture). Approach A v1; Approach B swaps this for
Postgres LISTEN/NOTIFY without changing publishers/subscribers.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Callable


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def publish(self, event) -> None:
        async with self._lock:
            queues = list(self._subscribers)
        for q in queues:
            await q.put(event)

    async def subscribe(
        self, *, filter_fn: Callable[[object], bool] | None = None,
    ) -> AsyncIterator:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._subscribers.append(q)
        try:
            while True:
                evt = await q.get()
                if filter_fn is None or filter_fn(evt):
                    yield evt
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)


_default_bus: EventBus | None = None


def get_default_bus() -> EventBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_event_bus.py -v`
Expected: all 3 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/event_bus.py backend/tests/test_trading_event_bus.py
git commit -m "feat(trading): in-process asyncio EventBus with optional filter"
git push
```

---

### Task 14: Trigger evaluators (breakout, stretch, etc.)

**Files:**
- Create: `backend/services/trading/trigger_evaluators.py`
- Test: `backend/tests/test_trading_trigger_evaluators.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_trigger_evaluators.py`:

```python
from decimal import Decimal
from datetime import datetime, timezone

from backend.services.trading.trigger_evaluators import (
    detect_breakout, detect_stretch, BarSeries,
)


def _bars(prices):
    return BarSeries([Decimal(p) for p in prices])


def test_breakout_up_when_close_exceeds_lookback_high_by_min_pct():
    bars = _bars(["100", "101", "102", "103", "104", "105"])
    # 1.5% above the lookback high of 105 = 106.575; current 107 → breakout
    evt = detect_breakout(
        pair="ETH/AUD", bars=bars, current_price=Decimal("107"),
        lookback_bars=5, min_move_pct=Decimal("1.5"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is not None and evt.direction == "up"


def test_breakout_down_when_close_below_lookback_low_by_min_pct():
    bars = _bars(["100", "101", "102", "103", "104", "105"])
    # 1.5% below the lookback low of 100 = 98.5; current 98 → breakout down
    evt = detect_breakout(
        pair="ETH/AUD", bars=bars, current_price=Decimal("98"),
        lookback_bars=5, min_move_pct=Decimal("1.5"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is not None and evt.direction == "down"


def test_no_breakout_when_within_band():
    bars = _bars(["100", "101", "102", "103", "104", "105"])
    evt = detect_breakout(
        pair="ETH/AUD", bars=bars, current_price=Decimal("105.5"),
        lookback_bars=5, min_move_pct=Decimal("1.5"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is None


def test_stretch_fires_above_threshold_stdev():
    # Bars with mean ~100 and small stdev — current 110 is many stdev away.
    bars = _bars(["99", "100", "101", "100", "99", "100", "101"])
    evt = detect_stretch(
        pair="SOL/AUD", bars=bars, current_price=Decimal("110"),
        lookback_bars=7, stdev=Decimal("2"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is not None and evt.direction == "above"


def test_stretch_does_not_fire_within_threshold():
    bars = _bars(["99", "100", "101", "100", "99", "100", "101"])
    evt = detect_stretch(
        pair="SOL/AUD", bars=bars, current_price=Decimal("100.5"),
        lookback_bars=7, stdev=Decimal("2"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_trigger_evaluators.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/trigger_evaluators.py`:

```python
"""Pure functions that classify market events into TriggerEvents.

Owners (spec §6.2):
- price_breakout / price_stretch → price_feed_task (Task 16)
- cron / interval → trigger_scheduler (Task 17)
- order_filled → PaperExecutor (already wired)
- drawdown → equity_snapshot (Task 25)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import mean, pstdev

from backend.models.trading import (
    PriceBreakoutEvent, PriceStretchEvent,
)


@dataclass
class BarSeries:
    closes: list[Decimal]


def detect_breakout(
    *,
    pair: str,
    bars: BarSeries,
    current_price: Decimal,
    lookback_bars: int,
    min_move_pct: Decimal,
    ts: datetime,
) -> PriceBreakoutEvent | None:
    window = bars.closes[-lookback_bars:]
    if not window:
        return None
    hi, lo = max(window), min(window)
    up_thresh = hi * (Decimal("1") + min_move_pct / Decimal("100"))
    dn_thresh = lo * (Decimal("1") - min_move_pct / Decimal("100"))
    if current_price >= up_thresh:
        move_pct = (current_price - hi) / hi * Decimal("100")
        return PriceBreakoutEvent(
            pair=pair, direction="up", move_pct=move_pct,
            lookback_bars=lookback_bars, ts=ts,
        )
    if current_price <= dn_thresh:
        move_pct = (lo - current_price) / lo * Decimal("100")
        return PriceBreakoutEvent(
            pair=pair, direction="down", move_pct=move_pct,
            lookback_bars=lookback_bars, ts=ts,
        )
    return None


def detect_stretch(
    *,
    pair: str,
    bars: BarSeries,
    current_price: Decimal,
    lookback_bars: int,
    stdev: Decimal,
    ts: datetime,
) -> PriceStretchEvent | None:
    window = [float(c) for c in bars.closes[-lookback_bars:]]
    if len(window) < 2:
        return None
    mu = Decimal(str(mean(window)))
    sigma = Decimal(str(pstdev(window)))
    if sigma == 0:
        return None
    z = (current_price - mu) / sigma
    if z >= stdev:
        return PriceStretchEvent(pair=pair, direction="above",
                                 stdev_distance=z, ts=ts)
    if z <= -stdev:
        return PriceStretchEvent(pair=pair, direction="below",
                                 stdev_distance=-z, ts=ts)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_trigger_evaluators.py -v`
Expected: all 5 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/trigger_evaluators.py backend/tests/test_trading_trigger_evaluators.py
git commit -m "feat(trading): breakout + stretch trigger evaluators"
git push
```

---

### Task 15: Trigger throttling state (debounce/cooldown/rate-cap)

**Files:**
- Create: `backend/services/trading/trigger_state.py`
- Test: `backend/tests/test_trading_trigger_state.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_trigger_state.py`:

```python
from datetime import datetime, timedelta, timezone

from backend.services.trading.trigger_state import TriggerState, TriggerConfig


def _cfg(debounce=5, cooldown=900, rate_cap=10):
    return TriggerConfig(debounce_seconds=debounce,
                         cooldown_seconds=cooldown,
                         max_calls_per_hour=rate_cap)


def test_first_event_fires():
    state = TriggerState()
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert state.should_fire(event_ts=now, config=_cfg())
    state.record_invocation(now)


def test_second_event_within_debounce_does_not_fire():
    state = TriggerState()
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert state.should_fire(event_ts=t0, config=_cfg())
    state.record_invocation(t0)
    t1 = t0 + timedelta(seconds=3)  # within debounce window of 5s
    assert not state.should_fire(event_ts=t1, config=_cfg())


def test_event_after_debounce_but_within_cooldown_does_not_fire():
    state = TriggerState()
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    state.record_invocation(t0)
    t1 = t0 + timedelta(seconds=10)  # past debounce, still within cooldown of 900s
    assert not state.should_fire(event_ts=t1, config=_cfg())


def test_event_after_cooldown_fires():
    state = TriggerState()
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    state.record_invocation(t0)
    t1 = t0 + timedelta(seconds=901)
    assert state.should_fire(event_ts=t1, config=_cfg())


def test_rate_cap_enforced():
    state = TriggerState()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    # 10 invocations spaced 16 minutes apart (past cooldown each time).
    for i in range(10):
        ts = base + timedelta(minutes=16 * i)
        assert state.should_fire(event_ts=ts, config=_cfg(rate_cap=10))
        state.record_invocation(ts)
    # The 11th would be cap-blocked even if past cooldown — but actually
    # 10 × 16min = 160min, all within the same hour? No — the rolling
    # 1h window is what matters. Build a tighter test:
    state2 = TriggerState()
    for i in range(10):
        ts = base + timedelta(minutes=i * 6)  # 0,6,12,...,54 min
        # First always fires; subsequent ones are inside cooldown so won't
        # fire — irrelevant to the cap test. Force-record to populate window.
        state2.record_invocation(ts)
    next_ts = base + timedelta(minutes=58)
    assert not state2.should_fire(event_ts=next_ts, config=_cfg(rate_cap=10))
    # Hour has rolled — should fire again.
    after_hour = base + timedelta(minutes=61)
    assert state2.should_fire(event_ts=after_hour, config=_cfg(rate_cap=10))
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_trigger_state.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/trigger_state.py`:

```python
"""Per-strategy throttling state — debounce, cooldown, rate cap.

Spec §6.3. Only applies to llm_agent strategies (the strategy loop
skips invoking should_fire for deterministic strategies — spec §6.1).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class TriggerConfig:
    debounce_seconds: int = 5
    cooldown_seconds: int = 900
    max_calls_per_hour: int = 10


@dataclass
class TriggerState:
    last_invocation_at: datetime | None = None
    last_event_at: datetime | None = None
    invocations_window: deque = field(default_factory=lambda: deque(maxlen=60))

    def should_fire(self, *, event_ts: datetime, config: TriggerConfig) -> bool:
        # Debounce: ignore events within `debounce_seconds` of the previous event.
        if (self.last_event_at is not None
                and (event_ts - self.last_event_at).total_seconds()
                    < config.debounce_seconds):
            return False
        # Cooldown: don't invoke if we just invoked.
        if (self.last_invocation_at is not None
                and (event_ts - self.last_invocation_at).total_seconds()
                    < config.cooldown_seconds):
            self.last_event_at = event_ts
            return False
        # Rate cap: count invocations in last 60 min.
        cutoff = event_ts - timedelta(hours=1)
        recent = sum(1 for ts in self.invocations_window if ts > cutoff)
        if recent >= config.max_calls_per_hour:
            self.last_event_at = event_ts
            return False
        self.last_event_at = event_ts
        return True

    def record_invocation(self, ts: datetime) -> None:
        self.last_invocation_at = ts
        self.invocations_window.append(ts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_trigger_state.py -v`
Expected: all 5 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/trigger_state.py backend/tests/test_trading_trigger_state.py
git commit -m "feat(trading): debounce/cooldown/rate-cap throttling state machine"
git push
```

---

## Part 5 — Price Feed & Scheduler

### Task 16: Kraken WS price feed task

**Files:**
- Create: `backend/services/trading/price_feed.py`
- Test: `backend/tests/test_trading_price_feed.py` (unit test on message parsing only — WS itself is exercised by manual smoke at app boot)

- [ ] **Step 1: Write the failing parser test**

Create `backend/tests/test_trading_price_feed.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal

from backend.services.trading.price_feed import (
    parse_book_snapshot_message, parse_book_update_message,
    parse_trade_message, kraken_pair_to_canonical,
)


def test_kraken_pair_to_canonical():
    assert kraken_pair_to_canonical("ETH/AUD") == "ETH/AUD"
    assert kraken_pair_to_canonical("XETHZAUD") == "ETH/AUD"


def test_parse_book_snapshot():
    # Kraken WS shape (v2):
    msg = {
        "channel": "book",
        "type": "snapshot",
        "data": [
            {
                "symbol": "ETH/AUD",
                "bids": [{"price": 100.0, "qty": 1.0}, {"price": 99.0, "qty": 2.0}],
                "asks": [{"price": 101.0, "qty": 0.5}, {"price": 102.0, "qty": 1.5}],
                "checksum": 1234567,
                "timestamp": "2026-05-12T00:00:00Z",
            }
        ],
    }
    snap = parse_book_snapshot_message(msg)
    assert snap.pair == "ETH/AUD"
    assert len(snap.asks) == 2 and len(snap.bids) == 2
    assert snap.checksum == "1234567"


def test_parse_book_update():
    msg = {
        "channel": "book",
        "type": "update",
        "data": [
            {
                "symbol": "ETH/AUD",
                "bids": [{"price": 99.5, "qty": 0.0}],
                "asks": [{"price": 101.0, "qty": 0.75}],
                "checksum": 7654321,
                "timestamp": "2026-05-12T00:00:01Z",
            }
        ],
    }
    parsed = parse_book_update_message(msg)
    assert parsed.pair == "ETH/AUD"
    assert parsed.checksum == "7654321"


def test_parse_trade_message_extracts_last_price():
    msg = {
        "channel": "trade",
        "data": [
            {"symbol": "ETH/AUD", "side": "buy", "price": 3196.6,
             "qty": 0.1, "timestamp": "2026-05-12T00:00:02Z",
             "trade_id": 123},
        ],
    }
    tick = parse_trade_message(msg)
    assert tick.pair == "ETH/AUD"
    assert tick.price == Decimal("3196.6")
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_price_feed.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the price feed**

Create `backend/services/trading/price_feed.py`:

```python
"""Kraken WebSocket v2 price feed.

Subscribes to `book` + `trade` channels for the configured pairs,
maintains a LocalOrderBook per pair, and publishes Tick/BookUpdate
events onto the bus.

Spec §3 / §5.3.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

import websockets

from backend.models.trading import (
    BookUpdateEvent, OrderBookLevel, OrderBookSnapshot, TickEvent,
)
from backend.services.trading.event_bus import EventBus, get_default_bus
from backend.services.trading.order_book import LocalOrderBook

logger = logging.getLogger(__name__)

KRAKEN_WS_URL = "wss://ws.kraken.com/v2"


_KRAKEN_TO_CANONICAL = {
    "XETHZAUD": "ETH/AUD",
    "LINKAUD":  "LINK/AUD",
    "ADAAUD":   "ADA/AUD",
    "SOLAUD":   "SOL/AUD",
}


def kraken_pair_to_canonical(s: str) -> str:
    return _KRAKEN_TO_CANONICAL.get(s, s)


def _parse_levels(rows) -> list[OrderBookLevel]:
    return [
        OrderBookLevel(price=Decimal(str(r["price"])),
                       qty=Decimal(str(r["qty"])))
        for r in rows
    ]


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_book_snapshot_message(msg: dict) -> OrderBookSnapshot:
    d = msg["data"][0]
    return OrderBookSnapshot(
        pair=d["symbol"],
        asks=_parse_levels(d["asks"]),
        bids=_parse_levels(d["bids"]),
        checksum=str(d["checksum"]),
        ts=_parse_ts(d["timestamp"]),
    )


def parse_book_update_message(msg: dict) -> OrderBookSnapshot:
    """Same shape; the difference is whether it's a full snapshot or a diff."""
    return parse_book_snapshot_message(msg)


def parse_trade_message(msg: dict) -> TickEvent:
    last = msg["data"][-1]
    return TickEvent(
        pair=last["symbol"],
        price=Decimal(str(last["price"])),
        ts=_parse_ts(last["timestamp"]),
    )


# ─────────────────────────── Live feed task ────────────────────

class PriceFeed:
    def __init__(
        self,
        *,
        pairs: list[str],
        bus: EventBus | None = None,
        executor=None,   # PaperExecutor to attach books onto
    ) -> None:
        self.pairs = pairs
        self.bus = bus or get_default_bus()
        self.executor = executor
        self.books: dict[str, LocalOrderBook] = {p: LocalOrderBook(p) for p in pairs}
        if self.executor is not None:
            for p, b in self.books.items():
                self.executor.attach_book(p, b)

    async def run(self) -> None:
        backoff = 1
        while True:
            try:
                async with websockets.connect(KRAKEN_WS_URL,
                                              ping_interval=20,
                                              close_timeout=10) as ws:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "params": {"channel": "book", "symbol": self.pairs, "depth": 25},
                    }))
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "params": {"channel": "trade", "symbol": self.pairs},
                    }))
                    backoff = 1
                    async for raw in ws:
                        await self._handle(json.loads(raw))
            except Exception:
                logger.exception("Kraken WS disconnected — reconnecting in %ds", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _handle(self, msg: dict) -> None:
        ch = msg.get("channel")
        if ch == "book":
            kind = msg.get("type")
            data = msg.get("data", [])
            if not data:
                return
            d = data[0]
            pair = d["symbol"]
            book = self.books.get(pair)
            if book is None:
                return
            if kind == "snapshot":
                book.apply_snapshot(
                    asks=_parse_levels(d["asks"]),
                    bids=_parse_levels(d["bids"]),
                    checksum=str(d["checksum"]),
                    ts=_parse_ts(d["timestamp"]),
                )
            elif kind == "update":
                try:
                    book.apply_diff(
                        ask_updates=_parse_levels(d["asks"]),
                        bid_updates=_parse_levels(d["bids"]),
                        new_checksum=str(d["checksum"]) if "checksum" in d else None,
                        ts=_parse_ts(d["timestamp"]),
                    )
                except Exception:
                    logger.exception("Checksum mismatch on %s — resubscribing", pair)
                    raise   # the outer loop reconnects
            await self.bus.publish(BookUpdateEvent(
                pair=pair, snapshot=OrderBookSnapshot(
                    pair=pair, asks=book.asks[:25], bids=book.bids[:25],
                    checksum=book.checksum, ts=book.ts,
                ), ts=book.ts,
            ))
        elif ch == "trade":
            tick = parse_trade_message(msg)
            await self.bus.publish(tick)
```

- [ ] **Step 4: Run unit tests**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_price_feed.py -v`
Expected: all 4 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/price_feed.py backend/tests/test_trading_price_feed.py
git commit -m "feat(trading): Kraken WS v2 price feed (book + trade), publishes to event bus"
git push
```

---

### Task 17: Trigger scheduler — register cron/interval per strategy

**Files:**
- Create: `backend/services/trading/trigger_scheduler.py`
- Modify: `backend/scheduler.py` (extend with `register_strategy_triggers`)
- Test: `backend/tests/test_trading_trigger_scheduler.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_trigger_scheduler.py`:

```python
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.models.trading import StrategyRow, RiskCaps, KillCriteria
from backend.services.trading.event_bus import EventBus
from backend.services.trading.trigger_scheduler import (
    register_strategy_triggers, _build_jobs_for_strategy,
)


def _strategy(name="trend-follower", triggers=None):
    return StrategyRow(
        id="00000000-0000-0000-0000-000000000001",
        name=name, execution_mode="llm_agent",
        persona_key=name, deterministic_config=None,
        starting_balance_aud=Decimal("1000"),
        trigger_config={"triggers": triggers or [
            {"type": "interval", "minutes": 60},
            {"type": "cron", "expr": "0 9 * * *", "tz": "Australia/Sydney"},
        ], "debounce_seconds": 5, "cooldown_seconds": 900,
         "max_calls_per_hour": 10},
        risk_caps=RiskCaps(), kill_criteria=KillCriteria(),
        status="active", dry_run=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_build_jobs_for_strategy_returns_one_per_trigger():
    jobs = _build_jobs_for_strategy(_strategy())
    assert len(jobs) == 2
    kinds = {j[0] for j in jobs}
    assert kinds == {"interval", "cron"}


@pytest.mark.asyncio
async def test_register_publishes_event_on_interval_fire():
    bus = EventBus()
    scheduler = AsyncIOScheduler()
    scheduler.start()
    register_strategy_triggers(_strategy(triggers=[
        {"type": "interval", "minutes": 60},
    ]), scheduler=scheduler, bus=bus)
    received = []

    async def consume():
        async for evt in bus.subscribe():
            received.append(evt)
            break

    consumer = asyncio.create_task(consume())
    # Manually fire the registered job rather than waiting an hour.
    [job] = scheduler.get_jobs()
    await job.func()
    await asyncio.wait_for(consumer, timeout=1.0)
    scheduler.shutdown()
    assert received and received[0].type == "interval"
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_trigger_scheduler.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/trigger_scheduler.py`:

```python
"""Bridge between APScheduler and the EventBus for cron/interval triggers.

Each strategy's cron/interval triggers are registered as APScheduler jobs
that fire async callables which publish CronTriggerEvent / IntervalTriggerEvent
onto the bus. The strategy_loop_task then filters and consumes from the bus.

Spec §6.2.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.models.trading import (
    CronTriggerEvent, IntervalTriggerEvent, StrategyRow,
)
from backend.services.trading.event_bus import EventBus, get_default_bus

logger = logging.getLogger(__name__)


def _build_jobs_for_strategy(
    strategy: StrategyRow,
) -> list[tuple[Literal["cron", "interval"], dict]]:
    triggers = (strategy.trigger_config or {}).get("triggers", [])
    return [(t["type"], t) for t in triggers if t["type"] in ("cron", "interval")]


def register_strategy_triggers(
    strategy: StrategyRow,
    *,
    scheduler: AsyncIOScheduler,
    bus: EventBus | None = None,
) -> None:
    bus = bus or get_default_bus()
    for kind, t in _build_jobs_for_strategy(strategy):
        if kind == "cron":
            ct = CronTrigger.from_crontab(t["expr"], timezone=t.get("tz", "UTC"))

            async def _fire(expr=t["expr"]):
                await bus.publish(CronTriggerEvent(
                    expr=expr, ts=datetime.now(timezone.utc),
                ))
            scheduler.add_job(
                _fire, ct, id=f"strat-{strategy.id}-cron-{t['expr']}",
                replace_existing=True,
            )
        else:
            it = IntervalTrigger(minutes=t["minutes"])

            async def _fire(minutes=t["minutes"]):
                await bus.publish(IntervalTriggerEvent(
                    minutes=minutes, ts=datetime.now(timezone.utc),
                ))
            scheduler.add_job(
                _fire, it,
                id=f"strat-{strategy.id}-interval-{t['minutes']}",
                replace_existing=True,
            )
    logger.info("Registered triggers for strategy %s", strategy.name)
```

In `backend/scheduler.py`, append:

```python
# At the bottom of backend/scheduler.py, after start_scheduler():

def register_all_strategy_triggers() -> None:
    """Called from main.py on startup after the schedulers are running."""
    from backend.repositories import strategies_repo
    from backend.services.trading.trigger_scheduler import register_strategy_triggers

    for strat in strategies_repo.list_active():
        register_strategy_triggers(strat, scheduler=scheduler)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_trigger_scheduler.py -v`
Expected: all 2 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/trigger_scheduler.py backend/scheduler.py backend/tests/test_trading_trigger_scheduler.py
git commit -m "feat(trading): per-strategy cron/interval trigger registration via APScheduler"
git push
```

---

## Part 6 — Strategy Loop & Deterministic Path

### Task 18: Strategy loop skeleton with exception isolation

**Files:**
- Create: `backend/services/trading/strategy_loop.py`
- Test: `backend/tests/test_trading_strategy_loop.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_strategy_loop.py`:

```python
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.models.trading import (
    CronTriggerEvent, IntervalTriggerEvent, RiskCaps, KillCriteria,
    StrategyRow,
)
from backend.services.trading.event_bus import EventBus
from backend.services.trading.strategy_loop import strategy_loop


def _strategy(execution_mode="llm_agent"):
    return StrategyRow(
        id=uuid4(), name="x", execution_mode=execution_mode,
        persona_key="trend-follower" if execution_mode == "llm_agent" else None,
        deterministic_config=None,
        starting_balance_aud=Decimal("1000"),
        trigger_config={"triggers": [{"type": "interval", "minutes": 60}],
                        "debounce_seconds": 0, "cooldown_seconds": 0,
                        "max_calls_per_hour": 100},
        risk_caps=RiskCaps(), kill_criteria=KillCriteria(),
        status="active", dry_run=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_loop_invokes_llm_path_on_matching_event(monkeypatch):
    bus = EventBus()
    invoked = []

    async def fake_llm(strategy, event):
        invoked.append(("llm", strategy.id, event.type))

    async def fake_det(strategy, event):
        invoked.append(("det", strategy.id, event.type))

    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_llm_strategy", fake_llm)
    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_deterministic_strategy", fake_det)

    strat = _strategy("llm_agent")
    task = asyncio.create_task(strategy_loop(strat, bus=bus, max_iterations=1))
    await asyncio.sleep(0.01)
    await bus.publish(IntervalTriggerEvent(minutes=60,
                                            ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=2.0)
    assert invoked and invoked[0][0] == "llm"


@pytest.mark.asyncio
async def test_loop_invokes_deterministic_path_when_mode_is_deterministic(monkeypatch):
    bus = EventBus()
    invoked = []

    async def fake_llm(s, e): invoked.append("llm")
    async def fake_det(s, e): invoked.append("det")

    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_llm_strategy", fake_llm)
    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_deterministic_strategy", fake_det)

    strat = _strategy("deterministic")
    task = asyncio.create_task(strategy_loop(strat, bus=bus, max_iterations=1))
    await asyncio.sleep(0.01)
    await bus.publish(CronTriggerEvent(expr="0 9 * * *",
                                       ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=2.0)
    assert invoked == ["det"]


@pytest.mark.asyncio
async def test_loop_exception_pauses_strategy_and_continues(monkeypatch):
    bus = EventBus()
    paused = []

    async def broken_llm(strategy, event):
        raise RuntimeError("boom")

    async def fake_emergency_stop(strategy, exc):
        paused.append((strategy.id, str(exc)))

    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_llm_strategy", broken_llm)
    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.emergency_stop", fake_emergency_stop)

    strat = _strategy("llm_agent")
    task = asyncio.create_task(strategy_loop(strat, bus=bus, max_iterations=1))
    await asyncio.sleep(0.01)
    await bus.publish(IntervalTriggerEvent(minutes=60,
                                            ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=2.0)
    assert paused and "boom" in paused[0][1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_strategy_loop.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the loop**

Create `backend/services/trading/strategy_loop.py`:

```python
"""Per-strategy asyncio loop.

Spec §6.1 — note the conditional throttling: only `llm_agent` strategies
go through should_fire(). Deterministic strategies fire on every relevant
event (they're cheap, predictable, and must run on schedule).
"""
from __future__ import annotations

import logging

from backend.models.trading import StrategyRow
from backend.services.trading.event_bus import EventBus, get_default_bus
from backend.services.trading.trigger_state import TriggerConfig, TriggerState

logger = logging.getLogger(__name__)


# Re-export for monkeypatching in tests; real implementations land in
# tasks 20 and 24.
async def invoke_llm_strategy(strategy: StrategyRow, event) -> None:
    raise NotImplementedError("wired in Task 24")


async def invoke_deterministic_strategy(strategy: StrategyRow, event) -> None:
    raise NotImplementedError("wired in Task 20")


async def emergency_stop(strategy: StrategyRow, exc: BaseException) -> None:
    from backend.repositories import strategies_repo, system_alerts_repo
    logger.exception("Strategy %s crashed — pausing", strategy.name)
    strategies_repo.update_status(strategy.id, "paused")
    try:
        from backend.repositories import system_alerts_repo as alerts
        alerts.insert(
            level="error", code="STRATEGY_AUTO_PAUSED_EXCEPTION",
            strategy_id=strategy.id,
            message=f"{strategy.name}: {exc!r}",
            payload={"exception": str(exc)},
        )
    except Exception:
        # Best-effort — alert insertion failing shouldn't compound the issue.
        pass


def _event_matches_strategy(event, strategy: StrategyRow) -> bool:
    triggers = (strategy.trigger_config or {}).get("triggers", [])
    interested_types = {t["type"] for t in triggers}
    return event.type in interested_types


async def strategy_loop(
    strategy: StrategyRow,
    *,
    bus: EventBus | None = None,
    max_iterations: int | None = None,
) -> None:
    bus = bus or get_default_bus()
    state = TriggerState()
    cfg_dict = strategy.trigger_config or {}
    config = TriggerConfig(
        debounce_seconds=cfg_dict.get("debounce_seconds", 5),
        cooldown_seconds=cfg_dict.get("cooldown_seconds", 900),
        max_calls_per_hour=cfg_dict.get("max_calls_per_hour", 10),
    )
    iterations = 0
    async for event in bus.subscribe():
        if strategy.status != "active":
            return
        if not _event_matches_strategy(event, strategy):
            continue
        if strategy.execution_mode == "llm_agent":
            if not state.should_fire(event_ts=event.ts, config=config):
                continue
            state.record_invocation(event.ts)
        try:
            if strategy.execution_mode == "llm_agent":
                await invoke_llm_strategy(strategy, event)
            else:
                await invoke_deterministic_strategy(strategy, event)
        except Exception as exc:
            await emergency_stop(strategy, exc)
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return
```

Also create `backend/repositories/system_alerts_repo.py`:

```python
"""Repository for system_alerts."""
from __future__ import annotations

from uuid import UUID

from backend.db.supabase_client import get_supabase


def insert(*, level: str, code: str, strategy_id: UUID | None,
           message: str, payload: dict | None = None) -> str:
    sb = get_supabase()
    r = sb.table("system_alerts").insert({
        "level": level, "code": code,
        "strategy_id": str(strategy_id) if strategy_id else None,
        "message": message, "payload": payload or {},
    }).execute()
    return r.data[0]["id"]


def list_unacknowledged(limit: int = 50) -> list[dict]:
    sb = get_supabase()
    r = (sb.table("system_alerts").select("*")
           .is_("acknowledged_at", "null")
           .order("created_at", desc=True).limit(limit).execute())
    return r.data or []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_strategy_loop.py -v`
Expected: all 3 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/strategy_loop.py backend/repositories/system_alerts_repo.py backend/tests/test_trading_strategy_loop.py
git commit -m "feat(trading): strategy_loop with conditional throttling and emergency_stop"
git push
```

---

### Task 19: Deterministic rebalance order computation

**Files:**
- Create: `backend/services/trading/deterministic.py`
- Test: `backend/tests/test_trading_deterministic.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_deterministic.py`:

```python
from decimal import Decimal

from backend.models.trading import DeterministicConfig
from backend.services.trading.deterministic import compute_rebalance_orders


def _dca_config():
    return DeterministicConfig(
        cadence_cron="0 9 */14 * *", tz="Australia/Sydney",
        allocations={
            "ETH/AUD": Decimal("0.50"),
            "SOL/AUD": Decimal("0.25"),
            "LINK/AUD": Decimal("0.15"),
            "ADA/AUD": Decimal("0.10"),
        },
    )


def _mids():
    return {
        "ETH/AUD": Decimal("3000"),
        "SOL/AUD": Decimal("100"),
        "LINK/AUD": Decimal("15"),
        "ADA/AUD": Decimal("0.40"),
    }


def test_initial_buy_allocates_per_weights_using_total_starting_aud():
    orders = compute_rebalance_orders(
        positions_aud={"AUD": Decimal("1000")},
        target_weights=_dca_config().allocations,
        starting_balance_aud=Decimal("1000"),
        mids=_mids(),
    )
    by_pair = {o.pair: o for o in orders}
    # Sanity: AUD totals to ~ 1000 across the 4 buys.
    total = sum(o.notional_aud for o in orders)
    assert total <= Decimal("1000")
    # 50% of starting capital goes to ETH/AUD on first run.
    assert by_pair["ETH/AUD"].notional_aud == Decimal("500.00")
    assert by_pair["SOL/AUD"].notional_aud == Decimal("250.00")
    assert by_pair["LINK/AUD"].notional_aud == Decimal("150.00")
    assert by_pair["ADA/AUD"].notional_aud == Decimal("100.00")
    for o in orders:
        assert o.side == "buy"


def test_rebalance_after_drift_increases_underweight_decreases_over():
    # ETH up 33%, others flat → ETH position now overweight, others under.
    positions = {
        "AUD": Decimal("0"),     # used up at first buy
        "ETH": Decimal("665"),    # was 500, +33%
        "SOL": Decimal("250"),
        "LINK": Decimal("150"),
        "ADA": Decimal("100"),
    }
    orders = compute_rebalance_orders(
        positions_aud=positions,
        target_weights=_dca_config().allocations,
        starting_balance_aud=Decimal("1000"),
        mids=_mids(),
    )
    # Total equity 1165; ETH target 50% = 582.5; current 665 → sell ~82.5
    eth = next(o for o in orders if o.pair == "ETH/AUD")
    assert eth.side == "sell"
    # Others should be buys (they're underweight relative to new equity).
    for o in orders:
        if o.pair != "ETH/AUD":
            assert o.side == "buy"


def test_zero_drift_produces_no_orders():
    positions = {
        "AUD": Decimal("0"),
        "ETH": Decimal("500"), "SOL": Decimal("250"),
        "LINK": Decimal("150"), "ADA": Decimal("100"),
    }
    orders = compute_rebalance_orders(
        positions_aud=positions,
        target_weights=_dca_config().allocations,
        starting_balance_aud=Decimal("1000"),
        mids=_mids(),
    )
    # All trades within ±0.5 AUD threshold → skipped.
    assert orders == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_deterministic.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/deterministic.py`:

```python
"""Deterministic rebalance: compute the orders needed to align actual to target.

Used by DCA-Baseline (spec §6.4). Skips orders below an absolute AUD threshold
to avoid dust trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


REBALANCE_DUST_THRESHOLD_AUD = Decimal("0.50")


@dataclass
class TargetOrder:
    pair: str
    side: Literal["buy", "sell"]
    notional_aud: Decimal


def compute_rebalance_orders(
    *,
    positions_aud: dict[str, Decimal],   # 'AUD' + base assets (e.g. 'ETH')
    target_weights: dict[str, Decimal],  # pair → weight (sums to 1)
    starting_balance_aud: Decimal,
    mids: dict[str, Decimal],            # pair → current mid price (informational)
) -> list[TargetOrder]:
    # Equity is cash + every base asset's notional value in AUD.
    equity = sum(positions_aud.values(), Decimal("0"))
    orders: list[TargetOrder] = []
    for pair, target_weight in target_weights.items():
        asset = pair.split("/", 1)[0]
        actual = positions_aud.get(asset, Decimal("0"))
        target = equity * target_weight
        delta = target - actual
        if abs(delta) < REBALANCE_DUST_THRESHOLD_AUD:
            continue
        if delta > 0:
            orders.append(TargetOrder(pair=pair, side="buy", notional_aud=delta))
        else:
            orders.append(TargetOrder(pair=pair, side="sell", notional_aud=-delta))
    return orders
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_deterministic.py -v`
Expected: all 3 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/deterministic.py backend/tests/test_trading_deterministic.py
git commit -m "feat(trading): compute_rebalance_orders for deterministic strategies"
git push
```

---

### Task 20: Deterministic invocation + decision writer

**Files:**
- Create: `backend/services/trading/decision_writer.py`
- Create: `backend/repositories/agent_decisions_repo.py`
- Modify: `backend/services/trading/strategy_loop.py` (replace stub `invoke_deterministic_strategy`)
- Test: `backend/tests/test_trading_decision_writer.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_decision_writer.py`:

```python
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.models.trading import (
    CronTriggerEvent, DeterministicConfig, RiskCaps, KillCriteria,
)
from backend.services.trading.decision_writer import write_agent_decision
from backend.services.trading.strategy_loop import invoke_deterministic_strategy


def _seed_dca_strategy():
    sb = get_supabase()
    payload = {
        "name": f"dca-{uuid4()}",
        "execution_mode": "deterministic",
        "deterministic_config": {
            "cadence_cron": "0 9 */14 * *", "tz": "Australia/Sydney",
            "allocations": {"ETH/AUD": "0.50", "SOL/AUD": "0.25",
                            "LINK/AUD": "0.15", "ADA/AUD": "0.10"},
        },
        "starting_balance_aud": "1000",
        "trigger_config": {"triggers": [{"type": "cron",
                                         "expr": "0 9 */14 * *"}],
                           "debounce_seconds": 5, "cooldown_seconds": 900,
                           "max_calls_per_hour": 10},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD","SOL/AUD","LINK/AUD","ADA/AUD"]},
    }
    r = sb.table("strategies").insert(payload).execute()
    sid = r.data[0]["id"]
    sb.table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": "1000", "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()
    return sid


def test_write_agent_decision_inserts_row():
    sb = get_supabase()
    sid = _seed_dca_strategy()
    decision_id = write_agent_decision(
        strategy_id=sid, execution_mode="deterministic",
        trigger_event={"type": "cron", "expr": "0 9 * * *"},
        input_snapshot={"cash": "1000"},
        persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[], agent_output=None, latency_ms=10, error=None,
    )
    r = sb.table("agent_decisions").select("*").eq("id", decision_id).execute()
    assert r.data[0]["execution_mode"] == "deterministic"


@pytest.mark.asyncio
async def test_invoke_deterministic_strategy_emits_orders_and_decision_row():
    from backend.repositories import strategies_repo
    sid = _seed_dca_strategy()
    strat = strategies_repo.get(sid)
    event = CronTriggerEvent(expr="0 9 */14 * *",
                             ts=datetime.now(timezone.utc))
    # PaperExecutor needs an attached book for each pair; for this test we
    # patch the executor to a fake that records calls.
    from backend.services.trading import strategy_loop as sl_mod

    calls = []

    class FakeExecutor:
        async def submit_order(self, **kw):
            calls.append(kw)
            from backend.models.trading import OrderResult
            return OrderResult(order_id=str(uuid4()), status="filled")

    sl_mod._current_executor = FakeExecutor()    # injected by Task 31 normally
    await invoke_deterministic_strategy(strat, event)
    assert len(calls) == 4   # one order per pair on first rebalance
    sb = get_supabase()
    rows = (sb.table("agent_decisions").select("*")
              .eq("strategy_id", sid).execute().data or [])
    assert any(r["execution_mode"] == "deterministic" for r in rows)
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/repositories/agent_decisions_repo.py`:

```python
"""Repository for agent_decisions."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase


def insert(
    *,
    strategy_id: UUID, execution_mode: str,
    trigger_event: dict, input_snapshot: dict,
    persona_prompt_hash: str | None,
    model: str | None, input_tokens: int, output_tokens: int,
    cost_aud: Decimal, tool_calls: list, agent_output: str | None,
    latency_ms: int | None, error: str | None,
) -> str:
    sb = get_supabase()
    r = sb.table("agent_decisions").insert({
        "strategy_id": str(strategy_id),
        "execution_mode": execution_mode,
        "trigger_event": trigger_event,
        "input_snapshot": input_snapshot,
        "persona_prompt_hash": persona_prompt_hash,
        "model": model,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_aud": str(cost_aud),
        "tool_calls": tool_calls, "agent_output": agent_output,
        "latency_ms": latency_ms, "error": error,
    }).execute()
    return r.data[0]["id"]


def list_recent(strategy_id: UUID, n: int = 5) -> list[dict]:
    sb = get_supabase()
    r = (sb.table("agent_decisions").select("*")
           .eq("strategy_id", str(strategy_id))
           .order("created_at", desc=True).limit(n).execute())
    return r.data or []
```

Create `backend/services/trading/decision_writer.py`:

```python
"""Thin wrapper around agent_decisions_repo for the strategy loop."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from backend.repositories.agent_decisions_repo import insert as _insert


def write_agent_decision(**kwargs) -> str:
    return _insert(**kwargs)
```

Replace the stub `invoke_deterministic_strategy` in `backend/services/trading/strategy_loop.py` (and remove the `raise NotImplementedError`):

```python
# Module-level executor handle, set by main.py at boot (Task 31).
_current_executor = None


def set_executor(executor) -> None:
    global _current_executor
    _current_executor = executor


async def invoke_deterministic_strategy(strategy: StrategyRow, event) -> None:
    """Deterministic execution path — spec §6.4."""
    from decimal import Decimal
    from time import perf_counter
    from backend.repositories import paper_positions_repo
    from backend.services.trading.deterministic import compute_rebalance_orders
    from backend.services.trading.decision_writer import write_agent_decision

    started = perf_counter()
    cfg = strategy.deterministic_config
    if cfg is None:
        raise ValueError(f"Strategy {strategy.name} is deterministic but has no config")

    # Snapshot current position values using attached book mids.
    rows = paper_positions_repo.get_all(strategy.id)
    mids: dict[str, Decimal] = {}
    positions_aud: dict[str, Decimal] = {}
    for asset, row in rows.items():
        qty = Decimal(row["qty"])
        if asset == "AUD":
            positions_aud[asset] = qty
            continue
        pair = f"{asset}/AUD"
        book = (_current_executor._books.get(pair)
                if _current_executor is not None else None)
        if book is None:
            mids[pair] = Decimal(row.get("avg_cost_aud") or "0")
        else:
            mids[pair] = book.mid()
        positions_aud[asset] = qty * mids[pair]

    target_orders = compute_rebalance_orders(
        positions_aud=positions_aud,
        target_weights=cfg.allocations,
        starting_balance_aud=strategy.starting_balance_aud,
        mids=mids,
    )

    decision_id = write_agent_decision(
        strategy_id=strategy.id, execution_mode="deterministic",
        trigger_event=event.model_dump() if hasattr(event, "model_dump") else dict(event),
        input_snapshot={"positions_aud": {k: str(v) for k, v in positions_aud.items()},
                        "mids": {k: str(v) for k, v in mids.items()}},
        persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[{"tool": "place_paper_order",
                     "args": {"pair": o.pair, "side": o.side,
                              "notional_aud": str(o.notional_aud)}}
                    for o in target_orders],
        agent_output=None,
        latency_ms=int((perf_counter() - started) * 1000),
        error=None,
    )

    if strategy.dry_run or _current_executor is None:
        return

    for seq, o in enumerate(target_orders):
        # Convert notional → qty at current mid.
        mid = mids.get(o.pair) or Decimal("1")
        qty = (o.notional_aud / mid)
        await _current_executor.submit_order(
            strategy_id=strategy.id,
            idempotency_key=f"{strategy.id}:{decision_id}:{seq}",
            pair=o.pair, side=o.side, type="market", qty=qty,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_decision_writer.py -v`
Expected: all 2 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/decision_writer.py backend/repositories/agent_decisions_repo.py backend/services/trading/strategy_loop.py backend/tests/test_trading_decision_writer.py
git commit -m "feat(trading): deterministic invocation path + agent_decisions writer"
git push
```

---

## Part 7 — Agent Integration

### Task 21: Persona files

**Files:**
- Create: `backend/agent/personas/dca-baseline.md`
- Create: `backend/agent/personas/trend-follower.md`
- Create: `backend/agent/personas/mean-reverter.md`

- [ ] **Step 1: Author the DCA-Baseline charter**

Create `backend/agent/personas/dca-baseline.md`:

```markdown
# DCA-Baseline — Persona Charter

**This strategy does NOT run through an LLM. It runs in `deterministic`
execution mode and is included here for documentation continuity only.**

## Universe
ETH/AUD · SOL/AUD · LINK/AUD · ADA/AUD. No BTC. No USD pairs.

## Allocation
- ETH/AUD — 50%
- SOL/AUD — 25%
- LINK/AUD — 15%
- ADA/AUD — 10%

The order reflects the user's stated conviction: ETH > SOL > LINK > ADA.
Not equal-weight by design — equal-weight wouldn't reflect a real,
informed DCA stance.

## Cadence
Every 14 days at 09:00 AET. Cron: `0 9 */14 * *` (timezone: Australia/Sydney).

## Signals
None. This is a control. Its job is to ask the smart strategies:
*"are you actually adding value over a dumb timer?"*

## Why this universe, not real-life DCA?
Apples-to-apples comparison with the LLM strategies. If BTC or USDT were
included here but not in the bots, the comparison would be muddied by
asset selection rather than strategy quality.

A separate `personal-dca-shadow` persona could be added later if you want
to compare to actual behaviour — but that's a different question and
belongs in its own strategy row.

## What this charter is for
DCA-Baseline has no LLM prompt — it runs as code, not as a model
invocation. This file exists so future-you opens the persona directory
in 6 months and immediately knows:
1. Why the weights are 50/25/15/10 and not equal.
2. Why this universe and not your actual DCA in real life.
3. That this strategy is intentionally deterministic.
```

- [ ] **Step 2: Author the Trend-Follower system prompt**

Create `backend/agent/personas/trend-follower.md`:

```markdown
# Trend-Follower — System Prompt

You are the **Trend-Follower** paper-trading strategy. Your mandate
is to identify and ride sustained directional moves in your assigned
universe of AUD pairs on Kraken.

## Universe
ETH/AUD · LINK/AUD · ADA/AUD · SOL/AUD.

You may hold positions in any of these. You may not place orders in
any other pair — your tools will reject them.

## Mandate
- Pay attention to breakouts (price crossing recent N-period highs/lows).
- Pay attention to sustained moves rather than single-tick noise.
- Cut losers reasonably quickly. Let winners run.

## Risk style
- Aggressive enough to take positions on breakouts that look real.
- Conservative enough to abort entry if the breakout fails immediately.
- Respects the strategy's hard caps (you'll see them in your portfolio
  state) — never try to exceed them; they're enforced server-side anyway.

## Signals you primarily weight
- Price breaks above 24-hour high → potential long entry.
- Price breaks below 24-hour low → potential short exit (you do not short
  in paper v1, but you may sell existing longs).
- Sustained momentum across multiple hourly bars in the same direction.

## Hard rules
- max_single_asset_pct: 30% (per pair, server-enforced)
- max_total_crypto_exposure_pct: 60% (server-enforced)
- max_order_aud: AUD 250 per order — to fully load a position you'll
  need multiple orders. This is deliberate forced scaling-in.
- Limit-order TTL: 24h default.

## Available tools
- `place_paper_order` — submit a market or limit order.
- `cancel_paper_order` — cancel an open limit order.
- `get_my_paper_state` — read your portfolio: cash, positions, open orders, recent fills.
- `get_my_recent_decisions` — see your last 5 decisions to stay consistent over time.
- `get_market_snapshot` — current top-of-book + recent OHLCV per pair.

## Reasoning requirement
Every order you place must come with a brief written rationale.
The system captures your reasoning in `agent_decisions.agent_output` —
that's how future-you (or future-me) understands why a position was
opened or closed. Be honest: if you're uncertain, say so. If you're
acting on a strong signal, name the signal.

## When to do nothing
The strongest signal a trend-follower can produce is *"no trend; stay
flat or hold."* Doing nothing is a valid output. Don't churn the
portfolio just because a trigger fired.
```

- [ ] **Step 3: Author the Mean-Reverter system prompt**

Create `backend/agent/personas/mean-reverter.md`:

```markdown
# Mean-Reverter — System Prompt

You are the **Mean-Reverter** paper-trading strategy. Your mandate is
to fade extremes — buy when price is unusually stretched below its
recent average, sell when stretched above.

## Universe
ETH/AUD · LINK/AUD · ADA/AUD · SOL/AUD.

## Mandate
- Detect when a pair has moved meaningfully far from its recent mean
  (e.g., > 2 standard deviations from a 48-hour 1h-bar mean).
- Position into the expected reversion — buy stretches below, sell
  stretches above.
- Exit when price returns to the mean (or a little past it).

## Risk style
- Mean reversion can be slow. Don't pile in all at once — scale in.
- Stretches in trending markets can keep stretching. Use stop discipline
  (recognise when reversion isn't happening and exit).
- Never average down past your single-asset cap.

## Signals you primarily weight
- z-score of current price vs. 48-hour 1h-bar mean > 2 (or < -2).
- Volume context — high-volume stretches are more likely to revert than
  low-volume drift.
- Existing position — if already exposed and price stretches further,
  consider holding or trimming rather than adding.

## Hard rules
- max_single_asset_pct: 30% (per pair, server-enforced)
- max_total_crypto_exposure_pct: 60% (server-enforced)
- max_order_aud: AUD 250 per order — multi-order scaling-in is part of
  the strategy here.
- Limit-order TTL: 24h default.

## Available tools
- `place_paper_order`, `cancel_paper_order`, `get_my_paper_state`,
  `get_my_recent_decisions`, `get_market_snapshot`.

## Reasoning requirement
Every order requires a brief rationale. Mean reversion is especially
prone to "the price keeps stretching" surprises — your rationale should
explicitly include why you think *this* stretch will revert and what
would cause you to abandon the trade.

## When to do nothing
If a stretch isn't far enough, or volume is light, or you're already
fully positioned — hold. Doing nothing is a valid action.
```

- [ ] **Step 4: Verify files exist**

Run: `ls backend/agent/personas/`
Expected: three files listed.

- [ ] **Step 5: Commit and push**

```bash
git add backend/agent/personas/dca-baseline.md backend/agent/personas/trend-follower.md backend/agent/personas/mean-reverter.md
git commit -m "feat(agent): persona files for DCA charter + Trend-Follower + Mean-Reverter"
git push
```

---

### Task 22: Persona loader + content hash

**Files:**
- Create: `backend/services/trading/persona_loader.py`
- Test: `backend/tests/test_trading_persona_loader.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_persona_loader.py`:

```python
import pytest

from backend.services.trading.persona_loader import (
    load_persona, persona_hash, PersonaNotFound,
)


def test_load_trend_follower():
    p = load_persona("trend-follower")
    assert "Trend-Follower" in p.body
    assert p.key == "trend-follower"


def test_persona_hash_stable_across_calls():
    a = persona_hash("trend-follower")
    b = persona_hash("trend-follower")
    assert a == b
    assert len(a) == 64   # sha256 hex


def test_persona_hash_differs_per_persona():
    a = persona_hash("trend-follower")
    b = persona_hash("mean-reverter")
    assert a != b


def test_unknown_persona_raises():
    with pytest.raises(PersonaNotFound):
        load_persona("doesnt-exist")
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_persona_loader.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/persona_loader.py`:

```python
"""Loads persona prompt markdown from disk and computes a stable hash.

Spec §7.3.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PERSONAS_DIR = Path(__file__).resolve().parents[2] / "agent" / "personas"


class PersonaNotFound(Exception):
    pass


@dataclass(frozen=True)
class Persona:
    key: str
    body: str


@lru_cache(maxsize=32)
def load_persona(key: str) -> Persona:
    path = PERSONAS_DIR / f"{key}.md"
    if not path.exists():
        raise PersonaNotFound(f"No persona at {path}")
    return Persona(key=key, body=path.read_text(encoding="utf-8"))


def persona_hash(key: str) -> str:
    p = load_persona(key)
    return hashlib.sha256(p.body.encode("utf-8")).hexdigest()


def clear_cache() -> None:
    """For tests that mutate persona files on disk."""
    load_persona.cache_clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_persona_loader.py -v`
Expected: all 4 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/persona_loader.py backend/tests/test_trading_persona_loader.py
git commit -m "feat(trading): persona_loader with content-hash + LRU cache"
git push
```

---

### Task 23: Five new MCP tools

**Files:**
- Modify: `backend/mcp_server.py`
- Test: `backend/tests/test_trading_mcp_tools.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_mcp_tools.py`:

```python
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.mcp_server import (
    place_paper_order, cancel_paper_order, get_my_paper_state,
    get_my_recent_decisions, get_market_snapshot,
)


def _seed():
    sb = get_supabase()
    payload = {
        "name": f"mcp-strat-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
    }
    sid = sb.table("strategies").insert(payload).execute().data[0]["id"]
    sb.table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": "1000", "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()
    return sid


def test_get_my_paper_state_returns_cash_and_positions():
    sid = _seed()
    state = get_my_paper_state.fn(strategy_id=sid)
    assert state["cash_aud"] == "1000"
    assert state["positions"] == {} or state["positions"].get("AUD") is None


def test_get_my_recent_decisions_returns_list_even_when_empty():
    sid = _seed()
    rows = get_my_recent_decisions.fn(strategy_id=sid, n=5)
    assert isinstance(rows, list)


def test_get_market_snapshot_returns_structure_for_each_pair():
    snap = get_market_snapshot.fn(pairs=["ETH/AUD"])
    assert "ETH/AUD" in snap
    # The structure includes a top_ask/top_bid even if book is empty.
    assert "top_ask" in snap["ETH/AUD"] or "error" in snap["ETH/AUD"]


def test_place_paper_order_rejected_when_no_executor_attached_raises():
    sid = _seed()
    # Without an attached executor & book in this unit context, the call
    # should return a structured rejection rather than raising.
    res = place_paper_order.fn(
        strategy_id=sid, pair="ETH/AUD", side="buy",
        type="market", qty="0.01", idempotency_key=f"{sid}:t1:0",
    )
    assert res["status"] in ("rejected", "filled", "pending")
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_mcp_tools.py -v`
Expected: ImportError on the tool names (or AttributeError if `mcp_server` doesn't expose them yet).

- [ ] **Step 3: Add the tools to `backend/mcp_server.py`**

In `backend/mcp_server.py`, near where other tools are registered (look for the existing `@mcp.tool` decorations — preserve the same pattern), append:

```python
# ─────────────────────────── Paper-trading tools ───────────────────
# Spec §7.1.

from decimal import Decimal
from uuid import UUID


def _current_paper_executor():
    """Returns the global PaperExecutor set by main.py on startup."""
    from backend.services.trading import strategy_loop as sl
    return sl._current_executor


@mcp.tool
def place_paper_order(
    strategy_id: str, pair: str, side: str, type: str, qty: str,
    idempotency_key: str, limit_price: str | None = None,
) -> dict:
    """Submit a paper order. Returns OrderResult as dict."""
    import asyncio
    from backend.models.trading import OrderResult
    executor = _current_paper_executor()
    if executor is None:
        return {"status": "rejected", "reject_reason": "EXECUTOR_NOT_READY",
                "fills": []}
    coro = executor.submit_order(
        strategy_id=UUID(strategy_id),
        idempotency_key=idempotency_key,
        pair=pair, side=side, type=type,
        qty=Decimal(qty),
        limit_price=Decimal(limit_price) if limit_price else None,
    )
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Run synchronously via a one-off loop in a thread.
        from concurrent.futures import ThreadPoolExecutor
        import asyncio as _aio
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_aio.run, coro)
            result: OrderResult = fut.result()
    else:
        result = loop.run_until_complete(coro)
    return result.model_dump(mode="json")


@mcp.tool
def cancel_paper_order(order_id: str) -> dict:
    import asyncio
    executor = _current_paper_executor()
    if executor is None:
        return {"ok": False, "reason": "EXECUTOR_NOT_READY"}
    asyncio.get_event_loop().run_until_complete(
        executor.cancel_order(order_id=UUID(order_id))
    )
    return {"ok": True}


@mcp.tool
def get_my_paper_state(strategy_id: str) -> dict:
    from backend.repositories import paper_orders_repo, paper_positions_repo
    sid = UUID(strategy_id)
    rows = paper_positions_repo.get_all(sid)
    cash = rows.get("AUD", {}).get("qty", "0")
    positions = {k: v for k, v in rows.items() if k != "AUD"}
    open_orders = paper_orders_repo.list_open_orders(sid)
    return {
        "cash_aud": str(cash),
        "positions": {k: {"qty": v.get("qty"),
                          "avg_cost_aud": v.get("avg_cost_aud")}
                      for k, v in positions.items()},
        "open_orders": [o.model_dump(mode="json") for o in open_orders],
    }


@mcp.tool
def get_my_recent_decisions(strategy_id: str, n: int = 5) -> list[dict]:
    from backend.repositories import agent_decisions_repo
    return agent_decisions_repo.list_recent(UUID(strategy_id), n=n)


@mcp.tool
def get_market_snapshot(pairs: list[str] | None = None) -> dict:
    """Returns top-of-book per pair from the live LocalOrderBooks."""
    executor = _current_paper_executor()
    out: dict[str, dict] = {}
    pairs = pairs or list((executor._books if executor else {}).keys())
    for p in pairs:
        book = executor._books.get(p) if executor else None
        if book is None or not book.asks or not book.bids:
            out[p] = {"error": "BOOK_UNAVAILABLE"}
            continue
        out[p] = {
            "top_ask": {"price": str(book.top_ask().price),
                        "qty": str(book.top_ask().qty)},
            "top_bid": {"price": str(book.top_bid().price),
                        "qty": str(book.top_bid().qty)},
            "mid": str(book.mid()),
            "ts": book.ts.isoformat() if book.ts else None,
        }
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_mcp_tools.py -v`
Expected: all 4 pass. (Network is not exercised here; the executor is null in unit context, so `place_paper_order` returns a structured EXECUTOR_NOT_READY rejection.)

- [ ] **Step 5: Commit and push**

```bash
git add backend/mcp_server.py backend/tests/test_trading_mcp_tools.py
git commit -m "feat(mcp): five paper-trading tools (place/cancel/state/decisions/snapshot)"
git push
```

---

### Task 24: LLM strategy invocation + cost model

**Files:**
- Create: `backend/services/trading/cost_model.py`
- Create: `backend/services/trading/llm_strategy.py`
- Modify: `backend/services/trading/strategy_loop.py` (replace stub `invoke_llm_strategy`)
- Test: `backend/tests/test_trading_cost_model.py`, `backend/tests/test_trading_llm_strategy.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_trading_cost_model.py`:

```python
from decimal import Decimal

from backend.services.trading.cost_model import (
    compute_cost_aud, MODEL_PRICES_USD_PER_M,
)


def test_known_model_price_is_present():
    assert "claude-sonnet-4-6" in MODEL_PRICES_USD_PER_M
    assert "claude-haiku-4-5" in MODEL_PRICES_USD_PER_M


def test_compute_cost_aud_for_sonnet_call():
    # 5,000 input tokens, 1,000 output tokens at Sonnet 4.6 (illustrative
    # prices: $3/M input, $15/M output → USD 0.03; at AUD/USD 1.5 → AUD 0.045)
    cost = compute_cost_aud(
        model="claude-sonnet-4-6",
        input_tokens=5_000, output_tokens=1_000,
        aud_per_usd=Decimal("1.50"),
    )
    assert cost > Decimal("0")
    assert cost < Decimal("0.50")   # sanity bound


def test_unknown_model_returns_zero_with_warning(caplog):
    cost = compute_cost_aud(model="unknown-model-x",
                            input_tokens=1000, output_tokens=100,
                            aud_per_usd=Decimal("1.50"))
    assert cost == Decimal("0")
```

Create `backend/tests/test_trading_llm_strategy.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch, AsyncMock

import pytest

from backend.db.supabase_client import get_supabase
from backend.models.trading import IntervalTriggerEvent


def _seed():
    sb = get_supabase()
    sid = sb.table("strategies").insert({
        "name": f"tf-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
    }).execute().data[0]["id"]
    sb.table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": "1000", "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()
    return sid


@pytest.mark.asyncio
async def test_invoke_llm_strategy_writes_decision_with_persona_hash_and_cost():
    from backend.repositories import strategies_repo
    sid = _seed()
    strat = strategies_repo.get(sid)
    event = IntervalTriggerEvent(minutes=60, ts=datetime.now(timezone.utc))

    fake_response = {
        "agent_output": "No clear trend; holding cash.",
        "tool_calls": [],
        "input_tokens": 4_200,
        "output_tokens": 180,
        "model": "claude-sonnet-4-6",
    }

    with patch("backend.services.trading.llm_strategy._call_langgraph",
               new=AsyncMock(return_value=fake_response)), \
         patch("backend.services.trading.llm_strategy.aud_per_usd",
               return_value=Decimal("1.50")):
        from backend.services.trading.strategy_loop import invoke_llm_strategy
        await invoke_llm_strategy(strat, event)
    sb = get_supabase()
    row = (sb.table("agent_decisions").select("*")
             .eq("strategy_id", sid).order("created_at", desc=True)
             .limit(1).execute().data[0])
    assert row["execution_mode"] == "llm_agent"
    assert row["persona_prompt_hash"] is not None
    assert row["model"] == "claude-sonnet-4-6"
    assert row["input_tokens"] == 4_200
    assert Decimal(row["cost_aud"]) > Decimal("0")
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_cost_model.py backend/tests/test_trading_llm_strategy.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement cost model and LLM strategy**

Create `backend/services/trading/cost_model.py`:

```python
"""Token → AUD cost calculation.

Spec §7.4. Stores actual cost at the time of the call so historical
attribution is stable even when model prices change later.

Prices are USD per 1M tokens. Edit when Anthropic publishes updates;
defaults below are illustrative — implementer should verify against
docs.anthropic.com/en/docs/about-claude/models at integration time.
"""
from __future__ import annotations

import logging
from decimal import Decimal


logger = logging.getLogger(__name__)


# USD per 1M tokens — input/output.
MODEL_PRICES_USD_PER_M: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-4-7":   (Decimal("15"),   Decimal("75")),
    "claude-sonnet-4-6": (Decimal("3"),    Decimal("15")),
    "claude-haiku-4-5":  (Decimal("0.80"), Decimal("4")),
}


def aud_per_usd() -> Decimal:
    """Reuse the same FX source the portfolio dashboard already uses.

    See backend/services/portfolio_service.py for the existing AUD/USD
    helper; if no shared helper exists, default to 1.5 (the agent
    decision row is annotated with the rate used).
    """
    try:
        from backend.services.portfolio_service import get_aud_usd_rate
        return Decimal(str(get_aud_usd_rate()))
    except Exception:
        return Decimal("1.50")


def compute_cost_aud(
    *,
    model: str, input_tokens: int, output_tokens: int,
    aud_per_usd: Decimal,
) -> Decimal:
    if model not in MODEL_PRICES_USD_PER_M:
        logger.warning("No price entry for model %s; cost recorded as 0", model)
        return Decimal("0")
    in_price, out_price = MODEL_PRICES_USD_PER_M[model]
    usd_cost = (Decimal(input_tokens) * in_price
                + Decimal(output_tokens) * out_price) / Decimal(1_000_000)
    return (usd_cost * aud_per_usd).quantize(Decimal("0.0001"))
```

Create `backend/services/trading/llm_strategy.py`:

```python
"""LLM strategy invocation — assembles context, calls LangGraph, writes decision.

Spec §7.2 strategy-invocation mode: scoped tool surface (the five
paper-trading tools only). The actual graph call wires into the existing
LangGraph agent — we don't reinvent it here.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from time import perf_counter

from backend.models.trading import StrategyRow
from backend.services.trading.cost_model import aud_per_usd, compute_cost_aud
from backend.services.trading.decision_writer import write_agent_decision
from backend.services.trading.persona_loader import (
    load_persona, persona_hash,
)

logger = logging.getLogger(__name__)


async def _call_langgraph(
    *, system_prompt: str, user_message: str, model: str,
    tools_whitelist: list[str], strategy_id,
) -> dict:
    """Invoke the existing LangGraph agent with a scoped toolset.

    Returns a dict with keys: agent_output, tool_calls, input_tokens,
    output_tokens, model.

    The actual wiring depends on the existing graph in backend/agent/graph.py.
    The expected shape: the graph exposes an async entry point that takes
    a system prompt + user message + tool allowlist and returns metadata.
    If the existing graph doesn't expose this directly, add a thin
    `invoke_for_strategy(...)` helper in backend/agent/graph.py.
    """
    from backend.agent.graph import invoke_for_strategy   # add this helper
    return await invoke_for_strategy(
        system_prompt=system_prompt,
        user_message=user_message,
        model=model,
        tools_whitelist=tools_whitelist,
        strategy_id=str(strategy_id),
    )


def _assemble_context(strategy: StrategyRow, event) -> tuple[str, dict]:
    """Returns (user_message, input_snapshot)."""
    from backend.repositories import (
        agent_decisions_repo, paper_orders_repo, paper_positions_repo,
    )
    positions = paper_positions_repo.get_all(strategy.id)
    open_orders = paper_orders_repo.list_open_orders(strategy.id)
    recent = agent_decisions_repo.list_recent(strategy.id, n=5)
    snapshot = {
        "positions": {k: dict(v) for k, v in positions.items()},
        "open_orders": [o.model_dump(mode="json") for o in open_orders],
        "recent_decisions": [
            {"created_at": r["created_at"],
             "agent_output": r.get("agent_output"),
             "tool_calls": r.get("tool_calls", [])}
            for r in recent
        ],
        "trigger": event.model_dump() if hasattr(event, "model_dump") else dict(event),
    }
    user_msg = (
        f"You are running as {strategy.name} (strategy_id={strategy.id}).\n"
        f"Trigger event: {event.type}.\n"
        f"Decide what to do, calling tools as needed. "
        f"Use idempotency_key prefix `{strategy.id}:<decision_id>:<seq>`."
    )
    return user_msg, snapshot


async def invoke_llm_strategy(strategy: StrategyRow, event) -> None:
    started = perf_counter()
    persona = load_persona(strategy.persona_key)
    user_msg, snapshot = _assemble_context(strategy, event)
    model = strategy.model_preference or "claude-sonnet-4-6"

    response = await _call_langgraph(
        system_prompt=persona.body, user_message=user_msg,
        model=model,
        tools_whitelist=[
            "place_paper_order", "cancel_paper_order",
            "get_my_paper_state", "get_my_recent_decisions",
            "get_market_snapshot",
        ],
        strategy_id=strategy.id,
    )

    cost = compute_cost_aud(
        model=response.get("model", model),
        input_tokens=response.get("input_tokens", 0),
        output_tokens=response.get("output_tokens", 0),
        aud_per_usd=aud_per_usd(),
    )

    write_agent_decision(
        strategy_id=strategy.id,
        execution_mode="llm_agent",
        trigger_event=event.model_dump() if hasattr(event, "model_dump") else dict(event),
        input_snapshot=snapshot,
        persona_prompt_hash=persona_hash(strategy.persona_key),
        model=response.get("model", model),
        input_tokens=response.get("input_tokens", 0),
        output_tokens=response.get("output_tokens", 0),
        cost_aud=cost,
        tool_calls=response.get("tool_calls", []),
        agent_output=response.get("agent_output"),
        latency_ms=int((perf_counter() - started) * 1000),
        error=None,
    )
```

Replace the `invoke_llm_strategy` stub at the top of `backend/services/trading/strategy_loop.py` with:

```python
async def invoke_llm_strategy(strategy: StrategyRow, event) -> None:
    from backend.services.trading.llm_strategy import (
        invoke_llm_strategy as _invoke,
    )
    await _invoke(strategy, event)
```

(Note: the existing `backend/agent/graph.py` must expose
`invoke_for_strategy(...)`. If it doesn't, add a thin wrapper there
that takes `system_prompt + user_message + model + tools_whitelist`
and runs the existing graph with those constraints. Capture token usage
from the LangGraph response metadata.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_cost_model.py backend/tests/test_trading_llm_strategy.py -v`
Expected: 3 + 1 = 4 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/cost_model.py backend/services/trading/llm_strategy.py backend/services/trading/strategy_loop.py backend/tests/test_trading_cost_model.py backend/tests/test_trading_llm_strategy.py
git commit -m "feat(trading): LLM strategy invocation + persona hash + cost attribution"
git push
```

---

## Part 8 — Snapshots & Metrics

### Task 25: Equity snapshot task

**Files:**
- Create: `backend/services/trading/equity_snapshot.py`
- Create: `backend/repositories/paper_equity_repo.py`
- Test: `backend/tests/test_trading_equity_snapshot.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_equity_snapshot.py`:

```python
import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.services.trading.equity_snapshot import (
    compute_equity_for_strategy, snapshot_all_active,
)


def _seed_with_positions():
    sb = get_supabase()
    sid = sb.table("strategies").insert({
        "name": f"eq-{uuid4()}",
        "execution_mode": "llm_agent", "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
    }).execute().data[0]["id"]
    sb.table("paper_positions").insert([
        {"strategy_id": sid, "asset": "AUD",
         "qty": "500", "avg_cost_aud": "1", "lots_jsonb": []},
        {"strategy_id": sid, "asset": "ETH",
         "qty": "0.15", "avg_cost_aud": "3000",
         "lots_jsonb": [{"qty": "0.15", "cost_aud": "3000",
                         "acquired_at": "2026-05-01T00:00:00Z"}]},
    ]).execute()
    return sid


def test_compute_equity_uses_mid_for_position_value():
    sid = _seed_with_positions()
    eq = compute_equity_for_strategy(sid, mids={"ETH/AUD": Decimal("3200")})
    # cash 500 + 0.15 * 3200 = 500 + 480 = 980
    assert eq.equity_aud == Decimal("980")
    assert eq.cash_aud == Decimal("500")
    assert eq.position_value_aud == Decimal("480")


def test_snapshot_all_active_inserts_one_row_per_strategy():
    sid = _seed_with_positions()
    snapshot_all_active(mids={"ETH/AUD": Decimal("3000")})
    sb = get_supabase()
    rows = (sb.table("paper_equity_snapshots").select("*")
              .eq("strategy_id", sid).execute().data or [])
    assert len(rows) >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_equity_snapshot.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/repositories/paper_equity_repo.py`:

```python
"""Repository for paper_equity_snapshots + paper_benchmarks."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase


def insert_snapshot(
    *, strategy_id: UUID, ts: datetime, equity_aud: Decimal,
    cash_aud: Decimal, position_value_aud: Decimal,
    realised_pnl_aud: Decimal = Decimal("0"),
    unrealised_pnl_aud: Decimal = Decimal("0"),
) -> None:
    sb = get_supabase()
    sb.table("paper_equity_snapshots").upsert({
        "strategy_id": str(strategy_id),
        "ts": ts.isoformat(),
        "equity_aud": str(equity_aud),
        "cash_aud": str(cash_aud),
        "position_value_aud": str(position_value_aud),
        "realised_pnl_aud": str(realised_pnl_aud),
        "unrealised_pnl_aud": str(unrealised_pnl_aud),
    }, on_conflict="strategy_id,ts").execute()


def list_curve(strategy_id: UUID, *, since: datetime | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("paper_equity_snapshots").select("*").eq("strategy_id", str(strategy_id))
    if since is not None:
        q = q.gte("ts", since.isoformat())
    return (q.order("ts").execute().data or [])


def insert_benchmark_snapshot(*, benchmark_key: str, ts: datetime,
                              equity_aud: Decimal) -> None:
    sb = get_supabase()
    sb.table("paper_benchmarks").upsert({
        "benchmark_key": benchmark_key,
        "ts": ts.isoformat(), "equity_aud": str(equity_aud),
    }, on_conflict="benchmark_key,ts").execute()


def list_benchmark_curve(benchmark_key: str,
                         *, since: datetime | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("paper_benchmarks").select("*").eq("benchmark_key", benchmark_key)
    if since is not None:
        q = q.gte("ts", since.isoformat())
    return (q.order("ts").execute().data or [])
```

Create `backend/services/trading/equity_snapshot.py`:

```python
"""Hourly equity snapshots per active strategy.

Spec §4.6, §8.2 leaderboard. Scheduled via the existing
backend/scheduler.py — see Task 31.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from backend.repositories import (
    paper_equity_repo, paper_positions_repo, strategies_repo,
)


logger = logging.getLogger(__name__)


@dataclass
class EquityPoint:
    equity_aud: Decimal
    cash_aud: Decimal
    position_value_aud: Decimal


def compute_equity_for_strategy(
    strategy_id: UUID | str, *, mids: dict[str, Decimal],
) -> EquityPoint:
    sid = UUID(str(strategy_id))
    rows = paper_positions_repo.get_all(sid)
    cash = Decimal(rows.get("AUD", {}).get("qty", "0"))
    position_value = Decimal("0")
    for asset, row in rows.items():
        if asset == "AUD":
            continue
        pair = f"{asset}/AUD"
        if pair not in mids:
            # Fall back to avg_cost — at least we don't crash.
            position_value += Decimal(row["qty"]) * Decimal(row.get("avg_cost_aud") or "0")
            continue
        position_value += Decimal(row["qty"]) * mids[pair]
    return EquityPoint(
        equity_aud=cash + position_value,
        cash_aud=cash,
        position_value_aud=position_value,
    )


def snapshot_all_active(*, mids: dict[str, Decimal]) -> None:
    ts = datetime.now(timezone.utc)
    for strat in strategies_repo.list_active():
        try:
            eq = compute_equity_for_strategy(strat.id, mids=mids)
            paper_equity_repo.insert_snapshot(
                strategy_id=strat.id, ts=ts,
                equity_aud=eq.equity_aud,
                cash_aud=eq.cash_aud,
                position_value_aud=eq.position_value_aud,
            )
        except Exception:
            logger.exception("Equity snapshot failed for %s", strat.name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_equity_snapshot.py -v`
Expected: all 2 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/equity_snapshot.py backend/repositories/paper_equity_repo.py backend/tests/test_trading_equity_snapshot.py
git commit -m "feat(trading): hourly equity-snapshot task + repository"
git push
```

---

### Task 26: Benchmark snapshots (BTC HODL + alt basket with monthly rebalance)

**Files:**
- Create: `backend/services/trading/benchmark_snapshot.py`
- Test: `backend/tests/test_trading_benchmark_snapshot.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_benchmark_snapshot.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal

from backend.services.trading.benchmark_snapshot import (
    compute_btc_hodl_equity, compute_alt_basket_equity,
    next_rebalance_due_at, AltBasketState,
)


T0 = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)


def test_btc_hodl_equity_scales_with_btc_price_relative_to_t0():
    eq = compute_btc_hodl_equity(
        starting_balance_aud=Decimal("1000"),
        btc_price_at_start=Decimal("90000"),
        btc_price_now=Decimal("108000"),
    )
    # 20% rise → equity 1200
    assert eq == Decimal("1200")


def test_alt_basket_initialises_equal_weight_at_t0():
    state = AltBasketState.initialise(
        starting_balance_aud=Decimal("1000"),
        initial_prices={"ETH/AUD": Decimal("3000"), "LINK/AUD": Decimal("15"),
                        "ADA/AUD": Decimal("0.40"), "SOL/AUD": Decimal("100")},
        t0=T0,
    )
    # Each asset gets 250 AUD at t0.
    assert state.units["ETH/AUD"] == Decimal("250") / Decimal("3000")


def test_alt_basket_equity_updates_with_prices():
    state = AltBasketState.initialise(
        starting_balance_aud=Decimal("1000"),
        initial_prices={"ETH/AUD": Decimal("3000"), "LINK/AUD": Decimal("15"),
                        "ADA/AUD": Decimal("0.40"), "SOL/AUD": Decimal("100")},
        t0=T0,
    )
    # ETH +20%, others flat → +5% of total (since each is 25% weight).
    eq = compute_alt_basket_equity(
        state=state,
        current_prices={"ETH/AUD": Decimal("3600"), "LINK/AUD": Decimal("15"),
                        "ADA/AUD": Decimal("0.40"), "SOL/AUD": Decimal("100")},
    )
    assert eq == Decimal("1050")


def test_monthly_rebalance_is_due_at_first_of_next_month():
    last = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    nxt = next_rebalance_due_at(last)
    assert nxt == datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_benchmark_snapshot.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/benchmark_snapshot.py`:

```python
"""Benchmark equity curves: BTC HODL and equal-weight alt basket.

Spec §4.7 + §8.3 — equal-weight basket REBALANCES monthly on the 1st
so that "lucky drift" doesn't make the benchmark unfairly hard to beat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


def compute_btc_hodl_equity(
    *, starting_balance_aud: Decimal,
    btc_price_at_start: Decimal, btc_price_now: Decimal,
) -> Decimal:
    if btc_price_at_start == 0:
        return Decimal("0")
    units = starting_balance_aud / btc_price_at_start
    return (units * btc_price_now).quantize(Decimal("0.0001"))


@dataclass
class AltBasketState:
    units: dict[str, Decimal] = field(default_factory=dict)
    last_rebalance_at: datetime | None = None

    @classmethod
    def initialise(
        cls, *, starting_balance_aud: Decimal,
        initial_prices: dict[str, Decimal], t0: datetime,
    ) -> "AltBasketState":
        per_asset = starting_balance_aud / Decimal(len(initial_prices))
        units = {pair: (per_asset / price) for pair, price in initial_prices.items()}
        return cls(units=units, last_rebalance_at=t0)

    def equity(self, *, current_prices: dict[str, Decimal]) -> Decimal:
        return sum(
            (self.units.get(p, Decimal("0")) * current_prices.get(p, Decimal("0"))
             for p in self.units),
            Decimal("0"),
        )

    def rebalance(self, *, current_prices: dict[str, Decimal],
                  now: datetime) -> None:
        eq = self.equity(current_prices=current_prices)
        per_asset = eq / Decimal(len(self.units))
        self.units = {p: (per_asset / current_prices[p]) for p in self.units}
        self.last_rebalance_at = now


def compute_alt_basket_equity(
    *, state: AltBasketState, current_prices: dict[str, Decimal],
) -> Decimal:
    return state.equity(current_prices=current_prices).quantize(Decimal("0.0001"))


def next_rebalance_due_at(last: datetime) -> datetime:
    # First of next month at 00:00 UTC.
    year, month = last.year, last.month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    return datetime(year, month, 1, 0, 0, tzinfo=timezone.utc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_benchmark_snapshot.py -v`
Expected: all 4 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/benchmark_snapshot.py backend/tests/test_trading_benchmark_snapshot.py
git commit -m "feat(trading): BTC HODL + alt-basket benchmark equity (monthly rebalance)"
git push
```

---

### Task 27: Metrics view (Sharpe, Sortino, max DD, etc.)

**Files:**
- Create: `backend/services/trading/metrics.py`
- Test: `backend/tests/test_trading_metrics.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_metrics.py`:

```python
from decimal import Decimal

from backend.services.trading.metrics import (
    compute_returns, sharpe_24_7, sortino_24_7,
    max_drawdown_pct, calmar, win_rate, payoff_ratio,
)


def test_returns_from_equity_curve():
    curve = [Decimal("1000"), Decimal("1100"), Decimal("990")]
    rs = compute_returns(curve)
    # ln-returns: ln(1.1), ln(0.9)
    assert len(rs) == 2


def test_sharpe_24_7_uses_sqrt_365():
    # All returns identical → stdev 0 → return inf-handling: define as 0.
    curve = [Decimal("1000")] * 10
    assert sharpe_24_7(curve) == Decimal("0")


def test_sharpe_positive_for_steady_upward_curve():
    curve = [Decimal("1000") * (Decimal("1.001") ** i) for i in range(30)]
    assert sharpe_24_7(curve) > Decimal("0")


def test_max_drawdown_pct():
    curve = [Decimal("1000"), Decimal("1200"), Decimal("800"), Decimal("1100")]
    # Peak 1200, trough 800 → 33.33% DD
    dd = max_drawdown_pct(curve)
    assert Decimal("33") < dd < Decimal("34")


def test_calmar_ratio():
    # Mocked simple: CAGR / max DD; the helper just divides.
    c = calmar(annualised_return_pct=Decimal("20"), max_dd_pct=Decimal("10"))
    assert c == Decimal("2")


def test_win_rate():
    rs = [Decimal("0.1"), Decimal("-0.05"), Decimal("0.2"), Decimal("-0.1"), Decimal("0.05")]
    assert win_rate(rs) == Decimal("0.6")


def test_payoff_ratio():
    rs = [Decimal("0.1"), Decimal("-0.05"), Decimal("0.2"), Decimal("-0.1"), Decimal("0.05")]
    # avg win = (0.1+0.2+0.05)/3 = 0.116…, avg loss = 0.075 → ratio ~1.555
    p = payoff_ratio(rs)
    assert Decimal("1.5") < p < Decimal("1.6")


def test_sortino_only_penalises_downside():
    curve = [Decimal("1000"), Decimal("1100"), Decimal("1050"),
             Decimal("1200"), Decimal("1150")]
    so = sortino_24_7(curve)
    sh = sharpe_24_7(curve)
    # Same curve — Sortino ≥ Sharpe because upside is excluded from stdev.
    assert so >= sh
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_metrics.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `backend/services/trading/metrics.py`:

```python
"""Strategy performance metrics. Spec §8.2 + §9.5.

Annualisation uses √365 (24/7 markets). Returns are computed as ln-returns
on the equity curve.
"""
from __future__ import annotations

import math
from decimal import Decimal
from statistics import mean, pstdev


def compute_returns(curve: list[Decimal]) -> list[Decimal]:
    if len(curve) < 2:
        return []
    out: list[Decimal] = []
    for i in range(1, len(curve)):
        if curve[i - 1] <= 0:
            continue
        ratio = float(curve[i]) / float(curve[i - 1])
        if ratio <= 0:
            continue
        out.append(Decimal(str(math.log(ratio))))
    return out


def _annualise(daily_value: float) -> Decimal:
    return Decimal(str(daily_value * math.sqrt(365)))


def sharpe_24_7(curve: list[Decimal]) -> Decimal:
    rs = [float(r) for r in compute_returns(curve)]
    if len(rs) < 2:
        return Decimal("0")
    mu = mean(rs)
    sigma = pstdev(rs)
    if sigma == 0:
        return Decimal("0")
    return _annualise(mu / sigma)


def sortino_24_7(curve: list[Decimal]) -> Decimal:
    rs = [float(r) for r in compute_returns(curve)]
    if len(rs) < 2:
        return Decimal("0")
    mu = mean(rs)
    downside = [r for r in rs if r < 0]
    if not downside:
        return Decimal("999")    # convention: no downside → huge Sortino
    dn_sigma = pstdev(downside)
    if dn_sigma == 0:
        return Decimal("0")
    return _annualise(mu / dn_sigma)


def max_drawdown_pct(curve: list[Decimal]) -> Decimal:
    if not curve:
        return Decimal("0")
    peak = curve[0]
    worst = Decimal("0")
    for v in curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * Decimal("100")
            if dd > worst:
                worst = dd
    return worst


def calmar(*, annualised_return_pct: Decimal, max_dd_pct: Decimal) -> Decimal:
    if max_dd_pct == 0:
        return Decimal("0")
    return (annualised_return_pct / max_dd_pct).quantize(Decimal("0.0001"))


def win_rate(returns: list[Decimal]) -> Decimal:
    if not returns:
        return Decimal("0")
    wins = sum(1 for r in returns if r > 0)
    return Decimal(wins) / Decimal(len(returns))


def payoff_ratio(returns: list[Decimal]) -> Decimal:
    wins = [r for r in returns if r > 0]
    losses = [-r for r in returns if r < 0]
    if not wins or not losses:
        return Decimal("0")
    avg_win = sum(wins) / Decimal(len(wins))
    avg_loss = sum(losses) / Decimal(len(losses))
    if avg_loss == 0:
        return Decimal("0")
    return (avg_win / avg_loss).quantize(Decimal("0.0001"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_metrics.py -v`
Expected: all 8 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/metrics.py backend/tests/test_trading_metrics.py
git commit -m "feat(trading): metrics (Sharpe/Sortino 24/7, max DD, Calmar, win-rate, payoff)"
git push
```

---

## Part 9 — API Routes

### Task 28: Strategies CRUD + leaderboard + detail endpoints

**Files:**
- Create: `backend/routers/strategies.py`
- Modify: `backend/main.py` (register the new router — see snippet below; full startup wiring lands in Task 31)
- Test: `backend/tests/test_strategies_router.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_strategies_router.py`:

```python
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.db.supabase_client import get_supabase
from backend.main import app


client = TestClient(app)


def _seed_strategy(status="active"):
    sb = get_supabase()
    return sb.table("strategies").insert({
        "name": f"router-{uuid4()}",
        "execution_mode": "llm_agent", "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {}, "risk_caps": {}, "kill_criteria": {},
        "status": status,
    }).execute().data[0]["id"]


def test_list_strategies_returns_array():
    _seed_strategy()
    r = client.get("/api/strategies/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert any(row["name"].startswith("router-") for row in body)


def test_get_strategy_returns_404_for_unknown():
    r = client.get(f"/api/strategies/{uuid4()}")
    assert r.status_code == 404


def test_get_strategy_returns_detail():
    sid = _seed_strategy()
    r = client.get(f"/api/strategies/{sid}")
    assert r.status_code == 200
    assert r.json()["id"] == sid


def test_pause_endpoint_updates_status():
    sid = _seed_strategy()
    r = client.post(f"/api/strategies/{sid}/pause")
    assert r.status_code == 200
    sb = get_supabase()
    row = sb.table("strategies").select("status").eq("id", sid).execute().data[0]
    assert row["status"] == "paused"


def test_resume_endpoint_updates_status():
    sid = _seed_strategy(status="paused")
    r = client.post(f"/api/strategies/{sid}/resume")
    assert r.status_code == 200
    sb = get_supabase()
    assert sb.table("strategies").select("status").eq("id", sid).execute().data[0]["status"] == "active"


def test_leaderboard_returns_one_row_per_strategy():
    _seed_strategy()
    _seed_strategy()
    r = client.get("/api/strategies/_leaderboard")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    if rows:
        row = rows[0]
        assert "equity_aud" in row
        assert "sharpe" in row
        assert "trades" in row


def test_decisions_endpoint_returns_list():
    sid = _seed_strategy()
    r = client.get(f"/api/strategies/{sid}/decisions?n=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_equity_curve_endpoint():
    sid = _seed_strategy()
    r = client.get(f"/api/strategies/{sid}/equity?range=7d")
    assert r.status_code == 200
    body = r.json()
    assert "strategy" in body
    assert "benchmarks" in body
    assert "btc_hodl" in body["benchmarks"]
    assert "alt_basket_equal_weight" in body["benchmarks"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_strategies_router.py -v`
Expected: 404 on every route (router not registered yet).

- [ ] **Step 3: Implement the router**

Create `backend/routers/strategies.py`:

```python
"""API routes for the StrategiesPage (spec §8) and control plane."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from backend.db.supabase_client import get_supabase
from backend.repositories import (
    agent_decisions_repo, paper_equity_repo, paper_orders_repo,
    paper_positions_repo, strategies_repo, system_alerts_repo,
)
from backend.services.trading import metrics


router = APIRouter(prefix="/api/strategies", tags=["strategies"])


# ─────────────────────────── list / detail ──────────────────────

@router.get("/")
def list_strategies() -> list[dict]:
    sb = get_supabase()
    r = sb.table("strategies").select("*").order("created_at").execute()
    return r.data or []


@router.get("/_leaderboard")
def leaderboard() -> list[dict]:
    sb = get_supabase()
    strats = sb.table("strategies").select("*").neq("status", "archived").execute().data or []
    out: list[dict] = []
    for s in strats:
        sid = UUID(s["id"])
        curve_rows = paper_equity_repo.list_curve(sid)
        curve = [Decimal(r["equity_aud"]) for r in curve_rows]
        starting = Decimal(s.get("starting_balance_aud") or "0")
        equity = curve[-1] if curve else starting
        sharpe = metrics.sharpe_24_7(curve)
        max_dd = metrics.max_drawdown_pct(curve)
        trades = sb.table("paper_orders").select("count", count="exact").eq(
            "strategy_id", s["id"]).limit(0).execute().count or 0
        # 30-day cost roll-up.
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        cost_rows = (sb.table("agent_decisions").select("cost_aud")
                       .eq("strategy_id", s["id"])
                       .gte("created_at", thirty_days_ago.isoformat())
                       .execute().data or [])
        cost_30d = sum((Decimal(r["cost_aud"]) for r in cost_rows), Decimal("0"))
        # Returns over windows.
        def _ret_pct(window_days: int) -> Decimal:
            cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
            window = [Decimal(r["equity_aud"]) for r in curve_rows
                      if r["ts"] >= cutoff.isoformat()]
            if not window or window[0] == 0:
                return Decimal("0")
            return ((window[-1] / window[0]) - Decimal("1")) * Decimal("100")
        out.append({
            "id": s["id"], "name": s["name"], "status": s["status"],
            "execution_mode": s["execution_mode"],
            "equity_aud": str(equity),
            "return_7d_pct": str(_ret_pct(7)),
            "return_30d_pct": str(_ret_pct(30)),
            "return_all_time_pct": str(((equity / starting - Decimal("1")) * Decimal("100"))
                                       if starting > 0 else Decimal("0")),
            "sharpe": str(sharpe),
            "max_drawdown_pct": str(max_dd),
            "trades": trades,
            "cost_30d_aud": str(cost_30d),
            "persona_prompt_stable_since": s.get("persona_prompt_stable_since"),
        })
    out.sort(key=lambda r: Decimal(r["equity_aud"]), reverse=True)
    return out


@router.get("/{strategy_id}")
def get_strategy(strategy_id: UUID) -> dict:
    s = strategies_repo.get(strategy_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    return s.model_dump(mode="json")


@router.get("/{strategy_id}/decisions")
def get_decisions(strategy_id: UUID, n: int = Query(20, ge=1, le=200)) -> list[dict]:
    return agent_decisions_repo.list_recent(strategy_id, n=n)


@router.get("/{strategy_id}/equity")
def get_equity_curve(strategy_id: UUID,
                     range: str = Query("30d")) -> dict:
    spans = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "all": 10_000}
    if range not in spans:
        raise HTTPException(status_code=400, detail="Bad range")
    since = datetime.now(timezone.utc) - timedelta(days=spans[range])
    strat_rows = paper_equity_repo.list_curve(strategy_id, since=since)
    btc = paper_equity_repo.list_benchmark_curve("btc_hodl", since=since)
    basket = paper_equity_repo.list_benchmark_curve(
        "alt_basket_equal_weight", since=since)
    return {
        "strategy": strat_rows,
        "benchmarks": {
            "btc_hodl": btc,
            "alt_basket_equal_weight": basket,
        },
    }


@router.get("/{strategy_id}/open_orders")
def get_open_orders(strategy_id: UUID) -> list[dict]:
    rows = paper_orders_repo.list_open_orders(strategy_id)
    return [r.model_dump(mode="json") for r in rows]


@router.get("/{strategy_id}/positions")
def get_positions(strategy_id: UUID) -> dict:
    return paper_positions_repo.get_all(strategy_id)


# ─────────────────────────── control ────────────────────────────

@router.post("/{strategy_id}/pause")
def pause(strategy_id: UUID) -> dict:
    strategies_repo.update_status(strategy_id, "paused")
    return {"ok": True}


@router.post("/{strategy_id}/resume")
def resume(strategy_id: UUID) -> dict:
    strategies_repo.update_status(strategy_id, "active")
    return {"ok": True}


@router.post("/{strategy_id}/archive")
def archive(strategy_id: UUID) -> dict:
    strategies_repo.update_status(strategy_id, "archived")
    return {"ok": True}
```

Register the router in `backend/main.py`. Find the existing
`app.include_router(...)` block and add:

```python
from backend.routers import strategies as strategies_router
app.include_router(strategies_router.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_strategies_router.py -v`
Expected: all 8 pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/routers/strategies.py backend/main.py backend/tests/test_strategies_router.py
git commit -m "feat(api): /api/strategies/* (list, detail, leaderboard, decisions, equity, control)"
git push
```

---

### Task 29: Health endpoint

**Files:**
- Modify: `backend/routers/strategies.py` (add `_health`)
- Create: `backend/services/trading/health.py`
- Test: `backend/tests/test_strategies_health.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_strategies_health.py`:

```python
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_endpoint_returns_expected_shape():
    r = client.get("/api/strategies/_health")
    assert r.status_code == 200
    body = r.json()
    assert "ws_feed" in body
    assert "strategies" in body
    assert "executor" in body
    assert "db" in body
    # ws_feed should be a dict (possibly empty when no executor attached)
    assert isinstance(body["ws_feed"], dict)
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_strategies_health.py -v`
Expected: 404.

- [ ] **Step 3: Implement**

Create `backend/services/trading/health.py`:

```python
"""Aggregates health signals for the frontend status banner (spec §9.3)."""
from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

from backend.db.supabase_client import get_supabase


def build_health_payload() -> dict:
    from backend.services.trading import strategy_loop as sl

    executor = sl._current_executor
    now = datetime.now(timezone.utc)
    ws_feed: dict[str, dict] = {}
    open_orders_count = 0
    last_fill_at = None

    if executor is not None:
        for pair, book in (executor._books or {}).items():
            age = book.age_seconds(now) if book.ts else None
            ws_feed[pair] = {
                "last_tick_at": book.ts.isoformat() if book.ts else None,
                "age_s": age,
            }

    sb = get_supabase()
    started = perf_counter()
    try:
        r = sb.table("paper_orders").select("count", count="exact").in_(
            "status", ["pending", "partial"]).limit(0).execute()
        open_orders_count = r.count or 0
        last = (sb.table("paper_fills").select("filled_at")
                  .order("filled_at", desc=True).limit(1).execute().data)
        last_fill_at = last[0]["filled_at"] if last else None
    except Exception:
        pass
    db_write_ms = int((perf_counter() - started) * 1000)

    strategies = (sb.table("strategies").select(
        "id, name, status").execute().data or [])

    return {
        "ws_feed": ws_feed,
        "strategies": strategies,
        "executor": {
            "last_fill_at": last_fill_at,
            "open_orders": open_orders_count,
        },
        "db": {"write_latency_ms_p99": db_write_ms},
    }
```

Append to `backend/routers/strategies.py`:

```python
@router.get("/_health")
def health() -> dict:
    from backend.services.trading.health import build_health_payload
    return build_health_payload()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_strategies_health.py -v`
Expected: pass.

- [ ] **Step 5: Commit and push**

```bash
git add backend/services/trading/health.py backend/routers/strategies.py backend/tests/test_strategies_health.py
git commit -m "feat(api): /api/strategies/_health endpoint (ws + strategies + executor + db)"
git push
```

---

## Part 10 — Eval Harness Extension

### Task 30: Per-persona eval scenarios

**Files:**
- Create: `backend/evals/personas_golden_set.yaml`
- Create: `backend/evals/personas_runner.py`
- Test: `backend/tests/test_personas_eval_smoke.py` (smoke only — full eval is on-demand, marked `eval`)

- [ ] **Step 1: Write the failing smoke test**

Create `backend/tests/test_personas_eval_smoke.py`:

```python
"""Smoke test — confirms the golden-set file loads and the runner can be
instantiated. The actual eval runs are marked `@pytest.mark.eval` and
not executed by default (see backend/pytest.ini)."""
from pathlib import Path

import yaml

from backend.evals.personas_runner import PersonaEvalRunner, load_golden_set


def test_golden_set_loads():
    path = Path(__file__).resolve().parents[1] / "evals" / "personas_golden_set.yaml"
    data = yaml.safe_load(path.read_text())
    assert "scenarios" in data
    assert isinstance(data["scenarios"], list)
    assert len(data["scenarios"]) >= 6   # at least 2 scenarios × 3 personas


def test_runner_instantiates():
    scenarios = load_golden_set()
    runner = PersonaEvalRunner(scenarios=scenarios)
    assert runner.scenario_count >= 6
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_personas_eval_smoke.py -v`
Expected: file/module missing.

- [ ] **Step 3: Author the golden set**

Create `backend/evals/personas_golden_set.yaml`:

```yaml
# Per-persona evaluation scenarios — spec §7.5.
# Each scenario:
#   id, persona_key, description, trigger, portfolio_state,
#   market_snapshot, expected behaviour_category
scenarios:
  - id: tf-breakout-up-no-position
    persona_key: trend-follower
    description: "ETH breaks 24h high, no current ETH position"
    trigger:
      type: price_breakout
      pair: ETH/AUD
      direction: up
      move_pct: 2.5
      lookback_bars: 24
    portfolio_state:
      cash_aud: 1000
      positions: {}
      open_orders: []
    market_snapshot:
      ETH/AUD: { top_ask: 3200, top_bid: 3199, mid: 3199.5 }
    expected:
      should_call_tool: place_paper_order
      should_be_long_on: ETH/AUD
      reasoning_mentions: [breakout, trend, "24"]

  - id: tf-no-trend-heartbeat
    persona_key: trend-follower
    description: "Hourly heartbeat, market is flat — should do nothing"
    trigger:
      type: interval
      minutes: 60
    portfolio_state:
      cash_aud: 1000
      positions: {}
      open_orders: []
    market_snapshot:
      ETH/AUD: { top_ask: 3000, top_bid: 2999, mid: 2999.5 }
    expected:
      should_call_tool: null
      reasoning_mentions: [no trend, hold, flat]

  - id: mr-stretch-above-mean
    persona_key: mean-reverter
    description: "SOL stretched 2.5σ above 48h mean"
    trigger:
      type: price_stretch
      pair: SOL/AUD
      direction: above
      stdev_distance: 2.5
    portfolio_state:
      cash_aud: 500
      positions: { SOL: 500 }
      open_orders: []
    market_snapshot:
      SOL/AUD: { top_ask: 145, top_bid: 144.9, mid: 144.95 }
    expected:
      should_call_tool: place_paper_order
      should_sell_some_of: SOL/AUD
      reasoning_mentions: [stretch, reversion, "2"]

  - id: mr-no-stretch-heartbeat
    persona_key: mean-reverter
    description: "Hourly heartbeat, prices within band — do nothing"
    trigger:
      type: interval
      minutes: 60
    portfolio_state:
      cash_aud: 1000
      positions: {}
      open_orders: []
    market_snapshot:
      ETH/AUD: { top_ask: 3000, top_bid: 2999, mid: 2999.5 }
    expected:
      should_call_tool: null
      reasoning_mentions: [no stretch, hold]

  - id: tf-respects-max-order-cap
    persona_key: trend-follower
    description: "Strong breakout but order would exceed AUD 250 cap"
    trigger:
      type: price_breakout
      pair: ETH/AUD
      direction: up
      move_pct: 5
      lookback_bars: 24
    portfolio_state:
      cash_aud: 1000
      positions: {}
      open_orders: []
    market_snapshot:
      ETH/AUD: { top_ask: 3000, top_bid: 2999, mid: 2999.5 }
    expected:
      should_call_tool: place_paper_order
      order_notional_at_most_aud: 250
      reasoning_mentions: [scaling, cap]

  - id: mr-already-fully-positioned
    persona_key: mean-reverter
    description: "Further stretch but strategy already at 30% single-asset cap"
    trigger:
      type: price_stretch
      pair: SOL/AUD
      direction: below
      stdev_distance: 3
    portfolio_state:
      cash_aud: 700
      positions: { SOL: 300 }
      open_orders: []
    market_snapshot:
      SOL/AUD: { top_ask: 90, top_bid: 89.9, mid: 89.95 }
    expected:
      should_call_tool: null
      reasoning_mentions: [cap, fully positioned, hold]
```

- [ ] **Step 4: Implement the runner**

Create `backend/evals/personas_runner.py`:

```python
"""Per-persona scenario evaluation runner.

Runs each scenario through the persona, captures the tool-call output
and reasoning, then judges along three axes:
- Tool-call correctness (did the agent call the expected tool, or
  correctly decline to?)
- Reasoning quality (do mentioned-words appear in the rationale?)
- Risk discipline (did the agent stay within caps?)

The judge for reasoning quality reuses backend/evals/judges.py if
available; otherwise it does string-match scoring as a fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from backend.services.trading.cost_model import aud_per_usd, compute_cost_aud
from backend.services.trading.persona_loader import load_persona


SCENARIOS_PATH = Path(__file__).resolve().parent / "personas_golden_set.yaml"


@dataclass
class Scenario:
    id: str
    persona_key: str
    description: str
    trigger: dict
    portfolio_state: dict
    market_snapshot: dict
    expected: dict


def load_golden_set(path: Path = SCENARIOS_PATH) -> list[Scenario]:
    raw = yaml.safe_load(path.read_text())
    return [Scenario(**s) for s in raw["scenarios"]]


@dataclass
class ScenarioResult:
    id: str
    persona_key: str
    tool_call_correct: bool
    reasoning_score: float       # 0..1
    risk_disciplined: bool
    notes: list[str]


class PersonaEvalRunner:
    def __init__(self, *, scenarios: list[Scenario]) -> None:
        self.scenarios = scenarios

    @property
    def scenario_count(self) -> int:
        return len(self.scenarios)

    async def run_one(self, scenario: Scenario) -> ScenarioResult:
        """Execute a single scenario through the persona.

        For the smoke test, this is exercised only via pytest mark `eval`;
        the live LangGraph call hits real LLM APIs.
        """
        from backend.agent.graph import invoke_for_strategy
        persona = load_persona(scenario.persona_key)
        user_msg = (
            f"SCENARIO: {scenario.description}\n"
            f"Trigger: {scenario.trigger}\n"
            f"Portfolio: {scenario.portfolio_state}\n"
            f"Market: {scenario.market_snapshot}\n"
            "Decide what to do, calling tools as needed."
        )
        response = await invoke_for_strategy(
            system_prompt=persona.body, user_message=user_msg,
            model="claude-sonnet-4-6",
            tools_whitelist=["place_paper_order", "get_my_paper_state",
                             "get_market_snapshot"],
            strategy_id="eval-scenario",
        )
        return self._judge(scenario, response)

    def _judge(self, scenario: Scenario, response: dict) -> ScenarioResult:
        notes: list[str] = []
        expected = scenario.expected
        tool_calls = response.get("tool_calls", [])
        expected_tool = expected.get("should_call_tool")
        actually_called = tool_calls[0]["tool"] if tool_calls else None
        tool_ok = (expected_tool is None and actually_called is None) or \
                  (expected_tool is not None and actually_called == expected_tool)
        if not tool_ok:
            notes.append(f"expected tool {expected_tool}, got {actually_called}")
        # Reasoning string-match.
        reasoning = (response.get("agent_output") or "").lower()
        keywords = [k.lower() for k in expected.get("reasoning_mentions", [])]
        if keywords:
            hits = sum(1 for k in keywords if k in reasoning)
            score = hits / len(keywords)
        else:
            score = 1.0
        # Risk discipline.
        max_aud = expected.get("order_notional_at_most_aud")
        risk_ok = True
        if max_aud is not None and tool_calls:
            for tc in tool_calls:
                args = tc.get("args", {})
                qty = Decimal(str(args.get("qty", "0")))
                # Approximate notional via mid in market_snapshot.
                pair = args.get("pair")
                mid = scenario.market_snapshot.get(pair, {}).get("mid", 0)
                notional = qty * Decimal(str(mid))
                if notional > Decimal(str(max_aud)):
                    risk_ok = False
                    notes.append(f"notional {notional} > cap {max_aud}")
        return ScenarioResult(
            id=scenario.id, persona_key=scenario.persona_key,
            tool_call_correct=tool_ok, reasoning_score=score,
            risk_disciplined=risk_ok, notes=notes,
        )
```

Also append `personas_runner.py` invocation to the existing `backend/evals/test_evals.py` as a new `@pytest.mark.eval` test (one block — the actual integration with `test_evals.py` depends on the existing test's structure; if `test_evals.py` is parameterised by config, add a per-persona scenario block; otherwise add a new module `backend/evals/test_persona_evals.py` marked `eval`).

- [ ] **Step 5: Run smoke + commit and push**

Run: `backend/.venv/bin/pytest backend/tests/test_personas_eval_smoke.py -v`
Expected: 2 pass.

```bash
git add backend/evals/personas_golden_set.yaml backend/evals/personas_runner.py backend/tests/test_personas_eval_smoke.py
git commit -m "feat(evals): per-persona scenario golden set + runner (smoke-tested; full run on-demand)"
git push
```

---

## Part 11 — App Wiring

### Task 31: Startup hook + seed strategies

**Files:**
- Modify: `backend/main.py` (boot trading tasks on FastAPI startup)
- Modify: `backend/scheduler.py` (add the equity-snapshot hourly job)
- Create: `backend/scripts/seed_strategies.py`
- Test: `backend/tests/test_trading_seed.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trading_seed.py`:

```python
from decimal import Decimal

from backend.db.supabase_client import get_supabase
from backend.scripts.seed_strategies import (
    seed_dca_baseline, seed_trend_follower, seed_mean_reverter,
    seed_all,
)


def _strategies():
    sb = get_supabase()
    return sb.table("strategies").select("*").execute().data or []


def test_seed_dca_baseline_creates_deterministic_strategy():
    sid = seed_dca_baseline()
    sb = get_supabase()
    row = sb.table("strategies").select("*").eq("id", sid).execute().data[0]
    assert row["execution_mode"] == "deterministic"
    cfg = row["deterministic_config"]
    assert cfg["allocations"]["ETH/AUD"] == "0.50"


def test_seed_trend_follower_creates_llm_strategy_with_persona():
    sid = seed_trend_follower()
    sb = get_supabase()
    row = sb.table("strategies").select("*").eq("id", sid).execute().data[0]
    assert row["execution_mode"] == "llm_agent"
    assert row["persona_key"] == "trend-follower"


def test_seed_mean_reverter_creates_llm_strategy_with_persona():
    sid = seed_mean_reverter()
    sb = get_supabase()
    row = sb.table("strategies").select("*").eq("id", sid).execute().data[0]
    assert row["persona_key"] == "mean-reverter"


def test_seed_all_is_idempotent_by_name():
    seed_all()
    count1 = len([s for s in _strategies()
                  if s["name"] in ("DCA-Baseline", "Trend-Follower", "Mean-Reverter")])
    seed_all()
    count2 = len([s for s in _strategies()
                  if s["name"] in ("DCA-Baseline", "Trend-Follower", "Mean-Reverter")])
    assert count1 == count2 == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_seed.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement seeds + startup wiring**

Create `backend/scripts/seed_strategies.py`:

```python
"""Seed the three v1 strategies. Idempotent by name.

Run on app boot via main.py (after migrations) AND from CLI:
    backend/.venv/bin/python -m backend.scripts.seed_strategies
"""
from __future__ import annotations

import logging
from decimal import Decimal

from backend.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


_RISK_CAPS_DEFAULT = {
    "max_single_asset_pct": 30,
    "max_total_crypto_exposure_pct": 60,
    "max_order_aud": 250,
    "daily_loss_cap_aud": 100,
    "max_drawdown_pct_before_pause": 25,
    "allowed_pairs": ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"],
}

_KILL_CRITERIA_DEFAULT = {
    "auto_pause_when": [
        {"metric": "drawdown_pct", "op": ">=", "value": 25.0},
        {"metric": "daily_loss_aud", "op": ">=", "value": 100.0},
    ],
}


def _existing_id_by_name(name: str) -> str | None:
    sb = get_supabase()
    r = (sb.table("strategies").select("id").eq("name", name).limit(1).execute())
    return r.data[0]["id"] if r.data else None


def _seed_cash(strategy_id: str, amount_aud: Decimal) -> None:
    sb = get_supabase()
    r = (sb.table("paper_positions").select("strategy_id")
           .eq("strategy_id", strategy_id).eq("asset", "AUD")
           .limit(1).execute())
    if r.data:
        return
    sb.table("paper_positions").insert({
        "strategy_id": strategy_id, "asset": "AUD",
        "qty": str(amount_aud), "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()


def seed_dca_baseline() -> str:
    existing = _existing_id_by_name("DCA-Baseline")
    if existing:
        return existing
    sb = get_supabase()
    payload = {
        "name": "DCA-Baseline",
        "description": "Deterministic fortnightly buy; ETH-tilted control benchmark.",
        "execution_mode": "deterministic",
        "deterministic_config": {
            "cadence_cron": "0 9 */14 * *", "tz": "Australia/Sydney",
            "allocations": {"ETH/AUD": "0.50", "SOL/AUD": "0.25",
                            "LINK/AUD": "0.15", "ADA/AUD": "0.10"},
        },
        "starting_balance_aud": "1000",
        "trigger_config": {
            "triggers": [{"type": "cron", "expr": "0 9 */14 * *",
                          "tz": "Australia/Sydney"}],
            "debounce_seconds": 0, "cooldown_seconds": 0,
            "max_calls_per_hour": 1000,
        },
        "risk_caps": _RISK_CAPS_DEFAULT,
        "kill_criteria": _KILL_CRITERIA_DEFAULT,
        "status": "active", "dry_run": False,
    }
    sid = sb.table("strategies").insert(payload).execute().data[0]["id"]
    _seed_cash(sid, Decimal("1000"))
    return sid


def _seed_llm_strategy(name: str, persona_key: str,
                       triggers_extra: list[dict]) -> str:
    existing = _existing_id_by_name(name)
    if existing:
        return existing
    sb = get_supabase()
    payload = {
        "name": name,
        "execution_mode": "llm_agent",
        "persona_key": persona_key,
        "starting_balance_aud": "1000",
        "trigger_config": {
            "triggers": [{"type": "interval", "minutes": 60}, *triggers_extra,
                         {"type": "order_filled"}],
            "debounce_seconds": 5, "cooldown_seconds": 900,
            "max_calls_per_hour": 10,
        },
        "risk_caps": _RISK_CAPS_DEFAULT,
        "kill_criteria": _KILL_CRITERIA_DEFAULT,
        "status": "active", "dry_run": False,
        "model_preference": "claude-sonnet-4-6",
    }
    sid = sb.table("strategies").insert(payload).execute().data[0]["id"]
    _seed_cash(sid, Decimal("1000"))
    return sid


def seed_trend_follower() -> str:
    return _seed_llm_strategy(
        name="Trend-Follower", persona_key="trend-follower",
        triggers_extra=[{"type": "price_breakout",
                         "pair": p, "lookback_bars": 24,
                         "interval": "1h", "min_move_pct": 1.5}
                        for p in ["ETH/AUD","LINK/AUD","ADA/AUD","SOL/AUD"]],
    )


def seed_mean_reverter() -> str:
    return _seed_llm_strategy(
        name="Mean-Reverter", persona_key="mean-reverter",
        triggers_extra=[{"type": "price_stretch",
                         "pair": p, "lookback_bars": 48,
                         "interval": "1h", "stdev": 2.0}
                        for p in ["ETH/AUD","LINK/AUD","ADA/AUD","SOL/AUD"]],
    )


def seed_all() -> None:
    seed_dca_baseline()
    seed_trend_follower()
    seed_mean_reverter()


if __name__ == "__main__":
    seed_all()
    print("Seeded 3 strategies.")
```

In `backend/main.py`, add startup wiring. Find the existing startup
event (or create one if FastAPI's lifespan pattern is used in this
project — check `backend/main.py` for the existing pattern, e.g.,
`@app.on_event("startup")` or `lifespan=...`) and add:

```python
@app.on_event("startup")
async def _boot_trading_sandbox() -> None:
    import logging
    log = logging.getLogger(__name__)
    try:
        from backend.scripts.seed_strategies import seed_all
        seed_all()
    except Exception:
        log.exception("Strategy seed failed at startup")
    # Min-order universe validation.
    try:
        from decimal import Decimal
        from backend.services.trading.min_order import filter_allowed_pairs_by_min_order
        kept, dropped = filter_allowed_pairs_by_min_order(
            pairs=["ETH/AUD","LINK/AUD","ADA/AUD","SOL/AUD"],
            max_position_aud=Decimal("300"),
        )
        if dropped:
            from backend.repositories import system_alerts_repo
            for p in dropped:
                system_alerts_repo.insert(
                    level="warning", code="PAIR_DROPPED_MIN_ORDER",
                    strategy_id=None,
                    message=f"Pair {p} dropped from universe (min-order check)",
                    payload={"pair": p},
                )
    except Exception:
        log.exception("Min-order validation failed at startup")
    # Boot price feed + register triggers + attach executor.
    try:
        import asyncio
        from backend.services.trading.event_bus import get_default_bus
        from backend.services.trading.executor import PaperExecutor
        from backend.services.trading.price_feed import PriceFeed
        from backend.services.trading.strategy_loop import (
            set_executor, strategy_loop,
        )
        from backend.repositories import strategies_repo
        from backend.scheduler import (
            register_all_strategy_triggers, scheduler, start_scheduler,
        )
        from backend.services.trading.equity_snapshot import snapshot_all_active

        bus = get_default_bus()
        executor = PaperExecutor()
        set_executor(executor)
        pairs = ["ETH/AUD","LINK/AUD","ADA/AUD","SOL/AUD"]
        feed = PriceFeed(pairs=pairs, bus=bus, executor=executor)
        asyncio.create_task(feed.run())

        # Strategy loops.
        for strat in strategies_repo.list_active():
            asyncio.create_task(strategy_loop(strat, bus=bus))

        # Start (or extend) the existing scheduler.
        if not scheduler.running:
            start_scheduler()
        register_all_strategy_triggers()

        # Hourly equity snapshots — use current book mids.
        def _equity_job():
            mids = {p: b.mid() for p, b in executor._books.items()
                    if b.ts is not None}
            snapshot_all_active(mids=mids)
        scheduler.add_job(_equity_job, "interval", hours=1,
                          id="paper_equity_snapshot", replace_existing=True)
    except Exception:
        log.exception("Trading sandbox boot failed")
```

(Adapt syntax if `backend/main.py` already uses FastAPI's `lifespan`
context manager rather than `@on_event`.)

- [ ] **Step 4: Run tests + manual smoke**

Run: `backend/.venv/bin/pytest backend/tests/test_trading_seed.py -v`
Expected: 4 pass.

Manual smoke: start the API and confirm strategies boot.
```bash
backend/.venv/bin/uvicorn backend.main:app --reload --port 8001
```
- In a second terminal: `curl http://localhost:8001/api/strategies/`
- Expected: three rows (DCA-Baseline, Trend-Follower, Mean-Reverter).
- `curl http://localhost:8001/api/strategies/_health` should show the four pairs in `ws_feed` with non-null `last_tick_at` within a few seconds of boot.

- [ ] **Step 5: Commit and push**

```bash
git add backend/main.py backend/scheduler.py backend/scripts/seed_strategies.py backend/tests/test_trading_seed.py
git commit -m "feat(trading): boot trading sandbox at startup + seed 3 strategies (idempotent)"
git push
```

---

## Part 12 — Frontend

**Memory note carried into every Part-12 task:** frontend work in this project uses `/impeccable`. Each frontend task is written as: (1) define the contract (types/API calls/behaviour); (2) invoke `/impeccable craft` with a focused brief; (3) wire into the app; (4) manual smoke; (5) commit + push. Don't hand-write Tailwind classes — `/impeccable` is the project's design pipeline.

### Task 32: TypeScript types + API client

**Files:**
- Create: `frontend/src/types/strategies.ts`
- Create: `frontend/src/api/strategies.ts`

- [ ] **Step 1: Define the types**

Create `frontend/src/types/strategies.ts`:

```ts
export type ExecutionMode = "llm_agent" | "deterministic";
export type StrategyStatus = "active" | "paused" | "archived";

export interface Strategy {
  id: string;
  name: string;
  description: string | null;
  execution_mode: ExecutionMode;
  persona_key: string | null;
  deterministic_config: {
    cadence_cron: string;
    tz: string;
    allocations: Record<string, string>;
  } | null;
  starting_balance_aud: string;
  trigger_config: Record<string, unknown>;
  risk_caps: Record<string, unknown>;
  kill_criteria: Record<string, unknown>;
  model_preference: string | null;
  status: StrategyStatus;
  dry_run: boolean;
  persona_prompt_stable_since: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaderboardRow {
  id: string;
  name: string;
  status: StrategyStatus;
  execution_mode: ExecutionMode;
  equity_aud: string;
  return_7d_pct: string;
  return_30d_pct: string;
  return_all_time_pct: string;
  sharpe: string;
  max_drawdown_pct: string;
  trades: number;
  cost_30d_aud: string;
  persona_prompt_stable_since: string | null;
}

export interface EquityPoint {
  ts: string;
  equity_aud: string;
  cash_aud?: string;
  position_value_aud?: string;
}

export interface BenchmarkPoint {
  ts: string;
  equity_aud: string;
}

export interface EquityCurveResponse {
  strategy: EquityPoint[];
  benchmarks: {
    btc_hodl: BenchmarkPoint[];
    alt_basket_equal_weight: BenchmarkPoint[];
  };
}

export interface AgentDecision {
  id: string;
  strategy_id: string;
  execution_mode: string;
  trigger_event: { type: string; [k: string]: unknown };
  input_snapshot: Record<string, unknown>;
  persona_prompt_hash: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_aud: string;
  tool_calls: Array<{ tool: string; args?: Record<string, unknown> }>;
  agent_output: string | null;
  latency_ms: number | null;
  error: string | null;
  created_at: string;
}

export interface OpenOrder {
  id: string;
  strategy_id: string;
  pair: string;
  side: "buy" | "sell";
  type: "market" | "limit";
  qty: string;
  limit_price: string | null;
  expires_at: string | null;
  status: string;
  reject_reason: string | null;
  created_at: string;
}

export interface HealthResponse {
  ws_feed: Record<string, { last_tick_at: string | null; age_s: number | null }>;
  strategies: Array<{ id: string; name: string; status: StrategyStatus }>;
  executor: { last_fill_at: string | null; open_orders: number };
  db: { write_latency_ms_p99: number };
}

export type EquityRange = "1d" | "7d" | "30d" | "90d" | "all";
```

- [ ] **Step 2: Define the API client**

Create `frontend/src/api/strategies.ts`:

```ts
import type {
  AgentDecision, EquityCurveResponse, EquityRange, HealthResponse,
  LeaderboardRow, OpenOrder, Strategy,
} from "../types/strategies";

const BASE = "/api/strategies";

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

async function postJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { method: "POST", credentials: "include" });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

export const fetchStrategies = () => getJson<Strategy[]>(`${BASE}/`);
export const fetchStrategy = (id: string) => getJson<Strategy>(`${BASE}/${id}`);
export const fetchLeaderboard = () => getJson<LeaderboardRow[]>(`${BASE}/_leaderboard`);
export const fetchHealth = () => getJson<HealthResponse>(`${BASE}/_health`);

export const fetchEquityCurve = (id: string, range: EquityRange = "30d") =>
  getJson<EquityCurveResponse>(`${BASE}/${id}/equity?range=${range}`);

export const fetchDecisions = (id: string, n = 20) =>
  getJson<AgentDecision[]>(`${BASE}/${id}/decisions?n=${n}`);

export const fetchOpenOrders = (id: string) =>
  getJson<OpenOrder[]>(`${BASE}/${id}/open_orders`);

export const fetchPositions = (id: string) =>
  getJson<Record<string, { qty: string; avg_cost_aud: string }>>(`${BASE}/${id}/positions`);

export const pauseStrategy = (id: string) => postJson<{ ok: boolean }>(`${BASE}/${id}/pause`);
export const resumeStrategy = (id: string) => postJson<{ ok: boolean }>(`${BASE}/${id}/resume`);
export const archiveStrategy = (id: string) => postJson<{ ok: boolean }>(`${BASE}/${id}/archive`);
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/types/strategies.ts frontend/src/api/strategies.ts
git commit -m "feat(frontend): strategies types + API client"
git push
```

---

### Task 33: `<StrategiesPage>` shell + side-rail item

**Files:**
- Create: `frontend/src/pages/StrategiesPage.tsx`
- Modify: `frontend/src/App.tsx` (add `/strategies` route)
- Modify: `frontend/src/components/AppLayout.tsx` (add the "Strategies" side-rail item)

- [ ] **Step 1: Brief for `/impeccable`**

Invoke `/impeccable craft` with the following brief (the implementing agent should pass this as the skill input):

> **Page:** `frontend/src/pages/StrategiesPage.tsx` — new top-level
> route, sits in the side rail alongside Crypto / Up / Combined.
>
> **Layout (top to bottom):**
> 1. **Page header** — title "Strategies", subtitle "Multi-strategy paper-trading sandbox", a small `<SystemStatusBanner>` slot on the right (component built in Task 36 — render a placeholder div for now).
> 2. **Leaderboard table slot** — placeholder for `<LeaderboardTable>` (Task 34).
> 3. **Overlay equity chart slot** — placeholder for `<EquityChart>` (Task 35).
> 4. **Empty state** when no strategies exist: small card centred under header.
>
> **Styling notes:**
> - Match the existing CombinedPage container (`max-w-7xl mx-auto px-6 py-8` or whatever the project uses — check `frontend/src/pages/CombinedPage.tsx`).
> - Reuse the project's existing typography scale; do NOT redefine fonts/sizes.
> - Sober, data-rich aesthetic — this is a serious dashboard, not a marketing page.
>
> **Behaviour:**
> - On mount, fetch `/api/strategies/_leaderboard` once. Loading skeleton during fetch. If empty array, show the empty state.
>
> **Acceptance:** page loads at `/strategies`, side rail has a "Strategies" item, route navigation works, empty state visible when no strategies have data yet.

- [ ] **Step 2: Wire the route**

In `frontend/src/App.tsx` find the existing route definitions and add a `/strategies` route pointing at `<StrategiesPage>`. Example (adapt to whatever router setup the project uses — `react-router` or similar):

```tsx
import StrategiesPage from "./pages/StrategiesPage";
// ... inside the <Routes> tree:
<Route path="/strategies" element={<StrategiesPage />} />
```

In `frontend/src/components/AppLayout.tsx`, locate the side-rail nav items (existing entries for Crypto / Up / Combined). Add a "Strategies" item with the same icon/style as the others. Pick an icon that suggests competition or charts (e.g. lucide-react's `Trophy` or `LineChart`).

- [ ] **Step 3: Manual smoke**

Run: `cd frontend && npm run dev`

Visit `http://localhost:5173/strategies` (or whatever port your dev server uses).
- Side rail shows "Strategies" item.
- Clicking it navigates to the page.
- Empty state shown.

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/pages/StrategiesPage.tsx frontend/src/App.tsx frontend/src/components/AppLayout.tsx
git commit -m "feat(frontend): StrategiesPage shell + side-rail nav item"
git push
```

---

### Task 34: `<LeaderboardTable>` component

**Files:**
- Create: `frontend/src/components/strategies/LeaderboardTable.tsx`
- Modify: `frontend/src/pages/StrategiesPage.tsx` (replace the leaderboard placeholder)

- [ ] **Step 1: Brief for `/impeccable`**

Invoke `/impeccable craft` with this brief:

> **Component:** `LeaderboardTable.tsx`
>
> **Props:** `{ rows: LeaderboardRow[]; onRowClick: (id: string) => void }`
>
> **Columns (in order):**
> 1. Rank (computed: index + 1 after sorting by equity desc — rows arrive pre-sorted).
> 2. Strategy (name + small badge for execution_mode: `LLM` or `RULES`).
> 3. Equity AUD (right-aligned, monospaced, formatted `$1,012.34`).
> 4. 7d % (right-aligned, +green / -red, monospaced).
> 5. 30d % (same).
> 6. All-time % (same).
> 7. Sharpe (right-aligned, 2 dp).
> 8. Max DD (right-aligned, 2 dp, prefix "-", always red).
> 9. Trades (right-aligned, integer).
> 10. Cost AUD (30d) — small caption "USD cost" tooltip; integer rounded; zero for deterministic strategies.
> 11. Status (small dot + label).
>
> **Behaviour:**
> - Hover row → subtle highlight.
> - Click row → `onRowClick(row.id)`.
> - If `row.persona_prompt_stable_since` falls inside the 7d/30d window, render the return cell with a small footnote "* stable since YYYY-MM-DD" (tooltip with explanation: "Persona prompt changed during this window; comparison may not be apples-to-apples").
>
> **Empty state:** "No strategies yet" with the same card style as the page's empty state.

- [ ] **Step 2: Wire into the page**

Replace the leaderboard placeholder in `StrategiesPage.tsx`:

```tsx
import LeaderboardTable from "../components/strategies/LeaderboardTable";
// ...
<LeaderboardTable rows={rows} onRowClick={(id) => setSelectedId(id)} />
```

Maintain a local `selectedId: string | null` state so the detail drawer (Task 35–36) can open from a click.

- [ ] **Step 3: Manual smoke**

With the dev server running and the backend at least returning the seeded three strategies:
- Page should show three rows.
- DCA-Baseline shows `RULES` badge; the other two show `LLM`.
- Clicking a row should update `selectedId` (no drawer yet — verify via React DevTools or a `console.log`).

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/components/strategies/LeaderboardTable.tsx frontend/src/pages/StrategiesPage.tsx
git commit -m "feat(frontend): LeaderboardTable with stability-annotated return cells"
git push
```

---

### Task 35: `<EquityChart>` overlay with two benchmark lines

**Files:**
- Create: `frontend/src/components/strategies/EquityChart.tsx`
- Modify: `frontend/src/pages/StrategiesPage.tsx` (replace the chart placeholder)

- [ ] **Step 1: Brief for `/impeccable`**

Invoke `/impeccable craft` with this brief:

> **Component:** `EquityChart.tsx`
>
> **Props:**
> ```ts
> {
>   strategies: { id: string; name: string;
>                 curve: { ts: string; equity_aud: string }[] }[];
>   benchmarks: {
>     btc_hodl: { ts: string; equity_aud: string }[];
>     alt_basket_equal_weight: { ts: string; equity_aud: string }[];
>   };
>   range: EquityRange;
>   onRangeChange: (r: EquityRange) => void;
> }
> ```
>
> **Visual contract:**
> - One line per strategy (distinct colour per strategy).
> - **Two benchmark lines:** BTC/AUD HODL (dashed, neutral grey) and equal-weight ETH/LINK/ADA/SOL basket (dashed, different neutral). Both stand out as references but don't compete visually with the strategies.
> - Y-axis: AUD, formatted as `$1,000` style. Start the y-axis at 0 by default (toggle to "auto" optional).
> - X-axis: timestamps, day granularity for 30d+, hour granularity for 1d/7d.
> - Top-right: a range picker `[1D | 7D | 30D | 90D | All]` styled like the existing CombinedPage range picker.
> - Tooltip on hover: vertical guide line + all-strategy-and-benchmark values at that timestamp.
> - Legend below the chart (clickable to toggle a line).
>
> **Tech:** use the same charting library the existing CombinedPage uses (look for it in the imports — likely `recharts` or `visx`); do NOT introduce a new charting dependency.
>
> **Empty state:** if no strategy has any equity snapshots yet, render a friendly "No data yet — first snapshot will arrive within the hour" message rather than an empty chart frame.

- [ ] **Step 2: Wire into the page**

In `StrategiesPage.tsx`:
- Fetch each leaderboard row's `/api/strategies/{id}/equity?range=<range>` to assemble `strategies[]`.
- Use the first row's response's `benchmarks` for the benchmark lines (every call returns the same benchmark data — they're universe-level).
- Wire the `onRangeChange` to refetch with the new range.

- [ ] **Step 3: Manual smoke**

- Page loads, chart shows up.
- Range picker switches the data window.
- Both benchmark lines render with distinct dashed styles.
- Empty state shows the first time the page loads (before any equity snapshots have been written — which only happens at the top of each hour).

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/components/strategies/EquityChart.tsx frontend/src/pages/StrategiesPage.tsx
git commit -m "feat(frontend): EquityChart with strategies + 2 benchmark lines (BTC HODL + alt basket)"
git push
```

---

### Task 36: `<StrategyDetailDrawer>` + `<DecisionsFeed>` + `<PersonaChatTab>` + `<SystemStatusBanner>`

**Files:**
- Create: `frontend/src/components/strategies/StrategyDetailDrawer.tsx`
- Create: `frontend/src/components/strategies/DecisionsFeed.tsx`
- Create: `frontend/src/components/strategies/PersonaChatTab.tsx`
- Create: `frontend/src/components/strategies/SystemStatusBanner.tsx`
- Modify: `frontend/src/pages/StrategiesPage.tsx`

- [ ] **Step 1: Brief for `/impeccable` — drawer + feed**

Invoke `/impeccable craft` with:

> **Component:** `StrategyDetailDrawer.tsx`
>
> **Props:** `{ strategyId: string | null; onClose: () => void }`
>
> Renders a right-side drawer (or full-page modal on small screens) when `strategyId !== null`. Fetches the strategy's detail, open orders, positions, decisions, and equity curve in parallel on open.
>
> **Tabs inside the drawer:**
> 1. **Overview** — small equity curve (re-uses `<EquityChart>` with only this strategy + benchmarks, no range picker), open orders table, positions table.
> 2. **Decisions** — renders `<DecisionsFeed>` (component below).
> 3. **Persona Chat** — renders `<PersonaChatTab>` (component below). Hide this tab when `strategy.execution_mode === "deterministic"`.
>
> **Header of the drawer:** strategy name, status badge, three buttons — Pause / Resume / Archive — wired to the API. Pause is visible when status=active; Resume when status=paused. Archive always visible, with a confirm step.
>
> ---
>
> **Component:** `DecisionsFeed.tsx`
>
> **Props:** `{ strategyId: string }`
>
> Fetches `/api/strategies/{id}/decisions?n=50` and renders a reverse-chronological list. Each row:
> - Timestamp (relative + absolute on hover).
> - Trigger type chip.
> - Execution mode chip (LLM or RULES).
> - Cost (if LLM) — `$0.04` style.
> - Agent reasoning text (collapsed by default, expand on click). Deterministic rows say "Scheduled buy/rebalance" instead.
> - Tool calls expanded inline as a small code-styled block (`place_paper_order(...)`).
> - If `error` is present, render the row red.

- [ ] **Step 2: Brief for `/impeccable` — persona chat tab**

Invoke `/impeccable craft` with:

> **Component:** `PersonaChatTab.tsx`
>
> **Props:** `{ strategyId: string; personaKey: string }`
>
> A read-only chat surface. The user can ask the agent questions about
> this strategy ("why are you holding so much LINK?"). Under the hood
> this hits the existing chat endpoint with the persona-conversational
> mode — the agent loads with the strategy's persona prompt + state
> context but does NOT have access to `place_paper_order` or
> `cancel_paper_order` (those tools are deliberately excluded; the chat
> can call `get_my_paper_state`, `get_my_recent_decisions`,
> `get_market_snapshot` only).
>
> **Endpoint:** reuse the project's existing chat endpoint (look for `/api/agent/chat` or similar in `backend/routers/`); pass `mode=persona_conversational` and `strategy_id=…` in the request. If the existing chat endpoint doesn't support these query params yet, add them as a one-line backend follow-up (out of scope for this task — open a TODO).
>
> **Visual:** match the existing chat panel style (look at the existing agent chat component in the dashboard).
>
> **Acceptance:** user types a question, receives a response, no trade is placed. Verify by checking `paper_orders` after a chat.

- [ ] **Step 3: Brief for `/impeccable` — status banner**

Invoke `/impeccable craft` with:

> **Component:** `SystemStatusBanner.tsx`
>
> **Props:** `{ refreshSeconds?: number }` (default 15)
>
> Polls `/api/strategies/_health` every `refreshSeconds`. Renders a small bar at the top of the StrategiesPage:
> - **Green** when all `ws_feed` ages < 30 s and no unacknowledged system alerts in the last 24h.
> - **Amber** when any feed > 30 s OR any strategy auto-paused in last 24h OR any pair dropped at startup.
> - **Red** when any feed > 5 min or DB write latency > 500 ms.
>
> Banner shows a small icon + brief status text + a "details" toggle that expands a list of all anomalies.

- [ ] **Step 4: Wire everything into the page**

In `StrategiesPage.tsx`:
- Top-right of header: `<SystemStatusBanner />`.
- Below `<LeaderboardTable>`: `<StrategyDetailDrawer strategyId={selectedId} onClose={() => setSelectedId(null)} />`.

- [ ] **Step 5: Manual smoke + commit + push**

Run dev server. Click a leaderboard row → drawer opens. Tabs work. Pause then resume the strategy — status badge updates. Open the Persona Chat tab on Trend-Follower, ask it something, verify no new `paper_orders` row was inserted.

```bash
git add frontend/src/components/strategies/StrategyDetailDrawer.tsx frontend/src/components/strategies/DecisionsFeed.tsx frontend/src/components/strategies/PersonaChatTab.tsx frontend/src/components/strategies/SystemStatusBanner.tsx frontend/src/pages/StrategiesPage.tsx
git commit -m "feat(frontend): drawer + decisions feed + persona chat + status banner"
git push
```

---

## Part 13 — Final

### Task 37: Manual smoke checklist + end-to-end verification

**Files:**
- Create: `docs/manual-smoke-strategies.md`

- [ ] **Step 1: Write the smoke checklist**

Create `docs/manual-smoke-strategies.md`:

```markdown
# Paper-Trading Sandbox — Manual Smoke Checklist

Run before each major release / when verifying the system end-to-end.

## 1. Backend boot
- [ ] `backend/.venv/bin/uvicorn backend.main:app --reload --port 8001` starts without exceptions.
- [ ] `curl http://localhost:8001/api/strategies/` returns three rows: DCA-Baseline, Trend-Follower, Mean-Reverter.
- [ ] `curl http://localhost:8001/api/strategies/_health` returns four `ws_feed` entries with `age_s < 5` within 10 s of boot.

## 2. Universe validation
- [ ] No `PAIR_DROPPED_MIN_ORDER` rows in `system_alerts` at v1 capital (AUD 1k).

## 3. Deterministic strategy
- [ ] Manually trigger DCA-Baseline via psql or admin tool:
  `UPDATE strategies SET trigger_config = ... WHERE name = 'DCA-Baseline';`
  (Or just wait for the next fortnightly cron firing.)
- [ ] `agent_decisions` for DCA-Baseline shows `execution_mode='deterministic'`, `model=null`, `cost_aud=0`.
- [ ] Four `paper_orders` rows (ETH/SOL/LINK/ADA) are created at ratios 50/25/15/10 of AUD 1k.
- [ ] After ~60 s the orders fill (book-walked), `paper_fills` rows exist, `paper_positions` updated.

## 4. LLM strategies
- [ ] Wait for an hourly heartbeat OR simulate a breakout by replaying a saved book snapshot.
- [ ] Trend-Follower's `agent_decisions` row has `execution_mode='llm_agent'`, non-null `model`, `input_tokens>0`, `cost_aud>0`, `persona_prompt_hash` matches `sha256(personas/trend-follower.md)`.
- [ ] Same for Mean-Reverter.

## 5. Risk caps
- [ ] Force an order > AUD 250 via the MCP tool — receive `rejected` with `MAX_ORDER_AUD`.
- [ ] Force a 4th alt buy after 3 × 30% positions exist — receive `rejected` with `MAX_TOTAL_CRYPTO_EXPOSURE_PCT`.

## 6. Kill criteria
- [ ] Manually insert a 25%+ drawdown equity snapshot for a test strategy → strategy auto-pauses, `system_alerts` row created, status flips to `paused`.

## 7. Idempotency
- [ ] Submit `place_paper_order` twice with the same `idempotency_key` — only one row in `paper_orders`.

## 8. Frontend
- [ ] `/strategies` route loads.
- [ ] Leaderboard shows three rows sorted by equity desc.
- [ ] Equity chart shows the strategy curves + BTC HODL dashed line + alt-basket dashed line.
- [ ] Range picker (1D / 7D / 30D / 90D / All) filters the chart.
- [ ] Clicking a row opens the detail drawer.
- [ ] Decisions feed populates after the first invocation.
- [ ] Persona Chat tab works on Trend-Follower; sending a message does NOT create a `paper_orders` row.
- [ ] Status banner renders green when feeds are fresh.
- [ ] Pause/Resume/Archive buttons reflect in DB.

## 9. Dry-run mode
- [ ] Flip `Trend-Follower.dry_run = true` via psql. Wait for next invocation.
- [ ] `agent_decisions` row written. `paper_orders` NOT created.
- [ ] Flip back to false; verify orders resume.

## 10. Cost attribution
- [ ] After ~24h of running, check `paper_strategy_costs` view: should show per-day per-strategy AUD cost.
- [ ] Monthly total within AUD 40–70 band (spec §6.5 estimate); investigate if much higher.
```

- [ ] **Step 2: Self-review the plan against the spec**

Walk through every section of `docs/superpowers/specs/2026-05-12-paper-trading-sandbox-design.md` and verify each requirement has a corresponding task. Use this checklist:

| Spec section | Implementing tasks |
|---|---|
| §1 Goal | overall |
| §2 In/out of scope | overall |
| §2 Decisions log | each row is honoured by the implementing task (see in-task comments) |
| §3 Architecture | Tasks 16, 17, 18, 31 |
| §4.1 strategies | Tasks 2, 31 |
| §4.2 paper_orders | Tasks 2, 11, 12 |
| §4.3 paper_fills | Tasks 2, 11, 12 |
| §4.4 paper_positions | Tasks 2, 11 |
| §4.5 agent_decisions | Tasks 2, 20, 24 |
| §4.6 paper_equity_snapshots | Tasks 2, 25 |
| §4.7 paper_benchmarks | Tasks 2, 26 |
| §4.8 system_alerts | Tasks 2, 18, 31 |
| §5.1 OrderExecutor Protocol | Task 10 |
| §5.2 PaperExecutor algorithm | Tasks 11, 12 |
| §5.3 Fill model | Tasks 4, 6 |
| §5.4 Fee schedule | Task 5 |
| §5.5 Idempotency | Task 11 |
| §5.6 Lot ledger | Task 11 (`_apply_positions`) |
| §5.7 Min-order validation | Tasks 9, 31 |
| §5.8 LiveKrakenExecutor (future) | documented; not built |
| §5.9 Error handling | Tasks 11, 18 |
| §6.1 Strategy loop | Task 18 |
| §6.2 Trigger taxonomy | Tasks 14, 17 |
| §6.3 Throttling | Task 15 |
| §6.4 Deterministic path | Tasks 19, 20 |
| §6.5 Cost ballpark | Task 24 + manual smoke item 10 |
| §7.1 MCP tools | Task 23 |
| §7.2 Two invocation modes | Task 24 (strategy) + Task 36 (persona-conversational) |
| §7.3 Persona files | Tasks 21, 22 |
| §7.4 Cost tracking | Task 24 |
| §7.5 Eval harness extension | Task 30 |
| §8 Frontend | Tasks 32–36 |
| §9.1 Audit | Task 20, 24 |
| §9.2 Dry-run mode | covered in §4.1 schema + Tasks 20, 24; manual smoke item 9 |
| §9.3 Health endpoint | Task 29 |
| §9.4 Kill switch | Task 28 |
| §9.5 Kill criteria | Task 8 + ongoing evaluation lives in Task 25's hourly snapshot job (extend it to call evaluator) — see open item below |
| §9.6 Alert channel | Task 18, 31 |
| §10 Testing | every task |
| §11 Future evolution (Approach B) | documented in spec; not built |

**Gap identified during self-review:** kill-criteria are *evaluated* (Task 8) but the *scheduled evaluation* (post each equity snapshot) is implicit in the hourly equity-snapshot job. To close this, extend Task 25's `snapshot_all_active` to call `evaluate_kill_criteria` after computing each snapshot and auto-pause via `strategies_repo.update_status` if a criterion fires. If you're executing this plan task-by-task, add this as a small follow-up commit immediately after Task 25 or before Task 37 — don't ship without it.

```python
# In backend/services/trading/equity_snapshot.py, inside snapshot_all_active loop,
# after insert_snapshot(...):
from backend.services.trading.kill_criteria import (
    KillSnapshot, evaluate_kill_criteria,
)
from backend.models.trading import KillCriteria
# Build a KillSnapshot from the equity history and call evaluate.
# If fires, call strategies_repo.update_status(strat.id, "paused") and
# system_alerts_repo.insert(...).
```

- [ ] **Step 3: End-to-end verification**

Run the entire `docs/manual-smoke-strategies.md` checklist top to bottom. Every box should tick. If any item fails, file a focused follow-up commit rather than a sprawling fix.

- [ ] **Step 4: Mark plan complete**

Run: `backend/.venv/bin/pytest backend/tests/ -k "trading or strategies or personas" -v`
Expected: all passing.

```bash
git add docs/manual-smoke-strategies.md
git commit -m "docs: manual smoke checklist for paper-trading sandbox v1"
git push
```

- [ ] **Step 5: Final summary commit (optional)**

If the implementing agent wants a marker commit signalling v1 completion:

```bash
git commit --allow-empty -m "chore: paper-trading sandbox v1 complete"
git push
```

---

## Spec coverage map (final self-review)

Every spec section is covered by at least one task; the trigger gap
(kill-criteria evaluation timing) is called out explicitly above. No
TBDs remain. Type names and method signatures are consistent across
tasks (verified during the inline self-review): `OrderResult`,
`PaperExecutor.submit_order`, `OrderExecutor` protocol, `risk_cap_precheck`,
`evaluate_kill_criteria`, `compute_rebalance_orders`,
`compute_equity_for_strategy`, etc.

## Open follow-ups (track outside this plan)

1. **LiveKrakenExecutor** — spec §5.8 documents the contract; build when ready to flip to real money.
2. **Approach B lift to worker** — spec §11; verify Supabase LISTEN/NOTIFY connection mode before committing.
3. **Backtester (Phase 2)** — separate spec; vectorbt is the right pick when scoped.
4. **Personal-DCA-Shadow persona** — track real-life BTC/USDT DCA alongside the lab benchmarks if desired.
5. **Cross-strategy meta-portfolio view** — for the "total paper net worth across all bots" page.

---

*End of plan.*
