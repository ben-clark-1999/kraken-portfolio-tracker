# Paper-Trading Sandbox — Manual Smoke Checklist

Run before each major release / when verifying the system end-to-end.

## 1. Backend boot
- [ ] `backend/.venv/bin/uvicorn backend.main:app --reload --port 8000` starts without exceptions.
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
- [ ] Manually insert a 25%+ drawdown equity snapshot for a test strategy → strategy auto-pauses, `system_alerts` row created (`KILL_CRITERIA_AUTO_PAUSED`), status flips to `paused`.

## 7. Idempotency
- [ ] Submit `place_paper_order` twice with the same `idempotency_key` — only one row in `paper_orders`.

## 8. Frontend
- [ ] `/strategies` route loads.
- [ ] Leaderboard shows three rows sorted by equity desc.
- [ ] Equity chart shows the strategy curves + BTC HODL dashed line + alt-basket dashed line.
- [ ] Range picker (1D / 7D / 30D / 90D / All) filters the chart.
- [ ] Clicking a row opens the detail drawer.
- [ ] Decisions feed populates after the first invocation.
- [ ] Persona Chat tab on Trend-Follower currently renders the read-only stub (backend persona-conversational mode is the open follow-up — see `PersonaChatTab.tsx`).
- [ ] Status banner renders green when feeds are fresh; expand → no anomalies.
- [ ] Pause/Resume/Archive buttons reflect in DB; leaderboard refreshes when the drawer is reopened.

## 9. Dry-run mode
- [ ] Flip `Trend-Follower.dry_run = true` via psql. Wait for next invocation.
- [ ] `agent_decisions` row written. `paper_orders` NOT created.
- [ ] Flip back to false; verify orders resume.

## 10. Cost attribution
- [ ] After ~24 h of running, check `paper_strategy_costs` view: should show per-day per-strategy AUD cost.
- [ ] Monthly total within AUD 40–70 band (spec §6.5 estimate); investigate if much higher.

## 11. Open follow-ups (tracked outside this plan)
- Backend persona-conversational chat mode (`/api/agent/chat?mode=persona_conversational&strategy_id=…`) — required for `PersonaChatTab` to wire up safely with a read-only tool surface.
- LiveKrakenExecutor — spec §5.8.
- Backtester (Phase 2).
- **LocalOrderBook checksum hardening.** Verification is currently soft (logged, not fatal) because the algorithm doesn't know each pair's `pair_decimals` / `lot_decimals` and `Decimal.normalize()` was stripping trailing zeros. Proper fix: extend `fetch_asset_pairs` in `min_order.py` to also return precision metadata, thread it into `LocalOrderBook.compute_checksum`, and reinstate the hard-fail behaviour. ~30-45 min and 4 files.
