# Codebase Hardening Pass — Design Spec

## Overview

A focused, four-step refactor that addresses the six concrete weaknesses identified in the post-Phase-4 codebase review. The goal is "production discipline as if shippable, but staying single-user" — every architectural signal that says "this person knows what production code looks like," without spending engineering effort on multi-tenancy plumbing that adds nothing distinctive in an AI Solutions Engineering context.

The headline ending is a real LLM-as-judge eval harness for the agent. Steps 1–3 are foundation that makes step 4 buildable instead of theatrical.

---

## Goals

1. **Stop signalling amateur hour.** No hardcoded `/Users/benclark/...` paths. No dead code that hints at features that don't exist. No three-place edits to add an asset.
2. **Make failures honest.** When something breaks, the user sees a clean message and the operator gets a request-correlated server log. No `str(e)` leakage. No silent agent-loop terminations.
3. **Separate business logic from data access.** Services stop calling `get_supabase()` directly. A thin repository layer sits between them and the database, making the agent eval harness possible.
4. **Real correctness coverage on the agent.** A pytest-runnable eval harness with a 35-query golden set graded across classification, tool-use, and answer-quality dimensions — the answer-quality dimension scored by an LLM-as-judge.

## Non-goals

- **Multi-tenancy / deployment.** Stays single-user. Multi-user refactor is undifferentiated grunt work that adds nothing in an AI interview.
- **LangSmith / observability platform integration.** Planned Phase 5; separate effort. Step 2 adds standard `logging` telemetry only.
- **Functional improvements** (CGT simulator, notifications, broader asset universe). Stated next phase, separate spec.
- **Frontend test pyramid.** Step 4 adds targeted tests on `useAgentChat` and one WebSocket integration test only.
- **Strict error-code taxonomy.** Single-developer project; one generic `internal_error` code is sufficient.

---

## 1. Step 1 — Plumbing pass

**Goal:** stop signalling amateur hour. No behavior change visible to a user.

### 1.1 Auto-derive MCP subprocess paths

**Problem.** `backend/agent/tools.py:24-28` hardcodes `cwd="/Users/benclark/..."` and `command="backend/.venv/bin/python"`. `.claude/settings.json` is committed with absolute paths.

**Fix.**
- `MCP_SERVER_PARAMS.command = sys.executable` (already running inside the venv that needs to spawn the subprocess).
- `MCP_SERVER_PARAMS.cwd = Path(__file__).resolve().parents[2]`.
- `.claude/settings.json` → `.gitignore`. Commit `.claude/settings.json.template` with placeholder paths and a 3-line README setup note.

**Verify.** Backend boots, MCP subprocess spawns, agent answers a question. `mv` the repo elsewhere and re-run — still works without code changes.

### 1.2 Eliminate the `from backend.main import app` circular import

**Problem.** `backend/routers/agent.py` does function-body imports of the FastAPI app object to read `app.state.agent_graph`.

**Fix.** Pull the graph off the FastAPI request/connection object directly:
- REST handler `get_session_messages` adds `request: Request` parameter; reads `request.app.state.agent_graph`.
- WebSocket handler `agent_chat` reads `ws.app.state.agent_graph`.

**Verify.** `pytest` passes. Hit `/api/agent/sessions/<id>/messages` and the WebSocket end-to-end.

### 1.3 Delete dead code + fix one typo

**Targets:**
- `MCPToolManager.restart`, `_in_cooldown`, `_record_failure`, `_failure_times` field — never called from anywhere. The decision recorded by this deletion: MCP subprocess is trusted to stay alive while FastAPI does. Restart-on-crash is the operator's responsibility.
- `MCP_MAX_FAILURES`, `MCP_FAILURE_WINDOW_SECONDS`, `MCP_COOLDOWN_SECONDS` constants in `agent_config.py` — die with the methods.
- `formatToolName` no-op `.replace(/_/g, '_')` in `frontend/src/components/AgentToolStatus.tsx:8` — should be `' '`.

**Verify.** `pytest` passes. Tool status pill in browser renders `portfolio summary` (with space), not `portfolio_summary`.

### 1.4 Consolidate asset registry

