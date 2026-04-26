# Codebase Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address the six weaknesses surfaced in the post-Phase-4 review — hardcoded paths, dead code, leaky service layer, silent agent failures, scattered asset registry, no agent correctness coverage — in a four-step refactor. Single-user scope; no multi-tenancy.

**Architecture:** Foundation-first. Step 1 clears plumbing rocks. Step 2 tightens error contracts and adds agent-loop telemetry. Step 3 introduces a thin repository layer between services and Supabase. Step 4 builds a `pytest -m eval` harness with 35-query golden set graded by mechanical and LLM-as-judge dimensions.

**Tech Stack:** Python 3.12, FastAPI, supabase-py, LangGraph 1.x, langchain-anthropic, MCP SDK 1.27, React 19, Vite 8, Tailwind 3, Vitest (added in step 4), PyYAML (added in step 4), pytest with custom marker.

**Spec:** `docs/superpowers/specs/2026-04-27-codebase-hardening-design.md`

**User workflow:** push to `origin/main` after every task. The user reviews each commit on the GitHub web UI.

---

## File Structure

### Created
- `.claude/settings.json.template`
- `backend/config/__init__.py`, `backend/config/assets.py`
- `backend/repositories/__init__.py`, `backend/repositories/lots_repo.py`, `backend/repositories/snapshots_repo.py`, `backend/repositories/sync_log_repo.py`, `backend/repositories/ohlc_cache_repo.py`
- `backend/evals/__init__.py`, `backend/evals/schema.py`, `backend/evals/runner.py`, `backend/evals/judges.py`, `backend/evals/prompts.py`, `backend/evals/golden_set.yaml`, `backend/evals/results/.gitkeep`
- `backend/middleware/__init__.py`, `backend/middleware/request_id.py`
- `backend/error_handlers.py`
- `backend/tests/test_request_id.py`, `backend/tests/test_error_handler.py`, `backend/tests/test_lots_repo.py`, `backend/tests/test_snapshots_repo.py`, `backend/tests/test_sync_log_repo.py`, `backend/tests/test_ohlc_cache_repo.py`, `backend/tests/test_eval_judges.py`, `backend/tests/test_eval_runner.py`, `backend/tests/test_agent_chat_e2e.py`, `backend/tests/test_agent_loop_telemetry.py`
- `frontend/src/utils/assetColors.ts`, `frontend/src/components/ErrorBanner.tsx`, `frontend/src/hooks/useAgentChat.test.ts`
- `frontend/vitest.config.ts`
- `docs/eval-baseline.md`

### Modified
- `.gitignore`
- `README.md`
- `backend/main.py`, `backend/agent/tools.py`, `backend/agent/agent_config.py`, `backend/agent/graph.py`, `backend/agent/websocket_handler.py`
- `backend/routers/agent.py`, `backend/routers/portfolio.py`, `backend/routers/history.py`, `backend/routers/sync.py`
- `backend/services/kraken_service.py`, `backend/services/snapshot_service.py`, `backend/services/sync_service.py`, `backend/services/portfolio_service.py`
- `backend/tests/test_portfolio_service.py`, `backend/tests/test_upsert_lots.py`, `backend/tests/test_snapshot_service.py`, `backend/tests/test_mcp_server.py`
- `backend/requirements.txt`
- `backend/pytest.ini` (created if absent — register `eval` marker)
- `frontend/src/components/AgentToolStatus.tsx`, `frontend/src/components/AllocationBar.tsx`, `frontend/src/pages/Dashboard.tsx`, `frontend/src/api/client.ts`, `frontend/package.json`

### Deleted
- Lines 60–118 of `backend/agent/tools.py` (the unused MCP recovery scaffolding)
- Lines 50–52 of `backend/agent/agent_config.py` (the dead constants)

---

## STEP 1 — Plumbing pass

### Task 1.1: Auto-derive MCP subprocess paths

**Files:**
- Modify: `backend/agent/tools.py:24-28`
- Create: `.claude/settings.json.template`
- Modify: `.gitignore`
- Modify: `README.md` (or create if absent)
- Create: `backend/tests/test_mcp_paths.py`

