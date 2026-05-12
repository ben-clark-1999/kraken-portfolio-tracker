# Paper Trading Sandbox — Design Spec

**Date:** 2026-05-12
**Status:** Draft (brainstorming complete; awaiting user review of written spec)
**Predecessor specs:**
- Recurring Charges — `docs/superpowers/specs/2026-05-12-recurring-charges-design.md`
- Tax Hub Foundation — `docs/superpowers/specs/2026-04-27-tax-hub-foundation-design.md`

**Sub-specs (deferred):**
- Phase 2 — Backtester (vectorbt-based historical replay)
- Phase 3 — Real-money execution (`LiveKrakenExecutor`)
- Approach B — Lift to separate worker process (Section 11 of this doc)

---

## 1. Goal

Build a multi-strategy paper-trading sandbox that lets the existing LangGraph
agent (and future deterministic strategies) place simulated trades on Kraken
AUD pairs. Designed from day one for a clean swap to real-money execution,
with isolation, idempotency, and audit trail baked into the `OrderExecutor`
contract.

This is the foundation for a long-term experimentation environment — paper
today, real later, multi-strategy throughout. v1 ships three strategies
running in parallel against the user's chosen alt-AUD universe, with a
leaderboard and two passive benchmark lines so "is this strategy any good"
has an honest answer.

### Why this exists

- **Resume value and learning.** Builds out the event-driven, agent-driven
  bot shape that's natural next territory from the existing LangGraph + MCP
  stack — without committing real capital while the design matures.
- **Honest evaluation.** Without paper-trading infrastructure, every "is
  this a good idea?" conversation with the agent is hypothetical. With it,
  the agent's decisions accumulate into an equity curve that argues for or
  against itself.
- **Foundation for a real bot.** The `OrderExecutor` abstraction means the
  day the user decides paper → live is a config change + one new class, not
  a rewrite.

---

## 2. Scope

### In scope (v1)

- **3 strategies running in parallel**, each in its own asyncio task:
  - **DCA-Baseline** — deterministic (no LLM); fortnightly cron buy at
    fixed weights (ETH 50 / SOL 25 / LINK 15 / ADA 10).
  - **Trend-Follower** — `llm_agent` execution mode; reacts to breakouts
    and an hourly heartbeat.
  - **Mean-Reverter** — `llm_agent` execution mode; reacts to price
    stretches and an hourly heartbeat.
- **4 trading pairs:** ETH/AUD, LINK/AUD, ADA/AUD, SOL/AUD. All four
  verified tradable at AUD 1,000 capital (see §5.7).
- **`OrderExecutor` abstraction** with `PaperExecutor` as v1 concrete
  implementation; designed so `LiveKrakenExecutor` later is a drop-in.
- **L2-book-walking fill model** using Kraken's live order-book WS feed
  per pair; fees and slippage applied per fill.
- **Risk caps** (per strategy): max single-asset %, max total crypto %,
  daily loss cap, max-drawdown auto-pause, max single order AUD.
- **Continuous / event-driven activity model** — cron + interval triggers
  from a scheduler, market-event triggers from the price feed,
  portfolio-event triggers from the executor.
- **Trigger throttling** — per-strategy debounce (5 s), cooldown (15 min),
  and rate cap (10 LLM calls/h) so a chatty market can't blow the LLM bill.
- **5 new MCP tools** for the agent: `place_paper_order`,
  `cancel_paper_order`, `get_my_paper_state`,
  `get_my_recent_decisions`, `get_market_snapshot`.
- **Persona prompts as markdown** in `backend/agent/personas/`, referenced
  by `strategies.persona_key`. Eval-harness extended to score each
  persona on canned trigger scenarios.
- **New top-level `<StrategiesPage>`** in the side rail with:
  - Leaderboard table (rank, equity, returns, Sharpe, max DD, trades).
  - Overlay equity chart for all strategies + two benchmark lines:
    BTC/AUD HODL and an equal-weight ETH/LINK/ADA/SOL basket
    (rebalanced monthly).
  - Per-strategy detail drawer with equity curve, open positions,
    decisions feed, and an in-context chat tab that queries the agent
    loaded with that strategy's persona.
- **Per-call cost attribution** — `model`, `input_tokens`, `output_tokens`,
  `cost_aud` columns on `agent_decisions`; per-strategy cost roll-up view.
- **Property-based tests** on risk caps using `hypothesis`.
- **Explicit boundary unit tests** on the kill-criteria evaluator.
- **Eval-harness extension** for per-persona scenario battery.

### Out of scope (deferred or excluded)

- **`LiveKrakenExecutor`** — designed-for but not built. Future spec.
- **Funding-rate-arbitrage persona** — would require Kraken Futures and a
  BTC perp leg; conflicts with the spot-AUD universe and is excluded for
  v1.
- **Market-making persona** — needs sub-second loops Approach A can't
  deliver responsibly.
- **ML-driven strategies** (López de Prado techniques — triple-barrier
  labelling, purged CV, fractional differentiation) — deferred until a
  future "ML-Predictor" persona is scoped. Mentioned here so future-us
  knows the body of work exists.
- **Historical backtester (`vectorbt` / `backtrader`)** — separate Phase 2
  spec. Useful but distinct from the paper-trading goal.
- **Multi-exchange via `ccxt`** — deferred. Single-Kraken keeps the build
  small; `OrderExecutor` abstraction makes the swap a 1-file change later.
- **QuantConnect Lean migration** — explicitly rejected. We're building on
  the existing stack, not replacing it.
- **Approach B (separate worker process)** — Section 11 captures the
  migration path; not v1 work.
- **Cross-strategy meta-portfolio view** — future. v1 each strategy is its
  own portfolio.
- **Personal-DCA-Shadow persona** (tracking real-life BTC/USDT DCA for
  comparison) — future, not v1.
- **CGT realisation events** on paper fills — paper trades aren't real
  disposals, so no CGT side-effects. The cost-basis-per-lot ledger is
  still maintained (§5.6) so the future `LiveKrakenExecutor` can feed
  the Tax Hub without retrofit.

### Design decisions log