**Problem.** Asset list is split across three backend structures (`ASSET_MAP`, `LEDGER_ASSET_TO_DISPLAY`, `BALANCE_KEY_TO_DISPLAY`) plus frontend `AllocationBar.COLORS`. Adding a new asset is a 3-file edit.

**Fix.**
- New `backend/config/assets.py` owns all three structures. `kraken_service.py` and `snapshot_service.py` import from it. `BALANCE_KEY_TO_DISPLAY` continues to be derived programmatically inside the new module (same logic, just relocated).
- New `frontend/src/utils/assetColors.ts` exports `getAssetColor(asset: string): string` with the four hex values + a gray fallback. `AllocationBar.tsx` calls it; local `COLORS` const deleted.

**Adding a new asset becomes:** edit `assets.py` (one entry), edit `assetColors.ts` (one entry).

**Verify.** `pytest` passes. Allocation bar renders unchanged.

### Step 1 task summary

| Task | Files touched | Commit |
|---|---|---|
| 1.1 Auto-derive MCP paths | `backend/agent/tools.py`, `.gitignore`, `.claude/settings.json.template`, `README.md` | `refactor(mcp): auto-derive subprocess paths, template settings.json` |
| 1.2 Drop circular import | `backend/routers/agent.py` | `refactor(routers): drop backend.main circular import in agent routes` |
| 1.3 Delete dead code | `backend/agent/tools.py`, `backend/agent/agent_config.py`, `frontend/src/components/AgentToolStatus.tsx` | `chore: remove unused MCP recovery scaffolding, fix tool name formatter` |
| 1.4 Consolidate asset registry | `backend/config/assets.py` (new), `backend/services/kraken_service.py`, `backend/services/snapshot_service.py`, `frontend/src/utils/assetColors.ts` (new), `frontend/src/components/AllocationBar.tsx` | `refactor(assets): consolidate asset registry to single backend + frontend source` |

---

## 2. Step 2 — Error contracts + reliability

**Goal:** when something breaks, the user sees a clean message and the operator gets enough server-side information to debug. No silent failures.

### 2.1 Global error handler + sanitized responses

**Problem.** Every router does `except Exception as e: raise HTTPException(502, str(e))`. Three things wrong: leaks Python exception text to the client, uses 502 for all failures (wrong semantics), most routers don't log the traceback so the server has *less* info than the client.

**Fix.**
- Register `@app.exception_handler(Exception)` in `backend/main.py`. Logs full traceback with `logger.exception`; returns `{"error_code": "internal_error", "request_id": "<uuid>"}` with HTTP 500.
- Request-ID middleware: every incoming request gets a UUID stored on `request.state.request_id`. Both the log line and the response body include it. Grep server logs by request ID when something is reported broken.
- Routers stop wrapping in `try/except Exception`. They retain specific catches when they want a different status (e.g., `KrakenServiceError` → 503 with safe message "Kraken upstream temporarily unavailable").
- Frontend `apiFetch` (`frontend/src/api/client.ts`) adds a generic 5xx branch that dispatches a new `SERVER_ERROR_EVENT` CustomEvent, mirroring the existing `UNAUTHORIZED_EVENT` pattern. Dashboard listens for it and renders a new top-of-page `ErrorBanner` component showing "Something went wrong. Please retry." with the request ID in small muted text and a Retry button. Banner auto-dismisses on next successful request.

**Error response shape:**
```json
{
  "error_code": "internal_error",
  "message": "Something went wrong. Please try again.",
  "request_id": "9b2c3d4e-..."
}
```

**Verify.** Force a Kraken API failure (bad key) → server log has full traceback + request ID; browser gets a clean banner with the same request ID; no Python text in the response body.

### 2.2 Agent loop telemetry + sanitized agent errors

**Problem.** Three silent-failure modes in the agent.

1. `_run_agent_loop` (`backend/agent/graph.py:88`) has `max_iterations = 5`. If hit, the loop exits silently and the user sees an incomplete answer.
2. `invoke_tool_with_timeout` returns `f"Error: Tool {tool.name} failed — {e}"` as a tool message — leaking exception text into the LLM context where it confuses downstream reasoning.
3. WebSocket `agent_chat_endpoint` catch-all sends `make_error("model", str(e))` to the client — same leak as the routers had.

