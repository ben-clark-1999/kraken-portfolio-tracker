# Phone Push Notifications for Trade Signals — Design

**Date:** 2026-05-19
**Status:** Approved (brainstorming complete; awaiting user review of written spec)

## Goal

When the user has decided which paper-trading strategy they want to follow as a live signal source, fire a phone push notification each time that strategy emits a buy/sell decision. The notification carries enough context (pair, side, notional, price, allocation-after, confidence) that the user can act manually on Kraken without opening the dashboard. Stays dormant by default — no strategy notifies until explicitly enabled.

This is the first half of a two-step migration from paper-only to autonomous live trading: phase 1 is "tell me what to do" (this spec); phase 2 is "do it for me" (a future `LiveKrakenExecutor`, separate spec).

## Scope

**In scope**

- A new `NotificationService` with a provider-agnostic `send(payload)` interface and one ntfy.sh implementation.
- A hook at the `write_agent_decision` seam that fans out one notification per `agent_decisions` row that contains buy/sell tool calls.
- One new column on `strategies` (`notify_enabled bool`) and one on `agent_decisions` (`notified_at timestamptz`).
- Two new env vars (`NTFY_TOPIC`, `NTFY_URL_BASE`) and ~5 README lines covering phone-app setup.
- Unit + integration tests for the service and the hook.

**Out of scope**

- Tap-to-execute. Notification is informational; user trades manually on Kraken.
- Quiet hours / DND. iOS Focus modes handle this.
- Confidence-based filtering. Confidence is *included in the body*, not used as a gate. Re-evaluate after real-use data.
- Price-level alerts ("ETH < $3000"). Different trigger source; separate feature if ever wanted.
- System-alert notifications on the phone. They live on the dashboard.
- Multi-device fanout, web push, email fallback. Single device, single channel.
- Notification history view in the UI. `agent_decisions` already shows the underlying record.
- Self-hosting the ntfy broker. Public broker is fine for personal use; design allows swap via `NTFY_URL_BASE`.

## User-facing decisions (locked)

| Decision | Choice |
|---|---|
| Trigger source | Strategy decisions only (buy/sell tool calls on `agent_decisions`). |
| Delivery channel | ntfy.sh public broker. Free, no account, ~5 min phone setup. |
| Scope | One strategy at a time, via per-strategy `notify_enabled` flag. Default off. |
| Content depth | Action + context (pair, side, notional, mid, allocation-after, confidence, source strategy). |
| Hook point | After `write_agent_decision` — i.e. on the strategy's *intent*, not on the paper executor's outcome. |
| Coalescing | One notification per `agent_decisions` row, regardless of how many legs it contains. |
| Confidence filter | None. Confidence is shown in body so the user can weigh it themselves. |

## Architecture

```
Strategy decides to act
(LLM persona or deterministic rebalance)
        │
        ▼
write_agent_decision(...)        writes row to agent_decisions
        │                        (tool_calls = [{place_paper_order, …}])
        │
        ▼
NotificationService.maybe_notify(decision_id)        ◄── NEW
        │
        ├─ 1. SELECT notify_enabled FROM strategies WHERE id = ...
        │     If false, return (most decisions exit here).
        ├─ 2. Filter tool_calls to place_paper_order with side ∈ {buy,sell}.
        │     If none, return.
        ├─ 3. For each leg: pull current mid + recompute allocation-after.
        ├─ 4. For LLM strategies: extract <confidence>...</confidence>
        │     from agent_output. Empty/missing → "—".
        ├─ 5. Render title + body (single-leg or multi-leg variant).
        ├─ 6. POST {NTFY_URL_BASE}/{NTFY_TOPIC} with 5s timeout.
        │     Retry once with 1s backoff on timeout / non-2xx.
        │     On persistent failure, insert system_alert(level=warning,
        │     code=PUSH_NOTIFY_FAILED, payload={"decision_id": ...}).
        └─ 7. UPDATE agent_decisions SET notified_at = now()
              WHERE id = ... AND notified_at IS NULL.
              The WHERE clause is the idempotency guard against retry.

        ▼
PaperExecutor.submit_order(...)   unchanged, runs after notify
```

Three things to highlight:

1. **The hook lives in `backend/services/trading/decision_writer.py`** — the seven-line file that wraps `agent_decisions_repo.insert(...)`. Adding the post-write call there means both deterministic (`strategy_loop.invoke_deterministic_strategy`) and LLM (`llm_strategy.invoke_llm_strategy`) decision paths get notifications without duplicate wiring.

