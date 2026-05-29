# Paper-Trading Experiment — Accuracy Fixes & Level Field — Design Spec

**Date:** 2026-05-29
**Status:** Draft (brainstorming complete; awaiting user review of written spec)
**Predecessor:** Paper Trading Sandbox — `docs/superpowers/specs/2026-05-12-paper-trading-sandbox-design.md`

---

## 1. Goal

The paper-trading sandbox (Phase 6) shipped and runs, but a leaderboard review
on 2026-05-29 found the strategy comparison is currently **meaningless as a test
of the project thesis** ("can any strategy beat DCA or my manual trades?").

The equity arithmetic is correct — every dollar figure is real cash + positions
marked to live prices. The problem is that **bugs prevent the strategies from
actually being invested**, so the leaderboard is measuring "who happened to be
sitting in cash during a downturn," not skill. The strategies look like they're
beating the user's manual portfolio (−7.5% / −8.8%) only because they're holding
cash while ETH fell ~13.5%.

This spec (a) fixes the five bugs, (b) puts every strategy on a **fully level
playing field**, and (c) adds **two deterministic rule-based strategies** as
controls — so the experiment can honestly answer not just "does an AI method
beat DCA?" but "does the AI add anything over a dumb mechanical rule of the same
style?" — the question that decides whether a strategy is worth mirroring with
real money.

Measurement accuracy is the priority (fees, fills, attribution) — consistent
with the project thesis — so where a fix trades accuracy for convenience, we
choose accuracy.

---

## 2. Findings (verified 2026-05-29)

Evidence gathered by querying the live Supabase tables and reading the code.

| # | Symptom | Verified root cause |
|---|---------|---------------------|
| 1 | DCA-Baseline only −0.70%, holds **no ETH** despite a 50%-ETH target | Three independent conflicts (see §3.1). It is not doing DCA; it is a target-weight rebalancer trying to deploy ~$500 of ETH in one order, rejected by the $250 per-order cap **and** the 30% single-asset cap **and** the 60% total-crypto cap. |
| 2 | Mean-Reverter flat at exactly $1,000, "12 trades", **0 fills ever** | It only places limit orders. `reconcile_resting_orders` (the code that fills a resting limit order when the market crosses it) is **never called in production** — only in a test. So a resting limit order can never fill. |
| 3 | ~half of all orders rejected `BOOK_UNAVAILABLE` | (a) at startup, strategies can fire before the live order book has loaded; (b) when the backend/WS connection is down there are simply no prices. (a) is fixable; (b) is operational. |
| 4 | BTC-HODL and alt-basket benchmark lines empty | `compute_btc_hodl_equity` / `compute_alt_basket_equity` exist but nothing calls the benchmark snapshot writer; only the per-strategy equity job is scheduled. |
| 5 | "TRADES" column overstates activity | The leaderboard counts **all** `paper_orders` rows regardless of status, including rejected and cancelled. |

Confirmed **not** broken: equity is marked to live market prices; the executor's
fill model, fee model, and FIFO lots all work correctly when an order actually
fills. The foundation is sound; these are wiring and configuration bugs.

---

## 3. The fixes

### 3.1 DCA-Baseline → true dollar-cost averaging

**Problem.** The current "DCA-Baseline" is a *target-weight rebalancer*: on each
fire it computes "I want 50% of equity in ETH" and submits the whole gap as one
~$500 market order — structurally impossible to fill (see §2 row 1). It is also
not dollar-cost averaging by any definition.

**Fix — fixed-slice weekly DCA.** Deploy the $1,000 in equal slices on a weekly
schedule until fully invested, then hold.

- `slice_total = starting_balance_aud / num_buys`, with `num_buys = 12` (≈ 3
  months), fired weekly (`0 9 * * 1`, Mondays 09:00 Australia/Sydney).
