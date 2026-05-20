# Manual Portfolio Tracking — Design

**Date:** 2026-05-20
**Status:** Approved (brainstorming complete; awaiting user review of written spec)

## Goal

Add the user's real Kraken portfolio to the strategies leaderboard as a fourth competitor — labeled "Manual" — so the project can answer its actual thesis question: *"Does any paper-trading strategy beat my own real-money trading?"*

The comparison uses **Time-Weighted Return (TWR)** over a common window starting 2026-05-12 (when paper strategies were created), with **Sharpe ratio** and **max drawdown** as risk co-pilots. TWR is the CFA/GIPS-mandated metric for comparing investment skill across portfolios with different cash-flow timing — the right shape for "is this bot more skilled than me" given the paper strategies have fixed starting balances and the user's account has periodic deposits.

The Manual row is computed on demand from existing `portfolio_snapshots` data plus a new lightweight `manual_cash_flows` table populated from the Kraken ledger. No new scheduler jobs; cash-flow scanning runs on the leaderboard-load path with a 5-minute debounce.

## Scope

**In scope**

- A new `manual_cash_flows` table (one row per deposit/withdrawal event detected on Kraken).
- A new `manual_performance` service module with pure functions for TWR (segmented), Sharpe, max drawdown.
- A new `kraken_service.get_cash_flow_entries(since)` helper that pulls deposit/withdrawal entries from Kraken's ledger.
- Extending the `_leaderboard` router to compute and append a `Manual` row alongside the paper strategies.
- A new `lifetime_return_pct` field on every leaderboard row (manual + paper).
- A small frontend tweak: new "Lifetime" column on the leaderboard, plus a visual highlight on the Manual row.

**Out of scope**

- UI to edit or delete cash flows. Auto-detection from Kraken is the source of truth.
- Other exchanges (Coinbase, Binance, etc.) — Kraken only.
- Non-AUD cash flows. If a USD/USDT deposit is detected, the system writes a `system_alert` and skips it; doesn't compute.
- Tax-lot accounting for manual trades.
- Per-asset attribution for the Manual entry (which coin contributed what to TWR).
- Backtesting paper strategies against historical Kraken trades — that would require feeding personas historical market states; separate spec.
- Sortino, Calmar, Information Ratio. Stick with Sharpe + drawdown for cross-row consistency.
- Scheduled cash-flow scan. Runs on leaderboard-load with debounce instead.

## User-facing decisions (locked)

| Decision | Choice |
|---|---|
| Comparison window start | **2026-05-12** (the day paper strategies were created). |
| Asset scope | **Everything in your Kraken account.** No coin filtering — your scope reflects your actual portfolio. |
| Headline metric | **Time-Weighted Return (TWR)** with segments cut at every cash flow. |
| Risk metrics | **Sharpe ratio** + **max drawdown**, both computed on the TWR-adjusted equity curve. |
| Cash-flow detection | **Automatic from Kraken ledger.** No manual entry. |
| Cash-flow scan trigger | **On leaderboard load, debounced to once per 5 minutes.** No scheduler job. |
| UI placement | **4th row in the existing strategies leaderboard.** Same columns + new "Lifetime" column. |
| Lifetime return display | **Yes**, as a secondary column on every row. Bots use their `return_all_time_pct`; Manual uses TWR over full Kraken history. |
| Visual treatment | **Subtle left-border or background tint** on the Manual row so it stands out. |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Hourly job (existing, unchanged): _hourly_snapshot       │
│  → records public.portfolio_snapshots (source='crypto')   │
└──────────────────────────────────────────────────────────┘
                                                            │
                                                            ▼
┌──────────────────────────────────────────────────────────┐
│  GET /api/strategies/_leaderboard                         │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼  (existing) compute paper strategy rows
         │
         ▼  (NEW) ensure_cash_flows_fresh()
         ├── 1. Read last_scanned_at from manual_cash_flows (max created_at)
         ├── 2. If now - last_scanned_at < 5 min → skip (debounce)
         ├── 3. Else: call kraken_service.get_cash_flow_entries(since=last_seen_kraken_ts)
         ├── 4. Insert new rows into manual_cash_flows; dedup on kraken_refid
         └── 5. On non-AUD asset → insert system_alert, skip
         │
         ▼  (NEW) compute_manual_metrics(window_start=2026-05-12)
         ├── 1. Pull portfolio_snapshots (source='crypto') since window_start
         ├── 2. Pull manual_cash_flows since window_start
         ├── 3. Segment the equity curve at each cash-flow event
         ├── 4. Compute TWR by geometric-compounding segment returns
         ├── 5. Build TWR-adjusted ("synthetic unit") curve
         ├── 6. Compute Sharpe + max drawdown on the synthetic curve
         └── 7. Compute lifetime TWR (same logic but window_start = oldest snapshot)
         │
         ▼  Append "Manual" row to the leaderboard response