**Why:** Currently `MCP_SERVER_PARAMS` hardcodes `/Users/benclark/...` and `backend/.venv/bin/python`. Anyone cloning the repo on a different machine breaks immediately. Auto-derive from `sys.executable` (we're already in the right venv when `tools.py` runs) and `Path(__file__).parents[2]` (project root relative to this file).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_mcp_paths.py`:
```python
"""Verify MCP subprocess params are derived from runtime, not hardcoded paths."""
import sys
from pathlib import Path

from backend.agent.tools import MCP_SERVER_PARAMS


def test_mcp_command_uses_current_python():
    assert MCP_SERVER_PARAMS.command == sys.executable


def test_mcp_cwd_is_project_root():
    expected = Path(__file__).resolve().parents[2]
    assert Path(MCP_SERVER_PARAMS.cwd) == expected


def test_mcp_cwd_is_absolute():
    """Stdio subprocess requires an absolute cwd."""
    assert Path(MCP_SERVER_PARAMS.cwd).is_absolute()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/pytest backend/tests/test_mcp_paths.py -v`

Expected: FAIL — `MCP_SERVER_PARAMS.command == "backend/.venv/bin/python"`, not `sys.executable`.

- [ ] **Step 3: Update `backend/agent/tools.py`**

Replace lines 24-28:
```python
import sys
from pathlib import Path

# Project root: backend/agent/tools.py → backend/agent → backend → project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

MCP_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "backend.mcp_server"],
    cwd=str(_PROJECT_ROOT),
)
```

(Keep the existing `import asyncio`, `import logging`, `import time` etc. above; just replace the `MCP_SERVER_PARAMS` block and add the `import sys` / `from pathlib import Path` / `_PROJECT_ROOT` lines.)

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_mcp_paths.py -v`

Expected: 3 PASS.

- [ ] **Step 5: Add `.claude/settings.json` to `.gitignore`**

Edit `.gitignore`, add line:
```
.claude/settings.json
```

(The existing `.gitignore` has `.env`, `.venv`, `**/__pycache__/`, `**/*.pyc`, `.superpowers/`. Add the new line at the end.)

- [ ] **Step 6: Create `.claude/settings.json.template`**

Create `.claude/settings.json.template`:
```json
{
  "mcpServers": {
    "kraken-portfolio": {
      "command": "<ABSOLUTE_PATH_TO_REPO>/backend/.venv/bin/python",
      "args": ["-m", "backend.mcp_server"],
      "cwd": "<ABSOLUTE_PATH_TO_REPO>"
    }
  }
}
```

- [ ] **Step 7: Add setup note to `README.md`**

If `README.md` doesn't exist, create it with this content. If it exists, append this section:

```markdown
## First-time setup

1. `cp .claude/settings.json.template .claude/settings.json`
2. Replace `<ABSOLUTE_PATH_TO_REPO>` with your local checkout path (twice).
3. Restart Claude Code so it picks up the MCP server config.

The backend itself derives all paths at runtime — no edits needed to Python code if the repo lives somewhere else.
```

- [ ] **Step 8: Manual smoke test**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/uvicorn backend.main:app --port 8000`

Open browser to dashboard, ask agent a question. Confirm: backend boots without error, agent answers normally, MCP subprocess spawns (check log line `[MCP] Started — N tools loaded`).

Stop the server with Ctrl-C.

- [ ] **Step 9: Commit and push**

Run:
```bash
git add backend/agent/tools.py backend/tests/test_mcp_paths.py .gitignore .claude/settings.json.template README.md
git commit -m "refactor(mcp): auto-derive subprocess paths, template settings.json"
git push origin main
```

---

### Task 1.2: Drop the `from backend.main import app` circular import

**Files:**
- Modify: `backend/routers/agent.py`

**Why:** Both routes in `agent.py` do function-body `from backend.main import app` to dodge a circular import — a workaround masking a layering problem. FastAPI exposes `request.app` on every connection. Use that instead.

- [ ] **Step 1: Read the current state**

Run: `cat backend/routers/agent.py`

Note the two function-body imports at lines 18 and 57.

- [ ] **Step 2: Update the REST handler signature**

Edit `backend/routers/agent.py`. Replace:
```python
@router.get("/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
async def get_session_messages(session_id: str):
    """Rehydrate conversation history from checkpoint.

    Called by the frontend on page reload or reconnect.
    """
    from backend.main import app

    graph = app.state.agent_graph
```

With:
```python
@router.get("/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
async def get_session_messages(session_id: str, request: Request):
    """Rehydrate conversation history from checkpoint.

    Called by the frontend on page reload or reconnect.
    """
    graph = request.app.state.agent_graph
```

Add `Request` to the imports at the top:
```python
from fastapi import APIRouter, Depends, Query, Request, WebSocket
```

- [ ] **Step 3: Update the WebSocket handler**

In the same file, replace:
```python
    from backend.agent.websocket_handler import agent_chat_endpoint
    from backend.main import app

    graph = app.state.agent_graph
    await agent_chat_endpoint(ws, graph, session_id)
```

With:
```python
    from backend.agent.websocket_handler import agent_chat_endpoint

    graph = ws.app.state.agent_graph
    await agent_chat_endpoint(ws, graph, session_id)
```

- [ ] **Step 4: Run the full test suite to verify nothing broke**

Run: `backend/.venv/bin/pytest backend/tests/ -v`

Expected: all tests pass (or the same set that passed before — there's a known pre-existing LINK failure in `test_get_prices_tool_default_assets`; that one is fixed in Task 4.1).

- [ ] **Step 5: Manual smoke test**

Run: `backend/.venv/bin/uvicorn backend.main:app --port 8000` in one terminal. In another:
```bash
curl -i http://localhost:8000/api/health
# Expected: 200 OK with {"status":"ok","agent":true}
```

Open the dashboard in browser, send the agent a question, verify response streams in. Stop the server.

- [ ] **Step 6: Commit and push**

```bash
git add backend/routers/agent.py
git commit -m "refactor(routers): drop backend.main circular import in agent routes"
git push origin main
```

---

### Task 1.3: Delete MCP recovery dead code + fix `formatToolName` typo

**Files:**
- Modify: `backend/agent/tools.py:60-118` (delete lines)
- Modify: `backend/agent/agent_config.py:50-52` (delete constants)
- Modify: `frontend/src/components/AgentToolStatus.tsx:8`

**Why:** `MCPToolManager.restart()`, `_in_cooldown()`, `_record_failure()` are never called from anywhere in the codebase. The cooldown constants in `agent_config.py` die with them. Also `formatToolName` does `.replace(/_/g, '_')` — a no-op; should be `' '`. Phase 3 memory flagged the typo; still in code. Deletion records the deliberate decision: MCP subprocess is trusted to stay alive while FastAPI does. Restart-on-crash is the operator's responsibility.

- [ ] **Step 1: Verify no caller of the doomed methods**

Run: `grep -rn "restart\|_in_cooldown\|_record_failure\|MCP_MAX_FAILURES\|MCP_FAILURE_WINDOW_SECONDS\|MCP_COOLDOWN_SECONDS" backend/ --include="*.py"`

Expected: only definitions in `backend/agent/tools.py` and `backend/agent/agent_config.py`. If anything else references them, stop and re-evaluate.

- [ ] **Step 2: Delete the methods + state from `MCPToolManager`**

In `backend/agent/tools.py`, in the `MCPToolManager` class:
- Delete the `_failure_times: list[float] = []` line from `__init__`.
- Delete the entire `_in_cooldown()` method.
- Delete the entire `_record_failure()` method.
- Delete the entire `restart()` method.

After this, `MCPToolManager` should only have: `__init__`, `tools` property, `start`, `stop`.

Also delete the now-unused imports if they're unused elsewhere in the file: `import time` (check via `grep "time\." backend/agent/tools.py` after the deletion — `time.time()` is no longer called).

- [ ] **Step 3: Delete the constants from `agent_config.py`**

In `backend/agent/agent_config.py`, delete lines 49-52:
```python
# ── MCP crash recovery ──────────────────────────────────────────────────
MCP_MAX_FAILURES = 3
MCP_FAILURE_WINDOW_SECONDS = 300  # 5 minutes
MCP_COOLDOWN_SECONDS = 300        # 5 minutes
```

Delete the section header comment too.

In `backend/agent/tools.py`, also remove these constants from the import block at the top:
```python
from backend.agent.agent_config import (
    MCP_COOLDOWN_SECONDS,
    MCP_FAILURE_WINDOW_SECONDS,
    MCP_MAX_FAILURES,
    MCP_RESPONSIVENESS_TIMEOUT,
    TOOL_SUBSETS,
    TOOL_TIMEOUT_SECONDS,
)
```

Becomes:
```python
from backend.agent.agent_config import (
    MCP_RESPONSIVENESS_TIMEOUT,
    TOOL_SUBSETS,
    TOOL_TIMEOUT_SECONDS,
)
```

- [ ] **Step 4: Fix `formatToolName` typo**

In `frontend/src/components/AgentToolStatus.tsx`, change line 8:
```typescript
function formatToolName(name: string): string {
  return name.replace(/^get_/, '').replace(/_/g, '_')  // OLD: no-op
}
```

To:
```typescript
function formatToolName(name: string): string {
  return name.replace(/^get_/, '').replace(/_/g, ' ')
}
```

- [ ] **Step 5: Run the full test suite**

Run: `backend/.venv/bin/pytest backend/tests/ -v`

Expected: same set as before passes. The deleted methods had no tests, so test count drops 0 (intended).

- [ ] **Step 6: Run the type check on the frontend**

Run: `cd frontend && ./node_modules/.bin/tsc -b`

Expected: zero errors. (The change in `AgentToolStatus.tsx` is just a string literal swap; no type implications.)

- [ ] **Step 7: Manual smoke test**

Run the dev server (`backend/.venv/bin/uvicorn backend.main:app --port 8000` and `cd frontend && npm run dev`), ask the agent a question that triggers a tool call. Confirm the in-flight tool pill renders `portfolio summary` (with space), not `portfolio_summary`.

- [ ] **Step 8: Commit and push**

```bash
git add backend/agent/tools.py backend/agent/agent_config.py frontend/src/components/AgentToolStatus.tsx
git commit -m "chore: remove unused MCP recovery scaffolding, fix tool name formatter"
git push origin main
```

---

### Task 1.4: Consolidate asset registry to one source

**Files:**
- Create: `backend/config/__init__.py`
- Create: `backend/config/assets.py`
- Modify: `backend/services/kraken_service.py:13-48` (remove asset definitions, import from new module)
- Modify: `backend/services/snapshot_service.py` (no functional change; just confirm `BALANCE_KEY_TO_DISPLAY` is imported via the new path)
- Create: `frontend/src/utils/assetColors.ts`
- Modify: `frontend/src/components/AllocationBar.tsx`

**Why:** Today, asset metadata lives in three structures in `kraken_service.py` (`ASSET_MAP`, `LEDGER_ASSET_TO_DISPLAY`, `BALANCE_KEY_TO_DISPLAY`) and a fourth in the frontend (`AllocationBar.COLORS`). Adding a new asset is a 3+ file edit. Consolidate so adding an asset is one entry in `assets.py` + one entry in `assetColors.ts`.

- [ ] **Step 1: Create `backend/config/__init__.py`**

Create empty file `backend/config/__init__.py`. (Marks the directory as a package.)

- [ ] **Step 2: Create `backend/config/assets.py`**

Create `backend/config/assets.py` with the canonical asset registry:
```python
"""Single source of truth for tracked assets.

Adding a new tracked asset = add one entry to ASSET_MAP and (optionally)
LEDGER_ASSET_TO_DISPLAY. BALANCE_KEY_TO_DISPLAY auto-derives.
"""

# Display name → spot/staked/bonded balance keys + AUD trading pair
ASSET_MAP: dict[str, dict] = {
    "ETH": {
        "keys": ["XETH", "ETH", "ETH.B", "ETH.S", "ETH2", "ETH2.S", "ETH.F"],
        "pair": "ETHAUD",
    },
    "SOL": {
        "keys": ["SOL", "SOL.S", "SOL.F", "SOL03.S"],
        "pair": "SOLAUD",
    },
    "ADA": {
        "keys": ["ADA", "ADA.S", "ADA.F"],
        "pair": "ADAAUD",
    },
    "LINK": {
        "keys": ["LINK", "LINK.S", "LINK.F"],
        "pair": "LINKAUD",
    },
}

# Ledger asset code → display name (used during trade reconstruction).
# The ledger uses native Kraken codes, e.g. XETH for ETH.
LEDGER_ASSET_TO_DISPLAY: dict[str, str] = {
    "XETH": "ETH",
    "SOL": "SOL",
    "ADA": "ADA",
    "LINK": "LINK",
}

# Auto-derived: every Kraken balance key → display name. Used for balance
# reconstruction across spot + staking variants.
BALANCE_KEY_TO_DISPLAY: dict[str, str] = {}
for _display_name, _info in ASSET_MAP.items():
    for _key in _info["keys"]:
        BALANCE_KEY_TO_DISPLAY[_key] = _display_name
for _key, _display_name in LEDGER_ASSET_TO_DISPLAY.items():
    BALANCE_KEY_TO_DISPLAY[_key] = _display_name
```

- [ ] **Step 3: Write a smoke test for the new module**

Create `backend/tests/test_assets_config.py`:
```python
"""Sanity-check the centralised asset registry."""
from backend.config.assets import ASSET_MAP, BALANCE_KEY_TO_DISPLAY, LEDGER_ASSET_TO_DISPLAY


def test_asset_map_has_eth_sol_ada_link():
    assert set(ASSET_MAP.keys()) == {"ETH", "SOL", "ADA", "LINK"}


def test_every_asset_has_pair_and_keys():
    for asset, info in ASSET_MAP.items():
        assert "pair" in info, f"{asset} missing pair"
        assert "keys" in info, f"{asset} missing keys"
        assert info["keys"], f"{asset} has empty keys list"
        assert info["pair"].endswith("AUD"), f"{asset} pair must be AUD-quoted"


def test_balance_key_to_display_covers_all_asset_map_keys():
    for asset, info in ASSET_MAP.items():
        for key in info["keys"]:
            assert BALANCE_KEY_TO_DISPLAY[key] == asset


def test_balance_key_to_display_covers_ledger_codes():
    for ledger_code, display in LEDGER_ASSET_TO_DISPLAY.items():
        assert BALANCE_KEY_TO_DISPLAY[ledger_code] == display
```

- [ ] **Step 4: Run the new test**

Run: `backend/.venv/bin/pytest backend/tests/test_assets_config.py -v`

Expected: 4 PASS.

- [ ] **Step 5: Migrate `kraken_service.py` to import from the new module**

In `backend/services/kraken_service.py`:
- Delete lines 13-48 (the three structures: `ASSET_MAP`, `LEDGER_ASSET_TO_DISPLAY`, `BALANCE_KEY_TO_DISPLAY` plus the building loop).
- Add at the top after existing imports:
  ```python
  from backend.config.assets import ASSET_MAP, BALANCE_KEY_TO_DISPLAY, LEDGER_ASSET_TO_DISPLAY
  ```

- [ ] **Step 6: Verify other consumers still work**

Run: `grep -rn "BALANCE_KEY_TO_DISPLAY\|LEDGER_ASSET_TO_DISPLAY\|ASSET_MAP" backend/ --include="*.py"`

Confirm: every reference outside `kraken_service.py` and `config/assets.py` either:
- Already imports from `kraken_service` (e.g., `snapshot_service.py` does `kraken_service.BALANCE_KEY_TO_DISPLAY`), which still works because `kraken_service` re-exports via its own import; or
- Imports directly from the new path.

No code changes needed in `snapshot_service.py` — `kraken_service.BALANCE_KEY_TO_DISPLAY` continues to resolve.

- [ ] **Step 7: Run the full test suite**

Run: `backend/.venv/bin/pytest backend/tests/ -v --ignore=backend/tests/test_mcp_server.py`

(Skip `test_mcp_server.py` for now — it has the known LINK pre-existing failure.)

Expected: all run tests pass.

- [ ] **Step 8: Create `frontend/src/utils/assetColors.ts`**

Create `frontend/src/utils/assetColors.ts`:
```typescript
/**
 * Single source of truth for asset display colors.
 * Adding a new asset = add one entry here.
 */

const COLORS: Record<string, string> = {
  ETH: '#627EEA',
  SOL: '#9945FF',
  ADA: '#06B6D4',
  LINK: '#2A5ADA',
}

const FALLBACK = '#5f5a70'

export function getAssetColor(asset: string): string {
  return COLORS[asset] ?? FALLBACK
}
```

- [ ] **Step 9: Update `AllocationBar.tsx` to use `getAssetColor`**

Edit `frontend/src/components/AllocationBar.tsx`:

Delete lines 8-13:
```typescript
const COLORS: Record<string, string> = {
  ETH: '#627EEA',
  SOL: '#9945FF',
  ADA: '#06B6D4',
}
const DEFAULT_COLOR = '#5f5a70'
```

Add at the top:
```typescript
import { getAssetColor } from '../utils/assetColors'
```

In the JSX, replace both occurrences of `COLORS[p.asset] ?? DEFAULT_COLOR` with `getAssetColor(p.asset)`.

- [ ] **Step 10: Type-check and visually verify the frontend**

Run: `cd frontend && ./node_modules/.bin/tsc -b`

Expected: zero errors.

Run: `cd frontend && npm run dev` — open dashboard in browser, confirm allocation bar renders the same colors as before. Stop the dev server.

- [ ] **Step 11: Commit and push**

```bash
git add backend/config/ backend/services/kraken_service.py backend/tests/test_assets_config.py frontend/src/utils/assetColors.ts frontend/src/components/AllocationBar.tsx
git commit -m "refactor(assets): consolidate asset registry to single backend + frontend source"
git push origin main
```

---

## STEP 2 — Error contracts + reliability

### Task 2.1: Global error handler + request-ID middleware + sanitized 5xx responses

**Files:**
- Create: `backend/middleware/__init__.py`
- Create: `backend/middleware/request_id.py`
- Create: `backend/error_handlers.py`
- Modify: `backend/main.py`
- Modify: `backend/routers/portfolio.py`, `backend/routers/history.py`, `backend/routers/sync.py`
- Create: `backend/tests/test_request_id.py`
- Create: `backend/tests/test_error_handler.py`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/components/ErrorBanner.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

**Why:** Today every router does `except Exception as e: raise HTTPException(502, str(e))` — leaks Python exception text to the client, uses 502 for everything, and most don't even log the traceback server-side. Replace with: (a) global exception handler that logs + sanitizes, (b) request-ID middleware so server logs and client errors can be correlated, (c) router cleanup that lets the global handler do its job, (d) frontend banner that surfaces 5xx without showing the raw payload.

- [ ] **Step 1: Create the request-ID middleware**

Create `backend/middleware/__init__.py` (empty file).

Create `backend/middleware/request_id.py`:
```python
"""Per-request UUID for log/response correlation."""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

- [ ] **Step 2: Write the failing test for request-ID middleware**

Create `backend/tests/test_request_id.py`:
```python
"""Verify every response gets an X-Request-ID header."""
import re

from fastapi.testclient import TestClient

from backend.main import app

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def test_health_response_has_request_id_header():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert UUID_PATTERN.match(response.headers["X-Request-ID"])


def test_each_request_gets_unique_id():
    client = TestClient(app)
    r1 = client.get("/api/health")
    r2 = client.get("/api/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_request_id.py -v`

Expected: FAIL — `X-Request-ID` header not present.

- [ ] **Step 4: Register the middleware in `main.py`**

In `backend/main.py`, add to the imports:
```python
from backend.middleware.request_id import RequestIDMiddleware
```

After the existing CORS middleware (after line 67), add:
```python
app.add_middleware(RequestIDMiddleware)
```

- [ ] **Step 5: Run the test again**

Run: `backend/.venv/bin/pytest backend/tests/test_request_id.py -v`

Expected: 2 PASS.

- [ ] **Step 6: Create the global error handler module**

Create `backend/error_handlers.py`:
```python
"""Global exception handler — logs traceback, returns sanitized JSON."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def handle_uncaught_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catch any uncaught exception, log traceback, return a sanitized 500.

    The response body never contains exception text. Operators correlate
    via the request_id which is stable across log line + response body +
    response header.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "[error] request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "internal_error",
            "message": "Something went wrong. Please try again.",
            "request_id": request_id,
        },
    )
```

- [ ] **Step 7: Write the failing test for the error handler**

Create `backend/tests/test_error_handler.py`:
```python
"""Verify uncaught exceptions return sanitized 500 with request_id."""
from fastapi import APIRouter
from fastapi.testclient import TestClient

from backend.main import app


# Inject a route that always throws — registered at module import time.
_test_router = APIRouter()


@_test_router.get("/api/__test_throw__")
async def _always_throws():
    raise RuntimeError("internal secret detail that must not leak")


app.include_router(_test_router)


def test_uncaught_exception_returns_sanitized_500():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/__test_throw__")
    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "internal_error"
    assert body["message"] == "Something went wrong. Please try again."
    assert "request_id" in body
    # Must NOT leak exception text:
    assert "internal secret detail" not in response.text
    assert "RuntimeError" not in response.text


def test_response_request_id_matches_header():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/__test_throw__")
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_error_handler.py -v`

Expected: FAIL — without the global handler, FastAPI returns 500 with default error body that leaks the exception text.

- [ ] **Step 9: Register the global error handler in `main.py`**

In `backend/main.py`, add to the imports:
```python
from backend.error_handlers import handle_uncaught_exception
```

After the `app.add_middleware(RequestIDMiddleware)` line, add:
```python
app.add_exception_handler(Exception, handle_uncaught_exception)
```

- [ ] **Step 10: Run the error handler test**

Run: `backend/.venv/bin/pytest backend/tests/test_error_handler.py -v`

Expected: 2 PASS.

- [ ] **Step 11: Strip generic try/except from the routers**

In `backend/routers/portfolio.py`, replace:
```python
@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary() -> PortfolioSummary:
    try:
        return portfolio_service.build_summary()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
```

With:
```python
@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary() -> PortfolioSummary:
    return portfolio_service.build_summary()
```

Remove `HTTPException` from the imports (no longer used).

In `backend/routers/history.py`, do the same for all three handlers (`get_snapshots`, `get_dca_history`, `backfill_snapshots`) — strip their generic `try/except Exception` blocks. Keep the function bodies.

In `backend/routers/sync.py`, the existing handler does `logger.exception` AND records the failure to `sync_log` AND raises HTTPException. Keep the `record_sync` call (it's domain logic, not error handling) but let the exception propagate to the global handler. Refactor:

```python
@router.post("")
async def trigger_sync() -> dict:
    last_trade_id = get_last_synced_trade_id()
    try:
        trades = kraken_service.get_trade_history(since_trade_id=last_trade_id)
        new_last_id = upsert_lots(trades)
        record_sync(last_trade_id=new_last_id or last_trade_id, status="success")
        return {"synced": len(trades), "last_trade_id": new_last_id}
    except Exception:
        # Persist failure in sync_log for the dashboard's audit trail, then
        # let the global handler return the sanitized 5xx.
        try:
            record_sync(last_trade_id=None, status="error", error_message="sync failed (see server logs)")
        except Exception:
            logger.exception("Failed to record sync error row")
        raise
```

(Note: `error_message` in `sync_log` is sanitized too — no `str(e)` written to the database. The full traceback goes to logs only.)

- [ ] **Step 12: Run the full test suite**

Run: `backend/.venv/bin/pytest backend/tests/ -v --ignore=backend/tests/test_mcp_server.py`

Expected: all run tests pass. Existing router tests should still work because the routes still raise on internal failure — they just raise the original exception now instead of wrapping it.

- [ ] **Step 13: Add `SERVER_ERROR_EVENT` to the frontend client**

In `frontend/src/api/client.ts`, replace the file with:
```typescript
/**
 * Shared fetch wrapper. Always sends cookies. Dispatches:
 *  - UNAUTHORIZED_EVENT on 401 (auth state machine listens)
 *  - SERVER_ERROR_EVENT on 5xx (Dashboard listens, renders ErrorBanner)
 */

export const UNAUTHORIZED_EVENT = 'auth:unauthorized'
export const SERVER_ERROR_EVENT = 'server:error'

export interface ServerErrorDetail {
  requestId: string
  status: number
}

export async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  } else if (response.status >= 500 && response.status < 600) {
    const detail: ServerErrorDetail = {
      requestId: response.headers.get('X-Request-ID') ?? 'unknown',
      status: response.status,
    }
    window.dispatchEvent(new CustomEvent<ServerErrorDetail>(SERVER_ERROR_EVENT, { detail }))
  }

  return response
}
```

- [ ] **Step 14: Create the `ErrorBanner` component**

Create `frontend/src/components/ErrorBanner.tsx`:
```typescript
import type { ServerErrorDetail } from '../api/client'

interface Props {
  detail: ServerErrorDetail
  onRetry: () => void
  onDismiss: () => void
}

export default function ErrorBanner({ detail, onRetry, onDismiss }: Props) {
  return (
    <div
      className="bg-loss/10 border-b border-loss/20 px-6 py-2 text-sm text-loss"
      role="alert"
      aria-live="polite"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <span>Something went wrong. Please retry.</span>
          <span className="text-xs text-txt-muted font-mono">
            req {detail.requestId.slice(0, 8)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRetry}
            className="px-3 py-1 bg-loss/20 hover:bg-loss/30 active:scale-[0.97] text-loss rounded text-xs font-medium transition-[colors,transform]"
          >
            Retry
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="text-xs text-txt-muted hover:text-txt-secondary transition-colors"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 15: Wire `Dashboard` to listen for `SERVER_ERROR_EVENT`**

In `frontend/src/pages/Dashboard.tsx`:

Add to imports:
```typescript
import { SERVER_ERROR_EVENT, type ServerErrorDetail } from '../api/client'
import ErrorBanner from '../components/ErrorBanner'
```

Inside the `Dashboard` component, after the existing `useState` calls, add:
```typescript
const [serverError, setServerError] = useState<ServerErrorDetail | null>(null)
```

Add a new `useEffect` next to the existing escape-key handler:
```typescript
useEffect(() => {
  function handleServerError(e: Event) {
    const detail = (e as CustomEvent<ServerErrorDetail>).detail
    setServerError(detail)
  }
  window.addEventListener(SERVER_ERROR_EVENT, handleServerError)
  return () => window.removeEventListener(SERVER_ERROR_EVENT, handleServerError)
}, [])
```

In the existing `refresh` callback, after the `setRefreshing(false)` line, add:
```typescript
// Successful refresh clears any banner from a previous failed call.
if (!summaryResult || summaryResult.status === 'fulfilled') {
  setServerError(null)
}
```

In the JSX, after the existing `{hasAnyError && hasAnyData && ...}` stale-data banner block, add:
```tsx
{serverError && (
  <ErrorBanner
    detail={serverError}
    onRetry={() => {
      setServerError(null)
      refresh()
    }}
    onDismiss={() => setServerError(null)}
  />
)}
```

- [ ] **Step 16: Type-check the frontend**

Run: `cd frontend && ./node_modules/.bin/tsc -b`

Expected: zero errors.

- [ ] **Step 17: Manual smoke test of the error path**

Start backend: `backend/.venv/bin/uvicorn backend.main:app --port 8000`. In the dashboard, trigger an error (e.g., temporarily break the Kraken API key in `.env`, refresh, then restore it).

Confirm:
- Banner appears with "Something went wrong. Please retry." + a request ID.
- Server log has the full traceback with the same request ID.
- Successful refresh dismisses the banner.

Restore the key, stop the server.

- [ ] **Step 18: Commit and push**

```bash
git add backend/middleware/ backend/error_handlers.py backend/main.py backend/routers/portfolio.py backend/routers/history.py backend/routers/sync.py backend/tests/test_request_id.py backend/tests/test_error_handler.py frontend/src/api/client.ts frontend/src/components/ErrorBanner.tsx frontend/src/pages/Dashboard.tsx
git commit -m "refactor(errors): global exception handler with sanitized 5xx responses + request IDs"
git push origin main
```

---

### Task 2.2: Agent loop telemetry + sanitized agent errors

**Files:**
- Modify: `backend/agent/graph.py`
- Modify: `backend/agent/tools.py`
- Modify: `backend/agent/websocket_handler.py`
- Create: `backend/tests/test_agent_loop_telemetry.py`

**Why:** Three silent-failure modes today — (1) `_run_agent_loop` exits silently if `max_iterations` is hit; (2) `invoke_tool_with_timeout` returns the raw exception text as a tool message that the LLM then sees in its context; (3) WS handler's catch-all sends `str(e)` to the client. Fix each.

- [ ] **Step 1: Write the failing test for max-iteration handling**

Create `backend/tests/test_agent_loop_telemetry.py`:
```python
"""Verify the agent loop handles max-iteration overrun honestly."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.agent.graph import _run_agent_loop


@pytest.mark.asyncio
async def test_max_iterations_injects_user_facing_message(monkeypatch):
    """When the loop hits its iteration cap, the agent must inject a final
    AIMessage explaining the situation rather than silently truncating."""

    # Fake model that always wants to call a tool — guarantees iteration cap is hit.
    fake_response = MagicMock(spec=AIMessage)
    fake_response.tool_calls = [{"name": "noop_tool", "args": {}, "id": "call_1"}]
    fake_response.content = ""

    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(return_value=fake_response)
    fake_model.bind_tools = MagicMock(return_value=fake_model)

    monkeypatch.setattr(
        "backend.agent.graph.ChatAnthropic",
        MagicMock(return_value=fake_model),
    )

    fake_tool = MagicMock()
    fake_tool.name = "noop_tool"
    fake_tool.ainvoke = AsyncMock(return_value="ok")

    state = {
        "messages": [HumanMessage(content="loop forever")],
        "classification": None,
    }
    config = {"configurable": {"thread_id": "test-thread"}}

    result = await _run_agent_loop(state, config, [fake_tool], "system prompt")

    # The final message should be the iteration-cap notice.
    last = result["messages"][-1]
    assert isinstance(last, AIMessage)
    assert "narrow" in last.content.lower() or "smaller" in last.content.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_agent_loop_telemetry.py -v`

Expected: FAIL — current implementation breaks out of the loop with no final message.

- [ ] **Step 3: Update `_run_agent_loop` in `backend/agent/graph.py`**

Replace the body of `_run_agent_loop` (currently lines 70-140) with the version below. The structural changes: per-iteration log line, max-iteration handling that injects a user-facing AIMessage, sanitized tool errors caught at this layer.

```python
async def _run_agent_loop(
    state: AgentState,
    config: RunnableConfig,
    tools: list[BaseTool],
    system_prompt: str,
    hitl_mode: str = "none",
) -> dict:
    """Shared ReAct loop for all agent nodes.

    hitl_mode:
      "none"       — never interrupt
      "all"        — interrupt before any tool call
      "selective"  — interrupt only for expensive tools (see _needs_hitl)
    """
    model = ChatAnthropic(model=AGENT_MODEL).bind_tools(tools)
    input_messages = [SystemMessage(content=system_prompt)] + list(state["messages"])

    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    classification = state.get("classification") or {}
    path = classification.get("primary_category", "unknown")

    max_iterations = 5
    hit_max = True

    for iteration in range(max_iterations):
        response = await model.ainvoke(input_messages, config=config)
        input_messages.append(response)

        tool_names = [tc["name"] for tc in (response.tool_calls or [])]
        logger.info(
            "[Agent] thread=%s iter=%d path=%s tools=%s",
            thread_id, iteration, path, ",".join(tool_names) or "<none>",
        )

        if not response.tool_calls:
            hit_max = False
            break

        broke_for_hitl = False
        for tc in response.tool_calls:
            tool_name = tc["name"]

            needs_hitl = hitl_mode == "all"
            if hitl_mode == "selective" and tool_name in HITL_TOOLS_GENERAL:
                if tool_name == "get_relative_performance":
                    tf = tc.get("args", {}).get("timeframe", "1M")
                    LONG_TIMEFRAMES = {"3M", "6M", "1Y", "ALL"}
                    needs_hitl = tf in LONG_TIMEFRAMES
                else:
                    needs_hitl = True

            if needs_hitl:
                approved = interrupt({
                    "tool": tool_name,
                    "params": tc["args"],
                    "reason": HITL_REASONS.get(tool_name, f"Execute {tool_name}"),
                    "estimated_duration_ms": HITL_DURATION_ESTIMATES.get(tool_name, 5000),
                })
                if not approved:
                    cancel = AIMessage(content="No problem — comparison cancelled.")
                    input_messages.append(cancel)
                    hit_max = False
                    broke_for_hitl = True
                    break

            tool = next((t for t in tools if t.name == tool_name), None)
            if tool is None:
                result = f"Error: Unknown tool {tool_name}"
            else:
                result = await invoke_tool_with_timeout(tool, tc["args"])

            input_messages.append(
                ToolMessage(content=result, tool_call_id=tc["id"])
            )

        if broke_for_hitl:
            break

    if hit_max:
        logger.warning(
            "[Agent] thread=%s max_iterations_exceeded path=%s",
            thread_id, path,
        )
        input_messages.append(AIMessage(content=(
            "I needed more steps than I'm allowed for one turn — could you "
            "narrow the question into a smaller piece?"
        )))

    original_count = 1 + len(state["messages"])
    return {"messages": input_messages[original_count:]}
```

- [ ] **Step 4: Run the max-iteration test**

Run: `backend/.venv/bin/pytest backend/tests/test_agent_loop_telemetry.py -v`

Expected: PASS.

- [ ] **Step 5: Add a sanitization test for `invoke_tool_with_timeout`**

Append to `backend/tests/test_agent_loop_telemetry.py`:
```python
import asyncio


@pytest.mark.asyncio
async def test_invoke_tool_with_timeout_sanitizes_exception():
    """Tool exceptions must not leak into the LLM context as raw Python text."""
    from backend.agent.tools import invoke_tool_with_timeout

    fake_tool = MagicMock()
    fake_tool.name = "broken_tool"
    fake_tool.ainvoke = AsyncMock(side_effect=ValueError("internal API key abc123 leaked"))

    result = await invoke_tool_with_timeout(fake_tool, {})

    assert "abc123" not in result
    assert "ValueError" not in result
    assert "broken_tool" in result  # tool name is fine to surface
    assert "fail" in result.lower() or "error" in result.lower()
```

- [ ] **Step 6: Run the sanitization test (expect failure)**

Run: `backend/.venv/bin/pytest backend/tests/test_agent_loop_telemetry.py::test_invoke_tool_with_timeout_sanitizes_exception -v`

Expected: FAIL — current implementation includes `str(e)` in the returned message.

- [ ] **Step 7: Sanitize `invoke_tool_with_timeout` in `backend/agent/tools.py`**

Replace the existing `invoke_tool_with_timeout` function with:
```python
async def invoke_tool_with_timeout(tool: BaseTool, args: dict) -> str:
    """Invoke a tool with a timeout. Returns sanitized error string on failure.

    Real exception detail logged server-side; tool message returned to the
    LLM is sanitized so internal text doesn't leak into the agent's reasoning
    context (or, downstream, into the user-facing answer).
    """
    start = time.time()
    try:
        result = await asyncio.wait_for(
            tool.ainvoke(args),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        duration_ms = int((time.time() - start) * 1000)
        logger.info(
            "[Tool] name=%s duration_ms=%d success=true", tool.name, duration_ms,
        )
        return str(result)
    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start) * 1000)
        logger.warning(
            "[Tool] name=%s duration_ms=%d success=false reason=timeout",
            tool.name, duration_ms,
        )
        return f"Tool {tool.name} timed out after {TOOL_TIMEOUT_SECONDS}s. Please retry."
    except Exception:
        duration_ms = int((time.time() - start) * 1000)
        logger.exception(
            "[Tool] name=%s duration_ms=%d success=false reason=exception",
            tool.name, duration_ms,
        )
        return f"Tool {tool.name} failed with a temporary upstream error. Please retry."
```

(`time` was removed in Task 1.3; re-add `import time` at the top of `tools.py`.)

- [ ] **Step 8: Run the sanitization test**

Run: `backend/.venv/bin/pytest backend/tests/test_agent_loop_telemetry.py -v`

Expected: 2 PASS.

- [ ] **Step 9: Sanitize the WebSocket catch-all**

In `backend/agent/websocket_handler.py`, find the `_stream_graph_response` function. Replace:
```python
    except Exception as e:
        logger.exception("[WS] Error during graph streaming")
        await ws.send_json(make_error("model", str(e)))
        return
```

With:
```python
    except Exception:
        logger.exception("[WS] Error during graph streaming")
        await ws.send_json(make_error(
            "model",
            "The agent ran into an internal error. Please try again.",
        ))
        return
```

- [ ] **Step 10: Run the full test suite**

Run: `backend/.venv/bin/pytest backend/tests/ -v --ignore=backend/tests/test_mcp_server.py`

Expected: all run tests pass.

- [ ] **Step 11: Manual smoke test**

Start backend + frontend. In the dashboard, ask the agent something benign (e.g., "How much is my portfolio worth?"). Confirm the per-iteration log line appears in the backend log stream:
```
[Agent] thread=<uuid> iter=0 path=quick tools=get_portfolio_summary
[Tool] name=get_portfolio_summary duration_ms=234 success=true
```

Stop the dev servers.

- [ ] **Step 12: Commit and push**

```bash
git add backend/agent/graph.py backend/agent/tools.py backend/agent/websocket_handler.py backend/tests/test_agent_loop_telemetry.py
git commit -m "feat(agent): loop telemetry, max-iteration handling, sanitized tool errors"
git push origin main
```

---

## STEP 3 — Repository layer

### Task 3.1: Introduce `lots_repo` and migrate `sync_service` callers

**Files:**
- Create: `backend/repositories/__init__.py`
- Create: `backend/repositories/lots_repo.py`
- Create: `backend/tests/test_lots_repo.py`
- Modify: `backend/services/sync_service.py`
- Modify: `backend/services/portfolio_service.py:189-203` (only the `sync_service.get_all_lots()` call site, no logic change)
- Modify: `backend/tests/test_upsert_lots.py`

**Why:** `sync_service` directly does `db.table("lots").select(...).execute()`. Extract those calls to a flat-functions repo module. Service-layer tests stop having to mock the supabase-py call chain.

- [ ] **Step 1: Create the repositories package**

Create `backend/repositories/__init__.py` (empty file).

- [ ] **Step 2: Write the failing repo integration test**

Create `backend/tests/test_lots_repo.py`:
```python
"""Integration test: lots_repo against the real test schema."""
import pytest

from backend.db.supabase_client import get_supabase
from backend.repositories import lots_repo


# These tests use the test schema — see conftest.py:clean_test_tables.
pytestmark = pytest.mark.usefixtures("clean_test_tables")


def _row(trade_id: str, asset: str = "ETH", qty: str = "0.1") -> dict:
    return {
        "asset": asset,
        "acquired_at": "2026-04-01T10:00:00+10:00",
        "quantity": qty,
        "cost_aud": "100.00",
        "cost_per_unit_aud": str(float(qty) * 100),  # not realistic, fine for test
        "kraken_trade_id": trade_id,
        "remaining_quantity": qty,
    }


def test_get_all_returns_empty_when_no_lots(test_db):
    # Use the test schema: insert via test_db, read via lots_repo with schema override
    result = lots_repo.get_all(schema="test")
    assert result == []


def test_insert_then_get_all_round_trip(test_db):
    lots_repo.insert([_row("T1"), _row("T2")], schema="test")
    result = lots_repo.get_all(schema="test")
    assert len(result) == 2
    trade_ids = {l.kraken_trade_id for l in result}
    assert trade_ids == {"T1", "T2"}


def test_get_existing_trade_ids_filters_correctly(test_db):
    lots_repo.insert([_row("T1"), _row("T2")], schema="test")
    existing = lots_repo.get_existing_trade_ids(["T1", "T3", "T4"], schema="test")
    assert existing == {"T1"}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_lots_repo.py -v`

Expected: FAIL — `backend.repositories.lots_repo` does not exist.

- [ ] **Step 4: Create `backend/repositories/lots_repo.py`**

Create `backend/repositories/lots_repo.py`:
```python
"""Data access for the `lots` table.

All Supabase concerns live here. Service layer stays free of `db.table().*`
chains.
"""

from backend.db.supabase_client import get_supabase
from backend.models.trade import Lot


def get_all(schema: str = "public") -> list[Lot]:
    """Return all lots, oldest first."""
    db = get_supabase()
    result = (
        db.schema(schema)
        .table("lots")
        .select("*")
        .order("acquired_at", desc=False)
        .execute()
    )
    return [Lot(**row) for row in result.data]


def get_existing_trade_ids(trade_ids: list[str], schema: str = "public") -> set[str]:
    """Given a list of candidate trade IDs, return the subset that already exist."""
    if not trade_ids:
        return set()
    db = get_supabase()
    result = (
        db.schema(schema)
        .table("lots")
        .select("kraken_trade_id")
        .in_("kraken_trade_id", trade_ids)
        .execute()
    )
    return {row["kraken_trade_id"] for row in result.data}


def insert(rows: list[dict], schema: str = "public") -> None:
    """Insert lot rows. Caller is responsible for filtering duplicates."""
    if not rows:
        return
    db = get_supabase()
    db.schema(schema).table("lots").insert(rows).execute()
```

- [ ] **Step 5: Run the repo test**

Run: `backend/.venv/bin/pytest backend/tests/test_lots_repo.py -v`

Expected: 3 PASS.

- [ ] **Step 6: Migrate `sync_service.upsert_lots` and `sync_service.get_all_lots`**

In `backend/services/sync_service.py`:

Replace the existing `get_all_lots` function with:
```python
def get_all_lots() -> list[Lot]:
    """Returns all lots from Supabase ordered oldest first.

    Thin wrapper kept for backward compatibility with existing call sites
    (router and MCP tool). New code should call lots_repo.get_all() directly.
    """
    from backend.repositories import lots_repo
    return lots_repo.get_all()
```

Replace `upsert_lots` with:
```python
def upsert_lots(trades: list[dict]) -> str | None:
    """
    Converts raw trade dicts into lot rows and inserts only trades not already
    in the database.

    Returns the trade_id of the first trade in the input (most recent),
    or None if trades is empty.
    """
    if not trades:
        return None

    from backend.repositories import lots_repo

    trade_ids = [t["trade_id"] for t in trades]
    existing_ids = lots_repo.get_existing_trade_ids(trade_ids)

    new_trades = [t for t in trades if t["trade_id"] not in existing_ids]
    if new_trades:
        rows = []
        for trade in new_trades:
            acquired_at = to_iso(unix_to_aest(trade["time"]))
            quantity = Decimal(trade["vol"])
            cost_per_unit = Decimal(trade["price"])
            cost_aud = Decimal(trade["cost"])
            rows.append({
                "asset": trade["asset"],
                "acquired_at": acquired_at,
                "quantity": str(quantity),
                "cost_aud": str(cost_aud),
                "cost_per_unit_aud": str(cost_per_unit),
                "kraken_trade_id": trade["trade_id"],
                "remaining_quantity": str(quantity),
            })
        lots_repo.insert(rows)

    return trades[0]["trade_id"]
```

Leave the `from backend.db.supabase_client import get_supabase` import in place — `get_last_synced_trade_id` and `record_sync` still use it. Task 3.3 will migrate those two and remove the import.

- [ ] **Step 7: Update `test_upsert_lots.py` to mock the repo, not Supabase**

Open `backend/tests/test_upsert_lots.py` and read its existing structure. Replace any `monkeypatch.setattr` calls that target `db.table` chains with mocks of `lots_repo.get_existing_trade_ids` and `lots_repo.insert`. The conceptual switch: instead of mocking three chained method calls on a fake Supabase client, mock two repo functions.

Concretely, anywhere the test does something like:
```python
fake_db = MagicMock()
fake_db.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []
monkeypatch.setattr("backend.services.sync_service.get_supabase", lambda: fake_db)
```

Replace with:
```python
monkeypatch.setattr(
    "backend.repositories.lots_repo.get_existing_trade_ids",
    lambda trade_ids, schema="public": set(),
)
inserted = []
monkeypatch.setattr(
    "backend.repositories.lots_repo.insert",
    lambda rows, schema="public": inserted.extend(rows),
)
```

(Adapt to the specific assertions in the existing test file.)

- [ ] **Step 8: Run the full test suite**

Run: `backend/.venv/bin/pytest backend/tests/ -v --ignore=backend/tests/test_mcp_server.py`

Expected: all run tests pass, including the updated `test_upsert_lots.py`.

- [ ] **Step 9: Manual smoke test of the sync flow**

Start the backend. Hit:
```bash
curl -X POST http://localhost:8000/api/sync -b "auth_token=<your-cookie>"
```

(Or click the sync button in the dashboard if there is one.) Confirm: response is `{"synced": <n>, "last_trade_id": "..."}`. Backend log shows no errors. Re-run — second call returns `{"synced": 0, ...}` (idempotent).

- [ ] **Step 10: Commit and push**

```bash
git add backend/repositories/__init__.py backend/repositories/lots_repo.py backend/services/sync_service.py backend/tests/test_lots_repo.py backend/tests/test_upsert_lots.py
git commit -m "refactor(data): introduce lots_repo, migrate sync_service callers"
git push origin main
```

---

### Task 3.2: Introduce `snapshots_repo` and migrate `snapshot_service`

**Files:**
- Create: `backend/repositories/snapshots_repo.py`
- Create: `backend/tests/test_snapshots_repo.py`
- Modify: `backend/services/snapshot_service.py`
- Modify: `backend/tests/test_snapshot_service.py`

**Why:** `snapshot_service` is the largest direct-Supabase consumer in the codebase (8 distinct queries). It also threads the `schema: str = "public"` parameter through every function — that test/prod split belongs in the data layer. Move it.

- [ ] **Step 1: Write the failing repo test**

Create `backend/tests/test_snapshots_repo.py`:
```python
"""Integration test: snapshots_repo against the real test schema."""
from datetime import datetime

import pytest

from backend.repositories import snapshots_repo


pytestmark = pytest.mark.usefixtures("clean_test_tables")


def _insert_snapshot(captured_at: str, total: float, schema: str = "test") -> None:
    snapshots_repo.insert(
        captured_at=captured_at,
        total_value_aud=total,
        assets_json={"ETH": {"quantity": 1.0, "value_aud": total, "price_aud": total}},
        schema=schema,
    )


def test_get_all_returns_empty_initially():
    assert snapshots_repo.get_all(from_dt=None, to_dt=None, schema="test") == []


def test_insert_then_get_all_round_trip():
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    _insert_snapshot("2026-04-02T10:00:00+10:00", 1100.0)
    result = snapshots_repo.get_all(from_dt=None, to_dt=None, schema="test")
    assert len(result) == 2
    assert result[0].total_value_aud == 1000.0
    assert result[1].total_value_aud == 1100.0


def test_get_oldest_returns_earliest():
    _insert_snapshot("2026-04-02T10:00:00+10:00", 1100.0)
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    oldest = snapshots_repo.get_oldest(schema="test")
    assert oldest is not None
    assert oldest.total_value_aud == 1000.0


def test_get_oldest_returns_none_when_empty():
    assert snapshots_repo.get_oldest(schema="test") is None


def test_get_existing_dates_returns_yyyy_mm_dd_set():
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    _insert_snapshot("2026-04-02T10:00:00+10:00", 1100.0)
    dates = snapshots_repo.get_existing_dates(schema="test")
    assert dates == {"2026-04-01", "2026-04-02"}


def test_clear_deletes_all_returns_count():
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    _insert_snapshot("2026-04-02T10:00:00+10:00", 1100.0)
    n = snapshots_repo.clear(schema="test")
    assert n == 2
    assert snapshots_repo.get_all(from_dt=None, to_dt=None, schema="test") == []


def test_get_nearest_picks_closest_neighbor():
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    _insert_snapshot("2026-04-10T10:00:00+10:00", 1500.0)
    nearest = snapshots_repo.get_nearest("2026-04-04T10:00:00+10:00", schema="test")
    assert nearest is not None
    assert nearest.total_value_aud == 1000.0  # 3 days vs 6 days → April 1 wins
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_snapshots_repo.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Create `backend/repositories/snapshots_repo.py`**

Create with the same logic that currently lives in `snapshot_service`, but parameterised on schema and stripped of business logic:
```python
"""Data access for the `portfolio_snapshots` table."""

from datetime import datetime, timedelta, timezone

from backend.db.supabase_client import get_supabase
from backend.models.snapshot import PortfolioSnapshot, SnapshotAsset


def _parse_snapshot_row(row: dict) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        id=row["id"],
        captured_at=row["captured_at"],
        total_value_aud=float(row["total_value_aud"]),
        assets={asset: SnapshotAsset(**data) for asset, data in row["assets"].items()},
    )


def get_all(
    from_dt: str | None,
    to_dt: str | None,
    schema: str = "public",
) -> list[PortfolioSnapshot]:
    db = get_supabase()
    query = (
        db.schema(schema)
        .table("portfolio_snapshots")
        .select("*")
        .order("captured_at", desc=False)
    )
    if from_dt:
        query = query.gte("captured_at", from_dt)
    if to_dt:
        query = query.lte("captured_at", to_dt)
    return [_parse_snapshot_row(row) for row in query.execute().data]


def get_nearest(target_dt: str, schema: str = "public") -> PortfolioSnapshot | None:
    db = get_supabase()
    after = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*").gte("captured_at", target_dt)
        .order("captured_at", desc=False).limit(1).execute()
    )
    before = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*").lt("captured_at", target_dt)
        .order("captured_at", desc=True).limit(1).execute()
    )
    candidates = []
    if after.data:
        candidates.append(after.data[0])
    if before.data:
        candidates.append(before.data[0])
    if not candidates:
        return None
    target = datetime.fromisoformat(target_dt)
    closest = min(
        candidates,
        key=lambda r: abs((datetime.fromisoformat(r["captured_at"]) - target).total_seconds()),
    )
    return _parse_snapshot_row(closest)


def get_oldest(schema: str = "public") -> PortfolioSnapshot | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*").order("captured_at", desc=False).limit(1).execute()
    )
    if result.data:
        return _parse_snapshot_row(result.data[0])
    return None


def get_existing_dates(schema: str = "public") -> set[str]:
    db = get_supabase()
    result = db.schema(schema).table("portfolio_snapshots").select("captured_at").execute()
    return {row["captured_at"][:10] for row in result.data}


def insert(
    captured_at: str,
    total_value_aud: float,
    assets_json: dict,
    schema: str = "public",
) -> None:
    db = get_supabase()
    db.schema(schema).table("portfolio_snapshots").insert({
        "captured_at": captured_at,
        "total_value_aud": total_value_aud,
        "assets": assets_json,
    }).execute()


def delete_today(schema: str = "public") -> None:
    """Delete all snapshots from today's UTC date.

    Used by save_snapshot to prevent duplicate rows on server restart.
    """
    db = get_supabase()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(tz=timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    db.schema(schema).table("portfolio_snapshots") \
        .delete() \
        .gte("captured_at", f"{today}T00:00:00+00:00") \
        .lt("captured_at", f"{tomorrow}T00:00:00+00:00") \
        .execute()


def clear(schema: str = "public") -> int:
    db = get_supabase()
    result = db.schema(schema).table("portfolio_snapshots") \
        .delete() \
        .gte("captured_at", "1970-01-01T00:00:00+00:00") \
        .execute()
    return len(result.data)
```

- [ ] **Step 4: Run the repo test**

Run: `backend/.venv/bin/pytest backend/tests/test_snapshots_repo.py -v`

Expected: 7 PASS.

- [ ] **Step 5: Migrate `snapshot_service.py`**

Rewrite `backend/services/snapshot_service.py` so it does NO direct Supabase access. The service keeps only orchestration logic (`save_snapshot`, `backfill_from_ledger`):

```python
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.models.portfolio import PortfolioSummary
from backend.models.snapshot import PortfolioSnapshot
from backend.repositories import snapshots_repo

logger = logging.getLogger(__name__)


def save_snapshot(summary: PortfolioSummary, schema: str = "public") -> None:
    """Save a live snapshot, replacing any existing snapshot from today."""
    snapshots_repo.delete_today(schema=schema)
    assets_json = {
        pos.asset: {
            "quantity": pos.quantity,
            "value_aud": pos.value_aud,
            "price_aud": pos.price_aud,
        }
        for pos in summary.positions
    }
    snapshots_repo.insert(
        captured_at=summary.captured_at,
        total_value_aud=summary.total_value_aud,
        assets_json=assets_json,
        schema=schema,
    )


# Re-export the read functions through the service for callers that already
# import them from snapshot_service. New code should import snapshots_repo directly.
get_snapshots = snapshots_repo.get_all
get_nearest_snapshot = snapshots_repo.get_nearest
get_oldest_snapshot = snapshots_repo.get_oldest
clear_snapshots = snapshots_repo.clear


def backfill_from_ledger(schema: str = "public") -> int:
    """Reconstruct daily portfolio snapshots from Kraken ledger + OHLC prices."""
    from backend.services import kraken_service

    entries = kraken_service.get_all_ledger_entries()
    if not entries:
        logger.info("Backfill: no ledger entries found — nothing to do")
        return 0

    logger.info("Backfill: fetched %d ledger entries", len(entries))

    running: dict[str, Decimal] = defaultdict(Decimal)
    daily_balances: dict[str, dict[str, Decimal]] = {}

    for entry in entries:
        asset_code = entry.get("asset", "")
        display = kraken_service.BALANCE_KEY_TO_DISPLAY.get(asset_code)
        if not display:
            continue
        running[display] += Decimal(str(entry["amount"]))
        ts = float(entry["time"])
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        daily_balances[date_str] = {k: v for k, v in running.items() if v > 0}

    if not daily_balances:
        logger.info("Backfill: no tracked-asset ledger entries — nothing to do")
        return 0

    sorted_ledger_dates = sorted(daily_balances.keys())
    logger.info(
        "Backfill: ledger activity spans %s to %s (%d days with activity)",
        sorted_ledger_dates[0], sorted_ledger_dates[-1], len(sorted_ledger_dates),
    )

    start = datetime.strptime(sorted_ledger_dates[0], "%Y-%m-%d").date()
    yesterday = datetime.now(tz=timezone.utc).date() - timedelta(days=1)
    if start > yesterday:
        logger.info("Backfill: all ledger activity is from today — nothing to backfill")
        return 0

    filled: dict[str, dict[str, Decimal]] = {}
    prev: dict[str, Decimal] = {}
    current = start
    while current <= yesterday:
        ds = current.strftime("%Y-%m-%d")
        if ds in daily_balances:
            prev = daily_balances[ds]
        filled[ds] = dict(prev)
        current += timedelta(days=1)

    all_assets: set[str] = set()
    for balances in filled.values():
        all_assets.update(balances.keys())

    ohlc: dict[str, dict[str, float]] = {}
    for asset in sorted(all_assets):
        pair = kraken_service.ASSET_MAP.get(asset, {}).get("pair")
        if not pair:
            continue
        try:
            ohlc[asset] = kraken_service.get_ohlc_daily(pair)
        except kraken_service.KrakenServiceError as e:
            logger.warning("Backfill: OHLC %s (%s) failed: %s", asset, pair, e)
            ohlc[asset] = {}

    existing = snapshots_repo.get_existing_dates(schema=schema)
    count = 0
    skipped_existing = 0
    skipped_no_price = 0

    for date_str in sorted(filled.keys()):
        if date_str in existing:
            skipped_existing += 1
            continue
        balances = filled[date_str]
        total = 0.0
        assets_json: dict[str, dict] = {}
        has_price = False
        for asset, balance in balances.items():
            bal = float(balance)
            if bal <= 0:
                continue
            price = ohlc.get(asset, {}).get(date_str, 0.0)
            if price > 0:
                has_price = True
            value = bal * price
            total += value
            assets_json[asset] = {
                "quantity": round(bal, 8),
                "value_aud": round(value, 2),
                "price_aud": round(price, 2),
            }
        if not has_price or total <= 0:
            skipped_no_price += 1
            continue
        snapshots_repo.insert(
            captured_at=f"{date_str}T00:00:00+00:00",
            total_value_aud=round(total, 2),
            assets_json=assets_json,
            schema=schema,
        )
        count += 1

    logger.info(
        "Backfill complete: %d created, %d skipped (existing), %d skipped (no price)",
        count, skipped_existing, skipped_no_price,
    )
    return count
```

- [ ] **Step 6: Update `test_snapshot_service.py` to mock the repo**

Open the file. Wherever it currently mocks Supabase calls (likely via `monkeypatch.setattr("backend.services.snapshot_service.get_supabase", ...)` or similar), switch to mocking the repo:
```python
monkeypatch.setattr("backend.repositories.snapshots_repo.insert", lambda **kw: None)
monkeypatch.setattr("backend.repositories.snapshots_repo.get_existing_dates", lambda schema="public": set())
```

Adapt to the specific assertions in the file.

- [ ] **Step 7: Run the full test suite**

Run: `backend/.venv/bin/pytest backend/tests/ -v --ignore=backend/tests/test_mcp_server.py`

Expected: all pass.

- [ ] **Step 8: Manual smoke test**

Start the backend. Hit `GET /api/history/snapshots?from_dt=2026-04-01T00:00:00+10:00`. Confirm a JSON array of snapshots returns. Trigger an hourly snapshot path by calling `POST /api/history/backfill?clear=false`. Backend log shows the backfill summary line.

- [ ] **Step 9: Commit and push**

```bash
git add backend/repositories/snapshots_repo.py backend/services/snapshot_service.py backend/tests/test_snapshots_repo.py backend/tests/test_snapshot_service.py
git commit -m "refactor(data): introduce snapshots_repo, move schema parameter into data layer"
git push origin main
```

---

### Task 3.3: Introduce `sync_log_repo` + `ohlc_cache_repo`, finish service-layer cleanup

**Files:**
- Create: `backend/repositories/sync_log_repo.py`
- Create: `backend/repositories/ohlc_cache_repo.py`
- Create: `backend/tests/test_sync_log_repo.py`
- Create: `backend/tests/test_ohlc_cache_repo.py`
- Modify: `backend/services/sync_service.py` (remove remaining `get_supabase()` calls)
- Modify: `backend/services/portfolio_service.py:302-315` (the `get_ohlc_cached` function)

**Why:** `sync_service.get_last_synced_trade_id` and `record_sync` still call `get_supabase()` directly. Same with `portfolio_service.get_ohlc_cached`. Move them to repos so the service layer is finally Supabase-free.

- [ ] **Step 1: Write the failing test for `sync_log_repo`**

Create `backend/tests/test_sync_log_repo.py`:
```python
"""Integration test: sync_log_repo against the real test schema."""
import pytest

from backend.repositories import sync_log_repo


pytestmark = pytest.mark.usefixtures("clean_test_tables")


def test_get_last_synced_returns_none_when_empty():
    assert sync_log_repo.get_last_synced_trade_id(schema="test") is None


def test_insert_success_then_get_returns_trade_id():
    sync_log_repo.insert(last_trade_id="T1", status="success", schema="test")
    assert sync_log_repo.get_last_synced_trade_id(schema="test") == "T1"


def test_get_last_synced_skips_error_rows():
    sync_log_repo.insert(last_trade_id="T1", status="success", schema="test")
    sync_log_repo.insert(last_trade_id=None, status="error", error_message="boom", schema="test")
    assert sync_log_repo.get_last_synced_trade_id(schema="test") == "T1"


def test_get_last_synced_returns_most_recent_success():
    sync_log_repo.insert(last_trade_id="T1", status="success", schema="test")
    sync_log_repo.insert(last_trade_id="T2", status="success", schema="test")
    assert sync_log_repo.get_last_synced_trade_id(schema="test") == "T2"
```

- [ ] **Step 2: Run the test (expect failure)**

Run: `backend/.venv/bin/pytest backend/tests/test_sync_log_repo.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Create `backend/repositories/sync_log_repo.py`**

```python
"""Data access for the `sync_log` table."""

from backend.db.supabase_client import get_supabase


def get_last_synced_trade_id(schema: str = "public") -> str | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("sync_log")
        .select("last_trade_id")
        .eq("status", "success")
        .order("synced_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data
    if rows and rows[0]["last_trade_id"]:
        return rows[0]["last_trade_id"]
    return None


def insert(
    last_trade_id: str | None,
    status: str,
    error_message: str | None = None,
    schema: str = "public",
) -> None:
    db = get_supabase()
    db.schema(schema).table("sync_log").insert({
        "last_trade_id": last_trade_id,
        "status": status,
        "error_message": error_message,
    }).execute()
```

- [ ] **Step 4: Run the test**

Run: `backend/.venv/bin/pytest backend/tests/test_sync_log_repo.py -v`

Expected: 4 PASS.

- [ ] **Step 5: Write the failing test for `ohlc_cache_repo`**

Create `backend/tests/test_ohlc_cache_repo.py`:
```python
"""Integration test: ohlc_cache_repo against the real test schema."""
import pytest

from backend.repositories import ohlc_cache_repo


pytestmark = pytest.mark.usefixtures("clean_test_tables")


def test_get_by_pair_returns_empty_dict_when_empty():
    assert ohlc_cache_repo.get_by_pair("ETHAUD", schema="test") == {}


def test_upsert_then_read_round_trip():
    rows = [
        {"pair": "ETHAUD", "date": "2026-04-01", "close_price": 4000.0},
        {"pair": "ETHAUD", "date": "2026-04-02", "close_price": 4100.0},
    ]
    ohlc_cache_repo.upsert(rows, schema="test")
    result = ohlc_cache_repo.get_by_pair("ETHAUD", schema="test")
    assert result == {"2026-04-01": 4000.0, "2026-04-02": 4100.0}


def test_get_by_pair_filters_by_pair():
    ohlc_cache_repo.upsert(
        [
            {"pair": "ETHAUD", "date": "2026-04-01", "close_price": 4000.0},
            {"pair": "SOLAUD", "date": "2026-04-01", "close_price": 200.0},
        ],
        schema="test",
    )
    assert ohlc_cache_repo.get_by_pair("ETHAUD", schema="test") == {"2026-04-01": 4000.0}
    assert ohlc_cache_repo.get_by_pair("SOLAUD", schema="test") == {"2026-04-01": 200.0}
```

- [ ] **Step 6: Run the test (expect failure)**

Run: `backend/.venv/bin/pytest backend/tests/test_ohlc_cache_repo.py -v`

Expected: FAIL.

- [ ] **Step 7: Create `backend/repositories/ohlc_cache_repo.py`**

```python
"""Data access for the `ohlc_cache` table."""

from backend.db.supabase_client import get_supabase


def get_by_pair(pair: str, schema: str = "public") -> dict[str, float]:
    db = get_supabase()
    result = (
        db.schema(schema).table("ohlc_cache")
        .select("date, close_price")
        .eq("pair", pair)
        .execute()
    )
    return {row["date"]: float(row["close_price"]) for row in result.data}


def upsert(rows: list[dict], schema: str = "public") -> None:
    if not rows:
        return
    db = get_supabase()
    db.schema(schema).table("ohlc_cache").upsert(rows, on_conflict="pair,date").execute()
```

- [ ] **Step 8: Run the test**

Run: `backend/.venv/bin/pytest backend/tests/test_ohlc_cache_repo.py -v`

Expected: 3 PASS.

- [ ] **Step 9: Migrate `sync_service` final calls to use the repo**

In `backend/services/sync_service.py`:

Replace:
```python
from backend.db.supabase_client import get_supabase
```

(at the top) with no import — `sync_service` no longer needs Supabase.

Replace `get_last_synced_trade_id` with:
```python
def get_last_synced_trade_id() -> str | None:
    from backend.repositories import sync_log_repo
    return sync_log_repo.get_last_synced_trade_id()
```

Replace `record_sync` with:
```python
def record_sync(last_trade_id: str | None, status: str, error_message: str | None = None) -> None:
    from backend.repositories import sync_log_repo
    sync_log_repo.insert(last_trade_id=last_trade_id, status=status, error_message=error_message)
```

Confirm there are no remaining direct uses of `get_supabase` in the file.

- [ ] **Step 10: Migrate `portfolio_service.get_ohlc_cached` to the repo**

In `backend/services/portfolio_service.py`, replace `get_ohlc_cached`:
```python
def get_ohlc_cached(pair: str) -> dict[str, float]:
    """Get daily OHLC close prices, caching to avoid redundant Kraken calls."""
    from backend.repositories import ohlc_cache_repo

    cached = ohlc_cache_repo.get_by_pair(pair)
    if cached:
        return cached

    prices = kraken_service.get_ohlc_daily(pair)
    if prices:
        rows = [{"pair": pair, "date": d, "close_price": p} for d, p in prices.items()]
        ohlc_cache_repo.upsert(rows)
    return prices
```

Remove the `from backend.db.supabase_client import get_supabase` import — `portfolio_service` no longer needs Supabase.

- [ ] **Step 11: Verify no service file imports `get_supabase`**

Run: `grep -n "get_supabase" backend/services/*.py`

Expected: zero matches. (If `kraken_service` still references it, that's fine — `kraken_service.py` is not a database service.)

- [ ] **Step 12: Run the full test suite**

Run: `backend/.venv/bin/pytest backend/tests/ -v --ignore=backend/tests/test_mcp_server.py`

Expected: all pass.

- [ ] **Step 13: Manual smoke test**

Start the backend. Trigger a buy-and-hold comparison via the agent (this exercises `portfolio_service.get_ohlc_cached` → `ohlc_cache_repo`). Trigger a sync (exercises `sync_log_repo`). All should work.

- [ ] **Step 14: Commit and push**

```bash
git add backend/repositories/sync_log_repo.py backend/repositories/ohlc_cache_repo.py backend/services/sync_service.py backend/services/portfolio_service.py backend/tests/test_sync_log_repo.py backend/tests/test_ohlc_cache_repo.py
git commit -m "refactor(data): introduce sync_log_repo and ohlc_cache_repo, finish service-layer cleanup"
git push origin main
```

---

## STEP 4 — Test depth + LLM-as-judge eval harness

### Task 4.1: Eval framework + classification + tool-use judges + first 20 queries

**Files:**
- Modify: `backend/requirements.txt` (add `pyyaml`)
- Create: `backend/pytest.ini` (register `eval` marker)
- Create: `backend/evals/__init__.py`
- Create: `backend/evals/schema.py`
- Create: `backend/evals/runner.py`
- Create: `backend/evals/judges.py`
- Create: `backend/evals/golden_set.yaml` (with 20 queries)
- Create: `backend/evals/results/.gitkeep`
- Modify: `.gitignore` (ignore `backend/evals/results/*.json`)
- Create: `backend/tests/test_eval_judges.py`
- Create: `backend/tests/test_eval_runner.py`
- Modify: `backend/tests/test_mcp_server.py` (fix the LINK pre-existing test failure)

**Why:** Build the eval framework skeleton with the two mechanical judges (no LLM) and 20 queries. Validates the infrastructure end-to-end before adding the LLM-as-judge piece in Task 4.2. Also fixes the long-standing LINK test failure since we're touching that area.

- [ ] **Step 1: Add pyyaml to requirements**

Edit `backend/requirements.txt`. Add a new line:
```
pyyaml==6.0.2
```

Run: `backend/.venv/bin/pip install pyyaml==6.0.2`

- [ ] **Step 2: Create pytest marker registration**

Create `backend/pytest.ini`:
```ini
[pytest]
markers =
    eval: agent eval suite — opt-in via `pytest -m eval`. Hits live LLM APIs.
asyncio_mode = auto
```

(If `pytest.ini` exists already at the project root, edit to add the `eval` marker entry.)

- [ ] **Step 3: Create the evals package skeleton**

Create `backend/evals/__init__.py` (empty file).
Create `backend/evals/results/.gitkeep` (empty file — keeps the directory tracked).

Edit `.gitignore`, add line:
```
backend/evals/results/*.json
```

- [ ] **Step 4: Create the eval schema**

Create `backend/evals/schema.py`:
```python
"""Pydantic schema for golden-set entries and eval results."""

from pydantic import BaseModel, Field


class JudgeDimension(BaseModel):
    """A single graded dimension for the answer-quality judge."""
    name: str
    criterion: str = Field(
        description="Human-readable pass criterion. Embedded in the judge prompt."
    )


class GoldenQuery(BaseModel):
    id: str
    query: str
    expected_classification: str | None = None
    min_confidence: float | None = None
    expected_tools_any_of: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    judge_dimensions: list[str] = Field(
        default_factory=list,
        description="Names of dimensions to apply (looked up in DIMENSION_CATALOGUE).",
    )
    previous: str | None = Field(
        default=None,
        description="ID of a prior query in the same session, for multi-turn tests.",
    )


class DimensionScore(BaseModel):
    name: str
    passed: bool
    reasoning: str


class QueryResult(BaseModel):
    id: str
    query: str
    actual_classification: str | None
    actual_confidence: float | None
    actual_tools: list[str]
    actual_answer: str
    classification_pass: bool | None
    classification_reason: str | None = None
    tool_use_pass: bool
    tool_use_reason: str | None = None
    answer_quality_scores: list[DimensionScore] = Field(default_factory=list)
    error: str | None = None


class EvalRun(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    results: list[QueryResult]

    @property
    def classification_pass_rate(self) -> float:
        rated = [r for r in self.results if r.classification_pass is not None]
        if not rated:
            return 0.0
        return sum(1 for r in rated if r.classification_pass) / len(rated)

    @property
    def tool_use_pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.tool_use_pass) / len(self.results)

    @property
    def answer_quality_pass_rate(self) -> float:
        all_dim_scores = [s for r in self.results for s in r.answer_quality_scores]
        if not all_dim_scores:
            return 0.0
        return sum(1 for s in all_dim_scores if s.passed) / len(all_dim_scores)
```

- [ ] **Step 5: Write the failing tests for the mechanical judges**

Create `backend/tests/test_eval_judges.py`:
```python
"""Unit tests for the mechanical (non-LLM) judges."""
from backend.evals.judges import judge_classification, judge_tool_use
from backend.evals.schema import GoldenQuery


def test_classification_pass_when_match_and_confident():
    query = GoldenQuery(
        id="q1", query="...", expected_classification="quick", min_confidence=0.8,
    )
    passed, reason = judge_classification(
        query, actual_classification="quick", actual_confidence=0.92,
    )
    assert passed is True


def test_classification_fail_on_wrong_category():
    query = GoldenQuery(
        id="q1", query="...", expected_classification="quick", min_confidence=0.8,
    )
    passed, reason = judge_classification(
        query, actual_classification="analysis", actual_confidence=0.92,
    )
    assert passed is False
    assert "expected=quick" in reason


def test_classification_fail_on_low_confidence():
    query = GoldenQuery(
        id="q1", query="...", expected_classification="quick", min_confidence=0.8,
    )
    passed, reason = judge_classification(
        query, actual_classification="quick", actual_confidence=0.6,
    )
    assert passed is False
    assert "confidence" in reason


def test_classification_skipped_when_no_expected():
    query = GoldenQuery(id="q1", query="...")
    passed, reason = judge_classification(
        query, actual_classification="quick", actual_confidence=0.6,
    )
    assert passed is None  # Not graded


def test_tool_use_pass_when_expected_called_and_no_forbidden():
    query = GoldenQuery(
        id="q1", query="...",
        expected_tools_any_of=["get_portfolio_summary"],
        forbidden_tools=["get_buy_and_hold_comparison"],
    )
    passed, reason = judge_tool_use(query, actual_tools=["get_portfolio_summary"])
    assert passed is True


def test_tool_use_fail_when_expected_missing():
    query = GoldenQuery(
        id="q1", query="...",
        expected_tools_any_of=["get_portfolio_summary"],
    )
    passed, reason = judge_tool_use(query, actual_tools=["get_balances"])
    assert passed is False
    assert "expected" in reason.lower()


def test_tool_use_fail_when_forbidden_called():
    query = GoldenQuery(
        id="q1", query="...",
        expected_tools_any_of=["get_portfolio_summary"],
        forbidden_tools=["get_buy_and_hold_comparison"],
    )
    passed, reason = judge_tool_use(
        query, actual_tools=["get_portfolio_summary", "get_buy_and_hold_comparison"],
    )
    assert passed is False
    assert "forbidden" in reason.lower()


def test_tool_use_pass_when_no_expectations_set():
    query = GoldenQuery(id="q1", query="...")
    passed, reason = judge_tool_use(query, actual_tools=["anything"])
    assert passed is True
```

- [ ] **Step 6: Run the tests (expect failure)**

Run: `backend/.venv/bin/pytest backend/tests/test_eval_judges.py -v`

Expected: FAIL — `backend.evals.judges` doesn't exist.

- [ ] **Step 7: Create `backend/evals/judges.py` with the mechanical judges**

Create `backend/evals/judges.py`:
```python
"""Eval judges. Mechanical judges live here; LLM-as-judge added in Task 4.2."""

from backend.evals.schema import GoldenQuery


def judge_classification(
    query: GoldenQuery,
    actual_classification: str | None,
    actual_confidence: float | None,
) -> tuple[bool | None, str | None]:
    """Pass if actual matches expected and confidence >= min_confidence.

    Returns (None, None) when the query has no classification expectation —
    that query simply isn't graded on this dimension.
    """
    if query.expected_classification is None:
        return None, None
    if actual_classification != query.expected_classification:
        return False, (
            f"expected={query.expected_classification} got={actual_classification} "
            f"(confidence={actual_confidence})"
        )
    if query.min_confidence is not None:
        if actual_confidence is None or actual_confidence < query.min_confidence:
            return False, (
                f"confidence too low: got={actual_confidence} min={query.min_confidence}"
            )
    return True, None


def judge_tool_use(
    query: GoldenQuery,
    actual_tools: list[str],
) -> tuple[bool, str | None]:
    """Pass when expected tools (any_of) were called and no forbidden tools fired."""
    actual_set = set(actual_tools)
    forbidden = set(query.forbidden_tools)
    forbidden_hit = actual_set & forbidden
    if forbidden_hit:
        return False, f"forbidden tool(s) called: {sorted(forbidden_hit)}"
    if query.expected_tools_any_of:
        expected = set(query.expected_tools_any_of)
        if not (actual_set & expected):
            return False, f"expected at least one of {sorted(expected)}, got {sorted(actual_set)}"
    return True, None
```

- [ ] **Step 8: Run the tests**

Run: `backend/.venv/bin/pytest backend/tests/test_eval_judges.py -v`

Expected: 8 PASS.

- [ ] **Step 9: Create the runner**

Create `backend/evals/runner.py`:
```python
"""Eval runner — invoke the agent graph against each golden-set entry, capture
classification + tools + answer, hand off to judges.
"""

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage

from backend.evals.judges import judge_classification, judge_tool_use
from backend.evals.schema import EvalRun, GoldenQuery, QueryResult

logger = logging.getLogger(__name__)


def load_golden_set(path: Path | None = None) -> list[GoldenQuery]:
    """Load and validate the golden_set.yaml file."""
    if path is None:
        path = Path(__file__).parent / "golden_set.yaml"
    with open(path) as f:
        raw = yaml.safe_load(f)
    return [GoldenQuery(**entry) for entry in raw]


async def _run_single(graph, query: GoldenQuery, prior_thread_id: str | None) -> QueryResult:
    """Invoke the graph on one query, capture the four observable outputs."""
    if query.previous and prior_thread_id is None:
        raise ValueError(f"Query {query.id} requires previous={query.previous} but no thread provided")

    thread_id = prior_thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    actual_classification = None
    actual_confidence = None
    actual_tools: list[str] = []
    actual_answer_parts: list[str] = []
    error_str: str | None = None

    try:
        async for mode, data in graph.astream(
            {"messages": [HumanMessage(content=query.query)]},
            config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                for node_name, update in data.items():
                    if node_name == "classify_query" and update.get("classification"):
                        cls = update["classification"]
                        actual_classification = cls.get("primary_category")
                        actual_confidence = cls.get("confidence")
            elif mode == "messages":
                chunk, _meta = data
                if isinstance(chunk, AIMessage) and chunk.content:
                    actual_answer_parts.append(str(chunk.content))
                if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        actual_tools.append(tc["name"])
    except Exception as e:
        error_str = str(e)
        logger.exception("[Eval] query %s failed", query.id)

    actual_answer = "".join(actual_answer_parts).strip()

    cls_pass, cls_reason = judge_classification(
        query, actual_classification, actual_confidence,
    )
    tool_pass, tool_reason = judge_tool_use(query, actual_tools)

    return QueryResult(
        id=query.id,
        query=query.query,
        actual_classification=actual_classification,
        actual_confidence=actual_confidence,
        actual_tools=actual_tools,
        actual_answer=actual_answer,
        classification_pass=cls_pass,
        classification_reason=cls_reason,
        tool_use_pass=tool_pass,
        tool_use_reason=tool_reason,
        error=error_str,
    )


async def run_evals(graph, queries: list[GoldenQuery]) -> EvalRun:
    """Run every query, return an EvalRun. Handles multi-turn linkage."""
    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.utcnow().isoformat() + "Z"

    results: list[QueryResult] = []
    # Map query_id → thread_id so multi-turn continuations re-use the session.
    thread_for: dict[str, str] = {}

    for query in queries:
        prior_thread = thread_for.get(query.previous) if query.previous else None
        thread_id = prior_thread or str(uuid.uuid4())
        thread_for[query.id] = thread_id

        result = await _run_single(graph, query, thread_id if query.previous else None)
        results.append(result)

    finished_at = datetime.utcnow().isoformat() + "Z"
    return EvalRun(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        results=results,
    )


def render_summary(run: EvalRun, baseline: EvalRun | None = None) -> str:
    """Pretty summary table for stdout."""
    lines = [
        f"EVAL RESULTS (run-id {run.run_id}, {run.finished_at})",
        "─" * 53,
    ]

    def _delta(current: float, base: float | None) -> str:
        if base is None:
            return ""
        diff = current - base
        if abs(diff) < 0.005:
            return f"  = baseline {base*100:.0f}%"
        arrow = "▲" if diff > 0 else "▼"
        return f"  {arrow} baseline {base*100:.0f}%"

    lines.append(
        f"Classification:    {sum(1 for r in run.results if r.classification_pass)}"
        f"/{sum(1 for r in run.results if r.classification_pass is not None)}"
        f"  ({run.classification_pass_rate*100:.0f}%)"
        f"{_delta(run.classification_pass_rate, baseline.classification_pass_rate if baseline else None)}"
    )
    lines.append(
        f"Tool-use:          {sum(1 for r in run.results if r.tool_use_pass)}"
        f"/{len(run.results)}"
        f"  ({run.tool_use_pass_rate*100:.0f}%)"
        f"{_delta(run.tool_use_pass_rate, baseline.tool_use_pass_rate if baseline else None)}"
    )
    lines.append(
        f"Answer quality:    {sum(1 for r in run.results for s in r.answer_quality_scores if s.passed)}"
        f"/{sum(len(r.answer_quality_scores) for r in run.results)} dimensions"
        f"  ({run.answer_quality_pass_rate*100:.0f}%)"
        f"{_delta(run.answer_quality_pass_rate, baseline.answer_quality_pass_rate if baseline else None)}"
    )
    lines.append("")

    failures = [r for r in run.results if (
        r.classification_pass is False or not r.tool_use_pass or r.error
        or any(not s.passed for s in r.answer_quality_scores)
    )]
    if failures:
        lines.append("FAILURES:")
        for r in failures:
            tag = r.actual_classification or "?"
            if r.error:
                lines.append(f"  {r.id} [{tag}]  error: {r.error[:80]}")
                continue
            if r.classification_pass is False:
                lines.append(f"  {r.id} [{tag}]  classification: {r.classification_reason}")
            if not r.tool_use_pass:
                lines.append(f"  {r.id} [{tag}]  tool-use: {r.tool_use_reason}")
            for s in r.answer_quality_scores:
                if not s.passed:
                    lines.append(f"  {r.id} [{tag}]  answer-quality {s.name}: FAIL — {s.reasoning}")
    return "\n".join(lines)


def load_baseline() -> EvalRun | None:
    """Load the most recent results JSON, if any."""
    results_dir = Path(__file__).parent / "results"
    if not results_dir.exists():
        return None
    files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    with open(files[-1]) as f:
        return EvalRun(**json.load(f))


def save_run(run: EvalRun) -> Path:
    """Persist a run record. Returns the file path."""
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    path = results_dir / f"{run.run_id}.json"
    with open(path, "w") as f:
        json.dump(run.model_dump(), f, indent=2, default=str)
    return path
```

- [ ] **Step 10: Write the failing test for the runner**

Create `backend/tests/test_eval_runner.py`:
```python
"""Unit tests for the eval runner — uses a stub graph, no real LLM."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from backend.evals.runner import load_golden_set, run_evals
from backend.evals.schema import GoldenQuery


class _StubGraph:
    """Minimal graph stub matching the .astream interface our runner uses."""

    def __init__(self, classification: str, confidence: float, tools: list[str], answer: str):
        self.classification = classification
        self.confidence = confidence
        self.tools = tools
        self.answer = answer

    async def astream(self, input_data, config, stream_mode):
        # Yield classify_query update first
        yield ("updates", {
            "classify_query": {
                "classification": {
                    "primary_category": self.classification,
                    "confidence": self.confidence,
                    "secondary_categories": [],
                },
            },
        })
        # Yield AIMessage chunks with tool_calls
        msg = MagicMock(spec=AIMessage)
        msg.content = self.answer
        msg.tool_calls = [{"name": t, "args": {}, "id": f"c{i}"} for i, t in enumerate(self.tools)]
        yield ("messages", (msg, {}))


@pytest.mark.asyncio
async def test_runner_captures_classification_and_tools():
    graph = _StubGraph("quick", 0.91, ["get_portfolio_summary"], "Your value is $5,000.")
    queries = [GoldenQuery(
        id="q1", query="value?",
        expected_classification="quick", min_confidence=0.8,
        expected_tools_any_of=["get_portfolio_summary"],
    )]
    run = await run_evals(graph, queries)
    assert len(run.results) == 1
    r = run.results[0]
    assert r.actual_classification == "quick"
    assert r.actual_confidence == 0.91
    assert r.actual_tools == ["get_portfolio_summary"]
    assert r.classification_pass is True
    assert r.tool_use_pass is True


@pytest.mark.asyncio
async def test_runner_marks_classification_failure():
    graph = _StubGraph("analysis", 0.91, [], "ok")
    queries = [GoldenQuery(
        id="q1", query="value?",
        expected_classification="quick", min_confidence=0.8,
    )]
    run = await run_evals(graph, queries)
    assert run.results[0].classification_pass is False


def test_load_golden_set_parses_yaml(tmp_path):
    yaml_content = """
- id: q001
  query: How much is my portfolio worth?
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_portfolio_summary]
"""
    path = tmp_path / "golden.yaml"
    path.write_text(yaml_content)
    queries = load_golden_set(path)
    assert len(queries) == 1
    assert queries[0].id == "q001"
    assert queries[0].expected_classification == "quick"
```

- [ ] **Step 11: Run the runner tests (expect pass)**

Run: `backend/.venv/bin/pytest backend/tests/test_eval_runner.py -v`

Expected: 3 PASS.

- [ ] **Step 12: Create `golden_set.yaml` with the first 20 queries**

Create `backend/evals/golden_set.yaml`. The full golden set lands in Task 4.2; this batch is the foundation:
```yaml
# Quick path (10)
- id: q001
  query: "How much is my portfolio worth?"
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_portfolio_summary]
  forbidden_tools: [get_buy_and_hold_comparison, get_relative_performance]

- id: q002
  query: "When's my next buy?"
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_portfolio_summary, get_dca_history, get_dca_analysis]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q003
  query: "How much have I put in so far?"
  expected_classification: quick
  min_confidence: 0.80
  expected_tools_any_of: [get_dca_analysis, get_dca_history, get_portfolio_summary]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q004
  query: "What do I hold right now?"
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_balances, get_portfolio_summary]
  forbidden_tools: [get_buy_and_hold_comparison, get_relative_performance]

