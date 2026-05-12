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