**Fix.**

**Loop telemetry.** Per-iteration log line:
```
[Agent] thread=<id> iter=<n> tools=<comma-separated-names> path=<classifier_category>
```

**Max-iteration handling.** When hit, log `WARNING [Agent] thread=<id> max_iterations_exceeded` and inject a final `AIMessage` to the user: *"I needed more steps than I'm allowed for one turn — could you narrow the question?"*. User gets honest feedback instead of a truncated answer.

**Sanitized tool errors.** `invoke_tool_with_timeout` returns a generic "Tool failed: temporary upstream error, please retry" tool message. Real exception logged server-side with thread ID. The LLM sees a clean failure; the operator sees the truth.

**Server-side tool timing.** Move duration measurement out of the WebSocket handler (which currently times client-side from stream events) into `invoke_tool_with_timeout`. Emit structured log: `tool=<name> duration_ms=<n> success=<bool>`. WS continues to compute its own duration for UX, but server log is the source of truth.

**WS catch-all.** Sanitized the same way as the global handler.

**Verify.** Pose a pathological query that would hit max_iterations → user sees "narrow the question" message, server log shows the WARNING. Force a tool to throw → user sees clean "tool failed" line, server log has full traceback.

### Step 2 task summary

| Task | Files touched | Commit |
|---|---|---|
| 2.1 Global error handler | `backend/main.py`, `backend/routers/*.py`, `frontend/src/api/client.ts`, new ErrorBanner component | `refactor(errors): global exception handler with sanitized 5xx responses + request IDs` |
| 2.2 Agent loop telemetry | `backend/agent/graph.py`, `backend/agent/tools.py`, `backend/agent/websocket_handler.py` | `feat(agent): loop telemetry, max-iteration handling, sanitized tool errors` |

---

## 3. Step 3 — Repository layer

**Goal:** services stop knowing about Supabase. Business logic becomes testable without a live database — required for the eval harness in step 4.

### 3.1 Layering

**Today.** Services do inline data access:
```python
# sync_service.py
db = get_supabase()
result = db.table("lots").select("*").order("acquired_at", desc=False).execute()
return [Lot(**row) for row in result.data]
```

**After step 3.** Services call repository functions:
```python
# sync_service.py
from backend.repositories import lots_repo
return lots_repo.get_all()
```

### 3.2 Package structure

New `backend/repositories/` with four modules. Each module is a flat collection of pure functions (no classes, no abstract interfaces). Each function gets its Supabase client internally via `get_supabase()`.

**`lots_repo.py`** (consumed by `sync_service`, `portfolio_service`)
- `get_all() -> list[Lot]`
- `get_existing_trade_ids(trade_ids: list[str]) -> set[str]`
- `insert(rows: list[dict]) -> None`

**`snapshots_repo.py`** (consumed by `snapshot_service`)
- `get_all(from_dt, to_dt, schema="public") -> list[PortfolioSnapshot]`
- `get_nearest(target_dt, schema="public") -> PortfolioSnapshot | None`
- `get_oldest(schema="public") -> PortfolioSnapshot | None`
- `get_existing_dates(schema="public") -> set[str]`
- `insert(captured_at, total_value_aud, assets_json, schema="public") -> None`
- `delete_today(schema="public") -> None`
- `clear(schema="public") -> int`

**`sync_log_repo.py`** (consumed by `sync_service`)
- `get_last_synced_trade_id() -> str | None`
- `insert(last_trade_id, status, error_message=None) -> None`

**`ohlc_cache_repo.py`** (consumed by `portfolio_service`)
- `get_by_pair(pair) -> dict[str, float]`
- `upsert(rows: list[dict]) -> None`

### 3.3 Schema parameter migration

The leaky `schema: str = "public"` parameter currently threaded through `snapshot_service` functions migrates into `snapshots_repo`. Tests target `schema="test"` at the data-access layer, where the test/prod split belongs. Service-layer tests stop carrying schema concerns at all.

### 3.4 Out of scope