- id: q005
  query: "How much did I spend on ETH in total?"
  expected_classification: quick
  min_confidence: 0.80
  expected_tools_any_of: [get_dca_analysis, get_dca_history]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q006
  query: "What's the current ETH price?"
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_prices, get_portfolio_summary]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q007
  query: "Show me my DCA history"
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_dca_history]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q008
  query: "How many lots do I have?"
  expected_classification: quick
  min_confidence: 0.75
  expected_tools_any_of: [get_dca_analysis, get_dca_history]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q009
  query: "What's my SOL balance?"
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_balances, get_portfolio_summary]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q010
  query: "When did I make my last buy?"
  expected_classification: quick
  min_confidence: 0.80
  expected_tools_any_of: [get_dca_history, get_dca_analysis]
  forbidden_tools: [get_buy_and_hold_comparison]

# Analysis path (8)
- id: q011
  query: "Am I up or down overall?"
  expected_classification: analysis
  min_confidence: 0.75
  expected_tools_any_of: [get_balance_change, get_portfolio_summary]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q012
  query: "How's ETH doing this month?"
  expected_classification: analysis
  min_confidence: 0.80
  expected_tools_any_of: [get_relative_performance, get_balance_change]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q013
  query: "Was last week good or bad for me?"
  expected_classification: analysis
  min_confidence: 0.80
  expected_tools_any_of: [get_balance_change]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q014
  query: "Which of my coins is doing best?"
  expected_classification: analysis
  min_confidence: 0.80
  expected_tools_any_of: [get_relative_performance]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q015
  query: "Which one is dragging me down?"
  expected_classification: analysis
  min_confidence: 0.75
  expected_tools_any_of: [get_relative_performance]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q016
  query: "How has my portfolio performed over the last 3 months?"
  expected_classification: analysis
  min_confidence: 0.85
  expected_tools_any_of: [get_balance_change, get_snapshots]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q017
  query: "Has my strategy paid off?"
  expected_classification: analysis
  min_confidence: 0.65
  expected_tools_any_of: [get_balance_change, get_dca_analysis, get_relative_performance]
  forbidden_tools: []

