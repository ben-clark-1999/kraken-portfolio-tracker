# Paper-Trading Experiment — Accuracy Fixes — Design Spec

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

This spec fixes the five issues that cause that, so the experiment can produce an
honest answer. Measurement accuracy is the priority (fees, fills, attribution)
— consistent with the project thesis — so where a fix trades accuracy for
convenience, we choose accuracy.

---

## 2. Findings (verified 2026-05-29)

Evidence gathered by querying the live Supabase tables and reading the code.

| # | Symptom | Verified root cause |
|---|---------|---------------------|
| 1 | DCA-Baseline only −0.70%, holds **no ETH** despite a 50%-ETH target | Three independent conflicts (see §3.1). It is not doing DCA at all; it is a target-weight rebalancer trying to deploy ~$500 of ETH in one order, which is rejected by the $250 per-order cap **and** the 30% single-asset cap **and** the 60% total-crypto cap. |
| 2 | Mean-Reverter flat at exactly $1,000, "12 trades", **0 fills ever** | It only places limit orders. `reconcile_resting_orders` (the code that fills a resting limit order when the market crosses it) is **never called in production** — only in a test. So a resting limit order can never fill. |
| 3 | ~half of all orders rejected `BOOK_UNAVAILABLE` | Two parts: (a) at startup, strategies can fire before the live order book has loaded; (b) when the backend/WS connection is down there are simply no prices. (a) is fixable; (b) is operational. |
| 4 | BTC-HODL and alt-basket benchmark lines empty | `compute_btc_hodl_equity` / `compute_alt_basket_equity` exist but nothing ever calls the benchmark snapshot writer; only the per-strategy equity job is scheduled. |
| 5 | "TRADES" column overstates activity | The leaderboard counts **all** `paper_orders` rows regardless of status, including rejected and cancelled. |

Confirmed **not** broken: equity is marked to live market prices (DCA's position
value recomputed from current Kraken prices matched the last snapshot to the
cent); the executor's fill model, fee model, and FIFO lots all work correctly
when an order actually fills. The foundation is sound; these are wiring and
configuration bugs.

---

## 3. The fixes

### 3.1 DCA-Baseline → true dollar-cost averaging

**Problem.** The current "DCA-Baseline" is a *target-weight rebalancer*: on each
fortnightly fire it computes "I want 50% of equity in ETH" and submits the whole
gap as one market order. On a $1,000 pot that is a ~$500 ETH order, which is
structurally impossible to fill because of three separate caps:

- `max_order_aud = 250` → rejected `MAX_ORDER_AUD`.
- `max_single_asset_pct = 30` → ETH can never exceed 30% of equity.
- `max_total_crypto_exposure_pct = 60` → never more than 60% invested.

It is also not dollar-cost averaging by any definition — it is lump-sum-to-target.

**Fix — fixed-slice weekly DCA.** Deploy the $1,000 in equal slices on a weekly
schedule until fully invested, then hold.

- `slice_total = starting_balance_aud / num_buys`, with `num_buys = 12` (≈ 3
  months), fired weekly.
- Each fire submits, per pair, a **market** buy of `slice_total × weight`:

  | Asset | Weight | Per weekly buy | Total after 12 |
  |-------|--------|----------------|----------------|
  | ETH   | 50%    | ~$41.67        | $500           |
  | SOL   | 25%    | ~$20.83        | $250           |
  | LINK  | 15%    | ~$12.50        | $150           |
  | ADA   | 10%    | ~$8.33         | $100           |
  | **Total** | **100%** | **~$83.33** | **$1,000**   |

- Each order (~$42 max) is far below the $250 per-order cap, so `MAX_ORDER_AUD`
  cannot fire.
- **Stop condition:** when cash is below one slice (≈ after 12 buys), it stops
  buying and just holds. **No rebalancing afterward** (a passive baseline must
  not introduce active sell/rebuy decisions).
- **Missed weeks are safe:** the slice is taken from remaining cash on the next
  successful fire, so a week skipped (feed down) just delays completion by a
  week — no money is lost or double-spent.

**DCA gets its own relaxed risk caps + kill criteria.** The anti-YOLO caps exist
to constrain the *active* LLM agents; a passive benchmark must be allowed to
execute its fixed plan and to ride through drawdowns (that is the whole point of
a DCA baseline). For DCA-Baseline only:

- `max_single_asset_pct = 100`, `max_total_crypto_exposure_pct = 100` (it is
  meant to be 50% ETH and fully invested).
- `max_order_aud = 250` unchanged (slices are ~$42; the cap stays as a sanity
  ceiling).