- **No abstract `Repository` base class.** YAGNI; we have one Supabase implementation and we'll keep it that way.
- **No swap to SQLAlchemy / SQLModel.** Supabase Python client is fine; the goal is layer separation, not ORM migration.
- **No write-through cache.** Single user; volume doesn't warrant it.

### 3.5 Test impact

- `test_kraken_service.py` is unaffected (no DB calls; only mocks `_get_user`).
- `test_portfolio_service.py` switches from mocking the Supabase chain to mocking `lots_repo.get_all` (one mock target instead of three chained calls). Tests get shorter and clearer.
- `test_sync_service.py` (currently exists as `test_upsert_lots.py`) — same simplification.
- New flat test files alongside existing ones: `backend/tests/test_lots_repo.py`, `test_snapshots_repo.py`, `test_sync_log_repo.py`, `test_ohlc_cache_repo.py` — integration tests against the real `test.*` schema, one file per repo, exercising the actual Supabase round-trip. Matches the existing flat `backend/tests/test_*.py` layout (no nested directories).

### Step 3 task summary

| Task | Files touched | Commit |
|---|---|---|
| 3.1 lots_repo + migrate sync_service consumers | `backend/repositories/lots_repo.py` (new), `backend/services/sync_service.py`, `backend/services/portfolio_service.py`, `backend/tests/test_lots_repo.py` (new), `backend/tests/test_upsert_lots.py` | `refactor(data): introduce lots_repo, migrate sync_service callers` |
| 3.2 snapshots_repo + migrate snapshot_service | `backend/repositories/snapshots_repo.py` (new), `backend/services/snapshot_service.py`, `backend/tests/test_snapshots_repo.py` (new), `backend/tests/test_snapshot_service.py` | `refactor(data): introduce snapshots_repo, move schema parameter into data layer` |
| 3.3 sync_log_repo + ohlc_cache_repo | `backend/repositories/sync_log_repo.py` (new), `backend/repositories/ohlc_cache_repo.py` (new), `backend/services/sync_service.py`, `backend/services/portfolio_service.py`, two new test files | `refactor(data): introduce sync_log_repo and ohlc_cache_repo, finish service-layer cleanup` |

---

## 4. Step 4 — Test depth + LLM-as-judge eval harness

**Goal:** real correctness coverage on the agent. After step 4, you can run `pytest -m eval` and get a graded report that catches prompt regressions, classification drift, and answer-quality issues before they ship.

### 4.1 Eval framework structure

```
backend/evals/
├── __init__.py
├── golden_set.yaml           # 35 graded queries across 5 paths
├── schema.py                 # Pydantic models: GoldenQuery, EvalResult, JudgeScore
├── runner.py                 # async run_evals(graph, dataset) -> list[EvalResult]
├── judges.py                 # classification_judge, tool_use_judge, answer_quality_judge
├── prompts.py                # LLM-as-judge prompt templates
└── results/                  # gitignored — historical run records
```

### 4.2 Golden set composition

**35 queries**, distribution mirroring real usage from the Phase 3 vision document:

| Path | Count | Examples |
|---|---|---|
| quick | 10 | "How much is my portfolio worth?", "When's my next buy?", "What do I hold right now?" |
| analysis | 8 | "How's ETH doing this month?", "Was last week good or bad for me?" |
| tax | 5 | "Which buys are almost old enough for the CGT discount?", "Anything I should think about before June 30?" |
| comparison | 5 | "Would I have been better off just holding ETH?", "Was DCA the right call?" |
| open | 4 | "What's changed since last week?", "Anything I should know?" |
| multi-turn | 3 sequences (2-3 turns each) | The phase 3 follow-up sequence: "How's ETH this month?" → "What about SOL?" → "Which one was a better buy?" |

**Each entry shape (in `golden_set.yaml`):**
```yaml
- id: q001
  query: "How much is my portfolio worth?"
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_portfolio_summary]
  forbidden_tools: [get_buy_and_hold_comparison, get_relative_performance]
  judge_dimensions:
    cites_aud_value: required          # answer must include actual AUD value
    cites_timestamp: required          # must say "as of <date/time>"
    no_filler_preamble: required       # no "let me check" etc.
    formatting_correct: required       # comma separators, AUD prefix
```

