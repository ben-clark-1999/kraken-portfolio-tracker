# Trend-Rule — Persona Charter

**This strategy does NOT run through an LLM. It runs in `deterministic`
execution mode (mode `trend_rule`) and exists here for documentation
continuity only.**

## What it is
The mechanical twin of the **LLM Trend-Follower**. It watches the same
signal the Trend-Follower's trigger reacts to — a 24-hour breakout — and
acts on a fixed cutoff instead of Claude's judgement.

## Universe
ETH/AUD · SOL/AUD · LINK/AUD · ADA/AUD. No BTC. No USD pairs.

## Rule
For each coin, on the trailing 24 hourly closes:
- Price breaks **above the 24h high by ≥1.5%** → go long (target into it).
- Price breaks **below the 24h low by ≥1.5%** → exit to cash.
- Otherwise → hold the current state.
Target = equal weight across the coins currently long (none long → 100% cash).
Evaluated **daily** at 09:00 AET (`0 9 * * *`); trades only when a coin's
state flips.

## Why it exists
To isolate whether the AI adds anything over a dumb version of itself. If
the LLM Trend-Follower can't beat this fixed-threshold twin, the model's
reasoning isn't earning its cost.