- id: q018
  query: "How's SOL doing this week vs last week?"
  expected_classification: analysis
  min_confidence: 0.80
  expected_tools_any_of: [get_balance_change, get_relative_performance]
  forbidden_tools: [get_buy_and_hold_comparison]

# Tax path (2 — full set in Task 4.2)
- id: q019
  query: "If I sold everything today, how much tax would I pay?"
  expected_classification: tax
  min_confidence: 0.85
  expected_tools_any_of: [get_unrealised_cgt]
  forbidden_tools: [get_buy_and_hold_comparison]

- id: q020
  query: "Which of my buys are almost old enough for the CGT discount?"
  expected_classification: tax
  min_confidence: 0.85
  expected_tools_any_of: [get_unrealised_cgt]
  forbidden_tools: [get_buy_and_hold_comparison]
```

- [ ] **Step 13: Add a pytest entry that runs evals**

Create `backend/tests/test_evals.py`:
```python
"""Eval suite entrypoint. Opt-in via `pytest -m eval`.

Hits live LLM APIs — runs only when the marker is selected.
"""

import pytest

from backend.evals.runner import (
    load_baseline, load_golden_set, render_summary, run_evals, save_run,
)


@pytest.mark.eval
@pytest.mark.asyncio
async def test_full_eval_suite():
    """Run the complete golden set against the real agent graph."""
    # Build the graph the same way main.py does, sharing tools/checkpointer.
    from backend.agent.checkpointer import create_checkpointer
    from backend.agent.graph import build_graph
    from backend.agent.tools import MCPToolManager

    tool_manager = MCPToolManager()
    tools = await tool_manager.start()
    try:
        checkpointer = create_checkpointer()
        graph = build_graph(tools, checkpointer)

        queries = load_golden_set()
        run = await run_evals(graph, queries)
    finally:
        await tool_manager.stop()

    baseline = load_baseline()
    summary = render_summary(run, baseline)
    print("\n" + summary)
    save_run(run)

    # Soft pass: don't fail the test on quality scores. The point of running
    # this is the printed report and the JSON record. Hard failures
    # (exceptions per query) DO fail the suite via the assertion below.
    errors = [r for r in run.results if r.error]
    assert not errors, f"{len(errors)} queries errored — see report above"
