# LLM-vs-Rule Trading Experiment — Redesign (v1)

**Date:** 2026-06-03
**Status:** Design — pending review

## The question

Does a hardcoded **rule** beat an **LLM that can use looked-up information** to
decide?

A single binary comparison, per strategy family: the existing deterministic
rule vs. one LLM strategy that is given external information the rule cannot
see. We test **whether** the informed LLM beats the rule — not decomposing
*why* (judgement vs. information). Two contestants per family, not a matrix of
variants.

## The problem with the current setup

The current LLM personas (`trend-follower.md`, `mean-reverter.md`) have exactly
one window to the market: `get_market_snapshot` — price, 1h OHLC, and a
precomputed z-score. **That is the identical data the deterministic rule
computes from.** Worse, the personas' "Signals you primarily weight" sections
restate the rule's thresholds in English:

- Trend-Follower: *"Price closing above the 24-hour high → long; below the
  24-hour low → exit"* — identical to `trend_signal`.
- Mean-Reverter: *"z > 2 = trim; < -2 = buy; between = hold"* — identical to
  `mean_reversion_signal`, and the z-score is even pre-computed and handed over.

So the LLM sees the same inputs and is told the same cutoffs. It can only differ
from the rule in soft margins (sizing, aborting borderline signals, volume
nuance, consistency) — all judgements over the **same price data**. With no
information the rule lacks, the comparison only asks "does fuzzy judgement over
identical inputs beat a crisp rule?" — to which the honest answer is "no, or
marginally, at extra cost." The personas have also already drifted into English
if/else (*"aim for 3-4%"*, *"a 1.5σ stretch reverting 1% is a loser — hold"*).

**The fix:** give the LLM information the rule *structurally cannot use* — news,
sentiment, broader-market context — so the experiment tests something real.

## v1 design — free sources, fixed-gather pipeline

### Architecture: gather-then-decide (NOT an agentic tool-choosing loop)

The LLM does **not** choose which tools to call. With a small set of cheap,
always-relevant sources, selective tool choice adds cost and nondeterminism for
no benefit — it would just call them all. So each wake runs two phases:

**Phase 1 — Gather (deterministic Python, no LLM):** fetch all the cheap
sources and assemble one structured **briefing** text block.

**Phase 2 — Decide (LLM, once):** the LLM receives its persona + portfolio
state + the signal that fired + the briefing, and outputs buy/hold/sell + size
+ rationale.

This is still orchestrated in the existing LangGraph setup, just as a
deterministic graph rather than a ReAct loop. (Why not agentic: see "Deferred".)

### The free sources and how they're fetched

| Source | Provides | Fetch | Key |
|---|---|---|---|
| **Kraken API** | Own 4 pairs: price, OHLC, z-score | existing `get_market_snapshot` | already configured |
| **CoinGecko free tier** | Broader market: BTC price + 24h move, total market cap, BTC dominance | HTTP GET `/global` + price, parse JSON | likely a free "demo" key now — verify |
| **RSS feeds** (CoinDesk, Cointelegraph, Decrypt) | Recent headlines + summaries + timestamps | Python `feedparser` over a list of feed URLs | none |
| **CryptoPanic free tier** | News aggregation + vote/sentiment signal | HTTP GET `/api/v1/posts/?currencies=…` | free API token |
| **Hardcoded macro calendar** | Known CPI / FOMC dates | static list in repo | none |

The genuine information **edge** is the news/sentiment (RSS + CryptoPanic) — the
rest is supporting context. All pricing/key details to be verified at build;
the search-tool/news line is the only cost that can creep.

### Handling news noise

Raw RSS is mostly irrelevant. The gather step filters: keep only the last ~24h,
only items mentioning the 4 coins or "bitcoin/crypto/market", cap at ~10-15
headlines (token budget). The LLM judges relevance of the filtered shortlist —
that judgement over messy text is part of what's being tested.

### Prompt design: facts, not verdicts; principles, not rules

The briefing injects **raw facts**, not pre-computed conclusions:

```
MARKET CONTEXT (gathered now):
- BTC: +5.2% (24h)   Total mcap: +4.8%   BTC dominance: 54% (rising)
- ETH (your coin): broke 24h high, +5.5% (24h)
RECENT HEADLINES (last 24h):
- 09:12  "ETH ETF sees record inflows"  (CoinDesk)
MACRO: FOMC decision today 2pm.
```

