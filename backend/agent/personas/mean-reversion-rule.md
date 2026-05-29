# Mean-Reversion-Rule — Persona Charter

**This strategy does NOT run through an LLM. It runs in `deterministic`
execution mode (mode `mean_reversion_rule`) and exists here for
documentation continuity only.**

## What it is
The mechanical twin of the **LLM Mean-Reverter**. It reads the same 48-hour
z-score the Mean-Reverter sees and acts on fixed cutoffs instead of Claude's
judgement.

## Universe
ETH/AUD · SOL/AUD · LINK/AUD · ADA/AUD. No BTC. No USD pairs.

## Rule
For each coin, using the 48h z-score `(mid − mean48) / stdev48`:
- **z ≤ −2** (unusually cheap) → buy in.
- **z ≥ 0** (reverted to its average) → exit to cash.
- Otherwise → hold.
Target weight per held coin = equal-weight share. Evaluated **daily** at
09:00 AET (`0 9 * * *`); trades only on threshold crossings.

## Why it exists
To isolate whether the AI adds anything over a dumb version of itself. If
the LLM Mean-Reverter can't beat this fixed-threshold twin, the model's
reasoning isn't earning its cost.