```

- [ ] **Step 14: Verify the suite runs (without `-m eval` it should be skipped)**

Run: `backend/.venv/bin/pytest backend/tests/test_evals.py -v`

Expected: SKIPPED — marker not selected.

Run: `backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v`

Expected: PASS — full eval runs against the agent graph, prints a summary table, writes a JSON record to `backend/evals/results/`. Costs ~$0.50-$1 in API calls.

- [ ] **Step 15: Fix the long-standing LINK pre-existing test failure**

Open `backend/tests/test_mcp_server.py`. Find the test `test_get_prices_tool_default_assets` (per Phase 2 memory, this expects 3 assets but ASSET_MAP now has 4).

Update the test's expected asset count from 3 to 4. (The exact assertion to change depends on the test body; locate the assertion that compares against `["ETH", "SOL", "ADA"]` and add `"LINK"`.)

Run: `backend/.venv/bin/pytest backend/tests/test_mcp_server.py::test_get_prices_tool_default_assets -v`

Expected: PASS.

- [ ] **Step 16: Run the full test suite (now no exclusions needed)**

Run: `backend/.venv/bin/pytest backend/tests/ -v`

Expected: all pass.

- [ ] **Step 17: Commit and push**

```bash
git add backend/requirements.txt backend/pytest.ini backend/evals/ backend/tests/test_eval_judges.py backend/tests/test_eval_runner.py backend/tests/test_evals.py backend/tests/test_mcp_server.py .gitignore
git commit -m "feat(evals): eval framework with classification + tool-use judges, 20 golden queries"
git push origin main
```

---

### Task 4.2: LLM-as-judge for answer quality + remaining 15 queries (full 35-query golden set)

**Files:**
- Create: `backend/evals/prompts.py`
- Modify: `backend/evals/judges.py` (add LLM judge)
- Modify: `backend/evals/runner.py` (call the new judge in `_run_single`)
- Modify: `backend/evals/golden_set.yaml` (grow to 35 queries; add `judge_dimensions` everywhere)
- Modify: `backend/tests/test_eval_judges.py` (add LLM judge tests with mocked Anthropic)
- Modify: `backend/tests/test_evals.py` (allow `--judge-model` override via env var for cheap iteration)

**Why:** The headline piece. Wire up the LLM-as-judge for answer-quality, expand the golden set to 35 queries, and add the multi-turn sequences. Each query gets graded across multiple independent dimensions — single-rubric judges produce mush.

- [ ] **Step 1: Create the dimension catalogue**

Create `backend/evals/prompts.py`:
```python
"""Dimension catalogue + LLM-as-judge prompt template.

Adding a new dimension = one entry in DIMENSION_CATALOGUE. The judge prompt
embeds whichever dimensions a given query requires.
"""