2. **`NotificationService` is provider-agnostic.** Public interface is one method: `async def maybe_notify(decision_id: UUID) -> None`. The ntfy implementation lives behind a private `_send_ntfy(payload)` so a future Pushover or FCM provider could slot in without changing the call site.

3. **Best-effort delivery.** A push failure (network, ntfy outage, missing env var) must never raise into `write_agent_decision`, must never pause a strategy, and must never block an order from being placed. The notification path is fire-and-forget from the trading loop's perspective.

## Data model changes

Two new files, following the existing `supabase/migrations/NNN_<name>.sql` convention (latest is `006_paper_trading.sql`):

`supabase/migrations/007_push_notifications.sql`:

```sql
ALTER TABLE public.strategies
  ADD COLUMN notify_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE public.agent_decisions
  ADD COLUMN notified_at timestamptz NULL;
```

`supabase/migrations/test_007_push_notifications.sql`:

```sql
ALTER TABLE test.strategies
  ADD COLUMN notify_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE test.agent_decisions
  ADD COLUMN notified_at timestamptz NULL;
```

Both columns are additive and default to a no-op state, so the migration is safe to apply ahead of code rollout. No backfill needed.

The `notified_at` column is *both* an idempotency guard (the `UPDATE ... WHERE notified_at IS NULL` clause in step 7) and a debugging breadcrumb ("was this decision notified, and when").

## Notification content

**Single-leg decision** (one buy/sell tool call):

```
Title:  BUY ETH/AUD — Trend-Follower
Body:   100 AUD @ ~$3450 (mid)
        ETH allocation after: 23% (was 18%)
        Confidence: medium
Tags:   buy, eth_aud
Click:  {FRONTEND_URL}/strategies/{strategy_id}
```

**Multi-leg decision** (e.g. fortnightly DCA rebalance produces 4 orders):

```
Title:  DCA-Baseline — 4 orders
Body:   BUY ETH    250 AUD @ ~$3450
        BUY SOL    150 AUD @ ~$140
        BUY LINK   100 AUD @ ~$22
        SELL AUD   500 AUD
        Source: DCA-Baseline (deterministic)
Tags:   rebalance
Click:  {FRONTEND_URL}/strategies/{strategy_id}
```

Cap at four legs; append `… +N more` if a future rebalance ever produces more (the current universe of `ETH/SOL/LINK/ADA` makes 4 the max in practice).

### Field extraction rules