| # | Decision | Reasoning |
|---|---|---|
| 1 | Single-process asyncio (Approach A), not separate worker (Approach B) | Faster to ship; same DB schema and `OrderExecutor` contract apply to both, so the lift later is a refactor not a rewrite. |
| 2 | Personas in code (`personas/*.md`), not DB-stored prompts | Git-reviewed, eval-testable, no DB-UI footgun. Matches existing `backend/agent/prompts.py` pattern. |
| 3 | DCA-Baseline runs in `deterministic` mode (no LLM) | Routing the control through an LLM lets it "think its way out" of scheduled buys. Real benchmarks must be predictable. Each strategy gets an `execution_mode` enum. |
| 4 | Starting capital AUD 1,000/strategy (not 10k) | Fees are deployment-honest at this scale. 10k would hide fee friction in paper that would emerge live. |
| 5 | Universe = ETH/AUD, LINK/AUD, ADA/AUD, SOL/AUD; no BTC, no USD pairs | User preference; all four verified tradable at AUD 1k capital against the 5%-of-max-position rule. |
| 6 | DCA-Baseline weights ETH 50 / SOL 25 / LINK 15 / ADA 10 | User's stated conviction ordering ETH > SOL > LINK > ADA. Captured to prevent future "wait, why not equal-weight?" confusion. |
| 7 | ETH-tilt enforced only on the baseline, not on smart strategies | Smart strategies need room to find edge in any pair; otherwise they're just "DCA-Baseline with timing." |
| 8 | Symmetric risk caps on smart strategies (30%/asset, 60%/total crypto) | Bounded but not strangled. Auto-pause on 25% drawdown or AUD 50/day loss. |
| 9 | One `OrderExecutor` Protocol shared by paper and live | Same strategy/agent code runs in both modes; cleaner than parallel interfaces. |
| 10 | Parallel `live_*` tables when going live (not a `mode` column) | Prevents cross-mode joins from accidentally mixing real and paper data. |
| 11 | Equal-weight basket benchmark **rebalanced monthly** | Buy-and-hold would drift toward whichever coin pumped hardest, making the benchmark "lucky." Monthly rebalance keeps it honest. |
| 12 | Two benchmark lines on the chart (BTC HODL + same-universe basket), not one | BTC HODL answers "did crypto win?"; same-universe basket answers "did your strategy add value within your chosen universe?" Both are needed. |
| 13 | Kraken Pro Starter fees (**0.25% maker / 0.40% taker**) — verified against kraken.com/features/fee-schedule | Realistic for sub-$10k 30-day volume. Using a deeper-tier fee would flatter strategies in paper that won't hold up live. |
| 14 | Limit-order TTL **24 h** default | Long enough for overnight, short enough to avoid stale orders firing on day-old logic. Overridable per order. |
| 15 | Rate cap **10 LLM calls/h/strategy** | Caps worst-case LLM cost at ~AUD 30–45/month across the three strategies (DCA-Baseline doesn't count). Tunable. |
| 16 | Min-order runtime check + drop on failure | Defensive: Kraken `ordermin × current_price` > 5% of max position → pair removed from `allowed_pairs` at strategy startup, system alert raised. As of 2026-05-12 all four pairs pass. |
| 17 | Trigger taxonomy: `cron`, `interval`, `price_breakout`, `price_stretch`, `order_filled`, `drawdown` | Explicit list rather than free-form "events." Each strategy declares which it subscribes to. |
| 18 | Persona-prompt-hash captured on every `agent_decisions` row | Lets you correlate performance with a specific prompt version after iteration. |
| 19 | Token + cost attribution from day one | `model`, `input_tokens`, `output_tokens`, `cost_aud` on every `agent_decisions` row. Per-strategy cost roll-up surfaces on the leaderboard. |
| 20 | Property-based tests on risk caps; explicit boundary tests on kill criteria | These are the load-bearing pieces of the discipline story — generic example-based tests miss edge cases. |

---

## 3. Architecture

### High-level shape (Approach A — single-process)

```
                     ┌───────────────────────────────────┐
                     │  Existing FastAPI process         │
                     │                                   │
                     │  ┌──────────────────────────────┐ │
   Kraken WS ───────►│  │ price_feed_task              │ │
   (tick + L2 book)  │  │  - one WS connection         │ │
                     │  │  - publishes Tick + Book     │ │
                     │  │    events                    │ │
                     │  └────────────┬─────────────────┘ │
                     │               │                   │
                     │  ┌────────────┴─────────────────┐ │
                     │  │ scheduler_task               │ │
                     │  │  - cron + interval triggers  │ │
                     │  │  - publishes Heartbeat       │ │
                     │  │    events                    │ │
                     │  └────────────┬─────────────────┘ │
                     │               │                   │
                     │      shared asyncio Queue         │
                     │  ┌────────────┼────────┬─────────┐│
                     │  ▼            ▼        ▼         ││
                     │ Strategy A  Strategy B  Strategy C│
                     │  loop_task   loop_task   loop_task│
                     │   │            │          │      ││
                     │   ▼            ▼          ▼      ││
                     │  Trigger policy (debounce,        │
                     │  cooldown, rate-cap)              │
                     │   │                               │
                     │   ▼                               │
                     │ if llm_agent → invoke LangGraph   │
                     │ if deterministic → compute trades │
                     │                  directly         │
                     │                  │                │
                     │                  ▼                │
                     │           OrderExecutor (Paper)   │
                     │                  │                │
                     │                  ▼                │
                     │           Postgres (Supabase)     │
                     │  strategies / paper_orders /      │
                     │  paper_fills / paper_positions /  │
                     │  agent_decisions /                │
                     │  paper_equity_snapshots /         │
                     │  system_alerts                    │
                     └───────────────────────────────────┘
                                      ▲
                                      │ reads
                  ┌───────────────────┴──────────────┐
                  │  Frontend StrategiesPage         │
                  │  - leaderboard                   │
                  │  - overlay equity chart          │
                  │    (strategies + 2 benchmarks)   │
                  │  - detail drawer + persona chat  │
                  └──────────────────────────────────┘
```

### Component responsibilities

- **`price_feed_task`** — one Kraken WS client subscribed to `trade` and
  `book` channels for all four pairs. Maintains a `LocalOrderBook` per pair
  (snapshot + diff + checksum reconciliation). Publishes normalised
  `TickEvent` and `BookUpdateEvent` to the shared bus.
- **`scheduler_task`** — APScheduler-style. Reads each strategy's
  `trigger_config`, fires `CronTriggerEvent` and `IntervalTriggerEvent` on
  schedule. Holds the only cron state machine in the process.
- **`strategy_loop_task`** (one per active strategy) — subscribes to the
  bus, filters events against this strategy's `trigger_config`, applies
  the trigger policy (debounce / cooldown / rate-cap), then either:
  - calls the LangGraph agent (if `execution_mode = llm_agent`), or
  - computes trades from `deterministic_config` directly (if
    `execution_mode = deterministic`).
- **`OrderExecutor`** — abstraction. `PaperExecutor` is the v1 impl;
  walks the local L2 book to fill orders, charges fees, writes to DB.
- **`agent_decisions` writer** — wraps both code paths so every
  invocation (LLM or deterministic) leaves an audit row.
- **API routes** — read-only `/api/strategies/*` for the frontend;
  `/api/strategies/{id}/pause`, `/resume`, `/archive` for control;
  `/api/strategies/_health` for system status.
- **Frontend `<StrategiesPage>`** — built with `/impeccable`. Reads
  from the API; doesn't talk to the bus directly.

### Why Approach A first

The user's longer-term shape is Approach B (separate worker process,
Postgres `LISTEN/NOTIFY` as event bus). Approach A is the deliberate
v1 because:

- Same DB schema, same `OrderExecutor` contract — lifting later is a
  refactor, not a rewrite (§11).
- One process to run locally and deploy; no new infrastructure.
- The single-user, low-volume reality (3 strategies, < 50 agent calls/day
  total) doesn't stress a single asyncio loop.
