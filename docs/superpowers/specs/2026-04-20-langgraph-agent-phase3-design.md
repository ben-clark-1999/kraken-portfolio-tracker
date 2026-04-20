# Phase 3: LangGraph Portfolio Analyst Agent — Design Spec

## Overview

A read-only portfolio analyst agent powered by LangGraph, exposed via WebSocket at `/api/agent/chat`. The agent answers natural-language questions about the user's Kraken crypto portfolio by calling the MCP tool surface built in Phase 2 (11 tools, 3 resources). It streams responses token-by-token, routes queries through a classifier to specialised agent paths, and requires human-in-the-loop approval for expensive operations.

**Hard boundary:** This agent is read-only. It must never execute trades, move funds, or generate buy/sell recommendations. The underlying Kraken API key is scoped to read-only permissions. Trade execution is a deliberately separate future phase.

---

## 1. Graph Architecture

### Nodes

1. **classify_query** — LLM classifier (Haiku) that labels the user's query
2. **quick_agent** — Fast single-tool-call responses
3. **analysis_agent** — Multi-step analytical reasoning
4. **tax_agent** — CGT and ATO-aware analysis
5. **comparison_agent** — Counterfactual comparisons with HITL gate
6. **general_agent** — All tools, for vague/cross-category queries
7. **respond** — Format and send via WebSocket

All agent nodes use the model specified by `AGENT_MODEL` in `agent_config.py`.

### Classifier Output

The classifier returns structured output, not a single label:

```json
{
  "primary_category": "tax",
  "confidence": 0.92,
  "secondary_categories": ["analysis"]
}
```

Categories: `quick`, `analysis`, `tax`, `comparison`, `open`.

### Routing Logic

| Condition | Route | Log treatment |
|-----------|-------|---------------|
| `confidence >= 0.8`, no secondary `>= 0.5` | Specialised agent for `primary_category` | Normal |
| `confidence >= 0.8`, any secondary `>= 0.5` | `general_agent` | Log as `multi_category` |
| `confidence < 0.8` | `general_agent` | Log as `low_confidence` with full classifier output |

### Tool Subsets Per Path

| Path | Tools |
|------|-------|
| quick | get_portfolio_summary, get_balances, get_prices, get_dca_history, get_dca_analysis |
| analysis | get_balance_change, get_relative_performance, get_dca_analysis, get_snapshots |
| tax | get_unrealised_cgt, get_dca_analysis, get_balance_change |
| comparison | get_buy_and_hold_comparison, get_relative_performance |
| general | All 11 tools |

### HITL Placement

- **Comparison path:** Interrupt before any tool call. User must approve.
- **General path:** Interrupt before `get_buy_and_hold_comparison` or `get_relative_performance` with timeframe `>= 3M`.
- **Quick/analysis/tax paths:** No HITL.

HITL has **no timeout**. The graph state is checkpointed — HITL stays pending indefinitely until the user responds or starts a new conversation.

### Model Configuration

All model choices exposed via `backend/agent/agent_config.py`:

```python
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"
AGENT_MODEL = "claude-sonnet-4-5-20241022"  # or opus, configurable
```

Swappable without rewiring the graph.

---

## 2. System Prompts

### Shared Base Prompt (all agents inherit)

**Tone:** Conversational, direct, no filler. You're a portfolio analyst talking to the person who owns this portfolio.

**Currency:** Always AUD, never USD. Format with comma separators ($5,777.83).

**Dates/times:** AEST/AEDT, `Australia/Sydney` timezone. Use DD/MM/YYYY for display, not ISO. Never say "today" if the data is from yesterday — say "as of 19/04/2026".

**Numeric formatting:** AUD with comma separators ($5,777.83). Percentages to 2 decimal places. Crypto quantities to 4 decimal places (1.1682 ETH, not 1.168234 ETH).

**Citation rule:** Every answer involving prices or date ranges must cite the actual values and dates used in the body of the answer. After the answer, include a `Tools used: ...` line only if more than one tool was called.

**Multi-turn context:** If the user's question references prior context ("what about SOL?", "same for last week"), carry forward timeframes, assets, and comparison targets from previous turns. Never ask the user to restate context that's already in the conversation.

