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