- Each fire submits, per pair, a **market** buy of `slice_total × weight`:

  | Asset | Weight | Per weekly buy | Total after 12 |
  |-------|--------|----------------|----------------|
  | ETH   | 50%    | ~$41.67        | $500           |
  | SOL   | 25%    | ~$20.83        | $250           |
  | LINK  | 15%    | ~$12.50        | $150           |
  | ADA   | 10%    | ~$8.33         | $100           |
  | **Total** | **100%** | **~$83.33** | **$1,000**   |

- **Stop condition:** when remaining cash is below one slice (≈ after 12 buys),
  it stops buying and holds. **No rebalancing afterward** (a passive baseline
  must not introduce active sell/rebuy decisions).
- **Missed weeks are safe:** the slice comes from remaining cash on the next
  successful fire, so a skipped week (feed down) just delays completion — no
  money lost or double-spent.
- Each order (~$42 max) is far below the $250 per-order cap.

**Code.** Add `compute_dca_orders(...)` (new, alongside the existing
`compute_rebalance_orders`). `invoke_deterministic_strategy` branches on
`deterministic_config.mode` (`"dca"` → DCA path). The existing REST
price-fallback for sizing is retained.

Caps/kill-criteria for DCA are covered by the level-field rules in §3.6.

### 3.2 Wire the limit-order reconciler (fixes Mean-Reverter)

**Problem.** Resting limit orders never fill because nothing re-checks them
against the moving book.

**Fix.** In `PriceFeed._handle`, after applying a book update for a pair and
publishing `BookUpdateEvent`, call `await self.executor.reconcile_resting_orders(pair)`
(guarded for when no executor is attached / in tests). The reconciler already
handles maker-fee fills, partial fills, expiry, and position updates.

After this, if Mean-Reverter still rarely fills, that is **persona tuning** (its
limit prices set too far from market), observed and adjusted later — out of
scope here. The mechanical blocker is what we fix now.

### 3.3 Warm-up gate (reduces `BOOK_UNAVAILABLE`)

**Problem.** At boot the strategy loops/triggers start before the WS feed has
delivered the first order-book snapshot per pair; events firing in that window
reject with `BOOK_UNAVAILABLE`.

**Fix.** In `_boot_trading_sandbox`, after starting the feed task, **wait until
every pair has a populated book** (`asks` and `bids` non-empty) or a timeout
(~30s), *before* starting strategy loops and registering triggers. The existing
reconnect-with-backoff loop already repopulates books after a mid-session drop.

**Explicit non-goal.** We will **not** fill orders from a REST ticker price when
the live book is missing — that trades away fill realism (book-walking,
slippage, maker/taker), the exact accuracy the project (and any future
real-money mirroring) depends on. When prices are genuinely unavailable, the
honest behavior is to skip: DCA defers the slice; an LLM/rule strategy
reconsiders next fire. **Trades only happen while the backend is running.**

### 3.4 Wire benchmark snapshots (fixes empty BTC / alt-basket lines)

**Fix.**

- At reset (§4), record experiment start `t0` and the t0 prices of BTC/AUD and
  the four alts, persisted in a small benchmark-state record.
- Extend the hourly job to also write two benchmark snapshots via
  `paper_equity_repo.insert_benchmark_snapshot`:
  - **`btc_hodl`** = `(1000 / btc_price_t0) × btc_price_now`.
  - **`alt_basket_equal_weight`** = buy-once-and-hold: fix units at t0 as
    `(1000/4)/price_i_t0` per alt, then `Σ units_i × price_i_now`.
- Both start at exactly $1,000 at `t0` so they line up with the strategies.
- **Monthly rebalance of the alt basket is intentionally dropped** (user
  decision). The `AltBasketState.rebalance` code stays on disk, unscheduled.

BTC/AUD price is fetched from Kraken's public REST ticker each hourly run (BTC
is not in the trading universe and not added to the WS feed; price reference
only).

### 3.5 "Trades" counts executions only

**Fix.** In the leaderboard, count only orders with `status in ('filled',
'partial')`. Rejected/cancelled/expired/pending no longer inflate the number.

### 3.6 Level playing field — identical rules for all five strategies