**Missing data handling:** If a tool returns incomplete data or a shorter window than requested, surface that clearly in the answer (e.g., "I only have snapshot data back to 15/04/2026, so this is a 5-day comparison, not 1M"). Never silently substitute a shorter window without telling the user.

**Error tone:** If a tool fails, acknowledge the failure in plain language, surface what cached data is available, and suggest retrying. Never expose raw error messages or HTTP status codes.

**Out-of-scope:** If asked for price predictions, trading signals, or anything outside the read-only analytical scope, decline clearly and explain what you *can* do instead.

**Read-only:** You have no ability to execute trades, move funds, or modify the portfolio. Don't suggest actions that imply you can.

### Path-Specific Appendices

**Quick:**
Minimum tool calls required — usually one, occasionally two if aggregating. No preamble, no "let me check." No `Tools used` suffix on quick-path answers.

**Analysis:**
You may chain 2-3 tool calls if needed. Summarise trends in plain language. When reporting performance over a period, state the start and end reference points explicitly. Instead of "+12% over 1M", say "up 12%, from $3,454 on 20/03/2026 to $3,868 on 20/04/2026".

**Tax:**
Cite the specific ATO rule you're applying (e.g., "CGT discount: asset held >12 months, per ATO schedule"). Show the math. If asked about tax in any framing, proactively flag any lot with `days_until_discount_eligible <= 30`, even if the user didn't specifically ask about that lot. The Australian tax year runs 1 July to 30 June. When the user references "this FY" or "tax year", interpret in Australian terms. Use `earliest_eligible_date` from the tool, not your own date arithmetic.

**Comparison:**
Explain what the comparison measures before showing results. State assumptions clearly (e.g., "this assumes you'd bought ETH at the daily close price on each DCA date"). If no timeframe is specified in a comparison question, default to 1M and state that assumption. The user draws their own conclusions — present data, not recommendations.

**General:**
You have all tools available. Pick sensible defaults for vague questions — prefer 1M timeframe if none specified. Don't ask clarifying questions unless genuinely ambiguous. For vague questions like "summarise my portfolio", produce at most 4-5 short paragraphs covering: current value and recent change, allocation, one notable observation (best/worst performer, approaching CGT threshold, DCA cadence issue), and anything the user should know. Don't produce full reports.

---

## 3. WebSocket Protocol

### Endpoint

`ws://localhost:8000/api/agent/chat?session_id={uuid}`

### Session IDs

UUID v4, always generated server-side. If `session_id` query param is omitted, a new session is created. If provided, the server loads checkpointed state for that session.

### Message Types

**Client → Server:**

```json
{ "type": "user_message", "content": "How's ETH doing?" }
{ "type": "hitl_response", "approved": true }
{ "type": "hitl_response", "approved": false }
{ "type": "ping" }
```

**Server → Client:**

```json
{ "type": "session_started", "session_id": "uuid-here" }
{ "type": "session_resumed", "session_id": "uuid-here" }
{ "type": "agent_thinking" }
{ "type": "classifier_result", "primary_category": "analysis", "confidence": 0.91 }
{ "type": "token", "content": "ETH" }
{ "type": "tool_start", "tool": "get_balance_change", "params": {"timeframe": "1M"} }
{ "type": "tool_end", "tool": "get_balance_change", "duration_ms": 342 }
{ "type": "hitl_request", "tool": "get_buy_and_hold_comparison", "params": {"asset": "ETH"}, "reason": "Fetches 2 years of daily OHLC price data for ETH and compares against your actual DCA buys. Returns whether all-in ETH would have outperformed your diversified strategy.", "estimated_duration_ms": 8000 }
{ "type": "message_complete" }
{ "type": "error", "error_type": "tool_failure|infrastructure|model|session_lost", "content": "..." }
{ "type": "pong" }
```

### Streaming Flow

1. User sends `user_message`
2. Server sends `agent_thinking` immediately
3. Server sends `classifier_result` with route and confidence
4. If tool call needed: `tool_start` → (tool executes) → `tool_end`
5. If HITL needed: `hitl_request` → wait for `hitl_response` (no timeout)
6. Agent reasoning streams as `token` messages
7. `message_complete` signals end of response

