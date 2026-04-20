# Phase 3: LangGraph Portfolio Analyst Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only LangGraph agent that answers natural-language portfolio questions via WebSocket, using the MCP tools from Phase 2.

**Architecture:** Classified multi-path graph (Haiku classifier → 5 specialised agent nodes) exposed over WebSocket at `/api/agent/chat`. Each agent node runs a ReAct-style tool loop against a subset of MCP tools loaded from a persistent stdio subprocess. State persisted via PostgresSaver to Supabase Postgres. Frontend agent panel as a fixed-width right column with typography-driven message rendering.

**Tech Stack:** LangGraph + langchain-anthropic + langchain-mcp-adapters (backend), React 19 + Tailwind + react-markdown (frontend), PostgresSaver with psycopg (checkpointer), FastAPI WebSocket (transport).

**Spec:** `docs/superpowers/specs/2026-04-20-langgraph-agent-phase3-design.md`

---

## File Structure

```
backend/
  agent/
    __init__.py              # Empty package marker
    agent_config.py          # Model IDs, thresholds, timeouts, tool subsets
    prompts.py               # Base + path-specific system prompts
    classifier.py            # ClassifierOutput model, classify_query node
    tools.py                 # MCP session lifecycle, tool loading, timeout wrapper
    checkpointer.py          # PostgresSaver pool, setup, message extraction helper
    graph.py                 # StateGraph: nodes, edges, routing, run_agent_loop
    websocket_handler.py     # WebSocket endpoint, streaming, HITL, heartbeat
  routers/
    agent.py                 # REST: GET /api/agent/sessions/{id}/messages

backend/tests/
    test_classifier.py       # Routing logic tests
    test_graph.py            # Graph construction and node routing tests
    test_websocket_handler.py # Message protocol tests

frontend/src/
  types/
    agent.ts                 # WebSocket message types
  hooks/
    useAgentChat.ts          # WebSocket connection, state, rehydration
  components/
    AgentInput.tsx           # Header-embedded input with Cmd+K
    AgentPanel.tsx           # 400px right column with message stream
    AgentMessage.tsx         # Markdown-rendered agent response
    AgentToolStatus.tsx      # Inline tool activity row
    AgentHITL.tsx            # Inline proceed/cancel text links
    NewConversationButton.tsx # Start fresh session
```

---

### Task 1: Backend dependencies and configuration

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`
- Create: `backend/agent/__init__.py`

- [ ] **Step 1: Add Python packages to requirements.txt**

Append these lines to `backend/requirements.txt` (look up latest stable versions on PyPI at implementation time and pin exact versions):

```
langgraph==<latest>
langgraph-checkpoint-postgres==<latest>
langchain-core==<latest>
langchain-anthropic==<latest>
langchain-mcp-adapters==<latest>
psycopg[binary]==<latest 3.x>
psycopg-pool==<latest 3.x>
```

- [ ] **Step 2: Install packages**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/pip install -r backend/requirements.txt`

- [ ] **Step 3: Add new settings to config.py**

Add two new fields to the `Settings` class in `backend/config.py`:

```python
class Settings(BaseSettings):
    kraken_api_key: str
    kraken_api_secret: str
    supabase_url: str
    supabase_key: str
    supabase_db_url: str = ""
    anthropic_api_key: str = ""
    kraken_live_tests: bool = False

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}
```

`supabase_db_url` is the **direct** Postgres connection string (`db.PROJECT_ID.supabase.co:5432`), not the pooler. `anthropic_api_key` is the Claude API key for langchain-anthropic.

- [ ] **Step 4: Create agent package**

Create an empty `backend/agent/__init__.py`.

- [ ] **Step 5: Verify imports**

Run: `backend/.venv/bin/python -c "from langgraph.graph import StateGraph; from langchain_anthropic import ChatAnthropic; from langchain_mcp_adapters.tools import load_mcp_tools; from langgraph.checkpoint.postgres import PostgresSaver; print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/config.py backend/agent/__init__.py
git commit -m "feat(agent): add Phase 3 dependencies and config"
```

---

### Task 2: Agent configuration module

**Files:**
- Create: `backend/agent/agent_config.py`

- [ ] **Step 1: Create agent_config.py**

```python
"""Centralised configuration for the LangGraph agent.

All model choices, thresholds, timeouts, and tool subsets live here.
Swap models by changing constants — no graph rewiring needed.
"""

# ── Models ──────────────────────────────────────────────────────────────
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"
AGENT_MODEL = "claude-sonnet-4-5-20241022"

# ── Classifier routing ──────────────────────────────────────────────────
CLASSIFIER_CONFIDENCE_THRESHOLD = 0.8

# ── Tool subsets per path ───────────────────────────────────────────────
TOOL_SUBSETS: dict[str, list[str] | None] = {
    "quick": [
        "get_portfolio_summary",
        "get_balances",
        "get_prices",
        "get_dca_history",
        "get_dca_analysis",
    ],
    "analysis": [
        "get_balance_change",
        "get_relative_performance",
        "get_dca_analysis",
        "get_snapshots",
    ],
    "tax": [
        "get_unrealised_cgt",
        "get_dca_analysis",
        "get_balance_change",
    ],
    "comparison": [
        "get_buy_and_hold_comparison",
        "get_relative_performance",
    ],
    "general": None,  # All tools
}

# ── HITL configuration ──────────────────────────────────────────────────
# Tools requiring HITL approval on the general path
HITL_TOOLS_GENERAL = {"get_buy_and_hold_comparison", "get_relative_performance"}

# ── Timeouts ────────────────────────────────────────────────────────────
TOOL_TIMEOUT_SECONDS = 30
MCP_RESPONSIVENESS_TIMEOUT = 5

# ── MCP crash recovery ──────────────────────────────────────────────────
MCP_MAX_FAILURES = 3
MCP_FAILURE_WINDOW_SECONDS = 300  # 5 minutes
MCP_COOLDOWN_SECONDS = 300        # 5 minutes

# ── WebSocket ───────────────────────────────────────────────────────────
WS_HEARTBEAT_INTERVAL = 30   # seconds
WS_HEARTBEAT_TIMEOUT = 90    # seconds without pong → close

# ── Category → node name mapping ───────────────────────────────────────
CATEGORY_TO_NODE = {
    "quick": "quick_agent",
    "analysis": "analysis_agent",
    "tax": "tax_agent",
    "comparison": "comparison_agent",
    "open": "general_agent",
}
```

- [ ] **Step 2: Verify import**

Run: `backend/.venv/bin/python -c "from backend.agent.agent_config import AGENT_MODEL, TOOL_SUBSETS; print(AGENT_MODEL, len(TOOL_SUBSETS))"`

Expected: `claude-sonnet-4-5-20241022 5`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/agent_config.py
git commit -m "feat(agent): add agent configuration module"
```

---

### Task 3: System prompts

**Files:**
- Create: `backend/agent/prompts.py`

- [ ] **Step 1: Create prompts.py**

```python
"""System prompts for the agent graph.

Base prompt is shared by all agent nodes. Path-specific appendices
are concatenated at graph build time.
"""

BASE_PROMPT = """\
You are a portfolio analyst for the user's Kraken crypto portfolio. \
You answer questions using the tools available to you. You are conversational, \
direct, and never use filler.

CURRENCY: Always AUD, never USD. Format with comma separators ($5,777.83).

DATES/TIMES: AEST/AEDT, Australia/Sydney timezone. Use DD/MM/YYYY for display, \
not ISO. Never say "today" if the data is from yesterday — say "as of 19/04/2026".

NUMERIC FORMATTING: AUD with comma separators ($5,777.83). Percentages to 2 \
decimal places. Crypto quantities to 4 decimal places (1.1682 ETH, not \
1.168234 ETH).

CITATION RULE: Every answer involving prices or date ranges must cite the actual \
values and dates used in the body of the answer. After the answer, include a \
"Tools used: ..." line only if more than one tool was called.

MULTI-TURN CONTEXT: If the user's question references prior context ("what about \
SOL?", "same for last week"), carry forward timeframes, assets, and comparison \
targets from previous turns. Never ask the user to restate context that's already \
in the conversation.

MISSING DATA: If a tool returns incomplete data or a shorter window than requested, \
surface that clearly in the answer (e.g. "I only have snapshot data back to \
15/04/2026, so this is a 5-day comparison, not 1M"). Never silently substitute a \
shorter window.

ERROR HANDLING: If a tool fails, acknowledge the failure in plain language, surface \
what cached data is available, and suggest retrying. Never expose raw error messages \
or HTTP status codes.

OUT OF SCOPE: If asked for price predictions, trading signals, or anything outside \
the read-only analytical scope, decline clearly and explain what you can do instead.

READ-ONLY: You have no ability to execute trades, move funds, or modify the \
portfolio. Don't suggest actions that imply you can.\
"""