```

Five things to highlight:

1. **No new scheduler job.** Cash-flow detection piggybacks on the existing leaderboard request, debounced. Zero idle work; the leaderboard is always current within 5 minutes when you check.

2. **The Manual entry is NOT a row in `strategies`.** It's a virtual leaderboard row. Putting it in the `strategies` table would force that table to handle two unrelated concepts (paper strategies with personas/triggers/risk caps vs. a real Kraken portfolio). Keeping Manual as a virtual row in the router preserves clean separation.

3. **Existing `portfolio_snapshots` is the equity source.** No new equity table. The `_hourly_snapshot` job already records the user's Kraken portfolio value every hour; we just need to read it back.

4. **Pure-function math layer.** TWR + Sharpe + drawdown live in `backend/services/manual_performance.py` as pure functions taking equity-curve + cash-flow inputs. Same shape as the existing `backend/services/trading/metrics.py`. Trivially unit-testable.

5. **5-minute debounce uses a single SELECT.** `SELECT MAX(created_at) FROM manual_cash_flows`. If that's within 5 minutes, skip the scan. Otherwise scan and update. No new state variable to manage.

## Data model changes

One new table, one new column on the leaderboard response shape (not a DB column — purely a response field).

**New table — `supabase/migrations/008_manual_cash_flows.sql`:**

```sql
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

**Mirror on the test schema — `supabase/migrations/test_008_manual_cash_flows.sql`:**

```sql
CREATE TABLE test.manual_cash_flows (LIKE public.manual_cash_flows INCLUDING ALL);
```

The `UNIQUE` constraint on `kraken_refid` is the idempotency guard — every Kraken ledger entry has a unique ref-id, so re-running the scan can't produce duplicates.

## TWR computation (with worked example)

Take the user's actual situation as the worked example: comparison window 2026-05-12 to today (2026-05-20). One cash-flow event: a $500 deposit today, immediately spent on ETH.

Assume hypothetical equity:

| Date | Portfolio value AUD | Event |
|---|---|---|
| 2026-05-12 | 1,847.00 | Window start |
| 2026-05-20 (pre-deposit) | 1,920.00 | Existing crypto appreciated |
| 2026-05-20 (post-deposit + ETH buy) | 2,420.00 | +500 AUD cash flow |

**Segment 1:** 2026-05-12 → 2026-05-20 (pre-deposit)
- Return = 1920 / 1847 − 1 = +0.0395 (3.95%)

**Segment 2:** 2026-05-20 (post-deposit) → onward
- Initial value = 2420; ending value depends on subsequent days

**Compound TWR for the window** = ∏(1 + segment_return) − 1, across all segments.

The deposit doesn't appear as performance — it appears as more capital deployed. This is the entire point of TWR vs. naive (value − invested) / invested: the latter would dilute your performance with new capital that hasn't had time to appreciate yet, making you look worse than you actually were.

**TWR-adjusted ("synthetic unit") equity curve** — used for Sharpe + drawdown:

| Date | Unit value | Source |
|---|---|---|
| 2026-05-12 | 1.0000 | Start |
| 2026-05-20 (pre-deposit) | 1.0395 | × (1 + segment 1 return) |
| 2026-05-20 (post-deposit) | 1.0395 | Deposit doesn't change unit value |
| Tomorrow (if ETH flat) | 1.0395 | × (1 + segment 2 return) |

Sharpe = `sharpe_24_7(synthetic_unit_curve)` — same function the paper strategies use.
Max drawdown = `max_drawdown_pct(synthetic_unit_curve)` — same.

### Reference Python signatures

```python
# backend/services/manual_performance.py

from decimal import Decimal
from datetime import datetime

@dataclass(frozen=True)
class CashFlowEvent:
    occurred_at: datetime
    amount_aud: Decimal     # positive = deposit, negative = withdrawal
    kind: str               # "deposit" | "withdrawal"

@dataclass(frozen=True)
class EquityPoint:
    captured_at: datetime
    total_value_aud: Decimal

def compute_twr(
    equity_curve: list[EquityPoint],
    cash_flows: list[CashFlowEvent],
) -> tuple[Decimal, list[Decimal]]:
    """Return (twr_pct, synthetic_unit_curve).

    Cuts segments at every cash-flow event. Geometrically compounds
    segment returns. Handles withdrawal (negative amount) symmetrically.
    Returns (0, [1.0]) for an empty equity curve.
    """
    ...

def compute_sharpe(synthetic_unit_curve: list[Decimal]) -> Decimal: ...
def compute_max_drawdown_pct(synthetic_unit_curve: list[Decimal]) -> Decimal: ...
```