- Kill criteria **empty** — a DCA baseline must not auto-pause during a crash,
  and the hourly auto-pause job (driven by `kill_criteria`) is what would
  otherwise stop it. (The per-order daily-loss/drawdown pre-checks read a
  session-loss/drawdown that the executor currently hardcodes to 0, so they are
  already inert — no change needed there.)

**Config changes** (in `seed_strategies.py` `seed_dca_baseline`):

```jsonc
"deterministic_config": {
  "mode": "dca",                 // NEW — selects fixed-slice path
  "cadence_cron": "0 9 * * 1",   // weekly, Mondays 09:00
  "tz": "Australia/Sydney",
  "num_buys": 12,
  "allocations": { "ETH/AUD": "0.50", "SOL/AUD": "0.25",
                   "LINK/AUD": "0.15", "ADA/AUD": "0.10" }
},
"trigger_config": { "triggers": [{"type": "cron", "expr": "0 9 * * 1",
                    "tz": "Australia/Sydney"}], ... },
"risk_caps": { ...relaxed as above... },
"kill_criteria": { "auto_pause_when": [] }
```

**Code.** Add a `compute_dca_orders(...)` function (new, alongside the existing
`compute_rebalance_orders`) that returns the per-pair slice orders given
remaining cash, weights, slice size, and current mids. `invoke_deterministic_strategy`
branches on `deterministic_config.mode` (`"dca"` → new path; default → existing
rebalance, kept for any future strategy). The existing REST price-fallback for
sizing is retained.

### 3.2 Wire the limit-order reconciler (fixes Mean-Reverter)

**Problem.** Resting limit orders never fill because nothing re-checks them
against the moving book.

**Fix.** In `PriceFeed._handle`, after applying a book update for a pair and
publishing `BookUpdateEvent`, call
`await self.executor.reconcile_resting_orders(pair)` (guarded for when no
executor is attached / in tests). The reconciler already handles maker-fee
fills, partial fills, expiry, and position updates.

- This makes Mean-Reverter's limit buys fill the moment the market dips to their
  price, and unblocks limit orders for every strategy.
- Expiry of stale limit orders is also handled by the reconciler, so expired
  orders stop lingering as "pending" forever.

After this fix, if Mean-Reverter still rarely trades, that is **persona tuning**
(its limit prices being set too far from market), to be observed and adjusted
later — out of scope here. The mechanical blocker is what we fix now.

### 3.3 Warm-up gate (reduces `BOOK_UNAVAILABLE`)

**Problem.** At boot the strategy loops and triggers start immediately, before
the WS feed has delivered the first order-book snapshot for each pair. A
cron/interval/price event firing in that window rejects with `BOOK_UNAVAILABLE`.

**Fix.** In `_boot_trading_sandbox`, after starting the feed task, **wait until
every pair has a populated book** (`asks` and `bids` non-empty) or a timeout
(e.g. 30s) elapses, *before* starting the strategy loops and registering
triggers. The existing reconnect-with-backoff loop already repopulates books
after a mid-session disconnect.

**Explicit non-goal.** We will **not** fall back to filling orders from a REST
ticker price when the live book is missing. That would trade away fill realism
(book-walking, slippage, maker/taker) — the exact measurement accuracy the
project depends on. When prices are genuinely unavailable (backend off, WS
down), the honest behavior is to skip: DCA defers the slice to next week; an LLM
strategy simply reconsiders on its next fire. **Trades only happen while the
backend is running** — no code change alters that.

### 3.4 Wire benchmark snapshots (fixes empty BTC / alt-basket lines)

**Problem.** The benchmark equity functions are never called.

**Fix.**

- At reset (§4), record the experiment start `t0` and the t0 prices of BTC/AUD
  and the four alts, persisted in a small benchmark-state record (e.g. a
  `benchmark_state` row or a single JSON config row keyed by benchmark).
- Extend the hourly scheduled job (or add a sibling job) to also write two
  benchmark snapshots via `paper_equity_repo.insert_benchmark_snapshot`:
  - **`btc_hodl`** = `(1000 / btc_price_t0) × btc_price_now`.
  - **`alt_basket_equal_weight`** = buy-once-and-hold: fix units at t0 as
    `(1000/4)/price_i_t0` per alt, then `Σ units_i × price_i_now`.
- Both start at exactly $1,000 at `t0` so they line up with the strategies.
- **Monthly rebalance of the alt basket is intentionally dropped** (user
  decision, 2026-05-29). The `AltBasketState.rebalance` / `next_rebalance_due_at`
  code remains on disk but is not scheduled.

BTC/AUD price is fetched from Kraken's public REST ticker each hourly job run
(BTC is not in the trading universe and is not added to the WS feed; it is only
a price reference for the benchmark line).

