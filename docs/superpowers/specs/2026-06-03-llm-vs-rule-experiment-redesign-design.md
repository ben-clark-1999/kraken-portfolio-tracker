# LLM-vs-Rule Trading Experiment — Redesign

**Date:** 2026-06-03
**Status:** Design — pending review

## Background

The paper-trading experiment pits LLM-driven strategies (Trend-Follower,
Mean-Reverter) against deterministic rule "twins" (Trend-Rule,
Mean-Reversion-Rule) and a DCA baseline. The thesis: *does an LLM make
better investing decisions than a hard rule, given the same job?*

As built, the experiment cannot answer that question, for two reasons
surfaced during design review:

1. **The LLM sees the same data as the rule.** Its only tools are
   `get_market_snapshot` (prices/candles), `get_my_paper_state`, and
   `get_my_recent_decisions`. With identical numeric inputs and no ability
   to seek outside information, "reasoning" collapses into a fuzzy decision
   tree — and a fuzzy decision tree is strictly worse than the exact rule
   (slower, costlier, non-reproducible). The rule wins by construction.

2. **The rule's parameters are unvalidated.** The Trend strategies trigger
   on a hardcoded `min_move_pct: 1.5%` breakout buffer with no derivation
   behind it. An arbitrary threshold in the control group silently decides
   the outcome: too tight and the rule over-trades and looks bad; too loose
   and it under-trades and looks bad. Either way the result reflects buffer
   choice, not reasoning-vs-rules.

A third, smaller issue: the event-driven breakout/stretch triggers were
designed but never wired to a publisher (`trigger_evaluators.py` exists;
`price_feed.py` publishes only `Tick`/`BookUpdate`). Today the only live
wake is the daily 09:00 cron, so the Trend-Follower is blind to intraday
breakouts — the exact move it is supposed to catch.

## Goal

Make the experiment a genuine test of *reasoning + information-seeking vs. a
well-calibrated rule*, while keeping LLM cost bounded.

### Success criteria

- The LLM can reach for information the rule structurally cannot use
  (news, on-chain/market data, macro/calendar), so its potential edge is
  real rather than a re-derivation of the same numbers.
- The rule is a *strong, fairly-calibrated opponent*, not a strawman.
- Every threshold (z entry/exit, breakout cushion) is **justified against
  real Kraken fees and measured price variance** — never an abstract number.
  A threshold whose expected captured move does not clear the round-trip cost
  is a guaranteed loser and must be rejected.
- The LLM and its deterministic twin wake on the **same** trigger at the
  **same** time on the **same** data, so the measured difference is
  attributable to reasoning, not cadence.
- LLM cost stays bounded and predictable.
- A "the rule wins / the LLM adds only cost" outcome is treated as a
  valuable, publishable result — not a failure.

### Out of scope (deliberately, to avoid overcomplicating)

- **Shorting.** Strategies stay long-only: "sell" = exit a held position to
  cash, never a short. A falling market can only hurt, never be shorted.
- **Universe changes.** Stays ETH/AUD, SOL/AUD, LINK/AUD, ADA/AUD.
- **Risk-cap / kill-criteria changes.** The level-playing-field defaults
  stay as-is.

## Decision 1 — Wire the breakout detector to the live price stream

Connect the existing `detect_breakout` logic to the tick stream
`price_feed` already receives, so breakouts fire **intraday** rather than
only at the daily cron.

**Mechanism (event-driven, not polling):** on each incoming tick,
`price_feed` (a) maintains a rolling 24h record to know the current high /
low, (b) checks whether the new price clears `high × (1 + cushion)`
(breakout up) or `low × (1 − cushion)` (breakdown), and (c) if so, and the
existing `cooldown_seconds` / `debounce_seconds` have not already
suppressed it, publishes a `PriceBreakoutEvent` to the event bus. The
strategy is already subscribed via its `price_breakout` trigger config.

The check is pure arithmetic over ~24 numbers — effectively free — and runs
only when a tick arrives (the stream pushes; we do not poll).

**Open choice to settle in planning:** evaluate on *every tick* (most
responsive, slightly noisier) vs. on *hourly bar close* (matches the
persona prompt's "price *closing* above the 24h high" language, up to ~1h
slower). Default recommendation: bar-close, to match the documented
semantics and reduce noise; revisit if it proves too laggy.

## Decision 2 — Give the LLM information the rule cannot use

Add tools that let the LLM autonomously fetch outside context. Selected
categories (from design review): **news/headlines**, **on-chain & market
data** (e.g. broader market, flows, funding/sentiment), and
**macro/calendar** (scheduled events: CPI, Fed, token unlocks). This is the
LLM's structural edge — the rule has no equivalent.

**Cadence — daily research + cheap intraday react:**

- **Daily research pass:** once per day the LLM runs a full research loop
  (news/on-chain/macro) and produces a cached "market view" summary.
  News/macro move slowly, so this does not need to re-run per signal.
- **Intraday reaction:** when a breakout event fires (Decision 1), the LLM
  runs a *cheaper* decision that references the cached market view instead
  of re-researching from scratch, then decides buy / hold / size / exit.

This decouples the slow, expensive part (research) from the fast, cheap
part (reacting to a price signal).

**Twin symmetry:** the deterministic twin must wake on the **same**
breakout event as the LLM (its trigger switches from daily cron to the same
`price_breakout` event). Same alarm clock for both; only the brain differs.