(Sharpe / drawdown reuse the existing `metrics` module's logic; this signature gives them a stable wrapper.)

## Leaderboard wire-up

Existing endpoint: `GET /api/strategies/_leaderboard` in `backend/routers/strategies.py:42`.

**Two changes:**

1. **Add `lifetime_return_pct` to every existing paper row.** For paper strategies it equals `return_all_time_pct` (fixed-pool, lifetime ≡ all-time). One line.

2. **Compute and append a Manual row at the end.** Before sorting:

   ```python
   manual_row = compute_manual_leaderboard_row(schema=SCHEMA)
   out.append(manual_row)
   ```

   Then the existing `out.sort(key=lambda r: Decimal(r["equity_aud"]), reverse=True)` sorts it alongside everything else.

   Note: the `equity_aud` sort isn't ideal for cross-comparison (Manual will likely have far more equity than a paper strategy starting at AUD 1000). Two options:
   - **Keep `equity_aud` sort.** Manual lands at the top by sheer scale; visually noisy.
   - **Sort by `return_all_time_pct` instead.** Apples-to-apples and that's actually what the user wants to compare.

   Recommend: **switch the sort to `return_all_time_pct`** as part of this change. Aligns with the thesis ("who returned the most?"), not "who has the most capital."

**Response shape unchanged otherwise.** Each row still has `id`, `name`, `status`, `execution_mode`, `equity_aud`, `return_7d_pct`, `return_30d_pct`, `return_all_time_pct`, `sharpe`, `max_drawdown_pct`, `trades`, `cost_30d_aud`, `persona_prompt_stable_since`, plus the new `lifetime_return_pct`.

Manual-specific values:

| Field | Manual value |
|---|---|
| `id` | `"manual"` (string literal, not a UUID) |
| `name` | `"Manual"` |
| `status` | `"active"` |
| `execution_mode` | `"manual"` |
| `equity_aud` | Live: sum of Kraken balances × current ticker prices |
| `return_7d_pct` / `return_30d_pct` / `return_all_time_pct` | TWR over each window (all-time = since 2026-05-12) |
| `sharpe`, `max_drawdown_pct` | Computed on synthetic unit curve |
| `trades` | Count of buy/sell trades from Kraken in the window |
| `cost_30d_aud` | `"0"` — Kraken trading fees are already in `equity_aud`; double-counting would mislead |
| `persona_prompt_stable_since` | `null` |
| `lifetime_return_pct` | TWR over the full Kraken history |

## Frontend changes

Existing `StrategiesPage` already renders the leaderboard as a sortable table. Three changes:

1. **New "Lifetime" column.** Smaller font / muted color to signal "context, not the apples-to-apples comparison." Right of `return_all_time_pct`.
2. **Visual highlight on Manual row.** Subtle left-border (e.g., 3px accent color) or background tint so the user can locate "me" without scanning.
3. **Caveat banner under the table** while the comparison window is short:

   > Comparisons are noisy until the window includes a few weeks of varied market conditions. Treat numbers cautiously through mid-June 2026.

   The cutoff date can be hard-coded (4 weeks past 2026-05-12) and removed in a follow-up PR.

No new pages, no new modals, no new charts. Same time-window selector (7d / 30d / all) drives both paper and Manual rows.

## Cash-flow scanning logic

```python
# backend/services/manual_cash_flow_scanner.py

_DEBOUNCE_SECONDS = 300  # 5 minutes

def ensure_cash_flows_fresh(*, schema: str = "public") -> None:
    """Idempotent. Pulls Kraken ledger deposit/withdrawal entries since the
    last known cash-flow timestamp; appends new ones to manual_cash_flows.
    Skipped if last scan was within the debounce window.
    """
    last_scanned = manual_cash_flows_repo.last_created_at(schema=schema)
    now = datetime.now(timezone.utc)
    if last_scanned and (now - last_scanned).total_seconds() < _DEBOUNCE_SECONDS:
        return
    last_seen_kraken_ts = manual_cash_flows_repo.latest_occurred_at(schema=schema)
    entries = kraken_service.get_cash_flow_entries(since=last_seen_kraken_ts)
    for entry in entries:
        if entry.asset != "AUD":
            system_alerts_repo.insert(
                level="warning", code="MANUAL_CASHFLOW_NON_AUD",
                strategy_id=None,
                message=f"Non-AUD cash flow detected: {entry.asset} {entry.amount}",
                payload={"refid": entry.refid, "asset": entry.asset},
                schema=schema,
            )
            continue
        manual_cash_flows_repo.upsert_by_refid(
            kraken_refid=entry.refid, kind=entry.kind,
            amount_aud=entry.amount, occurred_at=entry.occurred_at,
            schema=schema,
        )
```

**Failure semantics:** if the Kraken API call fails, log via `logger.exception` and continue with whatever cash flows are already in the DB. The leaderboard still renders; it just won't reflect the very newest deposit. This is best-effort by design — broken phone push notifications shouldn't crash trading decisions, and a broken Kraken ledger fetch shouldn't crash the leaderboard.

## Edge cases

| Case | Behavior |
|---|---|
| No `portfolio_snapshots` row on 2026-05-12 | Use `snapshots_repo.get_nearest("2026-05-12T00:00:00+00:00")`. If the nearest is >24h off, insert `system_alert(code="MANUAL_BASELINE_GAP")`. |
| Withdrawal during the window | Same segmentation as deposits. `kind="withdrawal"`, `amount_aud` stored as positive (the `kind` column distinguishes direction; the TWR math reads it). |
| No cash flows in window | TWR = `(current / start) - 1`. Single segment. Trivial. |
| Internal trade (sell ETH → buy SOL) | NOT a cash flow. No segment cut. Just shows up in the changing equity. Already handled because `get_cash_flow_entries` filters to `type ∈ {deposit, withdrawal}`. |
| Portfolio at $0 mid-window | Segment ending at $0 → return = `-1.0`. Compounding `(1 + (-1.0)) = 0` propagates forever. Detect this and stop segmenting; return TWR = -100%, lock the synthetic curve at 0 for subsequent points. |
| Non-AUD deposit (USD, USDT, etc.) | Skip; insert `system_alert(code="MANUAL_CASHFLOW_NON_AUD")`. Doesn't break the TWR computation. |
| First-time setup with no historical snapshots | Run `snapshot_service.backfill_from_ledger()` once. Function already exists. |
| Kraken API failure during scan | Log + continue. Leaderboard still renders using the cached `manual_cash_flows`. Never raises into the request. |
| Zero balance on every asset (user closed account) | `equity_aud = 0`. TWR was already computed before this; show -100% and don't crash. |

## Testing

| Test file | Coverage |
|---|---|
| `backend/tests/test_manual_twr.py` (unit) | TWR with: (a) no cash flow, (b) one deposit mid-window, (c) one withdrawal mid-window, (d) deposit + withdrawal in sequence, (e) zero-portfolio mid-window edge, (f) synthetic curve matches expected shape. Pure-function, no DB, no HTTP. |
| `backend/tests/test_manual_cash_flow_scanner.py` (unit) | Mock Kraken ledger response: (a) detects deposit, (b) detects withdrawal, (c) ignores trade entries, (d) dedup by refid on re-scan, (e) non-AUD entry triggers system_alert + skip, (f) Kraken failure swallowed. Uses `respx` for HTTP. |
| `backend/tests/test_manual_leaderboard.py` (integration) | Seed `portfolio_snapshots` + `manual_cash_flows` rows on test schema. Call the leaderboard endpoint. Assert the Manual row appears with correct TWR, Sharpe, drawdown, lifetime. Also assert sort order (by `return_all_time_pct`). |
| `backend/tests/test_manual_debounce.py` (unit) | Calling `ensure_cash_flows_fresh()` twice within 5 minutes makes exactly one Kraken API call. |

No new eval-suite changes — these are deterministic metrics, not LLM behavior.

## Open question for review

**Sort order on the leaderboard.** Today it sorts by `equity_aud` desc, which made sense when every entry started at AUD 1000. With Manual in the mix, that sort puts Manual at the top regardless of skill (because the real portfolio holds more). Switching to `return_all_time_pct` desc is more useful — it directly answers "who returned the most?" — but it's a behavior change for existing users. Flagging this for explicit user approval before the implementation plan.

## Future work (named, not in scope)

- **Per-asset attribution for Manual.** Which coin contributed what to TWR. Useful diagnostic, requires per-asset segmentation.
- **Sortino ratio** as an alternative risk metric. Better for crypto's fat-tailed returns. Would need to be added to paper strategies' metrics too for consistency.
- **Multi-exchange tracking.** Coinbase, Binance, etc. Each exchange would need its own ledger adapter.
- **Currency conversion** for non-AUD deposits (USDT, USDC). Requires real-time FX or stablecoin oracle.
- **Backtesting paper strategies on user's historical trades.** Would let us ask "what would Trend-Follower have done in the same windows Ben was active?" without waiting months for forward data. Separate, larger spec.