### Heartbeat

Ping/pong every 30 seconds. Server closes connections after 90 seconds of no pong.

### Error Types

| error_type | Frontend behaviour |
|------------|-------------------|
| `tool_failure` | Show error inline, continue conversation with cached data |
| `infrastructure` | Suggest retry |
| `model` | Degrade gracefully |
| `session_lost` | Force reconnect |

### Message Rehydration

`GET /api/agent/sessions/{session_id}/messages`

Returns the full conversation history from the checkpoint. Client calls this on page reload, new device, or cleared localStorage. WebSocket connect does not auto-replay messages.

---

## 4. Checkpointer & Persistence

### Approach

Use LangGraph's `PostgresSaver` with a direct `psycopg` connection to the Supabase Postgres database, bypassing the PostgREST client for checkpointer operations only. The rest of the app continues using supabase-py.

### Connection

- `SUPABASE_DB_URL` in `.env` — the **direct** Postgres connection string (`db.PROJECT_ID.supabase.co:5432`), **not** the pooler (`pooler.supabase.com:6543`). The pooler uses transaction-mode pooling which breaks prepared statements used by the checkpointer.
- Use `psycopg`'s connection pool with `max_size=5`. Supabase free tier has a 60-connection limit; the rest of the app uses the PostgREST client which doesn't consume connection slots.
- `SUPABASE_DB_URL` contains the database password with full DB access. Must be in `.gitignore`, never logged, redacted from error messages.

### Setup

Call `PostgresSaver.setup()` in the FastAPI lifespan handler at startup, alongside the scheduler. Not lazily on first WebSocket connection.

### Session Model

- `session_id`: UUID v4, generated server-side
- Thread config: `{"configurable": {"thread_id": session_id}}`
- No auto-expiry, no history caps
- "New conversation" = new UUID, fresh thread

### Message History Extraction

Wrap checkpoint state reading in a single helper: `extract_messages_from_checkpoint(state) -> list[dict]`. If LangGraph's internal state format changes across versions, the fix is one place.

### Tables

The checkpointer creates and owns: `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`. These are managed automatically by LangGraph — distinct from manually-created app tables (lots, snapshots, sync_log, ohlc_cache).

### Version Pinning

Pin `langgraph`, `langchain-core`, `langchain-mcp-adapters`, and `langchain-anthropic` precisely in `requirements.txt` (exact versions, not `>=`).

### Context Overflow (designed, not implemented day one)

The checkpointer schema supports this natively. When needed later, add a `summarize_history` node that fires when message count exceeds a threshold. It condenses older messages into a summary message and replaces them in state. No schema changes needed — graph modification only.

---

## 5. MCP Subprocess Management

### Single Shared Subprocess

One MCP subprocess for the entire application, spawned at FastAPI startup via the lifespan handler. Shared across all WebSocket sessions. Stored as a `MultiServerMCPClient` instance in FastAPI app state.

Tool calls are session-independent — the MCP server is stateless and doesn't know which session triggered the call.

### Spawn

Uses `langchain-mcp-adapters`' `MultiServerMCPClient` with stdio transport:
- Command: `backend/.venv/bin/python -m backend.mcp_server`
- CWD: project root

### Timeouts

| Layer | Timeout | Behaviour |
|-------|---------|-----------|
| Per-tool-call | 30 seconds | Treat as `service_timeout` error, surface to client, continue session |
| MCP responsiveness | 5 seconds | If subprocess doesn't acknowledge a request within 5s, treat as hung — trigger restart flow |

### Crash Handling

1. Tool call fails with subprocess/protocol error
2. Log with `error_type: mcp_protocol`, including tool name, params, traceback
3. Attempt one subprocess restart
4. If restart succeeds, retry the failed tool call
5. If restart fails, increment failure counter

### Restart Cooldown