- Risks (one strategy bug taking down the API) are mitigated by
  per-strategy exception isolation in the loop tasks.

---

## 4. Data Model

All tables live in the existing Supabase Postgres. AUD is the base
currency for equity, P&L, and benchmarks. Pair quoting follows
Kraken's symbol conventions (`ETH/AUD` etc).

### 4.1 `strategies`

One row per strategy.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `name` | text | Display name. e.g. "Trend-Follower" |
| `description` | text | Free-form note |
| `execution_mode` | enum (`llm_agent`, `deterministic`) | Switches the loop's code path |
| `persona_key` | text nullable | e.g. "trend-follower"; loads `personas/{persona_key}.md`. Null when `execution_mode = deterministic` |
| `deterministic_config` | jsonb nullable | `{ cadence: cron_expr, tz, allocations: {pair: weight} }`. Null when `execution_mode = llm_agent` |
| `starting_balance_aud` | numeric(12,2) | Default 1000.00 |
| `trigger_config` | jsonb | See §6.2 trigger taxonomy. Includes `triggers[]`, `debounce_seconds`, `cooldown_seconds`, `max_calls_per_hour` |
| `risk_caps` | jsonb | `{ max_single_asset_pct, max_total_crypto_exposure_pct, max_order_aud, daily_loss_cap_aud, max_drawdown_pct_before_pause, allowed_pairs[] }` |
| `kill_criteria` | jsonb | Pre-committed auto-pause conditions evaluated after every equity snapshot |
| `model_preference` | text nullable | e.g. "claude-sonnet-4-6" or "claude-haiku-4-5"; null = default |
| `status` | enum (`active`, `paused`, `archived`) | Loop reads before every invocation |
| `dry_run` | bool | If true, decisions are written but executor is not called |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### 4.2 `paper_orders`

Every order the strategy intended.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `strategy_id` | uuid FK | |
| `idempotency_key` | text | UNIQUE per `(strategy_id, idempotency_key)`. Format: `{strategy_id}:{decision_id}:{order_seq}`. Maps to Kraken `userref` when live |
| `pair` | text | e.g. "ETH/AUD" |
| `side` | enum (`buy`, `sell`) | |
| `type` | enum (`market`, `limit`) | |
| `qty` | numeric(20,10) | Base-currency quantity |
| `limit_price` | numeric(20,10) nullable | |
| `expires_at` | timestamptz nullable | Default 24 h from creation for limit orders |
| `status` | enum (`pending`, `filled`, `partial`, `rejected`, `cancelled`, `expired`) | |
| `reject_reason` | text nullable | Specific cap name or error code |
| `decided_by` | uuid FK → `agent_decisions.id` | Audit linkage |
| `created_at` | timestamptz | |

### 4.3 `paper_fills`

Actual fills against an order. One order may produce many (limit orders
fill in pieces, market orders walk multiple book levels).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `order_id` | uuid FK | |
| `qty` | numeric(20,10) | |
| `price` | numeric(20,10) | Volume-weighted level price |
| `fee_aud` | numeric(12,4) | Charged at maker or taker rate per the order's role |
| `fee_role` | enum (`maker`, `taker`) | |
| `book_state_hash` | text | Kraken L2 checksum at the time of fill; lets us replay the exact microstructure on post-mortem |
| `filled_at` | timestamptz | |

### 4.4 `paper_positions`

Materialised current state per strategy + asset. Derivable from fills,
stored for read performance. Cash sits in `asset = 'AUD'`.

| Column | Type | Notes |
|---|---|---|
| `strategy_id` | uuid | Composite PK with `asset` |
| `asset` | text | e.g. "ETH" or "AUD" |
| `qty` | numeric(20,10) | |
| `avg_cost_aud` | numeric(12,4) | Cost-basis per unit, for the lot ledger |
| `lots_jsonb` | jsonb | Per-lot detail: `[{qty, cost_aud, acquired_at, fill_id}]`. Feeds future Tax Hub once live |
| `updated_at` | timestamptz | |

### 4.5 `agent_decisions`

Audit row per strategy invocation. Written for both LLM and
deterministic strategies. Verbose but cheap and irreplaceable
for post-mortems.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `strategy_id` | uuid FK | |
| `execution_mode` | text | Mirrors strategy's mode at decision time |
| `trigger_event` | jsonb | The event that woke the strategy up |
| `input_snapshot` | jsonb | Portfolio + recent prices + recent fills passed to the agent (or to the deterministic code path) |
| `persona_prompt_hash` | text nullable | SHA-256 of the persona prompt; null for deterministic |
| `model` | text nullable | e.g. "claude-sonnet-4-6"; null for deterministic |
| `input_tokens` | int | 0 for deterministic |
| `output_tokens` | int | 0 for deterministic |
| `cost_aud` | numeric(10,4) | Computed at call time from `model_prices` constant + AUD/USD FX; stable across price changes |
| `tool_calls` | jsonb | List of MCP tools invoked with args and results |
| `agent_output` | text nullable | The agent's reasoning text; required when `execution_mode = llm_agent` |
| `latency_ms` | int | End-to-end |
| `error` | text nullable | If the invocation failed |
| `created_at` | timestamptz | Indexed with `strategy_id` for fast post-mortems |

### 4.6 `paper_equity_snapshots`

Hourly equity-curve points. Used for charts, leaderboard metrics, and
kill-criteria evaluation.

| Column | Type | Notes |
|---|---|---|
| `strategy_id` | uuid | Composite PK with `ts` |
| `ts` | timestamptz | |
| `equity_aud` | numeric(14,4) | Cash + position value at mid |
| `cash_aud` | numeric(14,4) | |
| `position_value_aud` | numeric(14,4) | |
| `realised_pnl_aud` | numeric(14,4) | Cumulative since strategy start |
| `unrealised_pnl_aud` | numeric(14,4) | |

### 4.7 `paper_benchmarks`

Mirror of `paper_equity_snapshots` for benchmark portfolios. Two
benchmark rows per hour: BTC HODL and equal-weight ETH/LINK/ADA/SOL.

| Column | Type | Notes |
|---|---|---|
| `benchmark_key` | text | "btc_hodl" or "alt_basket_equal_weight" |
| `ts` | timestamptz | Composite PK with `benchmark_key` |
| `equity_aud` | numeric(14,4) | Computed from a reference AUD starting balance (1000) plus the benchmark's evolution |

The alt basket rebalances on the 1st of each month to equal weight.

### 4.8 `system_alerts`

Surface non-fatal events to the frontend status banner and (later) to
email/Slack.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `level` | enum (`info`, `warning`, `error`) | |
| `code` | text | e.g. `STRATEGY_PAUSED_DRAWDOWN`, `PAIR_DROPPED_MIN_ORDER` |
| `strategy_id` | uuid nullable | |
| `message` | text | |
| `payload` | jsonb | |
| `acknowledged_at` | timestamptz nullable | |
| `created_at` | timestamptz | |

---

## 5. Order Executor

### 5.1 The `OrderExecutor` Protocol

Lives in `backend/app/trading/executor.py`:

