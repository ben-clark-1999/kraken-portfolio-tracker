## First-time setup

1. `cp .claude/settings.json.template .claude/settings.json`
2. Replace `<ABSOLUTE_PATH_TO_REPO>` with your local checkout path (twice).
3. Restart Claude Code so it picks up the MCP server config.

The backend itself derives all paths at runtime — no edits needed to Python code if the repo lives somewhere else.

## Agent eval harness

The agent's correctness is validated via a 35-query golden set graded along
three dimensions: classification accuracy, tool-use correctness, and
LLM-as-judge answer quality.

### Run the evals

```bash
backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s
```

This invokes the live agent graph against every golden-set query, hits real
LLM APIs, and prints a summary table. Cost: ~$1-2 per run at the default
model choice. Results are written to `backend/evals/results/<run-id>.json`.

### Cheap iteration mode

When tuning prompts, swap the judge to Haiku to cut cost ~5x:

```bash
EVAL_JUDGE_MODEL=claude-haiku-4-5 \
  backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s
```

### When to run

Before any PR that touches:

- Agent system prompts (`backend/agent/prompts.py`)
- Classifier configuration (`backend/agent/classifier.py`, `agent_config.py`)
- Agent graph routing (`backend/agent/graph.py`)
- MCP tool surface (`backend/mcp_server.py`)
- Eval golden set or judge prompts (`backend/evals/golden_set.yaml`,
  `backend/evals/prompts.py`)

Not on every commit — they hit live LLM APIs and aren't free. The pytest
`addopts = -m "not eval"` setting in `backend/pytest.ini` ensures default
runs skip the suite.

### Reading the report

```
EVAL RESULTS (run-id 1cf0bf9b, 2026-04-27T12:25:22.869240Z)
─────────────────────────────────────────────────────
Classification:    24/35  (69%)
Tool-use:          26/35  (74%)
Answer quality:    65/86 dimensions  (76%)

FAILURES:
  q011 [quick]  classification: expected=analysis got=quick (confidence=0.95)
  q022 [tax]    answer-quality cites_ato_rule: FAIL — mentions rule but
                doesn't cite the formal ATO provision name
```

When comparing against a prior run, deltas are shown:

```
Classification:    27/35  (77%)  ▲ baseline 69%
Tool-use:          35/35  (100%) ▲ baseline 74%
Answer quality:    70/86 dimensions (81%)  ▲ baseline 76%
```

▲/▼/= compare against the most recent prior run (the previous JSON in
`backend/evals/results/`). First run shows no deltas.

See `docs/eval-baseline.md` for the canonical first baseline.

## Phone push notifications

The backend optionally pushes a phone notification each time a strategy with `notify_enabled = true` emits a buy/sell decision. Delivery uses the free ntfy.sh public broker — no account, no per-notification cost.

### Setup

1. Install the official ntfy app (search "ntfy" on the iOS App Store or Google Play; icon is a yellow speech bubble).
2. Generate a topic name:
   ```bash
   backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(24))"
   ```
3. On Railway, set three env vars:
   - `NTFY_TOPIC` — the value from step 2.
   - `NTFY_URL_BASE` — leave as `https://ntfy.sh` unless self-hosting.
   - `FRONTEND_URL` — your deployed frontend origin (used for the tap-through link).
4. In the ntfy app, tap **+ → Subscribe to topic**, paste the same topic name, leave the server as default.

### Enabling a strategy

Notifications are off by default for every strategy. To enable one (via the Supabase SQL editor):

```sql
UPDATE strategies
   SET notify_enabled = true
 WHERE name = '<your strategy name>';
```

Switch back off the same way (`= false`). Only one strategy at a time is supported by design — flip the previous one off first.

### What's in the notification

For a single-leg decision: `BUY ETH/AUD — <strategy name>` with notional, mid price, allocation-after-trade, and (for LLM strategies) the confidence tag.

For a multi-leg decision (e.g. DCA rebalance): one notification listing up to four legs, with a `… +N more` indicator if a rebalance ever exceeds four. The notification is informational; you act on it manually on Kraken.

### Security note

The topic name is the only auth on ntfy — anyone who knows it can read or write. Don't share the value, don't commit it, and treat it like an API token. The notification body deliberately omits balances and total portfolio value; leak ceiling is "Ben's bot is interested in ETH right now."