from backend.evals.schema import JudgeDimension


DIMENSION_CATALOGUE: dict[str, JudgeDimension] = {
    "cites_aud_value": JudgeDimension(
        name="cites_aud_value",
        criterion=(
            "The answer must contain at least one AUD value with $ prefix and "
            "comma separators (e.g. $5,777.83)."
        ),
    ),
    "cites_timestamp": JudgeDimension(
        name="cites_timestamp",
        criterion=(
            "The answer must explicitly state when the data is from — either a "
            "date (DD/MM/YYYY) or a relative phrase like 'as of'."
        ),
    ),
    "no_filler_preamble": JudgeDimension(
        name="no_filler_preamble",
        criterion=(
            "The answer must start with substantive content. Phrases like "
            "'Let me check', 'I'll look that up', 'Here's what I found' as the "
            "opening are FAIL."
        ),
    ),
    "formatting_correct": JudgeDimension(
        name="formatting_correct",
        criterion=(
            "AUD values use comma separators, percentages have 2 decimal places, "
            "crypto quantities have 4 decimal places."
        ),
    ),
    "cites_actual_dates_from_tools": JudgeDimension(
        name="cites_actual_dates_from_tools",
        criterion=(
            "When the answer references a date or period, that date or period "
            "must appear in the tool results provided. No invented dates."
        ),
    ),
    "cites_ato_rule": JudgeDimension(
        name="cites_ato_rule",
        criterion=(
            "For any tax claim, the specific ATO rule must be named (e.g. "
            "'CGT discount: asset held >12 months')."
        ),
    ),
    "shows_math": JudgeDimension(
        name="shows_math",
        criterion=(
            "For tax / math-heavy answers, the calculation must be shown — "
            "not just a final number."
        ),
    ),
    "states_assumptions": JudgeDimension(
        name="states_assumptions",
        criterion=(
            "For comparison answers, the assumptions are stated (e.g. 'this "
            "assumes you'd bought ETH at the daily close price on each DCA date')."
        ),
    ),
    "no_recommendation": JudgeDimension(
        name="no_recommendation",
        criterion=(
            "The answer presents data, not buy/sell recommendations. No phrases "
            "like 'you should buy', 'consider selling', etc."
        ),
    ),
    "carries_timeframe_from_previous": JudgeDimension(
        name="carries_timeframe_from_previous",
        criterion=(
            "For follow-up queries, the answer carries forward the timeframe "
            "from the previous turn without asking the user to restate it."
        ),
    ),
    "carries_assets_from_previous": JudgeDimension(
        name="carries_assets_from_previous",
        criterion=(
            "For follow-up queries, the answer carries forward the asset(s) "
            "discussed in the previous turn."
        ),
    ),
    "addresses_question": JudgeDimension(
        name="addresses_question",
        criterion=(
            "The answer directly addresses what the user asked. Tangents or "
            "evasive non-answers are FAIL."
        ),
    ),
    "honest_about_missing_data": JudgeDimension(
        name="honest_about_missing_data",
        criterion=(
            "When tool results are incomplete, the answer surfaces that. No "
            "silently substituting a shorter window for the requested one."
        ),
    ),
}