**Implementation shape:** LangGraph ReAct loop (same pattern as Phase 3)
with the new tools added, looping until a concrete decision. A per-invocation
**turn/token cap** prevents the model from wandering and racking up cost.

## Decision 3 — Make the rule a fair, calibrated opponent

Two changes, both on the free deterministic side:

1. **Normalize the trend threshold.** Replace the arbitrary fixed `1.5%`
   with a volatility-scaled cushion (σ- or ATR-based), so a "meaningful
   breakout" adapts to each coin's volatility — the same way the
   Mean-Reverter's 2σ z-score already does. This does **not** merge the two
   strategies: the Mean-Reverter measures distance from the *center* of the
   range (buys on weakness, z ≤ −2); the Trend-Follower measures a break
   past the *edge* of the range (buys on strength, new high). Same unit of
   measure, opposite reference point, opposite direction of bet.

2. **Offline parameter sweep — net of cost.** Backtest the rule across a
   range of buffer values (e.g. 1σ / 1.5σ / 2σ / 3σ, or ATR multiples) over
   historical price data, offline. The backtest P&L must be computed **net
   of the real fee schedule (`fees.py`) and the walk-the-book fill model
   (`fill_model.py`)** — never gross price moves — or the sweep flatters
   over-trading. Report the LLM against the *whole curve*, not one
   cherry-picked buffer. Beating the best *hindsight-tuned* rule is a high
   bar (the rule is optimized on the same data it is judged on); clearing it
   is a strong result, beating only badly-tuned rules is a weak one — either
   way the truth is exposed.

## Decision 4 — Cost controls

Cost = (how often the LLM runs) × (tokens per run). Both bounded:

- **Free gate in front of the expensive brain.** The Python breakout
  detector filters out the ~23h/day of nothing; the LLM only spins up on a
  genuine signal. The sweep (Decision 3) is entirely on the free
  deterministic side — sweeping costs zero tokens.
- **One LLM per strategy.** No matter how many rule buffers are swept, only
  a single LLM instance runs live.
- **Prompt caching.** Cache the persona prompt and stable context (largest
  single lever; ~90% input discount on cache hits). Not currently used.
- **Existing brakes.** `cooldown_seconds: 900` and `max_calls_per_hour: 10`
  in the trigger config cap fire frequency even in volatile markets.
- **Per-invocation turn/token cap** on the research loop.

Rough order-of-magnitude (Haiku 4.5, **to verify against live pricing**):
~$0.10–0.40 per research-heavy decision before caching; daily-research +
gated-intraday keeps this to a handful of runs/day/strategy. Watch the
web-search / data-tool per-call fees separately — those may dominate token
cost.

## Decision 5 — Thresholds derived from Kraken fees + measured variance

No threshold is chosen in the abstract. Each is justified so the expected
captured move clears the real round-trip cost on the Kraken platform.

**The real cost stack (grounded in code):**

- **Fees (`fees.py`, verified vs kraken.com 2026-05-19):** 0.40% maker /
  0.80% taker. Round-trip = **0.8% maker-both-sides** or **1.6% taker-both-
  sides**. The assumed fee role must be stated per strategy — using passive
  limit orders (maker) halves the hurdle vs market orders (taker).
- **Spread + slippage (`fill_model.py`):** market orders walk the book and
  fill at progressively worse prices. The per-order AUD 250 cap (split into
  chunks) bounds but does not eliminate this. Estimate it from the order
  book at the order sizes actually used.

**The derivation (mean reversion):** a buy at `entry_z` σ below the mean
targets a reversion of roughly `|entry_z| × σ%` (σ as a percent of price).
Positive expectancy requires:

```
|entry_z| × σ%   >   round-trip fee  +  avg spread  +  expected slippage
```

So `entry_z` is set *per pair* from that pair's measured σ% and cost stack,
with a safety multiple — not a shared constant. Example: if a coin's 48h σ%
is ~0.5%, a 2σ entry targets ~1% < the 1.6% taker round-trip and is
rejected; that pair needs a wider entry (e.g. ~3.5σ) or maker-only
execution to be tradeable at all.

**The derivation (trend):** the breakout cushion (in σ/ATR) must be wide
enough that signals too small to overcome fees on the eventual losing exits
are filtered out. Trend lets winners run (open-ended upside), but each entry
still has to clear the round-trip cost on the trades that reverse.

**Requirements this imposes:**

1. Measure realized σ% per pair from actual Kraken price history (the same
   series feeding the live z-score), not assumed.
2. Estimate the per-pair cost stack (fee role + spread + slippage at the
   real order sizes) using `fees.py` and `fill_model.py`.
3. Set every live threshold from (1) and (2); record the justification
   alongside the value so it is auditable.
4. The offline sweep (Decision 3) and all P&L are net of this cost stack.

## Risks / open questions

- **Tick vs bar-close** evaluation (Decision 1) — settle in planning.
- **Which concrete data providers** for news/on-chain/macro, and their
  per-call pricing — needs a quick survey before implementation.
- **Mid-experiment change.** The live run is only ~1 day old (DCA started
  2026-06-02), so changing strategy behaviour now is essentially free; doing
  it later would invalidate before/after comparisons. This redesign should
  land before meaningful data accumulates, implying a clean t0 reset.
- **Prompt drift into hidden if/else.** Guard against the persona prompt
  becoming an English decision tree (e.g. "aim for 3–4% to clear fees" is a
  rule, not judgment). The prompt should give mandate + principles and let
  the LLM derive thresholds; otherwise the experiment collapses into
  "English rules vs Python rules," which Python wins by default.