Multi-turn entries chain via `previous: q005` and assert state-carrying behavior:
```yaml
- id: q006
  query: "What about SOL?"
  previous: q005
  expected_classification: analysis
  judge_dimensions:
    carries_timeframe_from_previous: required
```

### 4.3 The three judges

**Classification judge — mechanical, no LLM.**
- Compares actual classifier output to expected.
- Pass: `actual.primary == expected_classification AND actual.confidence >= min_confidence`.
- Reports: pass/fail + actual values for failures.

**Tool-use judge — mechanical, no LLM.**
- Set logic on tool calls captured during the run.
- Pass: `set(expected_tools_any_of) ∩ actual_tools != ∅ AND set(forbidden_tools) ∩ actual_tools == ∅`.
- Reports: pass/fail + which forbidden tool fired or which expected tool was missed.

**Answer-quality judge — LLM-as-judge.** This is the headline piece.
- Model: `claude-sonnet-4-5-20241022` (same as the agent itself; configurable).
- Input: query, full agent answer, captured tool results, the per-query `judge_dimensions` rubric.
- Output: structured JSON via `with_structured_output(AnswerQualityScore)`:
  ```python
  class DimensionScore(BaseModel):
      dimension: str
      pass_: bool = Field(alias="pass")
      reasoning: str
  class AnswerQualityScore(BaseModel):
      scores: list[DimensionScore]
  ```
- Each dimension graded independently with a one-sentence reasoning. Aggregate score = `% of dimensions passing`.

**Multi-dimensional, not single-rubric, deliberately.** Single "is this answer good" judges produce mush. Independent dimensions catch specific regressions ("answers stopped citing dates" vs "answers got worse vibes").

### 4.4 LLM-as-judge prompt design

The judge prompt enforces structured reasoning:

```
You are evaluating a portfolio analyst's answer against specific quality
dimensions. For each dimension, decide PASS or FAIL based ONLY on the
criteria stated. Provide a one-sentence reason for each decision.

QUERY: {query}
TOOL RESULTS AVAILABLE TO THE ANSWER: {tool_results}
ANSWER: {answer}
DIMENSIONS TO SCORE:
{dimensions_with_criteria}

For each dimension, return a structured score. Be strict: if the answer
"sort of" satisfies a dimension, that's FAIL. Reasons must reference the
specific text in the answer.
```

Each dimension carries its own pass criteria, embedded in the prompt:
- `cites_aud_value` → "The answer must contain at least one AUD value with $ prefix and comma separators."
- `cites_timestamp` → "The answer must explicitly state when the data is from (date or relative phrasing like 'as of')."
- `no_filler_preamble` → "The answer must start with substantive content, not phrases like 'Let me check' or 'I'll look that up'."

The dimension catalogue lives in `backend/evals/prompts.py` so adding a new dimension is one place.

### 4.5 Runner output

`pytest -m eval` produces a summary table:

```
EVAL RESULTS (run-id 9b2c3d4e, 2026-04-27 14:32 AEST)
─────────────────────────────────────────────────────
Classification:    32/35  (91%)  ▲ baseline 88%
Tool-use:          34/35  (97%)  = baseline
Answer quality:    87/118 dimensions (74%)  ▼ baseline 78%

FAILURES:
  q014 [analysis]  classification: expected=analysis got=open conf=0.62
  q022 [tax]       answer-quality: cites_ato_rule FAIL — answer paraphrased
                   "12-month rule" but did not cite ATO
  ...
```