The persona gives **principles** (*"consider whether a breakout is coin-specific
or market-wide; weigh news and imminent macro against the signal"*), never
if/then rules. Do **not** pre-compute "market is moving: YES" in Python — give
the numbers and let the LLM draw the conclusion. That conclusion-drawing is the
capability under test.

Critically, the existing persona lines that are English if/else (the "3-4%",
"1.5σ" rules) should be rewritten as principles or removed, or the experiment
collapses into English-rules-vs-Python-rules.

### Auditability (required by the thesis)

Save the assembled briefing alongside each decision, with timestamps. Every
trade must be answerable: "what did the LLM see, what did it reason
(`<rationale>`), what did it do (tool calls)?" Inputs + stated reasoning +
action logged = not a black box.

### Cadence & fairness

Both the rule and the LLM wake on the **same daily 09:00 cron, on the same
data**. Both stay daily, so the comparison is fair with no intraday wiring.

### Cost

One LLM wake per strategy per day, on Haiku, with a fixed handful of fetches.
Prompt-cache the persona; cap the decision turn. Bounded and tiny for a ~$1k
paper experiment.

### A fair rule threshold (volatility-normalized)

The trend rule currently triggers on a **flat 1.5% breakout cushion** — an
arbitrary number that means different things per coin (1.5% is a real move for
calm ETH but sits inside the normal noise of wilder SOL, which would then
"break out" on jitter). Since the threshold governs the *rule* and the LLM is
free of it, a badly-chosen 1.5% is a confound: the LLM could win merely because
the rule was mis-tuned, not because its information helped.

Fix: replace the flat percent with a **volatility-scaled cushion**.
- Breakout up when price exceeds the recent high by **k · σ**; exit when it
  drops below the recent low by **k · σ**.
- σ is `stdev_48h_1h`, already returned by `get_market_snapshot` (from the
  z-score work) — so the ingredient exists, minimal new code.
- k defaults to a sensible value (~2). "A meaningful breakout" then means the
  same statistical event (k normal-wiggles beyond the edge) for every coin, and
  the trend rule is expressed in the **same units (σ) as the mean-reverter** —
  one measures off the *edges*, one off the *center*. Methodologically symmetric.

Honest scope: k is still a chosen parameter — better than 1.5% (scale-free,
fair across coins, consistent with the mean-reverter), but *fair*, not *proven
optimal*. Finding the best k is the deferred offline sweep. Sanity-check that
the resulting cushion clears the round-trip fee.

### Fee-awareness (light)

Both contestants already pay the real Kraken fee model (`fees.py`: 0.40% maker /
0.80% taker; round-trip 0.8% / 1.6%) and walk-the-book slippage
(`fill_model.py`). Only requirement: don't configure a threshold targeting a
profit smaller than the round-trip cost. No per-pair derivation in v1.

## Out of scope (v1)

- **Shorting** — long-only stays ("sell" = exit to cash).
- **Universe** — ETH/AUD, SOL/AUD, LINK/AUD, ADA/AUD unchanged.
- **Risk-cap / kill-criteria** — level-playing-field defaults stay.

## Deferred — the agentic + paid future phase

Recorded, deliberately not built now. The architecture scales with the toolset:
**fixed gather while tools are cheap; agentic loop when they're expensive.**

1. **Agentic tool-use + paid tools.** When you add *expensive* sources —
   on-chain analytics (Glassnode/Nansen/Santiment: whale flows, exchange
   in/outflows), premium sentiment, token-unlock data — selective tool use earns
   its keep: the LLM decides whether a costly lookup is worth it for a given
   trade, and can follow leads iteratively. *That* justifies a ReAct loop.
2. **Intraday wiring** (fire on breakouts during the day) — and with it the
   **daily-research-cache / two-agent split**, which only pays off when
   amortising many intraday LLM calls.
3. **Offline net-of-cost buffer sweep** — backtest the (now volatility-scaled)
   rule across a range of k values on historical data, P&L net of fees/slippage,
   to find the best tuning and report the LLM against the whole curve. The
   normalization itself is in v1 (above); only the sweep that *optimizes* k is
   deferred.
4. **Variable-isolation variants** (e.g. a price-only LLM third arm) — only if
   you later want to attribute *why* it wins, not *whether*.

## Open question (settle before implementation)

**Maker-only (limit) vs. market orders.** Limits pay the maker rate (0.8%
round-trip) vs. market orders' taker (1.6%), halving the fee hurdle. Reasonable
v1 default: prefer limit orders.

## Risks

- **Prompt drift into hidden if/else** — the persona must give mandate +
  principles, not a decision tree. Rewrite the existing "3-4%"/"1.5σ" lines.
- **Mid-experiment change** — live run is ~1 day old; changing now is free, so
  do it before data accumulates and reset to a clean t0.
- **Source/key fragility** — RSS URLs and free-tier keys/limits change; the
  gather step must degrade gracefully (proceed with whatever it got) and log
  what was missing.