```python
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

    async def get_open_orders(
        self, *, strategy_id: UUID
    ) -> list[OrderRow]: ...
```

`OrderResult` is a dataclass: `order_id`, `status`, `fills:
list[Fill]`, `reject_reason: str | None`.

Structural typing (Protocol) means `PaperExecutor` and the future
`LiveKrakenExecutor` satisfy the same shape without inheritance.

### 5.2 `PaperExecutor` algorithm

Market order:

```
1. SELECT * FROM paper_orders WHERE strategy_id=X AND idempotency_key=Y
   If found → return cached OrderResult. (No double-fill.)

2. Run risk-cap pre-checks (in order):
   a. Pair in allowed_pairs?
   b. Would post-fill single-asset % > max_single_asset_pct?
   c. Would post-fill total crypto % > max_total_crypto_exposure_pct?
   d. Order AUD > max_order_aud?
   e. Today's session loss > daily_loss_cap_aud?
   f. Drawdown from session peak > max_drawdown_pct_before_pause?
   If any fail → write rejected order row, return rejection.

3. Look up LocalOrderBook[pair].
   If last book update > 5 s ago → reject BOOK_UNAVAILABLE.

4. Walk the opposite side:
   - buy → walk asks (cheapest first)
   - sell → walk bids (highest first)
   Consume min(level_qty, remaining_qty) at each level.
   Emit one paper_fill row per level.
   Charge taker fee on each fill.

5. Single DB transaction:
   - INSERT paper_orders row
   - INSERT N paper_fills rows
   - UPDATE paper_positions for the strategy

6. Return OrderResult.
```

Limit order:

```
1. Idempotency check (as above).
2. Risk-cap pre-check (as above).
3. INSERT paper_orders with status='pending', expires_at=now()+24h
   (or override).
4. Return OrderResult immediately; fills happen later.

A background reconciler task (one per pair, owned by
PaperExecutor) watches book updates:
- buy limit fills when ask <= limit_price
- sell limit fills when bid >= limit_price
Fills are recorded as MAKER (we provided liquidity).
Expiry: when expires_at passes, status → 'expired'.
```

### 5.3 Fill model — walking the L2 book

The `LocalOrderBook` is maintained from Kraken's WS `book` channel:
snapshot on connect, then diffs. Kraken supplies a checksum on every
update — on mismatch, the maintainer resubscribes for a fresh
snapshot. Stored as two sorted lists (`asks`, `bids`).

For an order:

```
filled_qty = 0
total_cost = 0
levels_consumed = []

for level in book[side]:
    take_qty = min(level.qty, qty - filled_qty)
    total_cost += take_qty * level.price
    filled_qty += take_qty
    levels_consumed.append((level.price, take_qty))
    if filled_qty == qty: break

if filled_qty < qty:
    reject INSUFFICIENT_DEPTH
else:
    avg_price = total_cost / qty
    # emit one fill per level for fidelity
```

This is the realism that protects against "paper fills are clean
because we used a constant slippage." Thin AUD books on Kraken
(LINK/AUD, SOL/AUD, ADA/AUD) get the slippage they deserve.

### 5.4 Fee schedule

Source: kraken.com/features/fee-schedule. **Pro Starter** (sub-$10k
30-day USD volume — the realistic deploy tier):

```python
@dataclass(frozen=True)
class FeeSchedule:
    maker_bps: int   # basis points; 1 bp = 0.01%
    taker_bps: int

KRAKEN_PRO_STARTER = FeeSchedule(maker_bps=25, taker_bps=40)
```

Fee per fill = `qty × price × (bps / 10_000)`. Stored on each
`paper_fill` so the leaderboard can show gross and net returns.

**Fee-drag expectation at AUD 1k capital:** a strategy doing 50%
monthly portfolio turnover round-trips ~AUD 500/month. At 0.4%
taker per side that's AUD 4/month in fees — ~0.4% monthly drag,
~5%/year if all taker. More active strategies eat more. This is
why we paper at the deployment-real scale.

### 5.5 Idempotency

Every order carries an `idempotency_key`. Format:
`f"{strategy_id}:{decision_id}:{order_seq}"`. Where:

- `strategy_id` — UUID.
- `decision_id` — the `agent_decisions.id` that produced the order.
- `order_seq` — 0-indexed sequence if one decision produces several
  orders (e.g. a rebalance).

If the same key is submitted twice, the second call returns the
cached `OrderResult` for the existing row instead of inserting again.

When `LiveKrakenExecutor` ships, this same key passes as Kraken's
`userref` parameter — Kraken dedups natively on `userref`. So the
contract on the paper side already speaks the language of the real
side.

### 5.6 Lot ledger (forward compatibility)

Each `paper_fill` writes a per-lot cost-basis entry into
`paper_positions.lots_jsonb`. For a buy: append a new lot. For a
sell: pop oldest lot first (FIFO), unless we add other methods later.

Paper trades aren't real CGT events, so this isn't surfaced to the
Tax Hub yet. The point is: when `LiveKrakenExecutor` ships, the
ledger structure already exists; the Tax Hub plugs in without a
retrofit.

### 5.7 Minimum-order validation

**Rule:** at strategy startup, for every pair in `risk_caps.allowed_pairs`:

```
ordermin = Kraken AssetPairs[pair].ordermin
current_price = LocalOrderBook[pair].mid  (fallback: REST ticker)
max_position_aud = strategy.starting_balance_aud * risk_caps.max_single_asset_pct
threshold_aud = max_position_aud * 0.05

if ordermin * current_price > threshold_aud:
    remove pair from allowed_pairs (in-memory only)
    INSERT system_alerts row with code='PAIR_DROPPED_MIN_ORDER'
```

The rule fires again whenever `risk_caps` changes, so a future user
raising `max_single_asset_pct` could re-admit a pair.

**Verified at v1 cutover (2026-05-12, AUD 1k capital, 30%
max_single_asset_pct → AUD 300 max position → AUD 15 threshold):**

| Pair | ordermin | last (AUD) | min order value (AUD) | pass? |
|---|---|---|---|---|
| ETH/AUD | 0.001 ETH | 3196.60 | 3.20 | ✓ |
| LINK/AUD | 0.55 LINK | 14.58 | 8.02 | ✓ |
| ADA/AUD | 20 ADA | 0.385 | 7.71 | ✓ |
| SOL/AUD | 0.02 SOL | 133.23 | 2.66 | ✓ |

All four pass. Universe intact at v1.

### 5.8 `LiveKrakenExecutor` (future, ~200 lines, separate spec)

Same `Protocol`. Implementation differences:

1. `submit_order` calls Kraken REST `AddOrder` with `userref =
   idempotency_key`. Kraken dedups on `userref`.