QUICK_APPENDIX = """\

PATH: QUICK
Minimum tool calls required — usually one, occasionally two if aggregating. \
No preamble, no "let me check." No "Tools used" suffix on quick-path answers.\
"""

ANALYSIS_APPENDIX = """\

PATH: ANALYSIS
You may chain 2-3 tool calls if needed. Summarise trends in plain language. \
When reporting performance over a period, state the start and end reference \
points explicitly. Instead of "+12% over 1M", say "up 12%, from $3,454 on \
20/03/2026 to $3,868 on 20/04/2026".\
"""

TAX_APPENDIX = """\

PATH: TAX
Cite the specific ATO rule you're applying (e.g. "CGT discount: asset held \
>12 months, per ATO schedule"). Show the math. If asked about tax in any \
framing, proactively flag any lot with days_until_discount_eligible <= 30, even \
if the user didn't specifically ask about that lot. The Australian tax year runs \
1 July to 30 June. When the user references "this FY" or "tax year", interpret \
in Australian terms. Use earliest_eligible_date from the tool, not your own \
date arithmetic.\
"""

COMPARISON_APPENDIX = """\

PATH: COMPARISON
Explain what the comparison measures before showing results. State assumptions \
clearly (e.g. "this assumes you'd bought ETH at the daily close price on each \
DCA date"). If no timeframe is specified in a comparison question, default to 1M \
and state that assumption. The user draws their own conclusions — present data, \
not recommendations.\
"""

GENERAL_APPENDIX = """\

PATH: GENERAL
You have all tools available. Pick sensible defaults for vague questions — prefer \
1M timeframe if none specified. Don't ask clarifying questions unless genuinely \
ambiguous. For vague questions like "summarise my portfolio", produce at most 4-5 \
short paragraphs covering: current value and recent change, allocation, one notable \
observation (best/worst performer, approaching CGT threshold, DCA cadence issue), \
and anything the user should know. Don't produce full reports.\
"""

CLASSIFIER_PROMPT = """\
Classify the user's portfolio question into exactly one primary category. \
Only include secondary_categories if another category is clearly relevant \
(confidence >= 0.5).

Categories:
- quick: Simple factual lookups — portfolio value, balances, next DCA date, \
total spent on an asset. Single tool call, instant answer.
- analysis: Performance trends, strategy assessment, period comparisons, \
best/worst performers. May need 2-3 tool calls.
- tax: Anything involving CGT, tax, ATO rules, discount eligibility, \
financial year. Even if phrased casually.
- comparison: Counterfactual questions — "would I have been better off", \
"what if I'd done X instead", DCA vs lump-sum, buy-and-hold comparisons.
- open: Vague, conversational, or cross-category — "what's going on", \
"anything I should know", "give me the quick version".

Respond with JSON only.\
"""

# Pre-built full prompts for each path
QUICK_PROMPT = BASE_PROMPT + QUICK_APPENDIX
ANALYSIS_PROMPT = BASE_PROMPT + ANALYSIS_APPENDIX
TAX_PROMPT = BASE_PROMPT + TAX_APPENDIX
COMPARISON_PROMPT = BASE_PROMPT + COMPARISON_APPENDIX
GENERAL_PROMPT = BASE_PROMPT + GENERAL_APPENDIX
```

- [ ] **Step 2: Verify import**

Run: `backend/.venv/bin/python -c "from backend.agent.prompts import QUICK_PROMPT, CLASSIFIER_PROMPT; print(len(QUICK_PROMPT), len(CLASSIFIER_PROMPT))"`

Expected: Two numbers (lengths of the prompt strings).

- [ ] **Step 3: Commit**

```bash
git add backend/agent/prompts.py
git commit -m "feat(agent): add system prompts — base + 5 path appendices + classifier"
```

---

### Task 4: Query classifier

**Files:**
- Create: `backend/agent/classifier.py`
- Create: `backend/tests/test_classifier.py`

- [ ] **Step 1: Write the routing logic tests**

Create `backend/tests/test_classifier.py`:

```python
import pytest
from backend.agent.classifier import ClassifierOutput, route_query


def _cls(primary: str, confidence: float, secondary: list[str] | None = None) -> ClassifierOutput:
    return ClassifierOutput(
        primary_category=primary,
        confidence=confidence,
        secondary_categories=secondary or [],
    )


def test_high_confidence_no_secondary_routes_to_specialised():
    result = route_query(_cls("quick", 0.95))
    assert result == "quick_agent"


def test_high_confidence_with_secondary_routes_to_general():
    result = route_query(_cls("tax", 0.90, ["analysis"]))
    assert result == "general_agent"


def test_low_confidence_routes_to_general():
    result = route_query(_cls("analysis", 0.6))
    assert result == "general_agent"


def test_open_category_routes_to_general():
    result = route_query(_cls("open", 0.95))
    assert result == "general_agent"


def test_comparison_routes_to_comparison_agent():
    result = route_query(_cls("comparison", 0.88))
    assert result == "comparison_agent"


def test_unknown_category_routes_to_general():
    result = route_query(_cls("nonsense", 0.99))
    assert result == "general_agent"


def test_exact_threshold_routes_to_specialised():
    result = route_query(_cls("tax", 0.8))
    assert result == "tax_agent"


def test_just_below_threshold_routes_to_general():
    result = route_query(_cls("tax", 0.79))
    assert result == "general_agent"
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_classifier.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: Implement classifier.py**

Create `backend/agent/classifier.py`:

```python
"""Query classifier — routes user questions to specialised agent paths."""

from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from backend.agent.agent_config import (
    CATEGORY_TO_NODE,
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    CLASSIFIER_MODEL,
)
from backend.agent.prompts import CLASSIFIER_PROMPT


class ClassifierOutput(BaseModel):
    """Structured output from the query classifier."""

    primary_category: str = Field(description="One of: quick, analysis, tax, comparison, open")
    confidence: float = Field(description="Confidence in primary classification, 0-1")
    secondary_categories: list[str] = Field(
        default_factory=list,
        description="Other relevant categories (only if confidence >= 0.5)",
    )


def route_query(classification: ClassifierOutput) -> str:
    """Determine which agent node to route to based on classifier output.

    Returns the node name string for LangGraph conditional routing.
    """
    if classification.confidence < CLASSIFIER_CONFIDENCE_THRESHOLD:
        return "general_agent"

    if classification.secondary_categories:
        return "general_agent"

    return CATEGORY_TO_NODE.get(classification.primary_category, "general_agent")


async def classify(messages: list) -> ClassifierOutput:
    """Classify a user query using Haiku.

    Extracts the last human message and classifies it.
    """
    model = ChatAnthropic(model=CLASSIFIER_MODEL).with_structured_output(ClassifierOutput)

    last_human = None
    for msg in reversed(messages):
        if hasattr(msg, "content") and hasattr(msg, "type") and msg.type == "human":
            last_human = msg.content
            break

    if last_human is None:
        last_human = str(messages[-1]) if messages else ""

    return await model.ainvoke([
        SystemMessage(content=CLASSIFIER_PROMPT),
        HumanMessage(content=last_human),
    ])
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_classifier.py -v`

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/agent/classifier.py backend/tests/test_classifier.py
git commit -m "feat(agent): add query classifier with routing logic"
```

---

### Task 5: MCP tool setup

**Files:**
- Create: `backend/agent/tools.py`
- Create: `backend/tests/test_agent_tools.py`

- [ ] **Step 1: Write tool subset filtering tests**

Create `backend/tests/test_agent_tools.py`:

```python
import pytest
from unittest.mock import MagicMock
from backend.agent.tools import filter_tools


def _mock_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    return tool


def test_filter_tools_quick_subset():
    all_tools = [_mock_tool(n) for n in [
        "get_portfolio_summary", "get_balances", "get_prices",
        "get_dca_history", "get_dca_analysis", "get_snapshots",
        "get_unrealised_cgt",
    ]]
    result = filter_tools(all_tools, "quick")
    names = [t.name for t in result]
    assert "get_portfolio_summary" in names
    assert "get_balances" in names
    assert "get_snapshots" not in names
    assert "get_unrealised_cgt" not in names