Results JSON written to `backend/evals/results/<run-id>.json` for over-time tracking. `results/` is gitignored (run records aren't repo artifacts).

**Baseline computation.** "Baseline" in the summary table = the most recent `results/*.json` file before the current run. The runner reads it on startup, computes deltas per metric, and renders ▲/▼/= indicators. If no prior results exist, baseline indicators are omitted. This keeps baseline tracking dead-simple — no separate baseline file to maintain, no opt-in flag, just "what was true last time you ran this."

### 4.6 Cost control

- ~35 queries × (classifier call + 1-3 agent reasoning calls + 1 LLM-judge call) ≈ 200-300 LLM calls per run.
- At Sonnet pricing, ~$1-2 per run.
- Run before agent-touching PRs only — not on every commit. Document in README.
- Optional cheaper iteration mode: `pytest -m eval --judge-model haiku` to use Haiku for the judge during prompt-tuning iterations.

### 4.7 Other tests in step 4

**WebSocket integration test** (`backend/tests/test_agent_chat_e2e.py`).
- FastAPI `TestClient` with `app.state.agent_graph` set to a stub graph (deterministic tool-call sequence, no real LLM).
- Connect, send `user_message`, assert exact sequence of `tool_start`, `tool_end`, `token`, `message_complete` events.
- Catches WebSocket-protocol regressions independent of LLM behaviour.

**Frontend `useAgentChat` hook test.**
- Add Vitest as devDependency (Vite-native, minimal config).
- Mock `WebSocket` (jsdom + manual stub). Drive fake server messages, assert React state transitions: thinking flips, tokens accumulate, HITL state appears, message_complete clears streaming flag.
- Single test file: `frontend/src/hooks/useAgentChat.test.ts`.

### Step 4 task summary

| Task | Files touched | Commit |
|---|---|---|
| 4.1 Eval framework + classification + tool-use judges + first 20 queries | `backend/evals/*` (all new), `backend/tests/test_evals.py` (new), `pytest.ini` mark registration | `feat(evals): eval framework with classification + tool-use judges, 20 golden queries` |
| 4.2 LLM-as-judge for answer quality + remaining 15 queries | `backend/evals/judges.py`, `backend/evals/prompts.py`, `backend/evals/golden_set.yaml` | `feat(evals): LLM-as-judge for answer quality, full 35-query golden set` |
| 4.3 WebSocket integration test + frontend useAgentChat tests | `backend/tests/test_agent_chat_e2e.py` (new), `frontend/package.json`, `frontend/vitest.config.ts` (new), `frontend/src/hooks/useAgentChat.test.ts` (new) | `test: WebSocket E2E + useAgentChat hook coverage` |
| 4.4 README + first baseline run | `README.md`, `docs/eval-baseline.md` (new) | `docs: eval harness usage + baseline run results` |

---

## 5. Verification / Definition of Done

The whole effort is "done" when all of the following are true:

1. **No path in the committed codebase contains `/Users/benclark/`.** `grep -r benclark` from project root returns nothing.
2. **`mv` the repo to a different directory and the backend boots, the MCP subprocess spawns, and the agent answers a question — without code changes.**
3. **Force any backend route to throw → server log has full traceback with request ID; browser shows a clean error banner with the same request ID; response body contains no Python text.**
4. **Force a tool to throw → user sees a clean failure message; agent reasoning continues with a sanitized tool message; server log has the full traceback.**
5. **A new test that needs portfolio data can be written without mocking `db.table().select().execute()` chains. It mocks the relevant repo function and runs in <100ms.**
6. **`pytest -m eval` runs end-to-end against the live agent, produces a summary table with classification / tool-use / answer-quality scores, and writes a JSON record to `backend/evals/results/`.**
7. **The `useAgentChat` hook has at least 5 unit tests covering: token accumulation, tool_start/tool_end transitions, hitl_request/respond cycle, message_complete clearing the streaming flag, error sanitization on the client.**

---

## 6. Decisions made (so we don't relitigate)

- **Single-user stays single-user.** No multi-tenancy.
- **No abstract repository base class.** Pure module-level functions.
- **Delete MCP recovery scaffolding** rather than wire it up. OS handles process restart.
- **Generic `internal_error` code only.** No taxonomy.
- **LLM-as-judge model is Sonnet by default**, with a `--judge-model haiku` flag for cheaper iteration.
- **Judges are multi-dimensional**, not single-rubric.
- **Eval harness runs on demand** (`pytest -m eval`), not on every commit.
- **Frontend tests scoped to `useAgentChat` only.** No broader test pyramid.
- **Schema parameter belongs in repos**, not services.
- **WebSocket integration test uses a stub graph**, not the real LLM, to keep it deterministic.