JUDGE_SYSTEM_PROMPT = """\
You are evaluating a portfolio analyst's answer against specific quality
dimensions. For each dimension, decide PASS or FAIL based ONLY on the criteria
stated. Provide a one-sentence reason for each decision that references
specific text in the answer.

Be strict: if the answer "sort of" satisfies a dimension, that is FAIL.
"""


def build_judge_user_prompt(
    query_text: str,
    answer: str,
    tool_results_summary: str,
    dimensions: list[JudgeDimension],
) -> str:
    """Build the per-query user prompt for the answer-quality judge."""
    dimension_block = "\n".join(
        f"- {d.name}: {d.criterion}" for d in dimensions
    )
    return (
        f"QUERY:\n{query_text}\n\n"
        f"TOOL RESULTS AVAILABLE TO THE ANSWER:\n{tool_results_summary or '<none>'}\n\n"
        f"ANSWER:\n{answer}\n\n"
        f"DIMENSIONS TO SCORE:\n{dimension_block}\n\n"
        f"Return one DimensionScore per dimension above."
    )
```

- [ ] **Step 2: Write the failing tests for the LLM judge**

Append to `backend/tests/test_eval_judges.py`:
```python
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.evals.judges import judge_answer_quality
from backend.evals.schema import GoldenQuery


@pytest.mark.asyncio
async def test_answer_quality_judge_returns_one_score_per_dimension(monkeypatch):
    """Mock Anthropic; assert judge returns DimensionScore per requested dimension."""
    from backend.evals.schema import DimensionScore

    fake_response = MagicMock()
    fake_response.scores = [
        DimensionScore(name="cites_aud_value", passed=True, reasoning="contains $5,000"),
        DimensionScore(name="cites_timestamp", passed=False, reasoning="no date stated"),
    ]

    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(return_value=fake_response)
    fake_model.with_structured_output = MagicMock(return_value=fake_model)

    monkeypatch.setattr(
        "backend.evals.judges.ChatAnthropic",
        MagicMock(return_value=fake_model),
    )

    query = GoldenQuery(
        id="q1", query="value?",
        judge_dimensions=["cites_aud_value", "cites_timestamp"],
    )
    scores = await judge_answer_quality(
        query, answer="Your portfolio is $5,000.", tool_results_summary="",
    )
    assert len(scores) == 2
    names = [s.name for s in scores]
    assert names == ["cites_aud_value", "cites_timestamp"]
    assert scores[0].passed is True
    assert scores[1].passed is False


@pytest.mark.asyncio
async def test_answer_quality_judge_returns_empty_when_no_dimensions(monkeypatch):
    """If a query has no judge_dimensions, the LLM is not invoked."""
    fake_chat = MagicMock(side_effect=AssertionError("ChatAnthropic should not be called"))
    monkeypatch.setattr("backend.evals.judges.ChatAnthropic", fake_chat)
    query = GoldenQuery(id="q1", query="x", judge_dimensions=[])
    scores = await judge_answer_quality(query, answer="anything", tool_results_summary="")
    assert scores == []
```

- [ ] **Step 3: Run the tests (expect failure)**

Run: `backend/.venv/bin/pytest backend/tests/test_eval_judges.py::test_answer_quality_judge_returns_one_score_per_dimension -v`

Expected: FAIL — `judge_answer_quality` not defined.

- [ ] **Step 4: Implement `judge_answer_quality` in `backend/evals/judges.py`**

Append to `backend/evals/judges.py`:
```python
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.evals.prompts import (
    DIMENSION_CATALOGUE,
    JUDGE_SYSTEM_PROMPT,
    build_judge_user_prompt,
)
from backend.evals.schema import DimensionScore, GoldenQuery


class _JudgeOutput(BaseModel):
    """Structured output target for the LLM judge."""
    scores: list[DimensionScore]


# Default judge model = same as the agent. Override via env var for cheap iteration.
DEFAULT_JUDGE_MODEL = "claude-sonnet-4-5-20241022"