**Decision (user, 2026-05-29):** a *fully* level field. The point is to learn
whether a method can beat DCA over the medium/long term; handicapping the active
strategies with risk limits the DCA baseline doesn't have would test our risk
rules, not the method. So **every strategy plays by identical rules:**

- **No allocation limits:** `max_single_asset_pct = 100`,
  `max_total_crypto_exposure_pct = 100` for all. A strategy may go up to 100% in
  one coin or 100% invested if its method dictates — that allocation choice *is*
  the strategy.
- **No auto-pause for anyone:** `kill_criteria.auto_pause_when = []` for all five.
  A fair medium/long comparison needs every method running the whole way
  through; a strategy that auto-freezes mid-experiment can't be compared.
  Drawdowns are still visible in the equity curve and max-DD metric. Manual
  pause/archive from the UI remains. (The kill-criteria machinery stays in the
  code for future real-money use; it is simply disabled for the experiment.)
- **Uniform execution realism only:** the same per-order cap (`max_order_aud`,
  kept as a sanity ceiling) and the same fee/fill model apply to everyone. This
  is not a handicap — it simulates a real exchange equally for all. Because it
  is uniform and does not constrain final allocation (strategies reach any
  target via multiple orders / order-splitting, §3.7), the field stays level.

This resolves the fairness caveat noted in the prior draft.

### 3.7 Two deterministic control strategies

Add two **rules-based** strategies (`execution_mode = "deterministic"`, no LLM —
cheap to run, perfectly reproducible). Each is the mechanical twin of an existing
LLM agent, so the leaderboard can isolate whether the AI adds value over the
rule.

**Trend Rule** (`deterministic_config.mode = "trend_rule"`)
- Hold each coin while it is **above its 50-day moving average**; exit to cash
  when it drops below.
- Target = **equal weight across the coins currently above their MA** (e.g. 3 of
  4 qualify → ~33% each; none qualify → 100% cash).
- Evaluated **daily** (`0 9 * * *`); trades only when the qualifying set changes
  (a coin crosses its MA), to limit churn/fees.
- Mechanical control for the **LLM Trend-Follower**.

**Mean-Reversion Rule** (`deterministic_config.mode = "mean_reversion_rule"`)
- For each coin: **RSI(14) < 30 (oversold) → target into it**; **RSI > 70
  (overbought) → exit to cash**; otherwise hold current.
- Target weight per qualifying (oversold) coin = equal-weight share.
- Evaluated **daily**; trades only on threshold crossings.
- Mechanical control for the **LLM Mean-Reverter**.

**Shared needs:**
- **Indicator data:** both need historical daily closes (50-day MA; RSI-14). Add
  a small Kraken **OHLC candle fetch** (`public/OHLC`, daily interval) + an
  indicator helper (`sma`, `rsi`) with light caching. New, self-contained.
- **Order-splitting on rebalance:** a target move can exceed the per-order cap
  (e.g. shifting ~$330 into one coin > $250). The deterministic submission path
  **splits any target order larger than `max_order_aud` into multiple ≤-cap
  orders**, so targets are always reachable under a uniform cap. (This also
  retroactively fixes the original "one giant order" failure mode for any
  rebalance-style strategy.)
- Same level-field caps as §3.6; routed through `invoke_deterministic_strategy`
  branching on `mode`.

**Tuning note:** the specific settings (MA length, RSI period/thresholds,
evaluation cadence, top-set sizing) are sensible standard defaults; exact values
will be grounded with quick research at implementation rather than guessed now.

---

## 4. Reset plan (clean slate)

Reset **all five strategies + both benchmarks** to a clean $1,000 from one common
`t0` (user decision: "start fresh"). The first 17 days are polluted across the
board and DCA is being redefined.

- A guarded script `backend/scripts/reset_paper_experiment.py` that:
  - Deletes rows for all strategies from `paper_orders`, `paper_fills`,
    `paper_positions`, `paper_equity_snapshots`, `agent_decisions`; clears
    `paper_benchmarks`.
  - Re-seeds $1,000 cash per strategy.
  - Records benchmark `t0` + t0 prices = reset moment.