2. Risk-cap pre-checks still run our side (Kraken doesn't know our
   strategy's portfolio rules).
3. Fills arrive asynchronously via the Kraken WS `ownTrades` feed →
   a reconciler writes them to a parallel `live_fills` table.
4. Position state: Kraken's `Balance` endpoint is source of truth;
   we sync periodically.

When that day arrives, we add `live_orders` / `live_fills` /
`live_positions` tables (not a `mode` column on the existing ones).
Strategies' `mode` column at the row level (`paper` / `live`) tells
the executor router which to use. No data-pollution risk.

### 5.9 Error handling — polite reject vs emergency stop

**Polite reject** (writes rejection row, strategy keeps running):

- Risk cap violated (specific cap name in `reject_reason`)
- Insufficient cash
- `BOOK_UNAVAILABLE` (book stale > 5 s)
- Pair not in `allowed_pairs` (e.g. dropped at startup by min-order
  check)
- Limit price malformed (negative, NaN)
- `INSUFFICIENT_DEPTH` (book doesn't have enough liquidity to fill)

**Emergency stop** (strategy.status → `paused`, system_alert raised):

- DB unreachable
- WS feed permanently disconnected (different from "stale")
- Unhandled exception in the executor or strategy loop
- Persistent reconciler failures (e.g. book checksums failing
  repeatedly)

The principle: rejections are *information the strategy could
react to*. Emergency stops are *the system is broken; halt and
wait*. Silently retrying through a broken system is how bots
go feral.

---

## 6. Strategy Loop & Triggers

### 6.1 The per-strategy asyncio loop

```python
async def strategy_loop(strategy_id: UUID):
    strategy = await load_strategy(strategy_id)
    bus = get_event_bus()
    state = TriggerState()  # last_call_at, calls_this_hour, etc.

    async for event in bus.subscribe(strategy.event_filter):
        if strategy.status != "active":
            continue

        if not state.should_fire(event, strategy.trigger_config):
            continue   # debounced, cooled-down, or rate-capped

        state.record_invocation()

        try:
            if strategy.execution_mode == "llm_agent":
                await invoke_llm_strategy(strategy, event)
            else:
                await invoke_deterministic_strategy(strategy, event)
        except Exception as exc:
            await emergency_stop(strategy, exc)
```

Per-strategy exception isolation: one strategy crashing doesn't take
down the others.

### 6.2 Trigger taxonomy

`strategies.trigger_config` is the source of truth. Schema:

```jsonc
{
  "triggers": [
    { "type": "cron", "expr": "0 9 */14 * *", "tz": "Australia/Sydney" },
    { "type": "interval", "minutes": 60 },
    { "type": "price_breakout", "pair": "ETH/AUD", "lookback_bars": 24,
      "interval": "1h", "min_move_pct": 1.5 },
    { "type": "price_stretch", "pair": "SOL/AUD", "lookback_bars": 48,
      "interval": "1h", "stdev": 2.0 },
    { "type": "order_filled" },
    { "type": "drawdown", "session_pct": 5.0 }
  ],
  "debounce_seconds": 5,
  "cooldown_seconds": 900,
  "max_calls_per_hour": 10
}
```

| Trigger type | Fires when | Owner |
|---|---|---|
| `cron` | A cron expression matches (timezone-aware) | `scheduler_task` |
| `interval` | Every N minutes since loop start | `scheduler_task` |
| `price_breakout` | A pair's price crosses an N-period high/low by min_move_pct | `price_feed_task` |
| `price_stretch` | A pair's price > N stdev from the lookback mean | `price_feed_task` |
| `order_filled` | One of this strategy's limit orders fills | `PaperExecutor` |
| `drawdown` | Intraday equity down > X % from session peak | `equity_snapshot_task` |

**Per-persona subscriptions:**

| Persona | Triggers |
|---|---|
| DCA-Baseline | `cron` only (fortnightly, 09:00 AET) |
| Trend-Follower | `interval` (60m) + `price_breakout` (per pair) + `order_filled` |
| Mean-Reverter | `interval` (60m) + `price_stretch` (per pair) + `order_filled` |

### 6.3 Throttling — debounce, cooldown, rate cap

Three knobs prevent agent-call spam:

- **Debounce** (default 5 s). If N events match in a 5 s window, only
  the most recent one triggers an invocation. Prevents reacting to
  every WS tick during a rapid move.
- **Cooldown** (default 900 s / 15 min). After an invocation, ignore
  further triggers for this duration. Stops the agent re-evaluating
  the same setup over and over.
- **Rate cap** (default 10/h). Hard ceiling on invocations per hour
  per strategy. Bug protection: a runaway loop can't accidentally
  cost AUD 200 in API fees overnight.

DCA-Baseline ignores debounce / cooldown / rate-cap (deterministic,
not LLM, no cost to throttle).

### 6.4 Deterministic execution path

For `execution_mode = deterministic`:

```python
async def invoke_deterministic_strategy(strategy, event):
    config = strategy.deterministic_config
    state = await load_paper_state(strategy.id)
    target_weights = config["allocations"]   # {pair: weight}

    orders = compute_rebalance_orders(
        state, target_weights, strategy.starting_balance_aud
    )

    decision = await write_agent_decision(
        strategy_id=strategy.id,
        execution_mode="deterministic",
        trigger_event=event,
        input_snapshot=state.snapshot(),
        model=None,
        cost_aud=Decimal("0"),
        agent_output=None,
    )

    for i, order in enumerate(orders):
        await executor.submit_order(
            strategy_id=strategy.id,
            idempotency_key=f"{strategy.id}:{decision.id}:{i}",
            **order,
        )
```

Result: DCA-Baseline costs AUD 0 in LLM fees, runs in milliseconds,
and cannot deviate from its schedule. The `agent_decisions` row is
still written so the audit story stays uniform.

### 6.5 Activity model & cost ballpark

With v1 defaults (3 strategies, 10 LLM calls/h cap, 15-min cooldown):

- DCA-Baseline: 2 invocations/month → AUD 0 LLM cost.
- Trend-Follower: ~10–20 invocations/day → ~AUD 0.50–1.50/day.
- Mean-Reverter: ~10–20 invocations/day → ~AUD 0.50–1.50/day.

**Worst-case (rate cap saturated 24/7):** 3 × 10 × 24 × ~AUD 0.05 ≈
AUD 36/day = AUD 1080/month. Won't happen in practice (cooldown
prevents most ticks from firing) — but the rate cap is the hard
ceiling so the worst case is bounded.

**Realistic monthly LLM spend at v1 defaults:** AUD 30–45.

---

## 7. Agent Integration

### 7.1 Five new MCP tools

Lives alongside existing tools in `backend/mcp_server.py`. Available
only when the agent is running in **strategy invocation mode**
(§7.2). Not exposed on conversational chat.

| Tool | Signature (logical) | What it does |
|---|---|---|
| `place_paper_order` | `(pair, side, type, qty, limit_price?, expires_at?)` | Submit to `PaperExecutor`. Returns `OrderResult` |
| `cancel_paper_order` | `(order_id)` | Cancel a pending limit order |
| `get_my_paper_state` | `()` | Read this strategy's portfolio: cash, positions, open orders, recent fills |
| `get_my_recent_decisions` | `(n=5)` | Last N agent_decisions rows for this strategy |
| `get_market_snapshot` | `(pairs?)` | Top-of-book + recent OHLCV for pairs (defaults to `allowed_pairs`) |

Tool implementations route through the same DB layer the API uses;
no shortcut paths.

### 7.2 Two invocation modes

The existing LangGraph agent is unchanged. We add two new
invocation paths:

- **Conversational** *(existing)* — when you talk to the agent from
  the dashboard. Full tool surface: Up Banking, recurring charges,
  lots, MCP tools, etc. Unaffected by v1.
- **Strategy** *(new)* — when a trigger fires. **Scoped tool
  surface:** the five paper-trading tools above plus market data.
  No Up Banking, no banking transactions. Smaller context → cheaper
  + more focused decisions. A "Trend-Follower" persona shouldn't be
  drawing inferences from your grocery spending.
- **Persona-conversational** *(new, used by §8.4 chat tab)* —
  conversational mode loaded with a specific strategy's persona
  prompt + state context. **Read-only scoped tools:**
  `get_my_paper_state`, `get_my_recent_decisions`,
  `get_market_snapshot`. `place_paper_order` and
  `cancel_paper_order` are **not** exposed. Lets the user
  interrogate a strategy without it accidentally placing trades
  mid-conversation.

### 7.3 Persona files

```
backend/agent/personas/
├── trend-follower.md
└── mean-reverter.md
```

(DCA-Baseline has no persona file; it's deterministic.)

Each persona file is the system prompt loaded by the strategy
invocation. The file documents:

- **Mandate** — what this strategy is supposed to do.
- **Risk style** — how aggressive, what to avoid.
- **Signals** — what to weight (breakouts, mean stretches, etc).
- **Hard rules from the strategy row** — caps, allowed pairs.
- **Reasoning requirement** — every order must include reasoning
  that gets captured in `agent_decisions.agent_output`.
- **DCA-Baseline charter (separate)** — though DCA-Baseline has no
  persona prompt, it gets a charter file (`personas/dca-baseline.md`)
  documenting why the weights are 50/25/15/10 and not equal-weight,
  for future-us continuity.

`agent_decisions.persona_prompt_hash` captures SHA-256 of the prompt
at invocation time. Lets you correlate performance with a specific
prompt version after iteration.

### 7.4 Cost tracking

Every strategy invocation that uses an LLM writes:

- `model` (e.g. `claude-sonnet-4-6`)
- `input_tokens`, `output_tokens` (from the API response)
- `cost_aud` (computed at call time from a `model_prices.py` constant
  table × current AUD/USD FX; stored stable)

A SQL view rolls these up:

```sql
CREATE VIEW paper_strategy_costs AS
SELECT
  strategy_id,
  date_trunc('day', created_at) AS day,
  SUM(cost_aud) AS cost_aud,
  COUNT(*) AS invocations
FROM agent_decisions
WHERE execution_mode = 'llm_agent'
GROUP BY 1, 2;
```

Surfaces on the leaderboard so you immediately see "Mean-Reverter
cost AUD 3.20 this week and lost AUD 8 — was that worth it?"

### 7.5 Eval-harness extension

Existing harness in `backend/evals/` already supports per-prompt
golden-set evaluation. Extension for personas:

- New scenario file: `backend/evals/personas_golden_set.yaml`
- Each row: persona key, trigger event (canned), expected behaviour
  category, portfolio state snapshot.
- For each persona × scenario, run the agent, capture:
  - **Tool-call correctness** — did it call `place_paper_order` with
    sensible args (right side, qty within caps)?
  - **Reasoning quality** — does the persona's mandate show up in
    the explanation? (LLM-as-judge.)
  - **Risk discipline** — did it respect the caps it knew about?
- Report alongside existing eval output.

**Why this matters:** lets a future prompt edit be evaluated before
it ships. "Did I break Trend-Follower" gets a tested answer.

---

## 8. Frontend (`<StrategiesPage>`)

New top-level route. Built with `/impeccable`. Lives at
`frontend/src/pages/StrategiesPage.tsx`.

### 8.1 Side-rail placement

Top-level item alongside Crypto / Up / Combined / Tax (once Tax
ships). Reflects that this is a major new area, not a sub-feature.

### 8.2 Top — leaderboard table

| Rank | Strategy | Equity AUD | 7d % | 30d % | All-time % | Sharpe | Max DD | Trades | Cost AUD (30d) | Status |
|---|---|---|---|---|---|---|---|---|---|---|

Columns:

- `Sharpe`, `Sortino`, `Calmar` available via tooltip (Sharpe is the
  default display column to avoid table clutter).
- `Trades` = count of `paper_orders` in the period (one
  user-intended action = one trade, even if it walked multiple book
  levels and produced several `paper_fills` rows).
- `Cost AUD (30d)` = sum from `paper_strategy_costs`. Zero for
  deterministic. Surfaces fee-vs-return ratio in tooltip.
- `Status` = green dot (`active`), yellow (`paused`), grey (`archived`).

### 8.3 Middle — overlay equity-curve chart

All strategies' equity curves on one chart, plus **two benchmark
lines**:

- **BTC/AUD HODL** — equity curve assuming AUD 1k bought BTC at
  strategy-start time, held untouched.
- **Equal-weight ETH/LINK/ADA/SOL basket** — equity curve assuming
  AUD 1k allocated 25% each at strategy-start time, **rebalanced on
  the 1st of each month back to equal weights**.

Range picker matches the existing CombinedPage pattern (1D / 7D /
30D / 90D / All).

### 8.4 Bottom — strategy detail drawer

Clicking a leaderboard row opens a side drawer with:

- **Equity curve** (zoomable, with markers where fills happened).
- **Open positions** table (asset, qty, avg cost, current value,
  unrealised P&L).
- **Open orders** table (limit orders waiting to fill).
- **Decisions feed** — reverse-chronological list of
  `agent_decisions` rows: timestamp, trigger reason, model + cost,
  agent reasoning text, orders placed, realised P&L of those orders
  to date. This is the "why did Strategy B sell yesterday?" answer.
- **Pause / Resume / Archive** buttons (writes to
  `strategies.status`).
- **Persona chat tab** — talk to the agent loaded with this
  strategy's persona and context. Ask "why are you holding so much
  LINK?" — the agent answers from inside that strategy's frame of
  reference. (Conversational mode but with the strategy's persona
  prompt overlay — no tool access to the executor; this is
  read-only conversation.)

### 8.5 System-status banner

Top of page. Reads `/api/strategies/_health`. Goes amber when:

- WS feed last-tick age > 30 s
- Any strategy auto-paused in the last 24 h (unacknowledged
  `system_alerts` rows)
- Any pair was dropped at startup by min-order check

Red when: WS feed dead > 5 min, or strategy in `error` state.

---

## 9. Safety & Observability

### 9.1 Audit trail

Every strategy invocation writes an `agent_decisions` row. Indexed
on `(strategy_id, created_at desc)` for fast post-mortems. Retained
indefinitely (Postgres rows are cheap; the audit log is the most
important artefact this system produces).

### 9.2 Dry-run mode

`strategies.dry_run = true` lets the agent decide and write the
would-have-been order to `agent_decisions.tool_calls`, but
`PaperExecutor.submit_order` is **never called**. Critical for
safely iterating on a persona prompt without burning paper P&L.

When toggled on: existing positions stay; new orders are
suppressed. Toggle off → resumes real (paper) execution.

### 9.3 Health endpoint

`GET /api/strategies/_health` returns:

```json
{
  "ws_feed": {
    "ETH/AUD": { "last_tick_at": "...", "age_s": 0.4 },
    "LINK/AUD": { ... }, ...
  },
  "strategies": [
    { "id": "...", "name": "Trend-Follower", "task_state": "running",
      "last_invocation_at": "...", "invocations_this_hour": 2 },
    ...
  ],
  "executor": { "last_fill_at": "...", "open_orders": 3 },
  "db": { "write_latency_ms_p99": 12 }
}
```

Drives the frontend status banner.

### 9.4 Per-strategy kill switch

Pause / Resume / Archive buttons in the UI write to
`strategies.status`. The loop reads `status` before every
invocation. Archive is permanent (status cannot return to
`active`); pause is reversible.

### 9.5 Kill criteria

`strategies.kill_criteria` is jsonb evaluated after every equity
snapshot. If matched, status flips to `paused` and a row is written
to `agent_decisions` describing why (so the audit trail captures
*the system pausing the strategy*, not just the strategy's own
actions).

Example:

```json
{
  "auto_pause_when": [
    { "metric": "drawdown_pct", "op": ">=", "value": 25.0 },
    { "metric": "daily_loss_aud", "op": ">=", "value": 50.0 },
    { "metric": "trailing_30d_sharpe", "op": "<", "value": -0.5 }
  ]
}
```

These are pre-committed disciplines (see López de Prado's
anti-p-hacking argument). The point: define before you see results.
The system enforces it; you can't talk yourself out of it later.

**Definitions used by these metrics:**

- **Session.** The current calendar day in the strategy's timezone
  (default `Australia/Sydney`). A "new session" starts at local
  00:00. `daily_loss_aud` and `session_pct` drawdown reset at that
  boundary.
- **Session peak.** Highest `equity_aud` snapshot since the current
  session began.
- **Drawdown_pct** (kill-criteria, all-time). Highest snapshot since
  strategy start vs. current — never resets.
- **Trailing 30d Sharpe.** Annualised on a 24/7 basis (daily
  returns × √365). Computed from hourly snapshots aggregated to
  daily.

### 9.6 Alert channel

`system_alerts` rows surface in the frontend banner. Optional later:
pipe to email or a Slack webhook (out of scope for v1).

---

## 10. Testing

### 10.1 Unit tests

| Layer | What's tested | Style |
|---|---|---|
| `LocalOrderBook` | Snapshot + diff application; checksum reconciliation | Example-based |
| Fill model | Walking the book produces correct avg price + per-level fills | Example-based with snapshot fixtures |
| Fee model | Maker vs taker classification + correct AUD fees | Example-based |
| Risk-cap pre-check | Each cap independently triggers rejection | Example + property-based (§10.2) |
| Kill-criteria evaluator | Each criterion fires at the exact boundary | **Explicit boundary tests** (§10.3) |
| Trigger evaluators | cron, interval, breakout, stretch all fire under the right input | Example-based |
| Throttling | Debounce + cooldown + rate-cap behave under fake event flood | Integration with fake clock |
| Deterministic strategy rebalance | Given current state + target weights, compute correct orders | Example-based |

### 10.2 Property-based tests (Hypothesis)

`hypothesis` added to backend `requirements.txt`.

Risk-cap properties:

```python
@given(portfolio=portfolios(), order=orders())
def test_pre_check_accept_implies_caps_hold_after_fill(portfolio, order):
    result = pre_check(portfolio, order)
    if result.accepted:
        post = apply_fill(portfolio, order)
        assert satisfies_all_caps(post)

@given(portfolio=portfolios(), order=orders())
def test_pre_check_reject_names_a_specific_cap(portfolio, order):
    result = pre_check(portfolio, order)
    if not result.accepted:
        assert result.reject_reason in CAP_NAMES
        post = apply_fill(portfolio, order)
        assert violates_specific_cap(post, result.reject_reason)

@given(portfolio=portfolios(), order=orders())
def test_pre_check_monotonic_in_qty(portfolio, order):
    """If an order is accepted, any smaller-qty version is also accepted."""
    if pre_check(portfolio, order).accepted:
        smaller = replace(order, qty=order.qty * Decimal("0.5"))
        assert pre_check(portfolio, smaller).accepted
```

### 10.3 Kill-criteria boundary tests

```python
def test_drawdown_kill_fires_at_exactly_threshold():
    state = PortfolioState(peak=Decimal("1000"), current=Decimal("750"))
    # 25.00% drawdown exactly
    assert evaluate_kill_criteria(state, {"max_drawdown_pct": 25.0}).fires

def test_drawdown_kill_does_not_fire_just_below():
    state = PortfolioState(peak=Decimal("1000"), current=Decimal("750.01"))
    # 24.999% drawdown
    assert not evaluate_kill_criteria(state, {"max_drawdown_pct": 25.0}).fires

def test_daily_loss_cap_uses_strategy_timezone():
    """A new 'day' starts at AU/Sydney 00:00, not UTC 00:00."""
    ...
```

### 10.4 Integration tests

- Strategy loop end-to-end with fake event stream + fake clock
  (`asyncio.sleep` stubbed). Asserts: debounce holds, cooldown
  holds, rate-cap rejects beyond N invocations/hour.
- `PaperExecutor` against a test Postgres schema: submit market →
  fills materialise → positions update → equity snapshot lines up.
- Idempotency: submit same key twice → only one order row.

### 10.5 Eval harness extension

Per §7.5. Run on demand (matches existing pattern — not on every
commit; live LLM calls have cost).

### 10.6 Manual frontend smoke

Checklist file `docs/manual-smoke-strategies.md`:

- Leaderboard loads with three strategies.
- Equity chart shows strategy curves + 2 benchmark lines.
- Range picker filters chart and table.
- Click row → drawer opens with decisions feed populated.
- Pause / Resume / Archive buttons reflect in `strategies.status`.
- System banner reflects WS health.
- Persona chat tab loads with that strategy's context.

Matches existing pattern — no Playwright/Cypress in repo.

---

## 11. Future Evolution (Approach B — separate worker)

### 11.1 The promise

Lifting to a separate worker process is a **refactor, not a
rewrite.** This section captures exactly what changes the day the
user decides to do it.

### 11.2 What doesn't change

- DB schema (every table in §4).
- `OrderExecutor` interface and `PaperExecutor` implementation.
- Persona files.
- Frontend (still reads from API).
- MCP tools (still server-side).
- Agent code, LangGraph graph.
- Eval harness.
- Risk-cap logic, fill model, kill criteria.
- Audit log.

### 11.3 What changes

1. Move four files from `backend/app/trading/loops/` into a new
   `backend/worker/` directory:
   - `price_feed_task.py`
   - `scheduler_task.py`
   - `strategy_loop_task.py`
   - `executor_reconciler_task.py`
2. Add `backend/worker/main.py` entry point that boots these tasks
   as a standalone process.
3. Replace the in-process `asyncio.Queue` event bus with **Postgres
   `LISTEN`/`NOTIFY`** (preferred — no broker dependency) or
   **Redis** (fallback — see §11.4).
4. API loses the strategy-loop bootstrap code (currently in
   FastAPI's startup hook).
5. Deploy two processes (`api` and `worker`) instead of one. Same
   container image, different entry points.

**Effort estimate:** ~1 focused working week. Most of the time is
verification and testing, not code.

### 11.4 Event-bus caveat — verify-before-commit

Supabase Postgres supports `LISTEN`/`NOTIFY`, but only on certain
connection modes:

| Connection mode | Port | Supports LISTEN/NOTIFY? |
|---|---|---|
| Direct | 5432 | ✓ Yes |
| Transaction pooler | 6543 | ✗ No (connections aren't held) |
| Session-mode pooler | varies | ✓ Yes (but more overhead) |

**Before committing LISTEN/NOTIFY** as the broker, verify the
worker can connect via direct (5432) or session-mode pooler in
the deployment target (Fly.io / Railway / etc).

If neither is feasible, fall back to:

- **Option B-alt:** Redis (Upstash free tier ~30k commands/day,
  or Railway plug-in ~AUD 7/mo).
- **Option B-alt2:** HTTP-based pub/sub via the existing API
  (worker polls `/api/_internal/events` — simpler but adds
  latency).

Decision: **deferred until the lift-to-worker moment.** No
infrastructure committed in v1.

### 11.5 When to do it

Signals the lift is overdue:

- A bug in one strategy causes the API to slow down (user-facing
  endpoint latency spikes correlate with strategy invocations).
- The user wants to add a 4th or 5th strategy and concurrency starts
  to bite.
- The user is about to flip to real money. **Strongly worth doing
  first** — real-money decisions deserve a process that can't be
  killed by a frontend deploy.

### 11.6 Future-future: deterministic strategies are the door

Now that `execution_mode = deterministic` exists, future strategies
beyond DCA-Baseline are cheap to add: a hardcoded momentum bot, a
fixed-weight rebalancer, a "buy after 3 red days" rule. No LLM
cost, no eval-harness work, just `deterministic_config` jsonb.

---

## 12. Configuration Summary

The reference table. Source of truth lives in code (`backend/app/trading/defaults.py`) and per-strategy DB rows; this table captures what v1 ships with.

| Setting | Value |
|---|---|
| Pair universe | ETH/AUD, LINK/AUD, ADA/AUD, SOL/AUD |
| Personas | DCA-Baseline (deterministic) + Trend-Follower + Mean-Reverter |
| Starting capital per strategy | AUD 1,000 |
| DCA-Baseline allocation | ETH 50% / SOL 25% / LINK 15% / ADA 10% |
| DCA-Baseline cadence | Every 14 days at 09:00 AET (cron `0 9 */14 * *`) |
| `max_single_asset_pct` | 30% |
| `max_total_crypto_exposure_pct` | 60% |
| `max_order_aud` | AUD 250 |
| `daily_loss_cap_aud` | AUD 50 (5% of 1k) |
| `max_drawdown_pct_before_pause` | 25% |
| Limit-order TTL | 24 h |
| Min-order threshold | 5% of max position (= AUD 15 at v1) |
| Fees (Kraken Pro Starter) | 0.25% maker / 0.40% taker |
| Throttling — debounce | 5 s |
| Throttling — cooldown | 15 min |
| Throttling — rate cap | 10 LLM calls / h / `llm_agent` strategy |
| LLM default model | `claude-sonnet-4-6` (overridable per strategy via `model_preference`) |
| Equity snapshot cadence | Hourly |
| Benchmarks on chart | BTC/AUD HODL + equal-weight ETH/LINK/ADA/SOL (monthly rebalance) |
| Side-rail nav | Top-level "Strategies" |
| Realistic monthly LLM spend | AUD 30–45 (v1 defaults; can drop further by switching to Haiku) |

---

## 13. Open questions to revisit during implementation

1. **AUD/USD FX source for cost attribution.** Kraken's fee
   schedule is denominated in USD volume; the LLM cost is denominated
   in USD per million tokens. We need a daily AUD/USD rate to
   compute `cost_aud`. Existing portfolio code already pulls this for
   AUD reporting — reuse that source.
2. **Equity-snapshot cadence on deterministic strategies.** DCA-Baseline
   barely changes between fortnightly buys; do we still take an
   hourly snapshot? Recommendation: yes, for chart continuity, but
   compute is essentially free.
3. **Whether to support `iceberg` or `post-only` order modifiers.**
   Out of v1 scope; flag if Trend-Follower or Mean-Reverter start
   needing them.
4. **Persona prompt iteration discipline.** When we tweak
   `trend-follower.md`, do we automatically archive the running
   strategy and spin up a fresh one (so the equity curve isn't
   continuous across prompt versions)? Or keep the strategy and rely
   on `persona_prompt_hash` to segment the curve?  Recommendation:
   keep the strategy continuous, draw a vertical marker on the chart
   at each prompt-hash change. Decide at implementation time.
5. **Whether the "Personal DCA Shadow" persona is worth adding once
   v1 is live.** Would track real-life BTC/USDT DCA for comparison.
   Useful but conceptually separate from "did the bots beat
   intra-universe passive."
6. **Whether dry-run mode should affect benchmark calculation.**
   Probably not (benchmarks are universe-level, not strategy-level)
   but worth being explicit at implementation.

---

## 14. Implementation phasing (rough sketch — final phasing lives in the plan)

1. **DB migrations + models** (Section 4): new tables, enums,
   constants. No behaviour yet.
2. **`OrderExecutor` Protocol + `PaperExecutor` core** (§5.1–5.5):
   the L2 walking, fees, idempotency. Fully unit-testable without
   any strategy logic.
3. **Trigger taxonomy + `scheduler_task`** (§6.2): cron + interval.
   Plus the per-strategy loop scaffold reading the event bus.
4. **Deterministic execution path + DCA-Baseline strategy row**
   (§6.4). End-to-end: cron fires → orders flow → fills land →
   positions update.
5. **MCP tools + LLM execution path + persona files for Trend +
   Mean-Reverter** (§7.1–7.4). Eval-harness extension (§7.5).
6. **Risk-cap pre-check + kill criteria + emergency-stop logic**
   (§5.2 step 2, §9.5). Property-based tests + boundary tests.
7. **Equity snapshots + benchmark snapshots + leaderboard data**
   (§4.6, 4.7).
8. **Frontend `<StrategiesPage>`** built via `/impeccable` (§8).
9. **Health endpoints + status banner + system_alerts** (§9.3–9.6).
10. **Manual smoke + final docs**.

Order is suggestive, not prescriptive — the `writing-plans` step
will sequence properly.

---

*End of design spec.*