Track `failure_count` and `last_failure_time` in FastAPI app state. If 3 failures within 5 minutes:
- Refuse further restarts for 5 minutes
- Surface persistent error: `error_type: infrastructure`, message: "Agent tools unavailable — please try again in a few minutes"
- Prevents thrashing when something is genuinely broken

### Structured Logging

```
[MCP] tool=get_balance_change params={"timeframe": "1M"} status=success duration_ms=342
[MCP] tool=get_unrealised_cgt params={} status=error duration_ms=1205 error_type=service error="KrakenServiceError: get_ticker_prices failed"
[MCP] tool=get_relative_performance params={"timeframe": "3M"} status=error duration_ms=50 error_type=mcp_protocol error="subprocess exited unexpectedly"
```

Distinguishes service errors (Kraken/Supabase call failed) from protocol errors (MCP plumbing broke).

### Cleanup

On server shutdown, the lifespan handler closes the `MultiServerMCPClient`, which terminates the subprocess.

---

## 6. Frontend Agent Panel

### Entry Point

A subtle text input embedded in the dashboard header. Placeholder: "Ask about your portfolio..." with a `Cmd+K` hint right-aligned. Clicking or pressing `Cmd/Ctrl+K` opens the agent panel and focuses the header input.

The header input is the **only** input. It stays in the header always. It never moves to the panel. User messages render in the panel; responses stream in below them.

No floating button. No chat icon. No unread indicator.

### Layout

When opened, a fixed 400px right column appears. Dashboard content reflows into the remaining space. A 1px hairline vertical rule in a muted surface colour separates the dashboard from the panel. Not a shadow, not a gradient — a single hairline.

No overlay, no backdrop dimming, no slide animation. The panel is part of the layout when open, absent when closed. Close via `Escape` or `Cmd/Ctrl+K` toggle. No X button.

### Message Rendering — Typography-Driven

| Element | Font | Size | Colour | Treatment |
|---------|------|------|--------|-----------|
| User input | Geist Sans | 12px | `text-txt-muted` | Left-aligned, no container. Reads like command history. |
| Agent response | Geist Sans | 15-16px | `text-txt-primary` | Full-width prose. Markdown: headings, tables, lists. Inline stats use `tabular-nums`. |
| Tool activity | Geist Mono | 11px | Subtle | Inline row: `fetching → get_balance_change(1M)` with 2px-height progress bar filling available width. On completion, row collapses to zero height over 150ms and is removed from DOM. |
| HITL prompt | Geist Sans | 15px | `text-txt-primary` | Inline prose: "Running this will fetch 2 years of historical data across 4 assets (~10s). Proceed or cancel." |

No message bubbles. No avatars. No "Agent" labels. No "Thinking..." text. No animated dots. Distinction between user and agent is purely typographic.

### HITL Button Treatment

"Proceed" and "cancel" are inline text. At rest: `text-txt-primary`, no underline, no border, no padding, no background. On hover: underline appears, purple accent colour. On click: 50ms colour flash. They read as inline text links, not buttons.

### Empty State

When the panel opens with no messages in the current session, render example queries in `text-txt-muted` as clickable prompts:

- "How's my portfolio doing?"
- "Am I approaching any CGT thresholds?"
- "What's changed since last week?"
- "Would I have been better off just holding ETH?"

Clicking one submits it immediately as if the user typed it.

### Components

| Component | Responsibility |
|-----------|---------------|
| `AgentInput` | Header-embedded input with `Cmd+K` hint. Always in header. Opens panel on focus. |
| `AgentPanel` | Fixed 400px right column with 1px hairline separator. Contains message stream. |
| `AgentMessage` | Single agent response rendered with `react-markdown`. |
| `AgentToolStatus` | Inline row with mono label + 2px progress bar. Self-removes on tool_end with 150ms collapse. |
| `AgentHITL` | Inline prose with proceed/cancel text links. |
| `NewConversationButton` | Minimal text button at top of panel. |

### Fonts

Geist Sans for prose and UI. Geist Mono for tool activity and numeric data. Added via `@fontsource/geist-sans` and `@fontsource/geist-mono`.

### WebSocket Hook