- `seed_strategies.py` updated: DCA config/caps per §3.1+§3.6; **two new
  deterministic strategies seeded** (§3.7); level-field caps applied to the two
  existing LLM strategies (§3.6).
- After reset, all seven leaderboard lines (5 strategies + 2 benchmarks) begin at
  $1,000 at the same `t0` — apples-to-apples.

---

## 5. Out of scope (this pass)

- **Relative-Strength Rotation** strategy — deferred (blunt with only 4 coins;
  revisit if the universe grows or after the first round).
- Monthly rebalance of the alt-basket benchmark (dropped by user).
- REST-price fallback fills when the book is unavailable (rejected — harms
  accuracy).
- A 3rd LLM persona (revisit after seeing AI-vs-rule results).
- Mean-Reverter persona/limit-price tuning (observe after §3.2).
- `LiveKrakenExecutor`, backtester — still deferred per the original spec.

---

## 6. Testing

- **DCA (`compute_dca_orders`)** — slice sizing + per-pair split; cap compliance;
  cash-exhaustion stop; final partial slice; weights sum to 1.
- **Trend Rule** — qualifying-set selection vs MA; equal-weight targets;
  all-cash when none qualify; trades only on crossings.
- **Mean-Reversion Rule** — RSI threshold entries/exits; hold-in-between; targets.
- **Indicators** — `sma`, `rsi` against known fixtures.
- **Order-splitting** — a target > cap produces N ≤-cap orders summing correctly.
- **Reconciler wiring** — place a resting limit buy, publish a crossing book
  update through the feed, assert it fills and positions/cash update.
- **Warm-up gate** — loops/triggers don't start until books populate (or timeout).
- **Benchmarks** — job computes + inserts `btc_hodl` and `alt_basket_equal_weight`;
  endpoints read them.
- **Trades count** — leaderboard counts only `filled`/`partial`.
- **Level-field caps** — a 100%-single-asset buy is accepted; no auto-pause fires.
- **Reset script** — clears exactly the intended tables; re-seeds $1,000; against
  the `test` schema.

Follow repo conventions (repos accept `schema=`; tests use `schema="test"`;
lifespan boot skipped under `PYTEST_CURRENT_TEST`).

---

## 7. Assumptions & open questions

1. **Roster** — DCA + Trend Rule + Mean-Reversion Rule + LLM Trend-Follower +
   LLM Mean-Reverter; rotation skipped (user-confirmed).
2. **Reset scope** — all five strategies + benchmarks to clean $1,000 (user
   "start fresh").
3. **DCA window** — weekly, 12 buys, ~3 months (user-chosen).
4. **Backend uptime** — trades occur only while the backend runs; the warm-up
   gate fixes boot races, not genuine downtime.
5. **Min-order sizes** — smallest weekly DCA slices are ADA ~$8.33 / LINK ~$12.50;
   verify they clear Kraken minimums at implementation (boot already runs a
   min-order universe check). Expected fine; flagged.
6. **Indicator settings** — MA length / RSI period+thresholds / cadence to be
   grounded at implementation (standard defaults assumed for now).

---

## 8. Order of implementation (for the plan)

1. Level-field caps + kill-criteria changes across all strategies (§3.6) — config
   + seed.
2. Order-splitting on the deterministic submission path (§3.7) — needed by both
   rule strategies (DCA's slices are already under the cap, so it's unaffected).
3. DCA `compute_dca_orders` + mode branch (§3.1).
4. Indicator helper + Kraken OHLC fetch; Trend Rule + Mean-Reversion Rule (§3.7).
5. Reconciler wiring (§3.2).
6. Warm-up gate (§3.3).
7. Benchmark wiring + t0 capture (§3.4).
8. Trades-count fix (§3.5).
9. Reset script (§4) + updated seed — run last, so the fresh start uses the new
   strategies and settings.

Each step is independently testable and committable.