| Field | Source |
|---|---|
| `title` | `<SIDE>` + `<pair>` for single-leg; `<strategy.name> — N orders` for multi-leg. |
| `notional_aud` | `tool_calls[i].args.notional_aud`. |
| `current_mid` | `app.state.trading_executor._books[pair].mid()` at notify time. If book is missing or stale (`age_seconds > 5`), omit the `@ ~$X` line rather than guess. |
| `allocation_after` | Recompute from `paper_positions_repo.get_all(strategy_id)` plus the leg's delta. Expressed as % of post-trade total notional. |
| `confidence` | Extract `<confidence>(high\|medium\|low)</confidence>` from `agent_decisions.agent_output`. Empty for deterministic strategies. Missing on an LLM strategy → "—". The tag contract is documented in `backend/agent/personas/trend-follower.md:85` and `mean-reverter.md:99`. |
| `click_url` | `{FRONTEND_URL}/strategies/{strategy_id}`. Uses the new `FRONTEND_URL` env var. |
| `tags` | `[side.lower(), pair.lower().replace("/", "_")]` for single-leg; `["rebalance"]` for multi-leg. ntfy auto-renders an emoji prefix for tags that match its [emoji-shortcode list](https://ntfy.sh/docs/publish/#tags-emojis); pick names from there (e.g. `chart_with_upwards_trend`, `chart_with_downwards_trend`, `arrows_counterclockwise`) during implementation if you want emoji on the lock screen. |

### Length budget

ntfy supports ~4KB bodies but iOS truncates the lock-screen preview around ~150 chars. The single-leg template fits inside that budget; the multi-leg template just fits with the 4-leg cap. We do *not* try to fit reasoning into the body — that's what the click-through to the dashboard is for.

## Configuration

| Env var | Example | Purpose |
|---|---|---|
| `NTFY_TOPIC` | `kr-tracker-7a3f2c9e8b1d4e5f6a7b8c9d0e1f2g3h` | The secret topic name. Generated with `secrets.token_urlsafe(24)`. Set once on Railway, never logged, added to the existing log-redaction list. |
| `NTFY_URL_BASE` | `https://ntfy.sh` | Defaults to public broker. Allows swap to a self-hosted instance without code change. |
| `FRONTEND_URL` | `https://<your-prod-domain>` | New. Used to build the `click` URL on the notification. If unset, notifications still send but without a tap-through link. |

### Phone-app setup (README addition)

1. Install the official ntfy app (search "ntfy" on the iOS App Store or Google Play; the app icon is a yellow speech bubble).
2. Tap `+` to add a subscription.
3. Paste the `NTFY_TOPIC` value from Railway env. Leave server at the default unless `NTFY_URL_BASE` was overridden.
4. (Optional but recommended) Enable iOS Critical Alerts for the ntfy app so DND doesn't suppress fills.

To enable a strategy:

```sql
UPDATE strategies SET notify_enabled = true WHERE name = '<your chosen strategy>';
```

(No UI surface in v1; you do this from the Supabase dashboard or via psql. A toggle on `StrategiesPage` is a possible v2 if you find yourself flipping it often, but YAGNI for now.)

## Failure handling

| Failure mode | Response |
|---|---|
| `httpx.TimeoutException` (5s) | Retry once after 1s backoff. If still failing, insert `system_alert(level=warning, code=PUSH_NOTIFY_FAILED, payload={"decision_id": ..., "error": "..."})` and continue. |
| Non-2xx HTTP response | Same as timeout — single retry, then alert. |
| `NTFY_TOPIC` unset at startup | Log one warning at startup (`"[Startup] NTFY_TOPIC unset — push notifications disabled"`). Subsequent `maybe_notify` calls return early without attempting POST or inserting alerts. |
| `decision_id` already has `notified_at != NULL` | Skip silently. Idempotency guard for retries from the strategy loop. |

The hook **never** raises into `write_agent_decision` or the strategy loop. Wrap the entire `maybe_notify` body in a top-level `try/except Exception` that logs and inserts a `system_alert` on truly unexpected errors.

## Security

- The ntfy topic name is the only auth. Anyone who knows it can both publish AND read. Generate via `secrets.token_urlsafe(24)`, store in Railway env, never commit to the repo, add to the existing log-redaction allowlist used by `backend/middleware/request_id.py` (or wherever log scrubbing lives).
- Notification body contains: pair, side, notional AUD, mid price, allocation %, confidence, strategy name. It does **not** contain: account balances, API keys, total portfolio value, AUD cash, position cost-basis, or any user-identifying string. Leak ceiling: "Ben's bot is interested in ETH right now." Tolerable.
- The `click` URL points at the existing frontend, which is already auth-gated by the JWT cookie. Tapping the notification on a device that isn't already logged in just shows the login screen — no bypass.
- No PII (`ben.clark12345@icloud.com`, account holder names, transaction descriptions from Up Bank) appears in any notification.

## Testing

| Test file | Coverage |
|---|---|
| `backend/tests/test_notification_service.py` (unit) | Title + body rendering for: single-leg buy, single-leg sell, multi-leg rebalance, missing-mid (book stale), missing-confidence tag, deterministic strategy (empty confidence). Uses `respx` to fake ntfy HTTP. |
| `backend/tests/test_decision_writer_notify.py` (integration) | (a) Writing an `agent_decisions` row when `notify_enabled=true` fires one POST. (b) `notify_enabled=false` fires zero POSTs. (c) Retry-failing transport still inserts the `agent_decisions` row and writes a `PUSH_NOTIFY_FAILED` `system_alert`. (d) Re-running the same `decision_id` is a no-op (`notified_at` idempotency). |
| `backend/tests/test_notify_e2e.py` (manual, gated) | End-to-end against the real ntfy public broker with a temporary topic. Marked `@pytest.mark.live`; not part of CI. |

No new eval-suite changes. Notifications are out-of-band from decision quality, and the existing `test_evals.py` golden set does not exercise the trading-sandbox boot.

## Future live mode (informational)

When the user later builds `LiveKrakenExecutor` for autonomous trading, the notification hook will *move* from the `write_agent_decision` seam (intent) to a new method on the executor that fires *after* a real Kraken fill is confirmed. The `NotificationService.send(...)` interface is unchanged — only the call site moves. Expected delta: ~10 lines, plus a small content tweak (title becomes `FILLED ETH/AUD — Trend-Follower @ $3451.20`).

This is mentioned for completeness; it is *not* in scope for this spec.

## Open questions for review

None. All decisions locked above. If anything in this spec contradicts your understanding from the brainstorm, flag it and the spec gets revised before the implementation plan is written.