`useAgentChat` custom hook manages:
- WebSocket connection lifecycle
- Token accumulation into current assistant message
- HITL state (pending, approved, denied)
- Reconnection on disconnect
- Session ID in `localStorage`
- Rehydration via `GET /api/agent/sessions/{session_id}/messages` on mount

### Design Test

If someone screenshots the panel mid-response, it should look like a content panel showing portfolio analysis — not a chat widget. Reference aesthetic: Linear Asks, Arc Max sidebar, Raycast AI.

---

## 7. Day-One Query Surface

The agent must handle these query categories on day one. The graph is designed around these, not a theoretical superset.

### Quick Check-Ins (quick path, instant)

- "How much is my portfolio worth?"
- "When's my next buy?"
- "How much have I put in so far?"
- "What do I hold right now?"
- "How much did I spend on ETH in total?"

### Strategy Assessment (analysis path)

- "Am I up or down overall?"
- "How's ETH doing this month?"
- "Was last week good or bad for me?"
- "Has my strategy paid off?"
- "Which of my coins is doing best?"
- "Which one is dragging me down?"

### Tax Questions (tax path)

- "If I sold everything today, how much tax would I pay?"
- "Which of my buys are almost old enough for the CGT discount?"
- "Is there anything I should think about before June 30?"
- "Which buys would save me the most tax if I waited a bit longer to sell?"

### Counterfactual Comparisons (comparison path, HITL)

- "Would I have been better off just buying ETH and holding?"
- "What if I'd started a year earlier?"
- "Is DCA actually working for me, or would lump-sum have been better?"
- "Which of my buys was my best one? My worst?"

### Vague/Open-Ended (general path)

- "What's changed since last week?"
- "Give me the quick version of where I'm at."
- "Anything I should know?"
- "What's the most interesting thing about my portfolio right now?"

### Follow-Up Sequence (critical checkpointer test)

Must work in a single session without restating context:

1. "How's ETH been this month?"
2. "What about SOL?" — carries "this month" forward
3. "Which one was a better buy?" — carries both assets + timeframe
4. "Would I have been better off just buying the better one?" — carries everything, triggers buy-and-hold comparison

If turn 2 asks the user to restate the timeframe, the checkpointer is broken.

### Out of Scope (day one)

- Reports, documents, or anything longer-form than conversational answers
- Price predictions or trading signals
- Data the tools don't expose — news, sentiment, on-chain metrics
- Actions modifying state outside read-only scope

---

## 8. Dependencies

### Backend (add to requirements.txt, pinned exact versions)

- `langgraph` — graph framework
- `langchain-core` — base abstractions
- `langchain-anthropic` — Claude chat model
- `langchain-mcp-adapters` — MCP-to-LangChain tool bridge
- `psycopg[binary]` — direct Postgres connection for checkpointer

### Frontend (add to package.json)

- `react-markdown` — markdown rendering for agent responses
- `@fontsource/geist-sans` — prose typography
- `@fontsource/geist-mono` — mono typography for tool activity

### Environment (.env additions)

- `SUPABASE_DB_URL` — direct Postgres connection string (`db.PROJECT_ID.supabase.co:5432`), **not** the pooler. Contains DB password — never log, never commit.
- `ANTHROPIC_API_KEY` — for Claude API calls via langchain-anthropic.

---

## 9. File Structure

```
backend/
  agent/
    __init__.py
    agent_config.py        # Model choices, confidence thresholds, timeouts
    graph.py               # LangGraph graph definition (nodes, edges, routing)
    prompts.py             # Base + path-specific system prompts
    classifier.py          # Query classification node
    tools.py               # MCP client setup, tool-call logging wrapper
    checkpointer.py        # PostgresSaver setup, connection pool, message extraction
    websocket_handler.py   # FastAPI WebSocket endpoint, message protocol
  routers/
    agent.py               # REST endpoint: GET /api/agent/sessions/{id}/messages

frontend/src/
  components/
    AgentInput.tsx
    AgentPanel.tsx
    AgentMessage.tsx
    AgentToolStatus.tsx
    AgentHITL.tsx
    NewConversationButton.tsx
  hooks/
    useAgentChat.ts        # WebSocket connection, state management, rehydration
```