def _judge_model_name() -> str:
    return os.environ.get("EVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)


async def judge_answer_quality(
    query: GoldenQuery,
    answer: str,
    tool_results_summary: str,
) -> list[DimensionScore]:
    """LLM-as-judge for answer quality. Returns one DimensionScore per dimension."""
    if not query.judge_dimensions:
        return []

    dimensions = [DIMENSION_CATALOGUE[name] for name in query.judge_dimensions]
    model = ChatAnthropic(model=_judge_model_name()).with_structured_output(_JudgeOutput)
    user_prompt = build_judge_user_prompt(
        query_text=query.query,
        answer=answer,
        tool_results_summary=tool_results_summary,
        dimensions=dimensions,
    )

    response: _JudgeOutput = await model.ainvoke([
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    return response.scores
```

- [ ] **Step 5: Run the LLM judge tests**

Run: `backend/.venv/bin/pytest backend/tests/test_eval_judges.py -v`

Expected: 10 PASS (the 8 from Task 4.1 + 2 new).

- [ ] **Step 6: Wire the judge into the runner**

In `backend/evals/runner.py`, modify `_run_single` to capture tool results and call the answer-quality judge.

Replace the existing `_run_single` body's tool capture loop with one that also retains tool results:
```python
    actual_tool_results: list[str] = []  # NEW

    try:
        async for mode, data in graph.astream(
            {"messages": [HumanMessage(content=query.query)]},
            config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                for node_name, update in data.items():
                    if node_name == "classify_query" and update.get("classification"):
                        cls = update["classification"]
                        actual_classification = cls.get("primary_category")
                        actual_confidence = cls.get("confidence")
            elif mode == "messages":
                chunk, _meta = data
                if isinstance(chunk, AIMessage) and chunk.content:
                    actual_answer_parts.append(str(chunk.content))
                if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        actual_tools.append(tc["name"])
                # Tool results arrive as ToolMessage chunks
                from langchain_core.messages import ToolMessage
                if isinstance(chunk, ToolMessage):
                    actual_tool_results.append(str(chunk.content)[:500])  # truncate for prompt
```

After the `tool_pass, tool_reason = judge_tool_use(...)` line, add:
```python
    from backend.evals.judges import judge_answer_quality
    tool_results_summary = "\n---\n".join(actual_tool_results)
    answer_quality_scores = await judge_answer_quality(
        query, actual_answer, tool_results_summary,
    )
```

Pass `answer_quality_scores=answer_quality_scores` into the `QueryResult(...)` constructor.

- [ ] **Step 7: Grow `golden_set.yaml` to 35 queries**

Open `backend/evals/golden_set.yaml`. For the existing 20 queries, add `judge_dimensions:` blocks. Then append the remaining 15 entries.

For each existing entry, add appropriate dimensions. Examples:

For q001 (quick portfolio value):
```yaml
  judge_dimensions:
    - cites_aud_value
    - cites_timestamp
    - no_filler_preamble
    - formatting_correct
    - addresses_question
```

For q012 (analysis: ETH this month):
```yaml
  judge_dimensions:
    - cites_aud_value
    - cites_actual_dates_from_tools
    - formatting_correct
    - addresses_question
```

For q019 (tax: sell everything today):
```yaml
  judge_dimensions:
    - cites_aud_value
    - cites_ato_rule
    - shows_math
    - addresses_question
```

After the existing 20, append:

```yaml
# Tax path (continuing — 3 more)
- id: q021
  query: "Anything I should think about before June 30?"
  expected_classification: tax
  min_confidence: 0.75
  expected_tools_any_of: [get_unrealised_cgt]
  forbidden_tools: [get_buy_and_hold_comparison]
  judge_dimensions: [cites_ato_rule, addresses_question, no_recommendation]

- id: q022
  query: "Which buys would save me the most tax if I waited longer to sell?"
  expected_classification: tax
  min_confidence: 0.75
  expected_tools_any_of: [get_unrealised_cgt]
  forbidden_tools: [get_buy_and_hold_comparison]
  judge_dimensions: [cites_ato_rule, shows_math, addresses_question]

- id: q023
  query: "What's my CGT position on ETH right now?"
  expected_classification: tax
  min_confidence: 0.85
  expected_tools_any_of: [get_unrealised_cgt]
  forbidden_tools: [get_buy_and_hold_comparison]
  judge_dimensions: [cites_aud_value, cites_ato_rule, addresses_question]

# Comparison path (5)
- id: q024
  query: "Would I have been better off just buying ETH and holding?"
  expected_classification: comparison
  min_confidence: 0.85
  expected_tools_any_of: [get_buy_and_hold_comparison]
  forbidden_tools: []
  judge_dimensions: [states_assumptions, no_recommendation, cites_aud_value]

- id: q025
  query: "What if I'd started a year earlier?"
  expected_classification: comparison
  min_confidence: 0.65
  expected_tools_any_of: [get_buy_and_hold_comparison, get_relative_performance]
  forbidden_tools: []
  judge_dimensions: [states_assumptions, no_recommendation]

- id: q026
  query: "Was DCA the right call vs lump sum?"
  expected_classification: comparison
  min_confidence: 0.75
  expected_tools_any_of: [get_buy_and_hold_comparison]
  forbidden_tools: []
  judge_dimensions: [states_assumptions, no_recommendation, addresses_question]

- id: q027
  query: "Which of my buys was my best one?"
  expected_classification: comparison
  min_confidence: 0.65
  expected_tools_any_of: [get_dca_history, get_relative_performance]
  forbidden_tools: []
  judge_dimensions: [cites_aud_value, addresses_question]

- id: q028
  query: "Would all-in SOL have done better than my DCA mix?"
  expected_classification: comparison
  min_confidence: 0.85
  expected_tools_any_of: [get_buy_and_hold_comparison]
  forbidden_tools: []
  judge_dimensions: [states_assumptions, no_recommendation, cites_aud_value]

# Open / vague (4)
- id: q029
  query: "What's changed since last week?"
  expected_classification: open
  min_confidence: 0.65
  expected_tools_any_of: [get_balance_change, get_relative_performance]
  forbidden_tools: []
  judge_dimensions: [cites_actual_dates_from_tools, addresses_question]

- id: q030
  query: "Give me the quick version of where I'm at."
  expected_classification: open
  min_confidence: 0.75
  expected_tools_any_of: [get_portfolio_summary, get_balance_change]
  forbidden_tools: []
  judge_dimensions: [cites_aud_value, addresses_question, no_filler_preamble]

- id: q031
  query: "Anything I should know?"
  expected_classification: open
  min_confidence: 0.65
  expected_tools_any_of: [get_portfolio_summary, get_balance_change, get_unrealised_cgt]
  forbidden_tools: []
  judge_dimensions: [no_recommendation, addresses_question]

- id: q032
  query: "What's the most interesting thing about my portfolio right now?"
  expected_classification: open
  min_confidence: 0.65
  expected_tools_any_of: [get_portfolio_summary, get_relative_performance, get_unrealised_cgt]
  forbidden_tools: []
  judge_dimensions: [no_recommendation, addresses_question]

# Multi-turn sequence (3 — the phase 3 vision sequence)
- id: q033
  query: "How's ETH been this month?"
  expected_classification: analysis
  min_confidence: 0.80
  expected_tools_any_of: [get_relative_performance, get_balance_change]
  forbidden_tools: []
  judge_dimensions: [cites_actual_dates_from_tools, addresses_question]

- id: q034
  query: "What about SOL?"
  previous: q033
  expected_classification: analysis
  min_confidence: 0.65
  expected_tools_any_of: [get_relative_performance, get_balance_change]
  forbidden_tools: []
  judge_dimensions: [carries_timeframe_from_previous, addresses_question]

- id: q035
  query: "Which one was a better buy?"
  previous: q034
  expected_classification: comparison
  min_confidence: 0.65
  expected_tools_any_of: [get_buy_and_hold_comparison, get_relative_performance]
  forbidden_tools: []
  judge_dimensions: [carries_assets_from_previous, states_assumptions, no_recommendation]
```

- [ ] **Step 8: Run the unit suite (no `-m eval`)**

Run: `backend/.venv/bin/pytest backend/tests/ -v`

Expected: all pass. Eval suite still skipped without the marker.

- [ ] **Step 9: Run the eval suite end-to-end**

Run: `backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s`

Expected: full 35-query run completes (~3-5 min). Summary table prints. JSON record written to `backend/evals/results/`. Cost: ~$1-2.

For cheaper iteration during prompt-tuning, you can use:
```bash
EVAL_JUDGE_MODEL=claude-haiku-4-5-20251001 backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s
```

- [ ] **Step 10: Commit and push**

```bash
git add backend/evals/prompts.py backend/evals/judges.py backend/evals/runner.py backend/evals/golden_set.yaml backend/tests/test_eval_judges.py
git commit -m "feat(evals): LLM-as-judge for answer quality, full 35-query golden set"
git push origin main
```

---

### Task 4.3: WebSocket E2E test + frontend `useAgentChat` hook tests

**Files:**
- Create: `backend/tests/test_agent_chat_e2e.py`
- Modify: `frontend/package.json` (add vitest, jsdom)
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/hooks/useAgentChat.test.ts`

**Why:** Two test gaps Step 4 set out to fix:
1. WebSocket protocol regressions are catastrophic (the chat panel goes silent) but currently uncaught — add a deterministic E2E test using a stub graph.
2. `useAgentChat` is the most state-dense piece of frontend code and has zero tests. Add Vitest + cover the critical state transitions.

- [ ] **Step 1: Write the WebSocket E2E test**

Create `backend/tests/test_agent_chat_e2e.py`:
```python
"""WebSocket protocol E2E test using a stub graph (no real LLM)."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from backend.main import app


class _StubGraph:
    """Yields a deterministic message sequence — exercises every branch of
    websocket_handler._stream_graph_response."""

    async def astream(self, input_data, config, stream_mode):
        yield ("updates", {
            "classify_query": {
                "classification": {
                    "primary_category": "quick", "confidence": 0.92,
                    "secondary_categories": [],
                },
            },
        })
        ai = MagicMock(spec=AIMessage)
        ai.content = ""
        ai.tool_calls = [{"name": "get_portfolio_summary", "args": {}, "id": "c1"}]
        yield ("messages", (ai, {}))
        # Tool result
        tm = MagicMock(spec=ToolMessage)
        tm.content = '{"total_value_aud": 5000.0}'
        yield ("messages", (tm, {"langgraph_tool_name": "get_portfolio_summary"}))
        # Final answer chunk
        ai2 = MagicMock(spec=AIMessage)
        ai2.content = "Your portfolio is worth $5,000."
        ai2.tool_calls = []
        yield ("messages", (ai2, {}))

    async def aget_state(self, config):
        state = MagicMock()
        state.values = {"messages": []}
        state.tasks = []
        return state


@pytest.fixture
def authed_client():
    """Override the agent graph to a stub and provide an auth cookie."""
    from backend.auth.jwt import encode_token

    app.state.agent_graph = _StubGraph()
    client = TestClient(app)
    client.cookies.set("auth_token", encode_token())
    return client


def test_websocket_emits_expected_message_sequence(authed_client):
    received: list[dict] = []
    with authed_client.websocket_connect("/api/agent/chat") as ws:
        # Wait for the session message
        first = ws.receive_json()
        assert first["type"] in ("session_started", "session_resumed")
        ws.send_json({"type": "user_message", "content": "value?"})

        # Drain until message_complete or limit
        for _ in range(20):
            msg = ws.receive_json()
            received.append(msg)
            if msg["type"] in ("message_complete", "error"):
                break

    types = [m["type"] for m in received]
    assert "agent_thinking" in types
    assert "classifier_result" in types
    assert "tool_start" in types
    assert "tool_end" in types
    assert "token" in types
    assert types[-1] == "message_complete"


def test_websocket_rejects_unauthenticated_connection():
    client_no_auth = TestClient(app)
    # Don't set the cookie
    with pytest.raises(Exception):  # WebSocket close with code 4401
        with client_no_auth.websocket_connect("/api/agent/chat") as ws:
            ws.receive_json()
```

- [ ] **Step 2: Run the E2E test**

Run: `backend/.venv/bin/pytest backend/tests/test_agent_chat_e2e.py -v`

Expected: 2 PASS.

- [ ] **Step 3: Add Vitest to the frontend**

In `frontend/package.json`, add to `devDependencies`:
```json
"vitest": "^2.1.0",
"@testing-library/react": "^16.0.1",
"@testing-library/jest-dom": "^6.4.0",
"jsdom": "^25.0.0"
```

Add to `scripts`:
```json
"test": "vitest run",
"test:watch": "vitest"
```

Run: `cd frontend && npm install`

- [ ] **Step 4: Create `vitest.config.ts`**

Create `frontend/vitest.config.ts`:
```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

- [ ] **Step 5: Create the hook test**

Create `frontend/src/hooks/useAgentChat.test.ts`:
```typescript
/**
 * Tests for useAgentChat — the agent WebSocket state machine.
 *
 * We mock WebSocket directly. The hook never sees a real socket.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAgentChat } from './useAgentChat'

class MockWebSocket {
  static OPEN = 1
  static CLOSED = 3
  readyState = MockWebSocket.OPEN
  onopen: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  sent: string[] = []
  url: string

  constructor(url: string) {
    this.url = url
    // Simulate immediate open
    setTimeout(() => this.onopen?.(new Event('open')), 0)
  }
  send(data: string) { this.sent.push(data) }
  close() { this.readyState = MockWebSocket.CLOSED }
  receive(payload: object) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent)
  }
}

let lastSocket: MockWebSocket | null = null

beforeEach(() => {
  lastSocket = null
  // @ts-expect-error — overriding global WebSocket
  globalThis.WebSocket = vi.fn().mockImplementation((url: string) => {
    lastSocket = new MockWebSocket(url)
    return lastSocket
  })
  globalThis.localStorage.clear()
  // Stub apiFetch so rehydration doesn't try to hit the network
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    json: () => Promise.resolve({ messages: [] }),
  }))
})

afterEach(() => {
  vi.restoreAllMocks()
})

async function flush() {
  await act(async () => { await new Promise(r => setTimeout(r, 5)) })
}

describe('useAgentChat', () => {
  it('accumulates token chunks into a single assistant message', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({ type: 'token', content: 'Hello ' }))
    act(() => lastSocket!.receive({ type: 'token', content: 'world.' }))
    expect(result.current.messages.length).toBe(1)
    expect(result.current.messages[0].content).toBe('Hello world.')
    expect(result.current.messages[0].streaming).toBe(true)
  })

  it('clears streaming flag on message_complete', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({ type: 'token', content: 'Hi.' }))
    act(() => lastSocket!.receive({ type: 'message_complete' }))
    expect(result.current.messages[0].streaming).toBe(false)
    expect(result.current.thinking).toBe(false)
  })

  it('tracks tool_start and tool_end activities', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({
      type: 'tool_start', tool: 'get_portfolio_summary', params: {},
    }))
    expect(result.current.activeTools).toHaveLength(1)
    act(() => lastSocket!.receive({
      type: 'tool_end', tool: 'get_portfolio_summary', duration_ms: 150,
    }))
    expect(result.current.activeTools).toHaveLength(0)
  })

  it('handles HITL request and clears it on respond', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({
      type: 'hitl_request',
      tool: 'get_buy_and_hold_comparison',
      params: { asset: 'ETH' },
      reason: 'Expensive call',
      estimated_duration_ms: 8000,
    }))
    expect(result.current.hitl).not.toBeNull()
    expect(result.current.hitl?.tool).toBe('get_buy_and_hold_comparison')

    act(() => result.current.respondHITL(true))
    expect(result.current.hitl).toBeNull()
    // Verify approval was sent over the wire
    expect(lastSocket!.sent.at(-1)).toContain('"approved":true')
  })

  it('responds to ping with pong', async () => {
    const { result: _r } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    const before = lastSocket!.sent.length
    act(() => lastSocket!.receive({ type: 'ping' }))
    expect(lastSocket!.sent[before]).toContain('"type":"pong"')
  })

  it('appends an error message and clears thinking on error', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({ type: 'agent_thinking' }))
    act(() => lastSocket!.receive({
      type: 'error', error_type: 'model', content: 'The agent ran into an internal error.',
    }))
    expect(result.current.thinking).toBe(false)
    const last = result.current.messages.at(-1)
    expect(last?.content).toContain('Something went wrong')
    expect(last?.content).not.toContain('agent_thinking')
  })
})
```

- [ ] **Step 6: Run the frontend tests**

Run: `cd frontend && npm test`

Expected: 6 PASS.

- [ ] **Step 7: Run the full backend suite to ensure nothing regressed**

Run: `backend/.venv/bin/pytest backend/tests/ -v`

Expected: all pass.

- [ ] **Step 8: Commit and push**

```bash
git add backend/tests/test_agent_chat_e2e.py frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/hooks/useAgentChat.test.ts
git commit -m "test: WebSocket E2E + useAgentChat hook coverage"
git push origin main
```

---

### Task 4.4: README + first baseline run + eval usage docs

**Files:**
- Modify: `README.md`
- Create: `docs/eval-baseline.md`

**Why:** Lock in usage instructions and capture the first baseline run as a reference point. After this task, anyone (including future-you in 6 months) knows how to run evals and what "normal" looks like.

- [ ] **Step 1: Run the eval suite to produce a baseline**

Run: `backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s 2>&1 | tee /tmp/eval-baseline.log`

Capture the printed summary table from the output. Note the run-id from the JSON file written under `backend/evals/results/`.

- [ ] **Step 2: Add the eval section to `README.md`**

Append (or create) a new section in `README.md`:
````markdown
## Agent eval harness

The agent's correctness is validated via a 35-query golden set graded along
three dimensions: classification accuracy, tool-use correctness, and
LLM-as-judge answer quality.

### Run the evals

```bash
backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s
```

This invokes the live agent graph against every golden-set query, hits real
LLM APIs, and prints a summary table. Cost: ~$1-2 per run at default model
choice. Results are written to `backend/evals/results/<run-id>.json`.

### Cheap iteration mode

When tuning prompts, swap the judge to Haiku to cut cost ~5x:
```bash
EVAL_JUDGE_MODEL=claude-haiku-4-5-20251001 \
  backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s
```

### When to run

Before any PR that touches:
- Agent system prompts (`backend/agent/prompts.py`)
- Classifier configuration (`backend/agent/classifier.py`, `agent_config.py`)
- Agent graph routing (`backend/agent/graph.py`)
- MCP tool surface (`backend/mcp_server.py`)

Not on every commit — they hit live LLM APIs and aren't free.

### Reading the report

```
EVAL RESULTS (run-id 9b2c3d4e, 2026-04-27 14:32 UTC)
─────────────────────────────────────────────────────
Classification:    32/35  (91%)  ▲ baseline 88%
Tool-use:          34/35  (97%)  = baseline
Answer quality:    87/118 dimensions (74%)  ▼ baseline 78%

FAILURES:
  q014 [analysis]  classification: expected=analysis got=open conf=0.62
  q022 [tax]       answer-quality cites_ato_rule: FAIL — paraphrased
                   "12-month rule" instead of citing ATO
```

▲/▼/= compare against the most recent prior run (the previous JSON in
`results/`). First run shows no deltas.

See `docs/eval-baseline.md` for the canonical baseline.
````

- [ ] **Step 3: Capture the baseline run**

Create `docs/eval-baseline.md`:
````markdown
# Eval baseline

First baseline run captured 2026-04-27 immediately after the eval harness
landed.

## Summary

```
<paste the printed summary table from your baseline run here>
```

## Notable failures (if any)

<list any classification/tool-use/answer-quality failures and what they
indicate. If the baseline was clean, note that.>

## Update protocol

- Re-run when intentionally changing agent prompts or routing — paste the
  new summary, replace the old failures section.
- Don't update for one-off failures (e.g., upstream Kraken transient error
  during a run).
- Don't claim a new baseline if the run was on a different `EVAL_JUDGE_MODEL`
  — Haiku and Sonnet score differently.
````

(Fill in the `<paste...>` placeholder with the actual table from Step 1.)

- [ ] **Step 4: Verify the docs build / render**

Open `README.md` and `docs/eval-baseline.md` in your editor or GitHub preview. Confirm code blocks render properly, no broken links.

- [ ] **Step 5: Commit and push**

```bash
git add README.md docs/eval-baseline.md
git commit -m "docs: eval harness usage + baseline run results"
git push origin main
```

---

## Verification (post-completion)

Run all of these manually after Task 4.4 ships. Each one corresponds to a Definition-of-Done item in the spec.

- [ ] **Path check:** `grep -r benclark backend/ frontend/ docs/superpowers/ --include="*.py" --include="*.ts" --include="*.tsx"` returns nothing.

- [ ] **Portability check:** `mv` the repo to a different absolute path. Re-run `backend/.venv/bin/uvicorn backend.main:app`. Confirm: backend boots, MCP subprocess spawns, agent answers a question — no code changes.

- [ ] **Error path check:** Temporarily break the Kraken API key, hit the dashboard. Confirm: server log has full traceback + request ID; browser shows a clean banner with the same request ID; response body has zero Python text.

- [ ] **Tool error check:** Add a temporary `raise RuntimeError("secret")` to one MCP tool. Ask the agent something that calls it. Confirm: user sees a clean "tool failed" line; agent reasoning gracefully terminates with a coherent message; server log has full traceback. Revert the temporary change.

- [ ] **Service-layer check:** `grep -n "get_supabase\|db\.table\|db\.schema" backend/services/*.py` returns nothing (except in `kraken_service.py` which is not a database service).

- [ ] **Eval run check:** `backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s` produces a summary table, writes `backend/evals/results/<run-id>.json`.

- [ ] **Frontend test check:** `cd frontend && npm test` runs and passes 6 tests for `useAgentChat`.

- [ ] **No dead code check:** `grep -rn "MCPToolManager\.restart\|_in_cooldown\|MCP_MAX_FAILURES" backend/` returns nothing.