def test_filter_tools_general_returns_all():
    all_tools = [_mock_tool(n) for n in ["a", "b", "c"]]
    result = filter_tools(all_tools, "general")
    assert len(result) == 3


def test_filter_tools_unknown_category_returns_all():
    all_tools = [_mock_tool(n) for n in ["a", "b"]]
    result = filter_tools(all_tools, "unknown")
    assert len(result) == 2
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_agent_tools.py -v`

Expected: FAIL

- [ ] **Step 3: Implement tools.py**

Create `backend/agent/tools.py`:

```python
"""MCP tool lifecycle — persistent subprocess, tool loading, timeout wrapper."""

import asyncio
import logging
import time
from contextlib import AsyncExitStack

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.agent.agent_config import (
    MCP_COOLDOWN_SECONDS,
    MCP_FAILURE_WINDOW_SECONDS,
    MCP_MAX_FAILURES,
    MCP_RESPONSIVENESS_TIMEOUT,
    TOOL_SUBSETS,
    TOOL_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

MCP_SERVER_PARAMS = StdioServerParameters(
    command="backend/.venv/bin/python",
    args=["-m", "backend.mcp_server"],
    cwd="/Users/benclark/Desktop/kraken-portfolio-tracker",
)


def filter_tools(tools: list[BaseTool], category: str) -> list[BaseTool]:
    """Return the tool subset for a given agent category.

    If category is "general" or not in TOOL_SUBSETS, returns all tools.
    """
    allowed = TOOL_SUBSETS.get(category)
    if allowed is None:
        return list(tools)
    return [t for t in tools if t.name in allowed]


class MCPToolManager:
    """Manages the MCP subprocess lifecycle and provides tools.

    Spawned once at FastAPI startup via an AsyncExitStack. The subprocess
    stays alive for the application lifetime. Crash recovery restarts the
    subprocess with cooldown protection.
    """

    def __init__(self) -> None:
        self._tools: list[BaseTool] = []
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self._failure_times: list[float] = []

    @property
    def tools(self) -> list[BaseTool]:
        return list(self._tools)

    def _in_cooldown(self) -> bool:
        """Check if we're in cooldown after repeated failures."""
        now = time.time()
        # Prune old failures outside the window
        self._failure_times = [
            t for t in self._failure_times
            if now - t < MCP_FAILURE_WINDOW_SECONDS
        ]
        return len(self._failure_times) >= MCP_MAX_FAILURES

    def _record_failure(self) -> None:
        self._failure_times.append(time.time())

    async def start(self) -> list[BaseTool]:
        """Start the MCP subprocess and load tools. Called once at startup."""
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        read, write = await self._stack.enter_async_context(
            stdio_client(MCP_SERVER_PARAMS)
        )
        self._session = await self._stack.enter_async_context(
            ClientSession(read, write)
        )
        await asyncio.wait_for(
            self._session.initialize(),
            timeout=MCP_RESPONSIVENESS_TIMEOUT,
        )
        self._tools = await load_mcp_tools(self._session)
        logger.info("[MCP] Started — %d tools loaded", len(self._tools))
        return self._tools

    async def stop(self) -> None:
        """Shut down the MCP subprocess."""
        if self._stack:
            await self._stack.aclose()
            self._stack = None
            self._session = None
            self._tools = []
            logger.info("[MCP] Stopped")

    async def restart(self) -> list[BaseTool] | None:
        """Restart after a crash. Returns None if in cooldown."""
        if self._in_cooldown():
            logger.warning(
                "[MCP] In cooldown — %d failures in last %ds",
                len(self._failure_times),
                MCP_FAILURE_WINDOW_SECONDS,
            )
            return None

        self._record_failure()
        logger.info("[MCP] Restarting subprocess...")
        await self.stop()
        try:
            return await self.start()
        except Exception:
            logger.exception("[MCP] Restart failed")
            return None


async def invoke_tool_with_timeout(tool: BaseTool, args: dict) -> str:
    """Invoke a tool with a timeout. Returns error string on failure."""
    try:
        result = await asyncio.wait_for(
            tool.ainvoke(args),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        return str(result)
    except asyncio.TimeoutError:
        return f"Error: Tool {tool.name} timed out after {TOOL_TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"Error: Tool {tool.name} failed — {e}"
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_agent_tools.py -v`

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/agent/tools.py backend/tests/test_agent_tools.py
git commit -m "feat(agent): add MCP tool manager with crash recovery and cooldown"
```

---

### Task 6: Checkpointer setup

**Files:**
- Create: `backend/agent/checkpointer.py`
- Create: `backend/tests/test_checkpointer.py`

- [ ] **Step 1: Write message extraction tests**

Create `backend/tests/test_checkpointer.py`:

```python
import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from backend.agent.checkpointer import extract_messages


def test_extract_messages_filters_to_human_and_ai():
    messages = [
        HumanMessage(content="What's my portfolio worth?"),
        AIMessage(content="Your portfolio is worth $5,000."),
    ]
    result = extract_messages(messages)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "What's my portfolio worth?"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "Your portfolio is worth $5,000."


def test_extract_messages_skips_tool_messages():
    messages = [
        HumanMessage(content="Hi"),
        AIMessage(content="", tool_calls=[{"id": "1", "name": "get_prices", "args": {}}]),
        ToolMessage(content='{"ETH": "4000"}', tool_call_id="1"),
        AIMessage(content="ETH is $4,000."),
    ]
    result = extract_messages(messages)
    assert len(result) == 3
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == ""
    assert result[2]["role"] == "assistant"
    assert result[2]["content"] == "ETH is $4,000."


def test_extract_messages_empty_list():
    assert extract_messages([]) == []
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_checkpointer.py -v`

Expected: FAIL

- [ ] **Step 3: Implement checkpointer.py**

Create `backend/agent/checkpointer.py`:

```python
"""PostgresSaver checkpointer — setup, connection pool, message extraction."""

import logging

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from backend.config import settings

logger = logging.getLogger(__name__)


def create_checkpointer() -> PostgresSaver:
    """Create a PostgresSaver backed by a psycopg connection pool.

    Uses the direct Supabase Postgres URL (not the pooler) to avoid
    transaction-mode pooling issues with prepared statements.
    Pool max_size=5 — Supabase free tier has 60 connections; the rest
    of the app uses PostgREST which doesn't consume connection slots.
    """
    if not settings.supabase_db_url:
        raise RuntimeError(
            "SUPABASE_DB_URL not set. Add the direct Postgres connection string "
            "(db.PROJECT_ID.supabase.co:5432) to .env."
        )

    pool = ConnectionPool(
        conninfo=settings.supabase_db_url,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    checkpointer = PostgresSaver(conn=pool)
    checkpointer.setup()
    logger.info("[Checkpointer] PostgresSaver initialised with pool (max_size=5)")
    return checkpointer


def extract_messages(messages: list) -> list[dict]:
    """Convert LangChain message objects to dicts for REST rehydration.

    Returns human and AI messages only — tool messages are internal.
    If LangGraph's internal state format changes, fix this one function.
    """
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"role": "assistant", "content": msg.content})
    return result
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_checkpointer.py -v`

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/agent/checkpointer.py backend/tests/test_checkpointer.py
git commit -m "feat(agent): add PostgresSaver checkpointer with message extraction"
```

---

### Task 7: Agent graph

**Files:**
- Create: `backend/agent/graph.py`
- Create: `backend/tests/test_graph.py`

- [ ] **Step 1: Write graph routing tests**

Create `backend/tests/test_graph.py`:

```python
import pytest
from backend.agent.graph import route_after_classify, AgentState


def _state(primary: str, confidence: float, secondary: list[str] | None = None) -> AgentState:
    return {
        "messages": [],
        "classification": {
            "primary_category": primary,
            "confidence": confidence,
            "secondary_categories": secondary or [],
        },
    }


def test_route_quick():
    assert route_after_classify(_state("quick", 0.9)) == "quick_agent"


def test_route_analysis():
    assert route_after_classify(_state("analysis", 0.85)) == "analysis_agent"


def test_route_tax():
    assert route_after_classify(_state("tax", 0.82)) == "tax_agent"


def test_route_comparison():
    assert route_after_classify(_state("comparison", 0.9)) == "comparison_agent"


def test_route_open_goes_to_general():
    assert route_after_classify(_state("open", 0.95)) == "general_agent"


def test_route_low_confidence_goes_to_general():
    assert route_after_classify(_state("quick", 0.5)) == "general_agent"


def test_route_secondary_goes_to_general():
    assert route_after_classify(_state("tax", 0.9, ["analysis"])) == "general_agent"


def test_route_no_classification_goes_to_general():
    state: AgentState = {"messages": [], "classification": None}
    assert route_after_classify(state) == "general_agent"


def test_route_delegates_to_route_query():
    """Verify route_after_classify delegates to classifier.route_query."""
    from backend.agent.classifier import route_query, ClassifierOutput

    cls = ClassifierOutput(primary_category="tax", confidence=0.9)
    state = _state("tax", 0.9)
    assert route_after_classify(state) == route_query(cls)
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_graph.py -v`

Expected: FAIL

- [ ] **Step 3: Implement graph.py**

Create `backend/agent/graph.py`:

```python
"""LangGraph agent graph — classified multi-path with HITL on comparison path."""

import logging
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph, add_messages
from langgraph.types import interrupt

from backend.agent.agent_config import (
    AGENT_MODEL,
    CATEGORY_TO_NODE,
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    HITL_TOOLS_GENERAL,
    TOOL_SUBSETS,
)
from backend.agent.classifier import ClassifierOutput, classify, route_query
from backend.agent.prompts import (
    ANALYSIS_PROMPT,
    COMPARISON_PROMPT,
    GENERAL_PROMPT,
    QUICK_PROMPT,
    TAX_PROMPT,
)
from backend.agent.tools import filter_tools, invoke_tool_with_timeout

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    classification: dict | None


# ── Routing ─────────────────────────────────────────────────────────────


def route_after_classify(state: AgentState) -> str:
    """Conditional edge: pick agent node based on classifier output."""
    cls = state.get("classification")
    if cls is None:
        return "general_agent"
    return route_query(ClassifierOutput(**cls))


# ── Shared ReAct loop ───────────────────────────────────────────────────


HITL_REASONS: dict[str, str] = {
    "get_buy_and_hold_comparison": (
        "Fetches historical daily OHLC price data and compares against your "
        "actual DCA buys. Returns whether all-in on this asset would have "
        "outperformed your diversified strategy."
    ),
    "get_relative_performance": (
        "Fetches historical daily OHLC price data for all tracked assets and "
        "compares their percentage change over the requested period."
    ),
}

HITL_DURATION_ESTIMATES: dict[str, int] = {
    "get_buy_and_hold_comparison": 8000,
    "get_relative_performance": 5000,
}


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

    max_iterations = 5
    for _ in range(max_iterations):
        response = await model.ainvoke(input_messages, config=config)
        input_messages.append(response)

        if not response.tool_calls:
            break

        for tc in response.tool_calls:
            tool_name = tc["name"]

            # HITL check — selective mode only triggers for genuinely
            # expensive calls (buy_and_hold always, relative_performance
            # only when timeframe >= 3M per spec)
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
                    break

            # Execute tool
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool is None:
                result = f"Error: Unknown tool {tool_name}"
            else:
                result = await invoke_tool_with_timeout(tool, tc["args"])

            input_messages.append(
                ToolMessage(content=result, tool_call_id=tc["id"])
            )
        else:
            # Inner for loop completed without break — continue outer loop
            continue
        # Break from outer loop if inner loop broke (HITL denied)
        break

    # Return only new messages (exclude system prompt and original messages)
    original_count = 1 + len(state["messages"])  # 1 for SystemMessage
    return {"messages": input_messages[original_count:]}


# ── Graph builder ───────────────────────────────────────────────────────


def build_graph(all_tools: list[BaseTool], checkpointer) -> "CompiledGraph":
    """Construct and compile the agent graph.

    Called once at startup with the loaded MCP tools and checkpointer.
    """
    # Pre-filter tool subsets
    quick_tools = filter_tools(all_tools, "quick")
    analysis_tools = filter_tools(all_tools, "analysis")
    tax_tools = filter_tools(all_tools, "tax")
    comparison_tools = filter_tools(all_tools, "comparison")

    # ── Node functions ──────────────────────────────────────────────

    async def classify_query(state: AgentState, config: RunnableConfig) -> dict:
        result = await classify(state["messages"])
        logger.info(
            "[Classifier] primary=%s confidence=%.2f secondary=%s",
            result.primary_category,
            result.confidence,
            result.secondary_categories,
        )
        return {"classification": result.model_dump()}

    async def quick_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(state, config, quick_tools, QUICK_PROMPT)

    async def analysis_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(state, config, analysis_tools, ANALYSIS_PROMPT)

    async def tax_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(state, config, tax_tools, TAX_PROMPT)

    async def comparison_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(
            state, config, comparison_tools, COMPARISON_PROMPT, hitl_mode="all"
        )

    async def general_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(
            state, config, all_tools, GENERAL_PROMPT, hitl_mode="selective"
        )

    # ── Build graph ─────────────────────────────────────────────────

    builder = StateGraph(AgentState)

    builder.add_node("classify_query", classify_query)
    builder.add_node("quick_agent", quick_agent)
    builder.add_node("analysis_agent", analysis_agent)
    builder.add_node("tax_agent", tax_agent)
    builder.add_node("comparison_agent", comparison_agent)
    builder.add_node("general_agent", general_agent)

    builder.set_entry_point("classify_query")

    builder.add_conditional_edges(
        "classify_query",
        route_after_classify,
        {
            "quick_agent": "quick_agent",
            "analysis_agent": "analysis_agent",
            "tax_agent": "tax_agent",
            "comparison_agent": "comparison_agent",
            "general_agent": "general_agent",
        },
    )

    builder.add_edge("quick_agent", END)
    builder.add_edge("analysis_agent", END)
    builder.add_edge("tax_agent", END)
    builder.add_edge("comparison_agent", END)
    builder.add_edge("general_agent", END)

    return builder.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_graph.py -v`

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/agent/graph.py backend/tests/test_graph.py
git commit -m "feat(agent): add LangGraph agent graph with classified routing and HITL"
```

---

### Task 8: WebSocket handler

**Files:**
- Create: `backend/agent/websocket_handler.py`
- Create: `backend/tests/test_websocket_handler.py`

- [ ] **Step 1: Write message serialisation tests**

Create `backend/tests/test_websocket_handler.py`:

```python
import pytest
from backend.agent.websocket_handler import (
    make_session_started,
    make_session_resumed,
    make_classifier_result,
    make_token,
    make_tool_start,
    make_tool_end,
    make_hitl_request,
    make_message_complete,
    make_error,
)


def test_session_started():
    msg = make_session_started("abc-123")
    assert msg == {"type": "session_started", "session_id": "abc-123"}


def test_session_resumed():
    msg = make_session_resumed("abc-123")
    assert msg == {"type": "session_resumed", "session_id": "abc-123"}


def test_classifier_result():
    msg = make_classifier_result("tax", 0.91)
    assert msg["type"] == "classifier_result"
    assert msg["primary_category"] == "tax"
    assert msg["confidence"] == 0.91


def test_token():
    msg = make_token("Hello")
    assert msg == {"type": "token", "content": "Hello"}


def test_tool_start():
    msg = make_tool_start("get_prices", {"assets": ["ETH"]})
    assert msg["type"] == "tool_start"
    assert msg["tool"] == "get_prices"
    assert msg["params"] == {"assets": ["ETH"]}


def test_tool_end():
    msg = make_tool_end("get_prices", 342)
    assert msg == {"type": "tool_end", "tool": "get_prices", "duration_ms": 342}


def test_hitl_request():
    msg = make_hitl_request("get_buy_and_hold_comparison", {"asset": "ETH"}, "Fetches data", 8000)
    assert msg["type"] == "hitl_request"
    assert msg["tool"] == "get_buy_and_hold_comparison"
    assert msg["estimated_duration_ms"] == 8000


def test_message_complete():
    assert make_message_complete() == {"type": "message_complete"}


def test_error():
    msg = make_error("tool_failure", "get_prices failed")
    assert msg["type"] == "error"
    assert msg["error_type"] == "tool_failure"
    assert msg["content"] == "get_prices failed"
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_websocket_handler.py -v`

Expected: FAIL

- [ ] **Step 3: Implement websocket_handler.py**

Create `backend/agent/websocket_handler.py`:

```python
"""WebSocket endpoint for the agent — streaming, HITL, heartbeat."""

import asyncio
import logging
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langgraph.types import Command

from backend.agent.agent_config import WS_HEARTBEAT_INTERVAL, WS_HEARTBEAT_TIMEOUT

logger = logging.getLogger(__name__)


# ── Message factories ───────────────────────────────────────────────────


def make_session_started(session_id: str) -> dict:
    return {"type": "session_started", "session_id": session_id}


def make_session_resumed(session_id: str) -> dict:
    return {"type": "session_resumed", "session_id": session_id}


def make_classifier_result(primary_category: str, confidence: float) -> dict:
    return {
        "type": "classifier_result",
        "primary_category": primary_category,
        "confidence": confidence,
    }


def make_token(content: str) -> dict:
    return {"type": "token", "content": content}


def make_tool_start(tool: str, params: dict) -> dict:
    return {"type": "tool_start", "tool": tool, "params": params}


def make_tool_end(tool: str, duration_ms: int) -> dict:
    return {"type": "tool_end", "tool": tool, "duration_ms": duration_ms}


def make_hitl_request(
    tool: str, params: dict, reason: str, estimated_duration_ms: int,
) -> dict:
    return {
        "type": "hitl_request",
        "tool": tool,
        "params": params,
        "reason": reason,
        "estimated_duration_ms": estimated_duration_ms,
    }


def make_message_complete() -> dict:
    return {"type": "message_complete"}


def make_error(error_type: str, content: str) -> dict:
    return {"type": "error", "error_type": error_type, "content": content}


def make_agent_thinking() -> dict:
    return {"type": "agent_thinking"}


# ── Stream processing ──────────────────────────────────────────────────


async def _stream_graph_response(ws: WebSocket, graph, session_id: str, input_data) -> None:
    """Run the graph and stream events to the WebSocket client."""
    config = {"configurable": {"thread_id": session_id}}
    tool_start_times: dict[str, float] = {}

    try:
        async for mode, data in graph.astream(
            input_data, config, stream_mode=["messages", "updates"]
        ):
            if mode == "updates":
                for node_name, update in data.items():
                    if node_name == "classify_query" and update.get("classification"):
                        cls = update["classification"]
                        await ws.send_json(
                            make_classifier_result(
                                cls["primary_category"], cls["confidence"]
                            )
                        )

            elif mode == "messages":
                chunk, metadata = data

                if isinstance(chunk, AIMessageChunk):
                    if chunk.content:
                        await ws.send_json(make_token(chunk.content))
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            tool_start_times[tc["name"]] = time.time()
                            await ws.send_json(
                                make_tool_start(tc["name"], tc.get("args", {}))
                            )

                elif isinstance(chunk, ToolMessage):
                    tool_name = metadata.get("langgraph_tool_name", "unknown")
                    start = tool_start_times.pop(tool_name, time.time())
                    duration_ms = int((time.time() - start) * 1000)
                    await ws.send_json(make_tool_end(tool_name, duration_ms))

    except Exception as e:
        logger.exception("[WS] Error during graph streaming")
        await ws.send_json(make_error("model", str(e)))
        return

    # Check for HITL interrupt
    state = await graph.aget_state(config)
    if state.tasks and any(
        hasattr(t, "interrupts") and t.interrupts for t in state.tasks
    ):
        interrupt_info = state.tasks[0].interrupts[0].value
        await ws.send_json(
            make_hitl_request(
                tool=interrupt_info["tool"],
                params=interrupt_info["params"],
                reason=interrupt_info["reason"],
                estimated_duration_ms=interrupt_info["estimated_duration_ms"],
            )
        )
        return  # Wait for hitl_response — don't send message_complete yet

    await ws.send_json(make_message_complete())


# ── WebSocket endpoint ──────────────────────────────────────────────────


async def agent_chat_endpoint(ws: WebSocket, graph, session_id: str | None = None):
    """Main WebSocket handler — called from the FastAPI route."""
    await ws.accept()

    # Session management
    if session_id:
        # Attempt to load existing session
        config = {"configurable": {"thread_id": session_id}}
        state = await graph.aget_state(config)
        if state.values:
            await ws.send_json(make_session_resumed(session_id))
        else:
            session_id = str(uuid.uuid4())
            await ws.send_json(make_session_started(session_id))
    else:
        session_id = str(uuid.uuid4())
        await ws.send_json(make_session_started(session_id))

    last_pong = time.time()

    async def heartbeat():
        nonlocal last_pong
        while True:
            await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                break
            if time.time() - last_pong > WS_HEARTBEAT_TIMEOUT:
                logger.warning("[WS] Client timeout — closing connection")
                await ws.close()
                break

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "pong":
                last_pong = time.time()

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

            elif msg_type == "user_message":
                await ws.send_json(make_agent_thinking())
                input_data = {"messages": [HumanMessage(content=data["content"])]}
                await _stream_graph_response(ws, graph, session_id, input_data)

            elif msg_type == "hitl_response":
                approved = data.get("approved", False)
                resume_input = Command(resume=approved)
                if approved:
                    await ws.send_json(make_agent_thinking())
                await _stream_graph_response(ws, graph, session_id, resume_input)

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected — session %s", session_id)
    except Exception:
        logger.exception("[WS] Unexpected error")
    finally:
        heartbeat_task.cancel()
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_websocket_handler.py -v`

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/agent/websocket_handler.py backend/tests/test_websocket_handler.py
git commit -m "feat(agent): add WebSocket handler with streaming, HITL, and heartbeat"
```

---

### Task 9: REST endpoint and FastAPI wiring

**Files:**
- Create: `backend/routers/agent.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create the agent router**

Create `backend/routers/agent.py`:

```python
"""REST endpoints for the agent — session message rehydration."""

from fastapi import APIRouter, Query, WebSocket

from backend.agent.checkpointer import extract_messages

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Rehydrate conversation history from checkpoint.

    Called by the frontend on page reload or reconnect.
    """
    from backend.main import app

    graph = app.state.agent_graph
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state.values:
        return {"session_id": session_id, "messages": []}

    messages = extract_messages(state.values.get("messages", []))
    return {"session_id": session_id, "messages": messages}


@router.websocket("/chat")
async def agent_chat(ws: WebSocket, session_id: str | None = Query(default=None)):
    """WebSocket endpoint for agent chat."""
    from backend.agent.websocket_handler import agent_chat_endpoint
    from backend.main import app

    graph = app.state.agent_graph
    await agent_chat_endpoint(ws, graph, session_id)
```

- [ ] **Step 2: Update main.py — add lifespan setup and router**

Replace `backend/main.py` with:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── MCP tools ───────────────────────────────────────────────────
    from backend.agent.tools import MCPToolManager

    tool_manager = MCPToolManager()
    try:
        tools = await tool_manager.start()
        app.state.mcp_tool_manager = tool_manager
        logger.info("[Startup] MCP tools loaded: %d", len(tools))
    except Exception:
        logger.exception("[Startup] MCP tool loading failed — agent unavailable")
        tools = []
        app.state.mcp_tool_manager = None

    # ── Checkpointer ────────────────────────────────────────────────
    from backend.agent.checkpointer import create_checkpointer

    try:
        checkpointer = create_checkpointer()
        logger.info("[Startup] Checkpointer ready")
    except Exception:
        logger.exception("[Startup] Checkpointer setup failed — agent unavailable")
        checkpointer = None

    # ── Agent graph ─────────────────────────────────────────────────
    if tools and checkpointer:
        from backend.agent.graph import build_graph

        app.state.agent_graph = build_graph(tools, checkpointer)
        logger.info("[Startup] Agent graph compiled")
    else:
        app.state.agent_graph = None
        logger.warning("[Startup] Agent graph NOT available")

    # ── Scheduler ───────────────────────────────────────────────────
    start_scheduler()

    yield

    # ── Shutdown ────────────────────────────────────────────────────
    stop_scheduler()
    if app.state.mcp_tool_manager:
        await app.state.mcp_tool_manager.stop()


app = FastAPI(title="Kraken Portfolio Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.routers import portfolio, history, sync, agent

app.include_router(portfolio.router)
app.include_router(history.router)
app.include_router(sync.router)
app.include_router(agent.router)


@app.get("/api/health")
async def health() -> dict:
    agent_ok = app.state.agent_graph is not None
    return {"status": "ok", "agent": agent_ok}
```

- [ ] **Step 3: Verify the server starts**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && timeout 10 backend/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 2>&1 | head -20`

Look for: startup logs showing MCP tools loaded, checkpointer ready, agent graph compiled. If `SUPABASE_DB_URL` or `ANTHROPIC_API_KEY` are not set, the agent will be unavailable but the server should still start.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/agent.py backend/main.py
git commit -m "feat(agent): wire agent graph into FastAPI — lifespan, WebSocket, REST"
```

---

### Task 10: Frontend dependencies and WebSocket proxy

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Install react-markdown**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npm install react-markdown`

- [ ] **Step 2: Enable WebSocket proxying in Vite**

In `frontend/vite.config.ts`, add `ws: true` to the proxy config:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
```

- [ ] **Step 3: Verify build**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npm run build`

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts
git commit -m "feat(frontend): add react-markdown and enable WebSocket proxy"
```

---

### Task 11: Agent types and useAgentChat hook

**Files:**
- Create: `frontend/src/types/agent.ts`
- Create: `frontend/src/hooks/useAgentChat.ts`

- [ ] **Step 1: Create agent types**

Create `frontend/src/types/agent.ts`:

```ts
// ── Server → Client messages ───────────────────────────────────────────

export type ServerMessage =
  | { type: 'session_started'; session_id: string }
  | { type: 'session_resumed'; session_id: string }
  | { type: 'agent_thinking' }
  | { type: 'classifier_result'; primary_category: string; confidence: number }
  | { type: 'token'; content: string }
  | { type: 'tool_start'; tool: string; params: Record<string, unknown> }
  | { type: 'tool_end'; tool: string; duration_ms: number }
  | { type: 'hitl_request'; tool: string; params: Record<string, unknown>; reason: string; estimated_duration_ms: number }
  | { type: 'message_complete' }
  | { type: 'error'; error_type: string; content: string }
  | { type: 'ping' }
  | { type: 'pong' }

// ── Client → Server messages ───────────────────────────────────────────

export type ClientMessage =
  | { type: 'user_message'; content: string }
  | { type: 'hitl_response'; approved: boolean }
  | { type: 'ping' }
  | { type: 'pong' }

// ── UI state ───────────────────────────────────────────────────────────

export interface AgentMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** True while tokens are still streaming in */
  streaming: boolean
}

export interface ToolActivity {
  tool: string
  params: Record<string, unknown>
  /** null while in progress */
  duration_ms: number | null
}

export interface HITLState {
  pending: boolean
  tool: string
  params: Record<string, unknown>
  reason: string
  estimated_duration_ms: number
}
```

- [ ] **Step 2: Create useAgentChat hook**

Create `frontend/src/hooks/useAgentChat.ts`:

```ts
import { useState, useCallback, useRef, useEffect } from 'react'
import type { AgentMessage, ToolActivity, HITLState, ServerMessage, ClientMessage } from '../types/agent'

const SESSION_KEY = 'agent_session_id'
const REHYDRATE_URL = '/api/agent/sessions'

interface UseAgentChatReturn {
  messages: AgentMessage[]
  activeTools: ToolActivity[]
  hitl: HITLState | null
  thinking: boolean
  connected: boolean
  sessionId: string | null
  send: (content: string) => void
  respondHITL: (approved: boolean) => void
  newConversation: () => void
}

export function useAgentChat(): UseAgentChatReturn {
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [activeTools, setActiveTools] = useState<ToolActivity[]>([])
  const [hitl, setHitl] = useState<HITLState | null>(null)
  const [thinking, setThinking] = useState(false)
  const [connected, setConnected] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const currentAssistantId = useRef<string | null>(null)

  // ── WebSocket connection ─────────────────────────────────────────

  const connect = useCallback((sid?: string) => {
    const params = sid ? `?session_id=${sid}` : ''
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/agent/chat${params}`)

    ws.onopen = () => setConnected(true)
    ws.onclose = () => {
      setConnected(false)
      // Reconnect after 2s
      setTimeout(() => {
        const storedSid = localStorage.getItem(SESSION_KEY)
        if (storedSid) connect(storedSid)
      }, 2000)
    }

    ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data)
      handleServerMessage(msg)
    }

    wsRef.current = ws
  }, [])

  // ── Message handling ─────────────────────────────────────────────

  const handleServerMessage = useCallback((msg: ServerMessage) => {
    switch (msg.type) {
      case 'session_started':
      case 'session_resumed':
        setSessionId(msg.session_id)
        localStorage.setItem(SESSION_KEY, msg.session_id)
        if (msg.type === 'session_resumed') {
          // Rehydrate messages
          fetch(`${REHYDRATE_URL}/${msg.session_id}/messages`)
            .then((r) => r.json())
            .then((data) => {
              const hydrated: AgentMessage[] = data.messages.map(
                (m: { role: string; content: string }, i: number) => ({
                  id: `rehydrated-${i}`,
                  role: m.role as 'user' | 'assistant',
                  content: m.content,
                  streaming: false,
                })
              )
              setMessages(hydrated)
            })
            .catch(() => {})
        }
        break

      case 'agent_thinking':
        setThinking(true)
        break

      case 'classifier_result':
        // Could display in UI — for now just log
        break

      case 'token': {
        setThinking(false)
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.id === currentAssistantId.current && last.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + msg.content },
            ]
          }
          const newId = `assistant-${Date.now()}`
          currentAssistantId.current = newId
          return [
            ...prev,
            { id: newId, role: 'assistant', content: msg.content, streaming: true },
          ]
        })
        break
      }

      case 'tool_start':
        setActiveTools((prev) => [
          ...prev,
          { tool: msg.tool, params: msg.params, duration_ms: null },
        ])
        break

      case 'tool_end':
        setActiveTools((prev) =>
          prev.filter((t) => t.tool !== msg.tool)
        )
        break

      case 'hitl_request':
        setThinking(false)
        setHitl({
          pending: true,
          tool: msg.tool,
          params: msg.params,
          reason: msg.reason,
          estimated_duration_ms: msg.estimated_duration_ms,
        })
        break

      case 'message_complete':
        setThinking(false)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === currentAssistantId.current ? { ...m, streaming: false } : m
          )
        )
        currentAssistantId.current = null
        break

      case 'error':
        setThinking(false)
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: `Something went wrong: ${msg.content}`,
            streaming: false,
          },
        ])
        break

      case 'ping':
        wsRef.current?.send(JSON.stringify({ type: 'pong' } satisfies ClientMessage))
        break
    }
  }, [])

  // ── Actions ──────────────────────────────────────────────────────

  const send = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: 'user', content, streaming: false },
    ])
    const msg: ClientMessage = { type: 'user_message', content }
    wsRef.current.send(JSON.stringify(msg))
  }, [])

  const respondHITL = useCallback((approved: boolean) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setHitl(null)
    const msg: ClientMessage = { type: 'hitl_response', approved }
    wsRef.current.send(JSON.stringify(msg))
  }, [])

  const newConversation = useCallback(() => {
    setMessages([])
    setActiveTools([])
    setHitl(null)
    setThinking(false)
    currentAssistantId.current = null
    localStorage.removeItem(SESSION_KEY)
    // Reconnect without session_id to get a new one
    wsRef.current?.close()
    connect()
  }, [connect])

  // ── Lifecycle ────────────────────────────────────────────────────

  useEffect(() => {
    const storedSid = localStorage.getItem(SESSION_KEY)
    connect(storedSid || undefined)
    return () => {
      wsRef.current?.close()
    }
  }, [connect])

  return {
    messages,
    activeTools,
    hitl,
    thinking,
    connected,
    sessionId,
    send,
    respondHITL,
    newConversation,
  }
}
```

- [ ] **Step 3: Verify build**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npx tsc --noEmit`

Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/agent.ts frontend/src/hooks/useAgentChat.ts
git commit -m "feat(frontend): add agent types and useAgentChat WebSocket hook"
```

---

### Task 12: AgentInput and AgentPanel layout

**Files:**
- Create: `frontend/src/components/AgentInput.tsx`
- Create: `frontend/src/components/AgentPanel.tsx`

- [ ] **Step 1: Create AgentInput**

Create `frontend/src/components/AgentInput.tsx`:

```tsx
import { useRef, useEffect } from 'react'

interface Props {
  onSubmit: (content: string) => void
  onFocus: () => void
  panelOpen: boolean
}

export default function AgentInput({ onSubmit, onFocus, panelOpen }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        if (panelOpen) {
          // Toggle off is handled by parent
          onFocus()
        } else {
          inputRef.current?.focus()
          onFocus()
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onFocus, panelOpen])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const input = inputRef.current
    if (!input || !input.value.trim()) return
    onSubmit(input.value.trim())
    input.value = ''
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 flex-1 max-w-sm">
      <input
        ref={inputRef}
        type="text"
        placeholder="Ask about your portfolio..."
        onFocus={onFocus}
        className="w-full bg-transparent text-sm text-txt-primary placeholder:text-txt-muted outline-none"
      />
      <kbd className="hidden sm:inline text-[10px] text-txt-muted border border-surface-border rounded px-1.5 py-0.5 font-mono">
        ⌘K
      </kbd>
    </form>
  )
}
```

- [ ] **Step 2: Create AgentPanel**

Create `frontend/src/components/AgentPanel.tsx`:

```tsx
import type { AgentMessage as AgentMessageType, ToolActivity, HITLState } from '../types/agent'
import AgentMessage from './AgentMessage'
import AgentToolStatus from './AgentToolStatus'
import AgentHITL from './AgentHITL'
import NewConversationButton from './NewConversationButton'
import { useEffect, useRef } from 'react'

interface Props {
  messages: AgentMessageType[]
  activeTools: ToolActivity[]
  hitl: HITLState | null
  thinking: boolean
  onRespondHITL: (approved: boolean) => void
  onNewConversation: () => void
  onSubmit: (content: string) => void
}

const EXAMPLE_QUERIES = [
  "How's my portfolio doing?",
  "Am I approaching any CGT thresholds?",
  "What's changed since last week?",
  "Would I have been better off just holding ETH?",
]

export default function AgentPanel({
  messages,
  activeTools,
  hitl,
  thinking,
  onRespondHITL,
  onNewConversation,
  onSubmit,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, activeTools, hitl, thinking])

  const isEmpty = messages.length === 0 && !thinking

  return (
    <aside className="w-[400px] shrink-0 border-l border-surface-border overflow-y-auto h-screen sticky top-0">
      <div className="px-4 pt-4 pb-2 flex items-center justify-between">
        <NewConversationButton onClick={onNewConversation} />
      </div>

      <div className="px-4 pb-6">
        {isEmpty ? (
          <div className="pt-8 space-y-3">
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onSubmit(q)}
                className="block w-full text-left text-sm text-txt-muted hover:text-txt-secondary transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        ) : (
          <div className="space-y-4 pt-2">
            {messages.map((msg) => (
              <AgentMessage key={msg.id} message={msg} />
            ))}

            {activeTools.map((tool) => (
              <AgentToolStatus key={tool.tool} activity={tool} />
            ))}

            {hitl && (
              <AgentHITL hitl={hitl} onRespond={onRespondHITL} />
            )}

            {thinking && activeTools.length === 0 && !hitl && (
              <div className="h-4 w-16 bg-surface-border rounded animate-pulse-subtle" />
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </aside>
  )
}
```

- [ ] **Step 3: Verify build**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npx tsc --noEmit`

Expected: Errors for missing AgentMessage, AgentToolStatus, AgentHITL, NewConversationButton (these are created in the next task). This is expected — proceed to Task 13.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AgentInput.tsx frontend/src/components/AgentPanel.tsx
git commit -m "feat(frontend): add AgentInput and AgentPanel layout components"
```

---

### Task 13: Message rendering components

**Files:**
- Create: `frontend/src/components/AgentMessage.tsx`
- Create: `frontend/src/components/AgentToolStatus.tsx`
- Create: `frontend/src/components/AgentHITL.tsx`
- Create: `frontend/src/components/NewConversationButton.tsx`

- [ ] **Step 1: Create AgentMessage**

Create `frontend/src/components/AgentMessage.tsx`:

```tsx
import Markdown from 'react-markdown'
import type { AgentMessage as AgentMessageType } from '../types/agent'

interface Props {
  message: AgentMessageType
}

export default function AgentMessage({ message }: Props) {
  if (message.role === 'user') {
    return (
      <p className="text-xs text-txt-muted font-sans">
        {message.content}
      </p>
    )
  }

  return (
    <div className="text-[15px] leading-relaxed text-txt-primary font-sans prose-invert max-w-none">
      <Markdown
        components={{
          table: (props) => (
            <table className="text-sm font-mono tabular-nums w-full" {...props} />
          ),
          th: (props) => (
            <th className="text-left text-xs text-txt-muted font-medium pb-1 pr-3" {...props} />
          ),
          td: (props) => (
            <td className="text-sm text-txt-primary py-0.5 pr-3 tabular-nums" {...props} />
          ),
        }}
      >
        {message.content}
      </Markdown>
      {message.streaming && (
        <span className="inline-block w-1.5 h-4 bg-txt-muted animate-pulse-subtle ml-0.5 align-text-bottom" />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create AgentToolStatus**

Create `frontend/src/components/AgentToolStatus.tsx`:

```tsx
import type { ToolActivity } from '../types/agent'

interface Props {
  activity: ToolActivity
}

function formatToolName(name: string): string {
  return name.replace(/^get_/, '').replace(/_/g, '_')
}

function formatParams(params: Record<string, unknown>): string {
  const entries = Object.entries(params)
  if (entries.length === 0) return ''
  return `(${entries.map(([, v]) => String(v)).join(', ')})`
}

export default function AgentToolStatus({ activity }: Props) {
  return (
    <div className="flex items-center gap-2 text-[11px] font-mono text-txt-muted overflow-hidden">
      <span className="whitespace-nowrap shrink-0">
        fetching → {formatToolName(activity.tool)}{formatParams(activity.params)}
      </span>
      <div className="flex-1 h-[2px] bg-surface-border rounded-full overflow-hidden">
        <div className="h-full bg-kraken/40 rounded-full animate-progress" />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create AgentHITL**

Create `frontend/src/components/AgentHITL.tsx`:

```tsx
import type { HITLState } from '../types/agent'

interface Props {
  hitl: HITLState
  onRespond: (approved: boolean) => void
}

export default function AgentHITL({ hitl, onRespond }: Props) {
  return (
    <p className="text-[15px] leading-relaxed text-txt-primary font-sans">
      {hitl.reason}{' '}
      <button
        type="button"
        onClick={() => onRespond(true)}
        className="text-txt-primary hover:underline hover:text-kraken transition-colors active:opacity-70"
      >
        Proceed
      </button>
      {' or '}
      <button
        type="button"
        onClick={() => onRespond(false)}
        className="text-txt-primary hover:underline hover:text-kraken transition-colors active:opacity-70"
      >
        cancel
      </button>
      .
    </p>
  )
}
```

- [ ] **Step 4: Create NewConversationButton**

Create `frontend/src/components/NewConversationButton.tsx`:

```tsx
interface Props {
  onClick: () => void
}

export default function NewConversationButton({ onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-xs text-txt-muted hover:text-txt-secondary transition-colors"
    >
      New conversation
    </button>
  )
}
```

- [ ] **Step 5: Add progress bar animation to globals.css**

Append to `frontend/src/globals.css`, inside the `@layer utilities` block:

```css
  .animate-progress {
    animation: progress 1.5s ease-in-out infinite;
  }
```

And add after the existing `@keyframes pulse-subtle` block:

```css
@keyframes progress {
  0% { width: 0%; }
  50% { width: 80%; }
  100% { width: 100%; }
}
```

- [ ] **Step 6: Verify build**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npx tsc --noEmit`

Expected: No type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/AgentMessage.tsx frontend/src/components/AgentToolStatus.tsx frontend/src/components/AgentHITL.tsx frontend/src/components/NewConversationButton.tsx frontend/src/globals.css
git commit -m "feat(frontend): add agent message rendering components"
```

---

### Task 14: Dashboard integration

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Wire agent panel into Dashboard**

Update `frontend/src/pages/Dashboard.tsx` to add the agent input to the header and the agent panel as a right column. Key changes:

1. Import `useAgentChat`, `AgentInput`, and `AgentPanel`
2. Add `panelOpen` state, toggle via `Cmd+K` and input focus
3. Wrap existing content in a flex layout — dashboard on the left, agent panel on the right
4. Add `AgentInput` to the header metadata row
5. Render `AgentPanel` when open

Replace the entire file with:

```tsx
import { useState, useEffect, useCallback, useMemo } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'
import SummaryBar from '../components/SummaryBar'
import type { Range } from '../components/SummaryBar'
import PortfolioLineChart from '../components/PortfolioLineChart'
import AssetBreakdown from '../components/AssetBreakdown'
import DCAHistoryTable from '../components/DCAHistoryTable'
import AgentInput from '../components/AgentInput'
import AgentPanel from '../components/AgentPanel'
import { useAgentChat } from '../hooks/useAgentChat'

interface DashboardErrors {
  summary?: string
  snapshots?: string
  dca?: string
}

interface DashboardState {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  dcaHistory: DCAEntry[]
  errors: DashboardErrors
}

function errMsg(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

const RANGE_DAYS: Record<Range, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '6M': 180,
  '1Y': 365,
  ALL: null,
}

function filterByRange(snapshots: PortfolioSnapshot[], range: Range): PortfolioSnapshot[] {
  const days = RANGE_DAYS[range]
  if (days === null) return snapshots
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snapshots.filter((s) => new Date(s.captured_at) >= cutoff)
}

export default function Dashboard() {
  const [state, setState] = useState<DashboardState>({
    summary: null,
    snapshots: [],
    dcaHistory: [],
    errors: {},
  })
  const [refreshing, setRefreshing] = useState(false)
  const [range, setRange] = useState<Range>('1M')
  const [panelOpen, setPanelOpen] = useState(false)

  const agent = useAgentChat()

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const errors: DashboardErrors = {}

    const [summaryResult, snapshotsResult, dcaResult] = await Promise.allSettled([
      fetchPortfolioSummary(),
      fetchSnapshots(),
      fetchDCAHistory(),
    ])

    const summary = summaryResult.status === 'fulfilled' ? summaryResult.value : null
    if (summaryResult.status === 'rejected') errors.summary = errMsg(summaryResult.reason)

    const snapshots = snapshotsResult.status === 'fulfilled' ? snapshotsResult.value : []
    if (snapshotsResult.status === 'rejected') errors.snapshots = errMsg(snapshotsResult.reason)

    const dcaHistory = dcaResult.status === 'fulfilled' ? dcaResult.value : []
    if (dcaResult.status === 'rejected') errors.dca = errMsg(dcaResult.reason)

    setState((prev) => ({
      summary: summary ?? prev.summary,
      snapshots: snapshots.length > 0 ? snapshots : prev.snapshots,
      dcaHistory: dcaHistory.length > 0 ? dcaHistory : prev.dcaHistory,
      errors,
    }))
    setRefreshing(false)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Cmd+K toggle
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setPanelOpen((prev) => !prev)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Close on Escape
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && panelOpen) {
        setPanelOpen(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [panelOpen])

  const { summary, snapshots, dcaHistory, errors } = state
  const filteredSnapshots = useMemo(() => filterByRange(snapshots, range), [snapshots, range])
  const hasAnyError = Boolean(errors.summary || errors.snapshots || errors.dca)
  const hasAnyData = summary !== null || snapshots.length > 0 || dcaHistory.length > 0

  function handleAgentSubmit(content: string) {
    setPanelOpen(true)
    agent.send(content)
  }

  return (
    <div className="flex min-h-screen bg-surface text-txt-primary font-sans">
      {/* Main dashboard content */}
      <main className="flex-1 min-w-0">
        {/* Hero: portfolio value + deltas + agent input */}
        {summary ? (
          <header className="px-6 pt-10 pb-8">
            <div className="max-w-7xl mx-auto">
              <p className="text-sm font-medium text-txt-muted mb-2">Portfolio value</p>
              <p className="text-hero font-bold text-txt-primary font-mono leading-none mb-5">
                {new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' }).format(summary.total_value_aud)}
              </p>

              {/* Metadata row with agent input */}
              <div className="flex items-center gap-6 text-xs text-txt-muted">
                <span>Updated {new Date(summary.captured_at).toLocaleString('en-AU', { timeZone: 'Australia/Sydney', dateStyle: 'short', timeStyle: 'short' })}</span>
                <span className="border-l border-surface-border h-4" />
                <AgentInput
                  onSubmit={handleAgentSubmit}
                  onFocus={() => setPanelOpen(true)}
                  panelOpen={panelOpen}
                />
              </div>
            </div>
          </header>
        ) : (
          <header className="px-6 pt-10 pb-8">
            <div className="max-w-7xl mx-auto">
              <p className="text-sm font-medium text-txt-muted mb-2">Portfolio value</p>
              <p className={`text-hero font-bold font-mono text-txt-muted ${!errors.summary ? 'animate-pulse-subtle' : ''}`}>
                {errors.summary ?? '—'}
              </p>
              {errors.summary && (
                <button type="button" onClick={refresh} disabled={refreshing} className="mt-4 text-xs text-kraken hover:text-kraken-light active:scale-[0.97] font-medium disabled:opacity-50 transition-[colors,transform]">
                  {refreshing ? 'Loading…' : 'Retry'}
                </button>
              )}
            </div>
          </header>
        )}

        {/* Stale-data banner */}
        {hasAnyError && hasAnyData && (
          <div className="bg-loss/10 border-b border-loss/20 px-6 py-2 text-sm text-loss" role="alert" aria-live="polite">
            <div className="max-w-7xl mx-auto flex items-center justify-between">
              <span>Refresh failed — showing cached data.</span>
              <button type="button" onClick={refresh} disabled={refreshing} className="px-3 py-1 bg-loss/20 hover:bg-loss/30 active:scale-[0.97] disabled:opacity-50 text-loss rounded text-xs font-medium transition-[colors,transform]">
                {refreshing ? 'Retrying…' : 'Retry'}
              </button>
            </div>
          </div>
        )}

        {/* Main content */}
        <div className="max-w-7xl mx-auto px-6">
          <div className="pt-2 pb-12">
            {snapshots.length > 0 ? (
              <PortfolioLineChart snapshots={filteredSnapshots} range={range} onRangeChange={setRange} />
            ) : errors.snapshots ? (
              <div className="text-base text-loss" role="status" aria-live="polite">Chart unavailable: {errors.snapshots}</div>
            ) : (
              <div className="text-base text-txt-muted py-8">No snapshot history yet — data appears after the first hourly capture.</div>
            )}
          </div>

          <div className="pb-12">
            {summary ? (
              <AssetBreakdown positions={summary.positions} />
            ) : errors.summary ? (
              <div className="text-base text-loss" role="status" aria-live="polite">Assets unavailable: {errors.summary}</div>
            ) : (
              <div className="text-base text-txt-muted animate-pulse-subtle">Loading…</div>
            )}
          </div>

          <div className="border-t border-surface-border pt-10 pb-16">
            {dcaHistory.length > 0 ? (
              <DCAHistoryTable entries={dcaHistory} />
            ) : errors.dca ? (
              <div className="text-base text-loss" role="status" aria-live="polite">DCA history unavailable: {errors.dca}</div>
            ) : (
              <div className="text-base text-txt-muted">No DCA history yet. Sync your Kraken trades to see purchase history.</div>
            )}
          </div>
        </div>
      </main>

      {/* Agent panel */}
      {panelOpen && (
        <AgentPanel
          messages={agent.messages}
          activeTools={agent.activeTools}
          hitl={agent.hitl}
          thinking={agent.thinking}
          onRespondHITL={agent.respondHITL}
          onNewConversation={agent.newConversation}
          onSubmit={handleAgentSubmit}
        />
      )}
    </div>
  )
}
```

Note: This replaces the existing `SummaryBar` usage in the header with an inline version that includes the `AgentInput`. The `SummaryBar` component can still be used if preferred — in that case, pass `AgentInput` as a child or prop. The existing `SummaryBar` component is not modified; the header is rebuilt inline to integrate the agent input. If you prefer to keep using `SummaryBar`, add an `agentInput` slot/prop to it instead.

- [ ] **Step 2: Verify build**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && npx tsc --noEmit && npm run build`

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): integrate agent panel into dashboard with Cmd+K toggle"
```

---

## Post-Implementation Verification

After all 14 tasks are complete, verify end-to-end:

1. **Backend starts:** `backend/.venv/bin/uvicorn backend.main:app` — check logs for MCP tools, checkpointer, and graph compilation.
2. **Frontend builds:** `cd frontend && npm run build`
3. **WebSocket connects:** Open browser dev tools → Network → WS, navigate to localhost:5173, press Cmd+K, type a message. Verify `session_started` and token streaming.
4. **Multi-turn context:** Ask "How's ETH doing this month?", then "What about SOL?" — second answer should carry "this month" forward.
5. **HITL:** Ask "Would I have been better off just holding ETH?" — should receive `hitl_request`, clicking Proceed should complete the comparison.
6. **Rehydration:** Reload the page — messages should reappear from checkpoint via REST endpoint.
7. **Run all backend tests:** `backend/.venv/bin/python -m pytest backend/tests/ -v`