### 3.5 "Trades" counts executions only

**Problem.** Leaderboard counts all `paper_orders` regardless of status.

**Fix.** In `routers/strategies.py` leaderboard, count only orders with
`status in ('filled', 'partial')`. (Rejected, cancelled, expired, and pending
orders no longer inflate the number.) Optionally relabel the column intent in
the frontend as executed trades, but the count fix is the substance.

---

## 4. Reset plan (clean slate)

Because the DCA strategy is being fundamentally redefined and the first 17 days
of data are polluted across all strategies, **reset everything to a clean
$1,000 from one common start point** (user decision, 2026-05-29 — assumed
"reset all three + benchmarks", not DCA-only).

- A guarded script `backend/scripts/reset_paper_experiment.py` that:
  - Deletes rows for the three strategies from: `paper_orders`, `paper_fills`,
    `paper_positions`, `paper_equity_snapshots`, `agent_decisions`, and clears
    `paper_benchmarks`.
  - Re-seeds $1,000 cash (`AUD` position) per strategy.
  - Records benchmark `t0` + t0 prices = reset moment.
  - Leaves strategy definitions intact (with DCA's updated config/caps from
    §3.1 applied via the updated seed).
- Strategy IDs may be preserved (update in place) or regenerated (delete +
  reseed); since all referencing data is wiped, either is acceptable —
  implementation detail for the plan.
- After reset, all leaderboard lines (3 strategies + 2 benchmarks) begin at
  $1,000 at the same `t0`, so comparisons are apples-to-apples.

---

## 5. Out of scope (this pass)

- Monthly rebalance of the alt-basket benchmark (dropped by user).
- REST-price fallback fills when the book is unavailable (rejected — harms
  accuracy).
- Mean-Reverter persona/limit-price tuning (observe after §3.2; tune later if
  needed).
- Whether the **LLM** strategies' risk caps (30% single / 60% total) make the
  comparison uneven vs an unconstrained DCA baseline. Noted as a fairness
  consideration (see §7); left as-is for now so the test answers "can a
  risk-managed bot beat naive DCA?". Revisit if desired.
- `LiveKrakenExecutor`, backtester — still deferred per the original spec.

---

## 6. Testing

- **DCA (`compute_dca_orders`)** — unit tests: slice sizing and per-pair split;
  cap compliance (every order ≤ $250); cash-exhaustion stop; the final partial
  slice; weights sum to 1.
- **Reconciler wiring** — integration-style test: place a resting limit buy,
  publish a book update through the feed that crosses it, assert the order fills
  and positions/cash update.
- **Warm-up gate** — test that strategy loops/triggers do not start until books
  are populated (or the timeout fires), and that a cold-start order is not
  spuriously rejected.
- **Benchmarks** — test the job computes and inserts `btc_hodl` and
  `alt_basket_equal_weight` snapshots; test the leaderboard/equity endpoints read
  them.
- **Trades count** — test the leaderboard counts only `filled`/`partial`.
- **Reset script** — test it clears exactly the intended tables and re-seeds
  $1,000 cash, against the `test` schema.

Follow the existing repo conventions (repos accept `schema=`; tests use
`schema="test"`; lifespan boot skipped under `PYTEST_CURRENT_TEST`).

---

## 7. Assumptions & open questions

1. **Reset scope** — assumed *reset all three strategies + benchmarks* to a
   clean $1,000 (user said "start fresh"). Flag if DCA-only was intended.
2. **DCA cadence/window** — weekly, 12 buys, ~3 months (Option B, user-chosen).
3. **Backend uptime** — trades only occur while the backend runs; the warm-up
   gate fixes boot-time races, not genuine downtime. Recent data suggests it
   runs mostly continuously (~22 hourly snapshots/day), with the big
   `BOOK_UNAVAILABLE` cluster in launch week.
4. **Min-order sizes** — the smallest weekly slices are ADA ~$8.33 and LINK
   ~$12.50; need to verify these clear Kraken's minimum order size at
   implementation (boot already runs a min-order universe check). Expected fine,
   but flagged.
5. **LLM-vs-DCA cap fairness** — see §5; left as a deliberate choice for now.

---

## 8. Order of implementation (for the plan)

1. DCA config + `compute_dca_orders` + relaxed caps (§3.1).
2. Reconciler wiring (§3.2).
3. Warm-up gate (§3.3).
4. Benchmark wiring + t0 capture (§3.4).
5. Trades-count fix (§3.5).
6. Reset script (§4) — run last, after the new DCA config exists so the fresh
   start uses correct settings.

Each step is independently testable and committable.
