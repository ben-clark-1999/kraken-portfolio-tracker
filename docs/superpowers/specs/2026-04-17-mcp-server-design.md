# Kraken Portfolio Tracker — Phase 2 MCP Server Design Spec

**Date:** 2026-04-17
**Scope:** Phase 2 — MCP server exposing portfolio services as AI-callable tools and resources
**Depends on:** Phase 1 (complete)
**Future phases:** LangGraph Agent (3), pgvector RAG (4), LangSmith (5)

---

## Overview

A standalone MCP (Model Context Protocol) server that exposes the Phase 1 service layer as tools and resources consumable by any MCP-compatible AI client (Claude Code, Claude Desktop, Cursor, etc.). The server uses stdio transport and runs as a subprocess spawned by the client.

**Key decisions:**
- Standalone entry point (`backend/mcp_server.py`), not embedded in FastAPI
- stdio transport (standard for local MCP servers, required by Claude Code)
- Six tools (read + write operations) and two resources (ambient context)
- Async tool handlers wrapping sync services via `asyncio.to_thread()`
- Official `mcp` Python SDK for protocol handling
- Pre-cleanup: extract `build_summary()` helper, fix `upsert_lots` conflict behavior

---

## Architecture

### Runtime Topology

```
Claude Code (or any MCP client)
       ↕ JSON-RPC over stdio
MCP Server (backend/mcp_server.py)
  ├── Tool handlers       (thin wrappers)
  ├── Resource handlers   (thin wrappers)
  └── Services            (shared with FastAPI)
       ├── kraken_service.py
       ├── portfolio_service.py
       ├── snapshot_service.py
       └── sync_service.py
            ↕
Kraken REST API + Supabase (PostgreSQL)
```

The MCP server and FastAPI backend are independent processes. Both import the same service layer. They can run simultaneously without conflict — MCP uses stdio, FastAPI uses port 8000.

### Project Structure (new/modified files only)

```
backend/
├── mcp_server.py                  # NEW — MCP server entry point
├── services/
│   └── portfolio_service.py       # MODIFIED — add build_summary() helper
├── services/
│   └── sync_service.py            # MODIFIED — fix upsert_lots conflict
└── tests/
    └── test_mcp_server.py         # NEW — tool + integration tests
.claude/settings.json              # MODIFIED — add MCP server config
```

### New dependency

- `mcp` — official Python MCP SDK (pip install)

---

## Pre-Phase-2 Cleanup

Two items from the Phase 1 backlog that must be addressed before adding MCP tools.

### 1. Extract `build_summary()` helper

**Problem:** The orchestration `balances → prices → lots → calculate_summary` is duplicated in:
- `routers/portfolio.py` (GET /api/portfolio/summary)
- `scheduler.py` (_hourly_snapshot)

The MCP `get_portfolio_summary` tool would be a third copy. Three call sites with subtle divergence risk.

**Fix:** Add `build_summary()` to `portfolio_service.py`:

```python
def build_summary() -> PortfolioSummary:
    """Orchestrate balances, prices, lots into a full portfolio summary."""
    balances = kraken_service.get_balances()
    prices = kraken_service.get_ticker_prices(list(balances.keys()))
    lots = sync_service.get_all_lots()
    return calculate_summary(balances, prices, lots)
```

Update `routers/portfolio.py` and `scheduler.py` to call `build_summary()` instead of inlining the orchestration. The MCP tool will also call `build_summary()`.

### 2. Fix `upsert_lots` remaining_quantity conflict

**Problem:** `sync_service.upsert_lots()` does an unconditional upsert on `kraken_trade_id`, which resets `remaining_quantity` to the original quantity on conflict. Safe in Phase 1 (no sells), but the MCP `sync_trades` tool makes syncing easier and more frequent, increasing the risk of accidentally resetting a partially-disposed lot.

**Fix:** Switch to insert-only-if-new. Query existing `kraken_trade_id` values first, filter the trades list to only new ones, then insert (not upsert):

```python
def upsert_lots(trades: list[dict]) -> str | None:
    if not trades:
        return None
    db = get_supabase()
    trade_ids = [t["trade_id"] for t in trades]
    existing = db.table("lots").select("kraken_trade_id").in_("kraken_trade_id", trade_ids).execute()
    existing_ids = {row["kraken_trade_id"] for row in existing.data}
    new_trades = [t for t in trades if t["trade_id"] not in existing_ids]
    if not new_trades:
        return trades[0]["trade_id"]
    rows = [...]  # build rows from new_trades only
    db.table("lots").insert(rows).execute()
    return trades[0]["trade_id"]
```

This avoids the conflict entirely — existing lots (and their `remaining_quantity`) are never touched.

---

## Tools

Six tools registered with the MCP server. Each is a thin async wrapper that calls the existing service layer via `asyncio.to_thread()` (services are sync).

### get_portfolio_summary

- **Description:** Get current portfolio value, per-asset breakdown with quantities, AUD prices, values, cost basis, unrealised P&L, and allocation percentages.
- **Parameters:** none
- **Returns:** JSON object with `total_value_aud`, `positions` array, `captured_at`, `next_dca_date`
- **Service call:** `portfolio_service.build_summary()`

### get_balances

- **Description:** Get current crypto quantities held on Kraken, including staked and bonded positions.
- **Parameters:** none
- **Returns:** JSON object mapping asset names to quantities, e.g. `{"ETH": "0.9445", "SOL": "9.03", "ADA": "692.77"}`
- **Service call:** `kraken_service.get_balances()`

### get_prices

- **Description:** Get live AUD prices for tracked crypto assets from Kraken.
- **Parameters:**
  - `assets` (optional, array of strings) — asset names to query. Defaults to all tracked assets (ETH, SOL, ADA).
- **Returns:** JSON object mapping asset names to AUD prices
- **Service call:** `kraken_service.get_ticker_prices(assets)`

### get_dca_history

- **Description:** Get dollar-cost averaging history showing every individual purchase lot with acquisition date, quantity, cost paid, current value, and unrealised P&L.
- **Parameters:** none
- **Returns:** JSON array of DCAEntry objects
- **Service call:** `portfolio_service.get_dca_history(lots, prices)` — requires fetching lots and prices first

### get_snapshots

- **Description:** Get historical portfolio value snapshots for charting trends over time.
- **Parameters:**
  - `range` (optional, string) — one of "7d", "30d", "all". Defaults to "7d".
- **Returns:** JSON array of snapshot objects with `captured_at`, `total_value_aud`, `assets`
- **Service call:** `snapshot_service.get_snapshots(from_dt, to_dt)` — handler computes `from_dt` from the range parameter

### sync_trades

- **Description:** Pull latest trades from Kraken and sync to the database. Returns the number of new trades imported.
- **Parameters:** none
- **Returns:** JSON object with `new_trades_count`, `last_trade_id`, `status`
- **Service call:** Orchestrates `sync_service.get_last_synced_trade_id()` → `kraken_service.get_trade_history()` → `sync_service.upsert_lots()` → `sync_service.record_sync()` — same sequence as `POST /api/sync` router

### Error handling

All tool handlers wrap service calls in try/except. On failure, return a structured error via `mcp`'s error response mechanism with a human-readable message. Kraken API errors, Supabase errors, and unexpected exceptions are caught and reported — no raw stack traces exposed to the AI client.

---

## Resources

Two read-only resources that MCP clients can pull into conversation context.

### portfolio://summary

- **Description:** Current portfolio summary — total value, positions, P&L, allocations
- **MIME type:** application/json
- **Data:** Same output as `get_portfolio_summary` tool
- **Use case:** Claude loads this as ambient context at the start of a conversation. When you ask "should I rebalance?" Claude already knows your positions without calling a tool.

### portfolio://snapshots/7d

- **Description:** Portfolio value snapshots from the last 7 days
- **MIME type:** application/json
- **Data:** Same output as `get_snapshots` tool with range="7d"
- **Use case:** Gives Claude trend context passively — it can reference recent performance without being asked.

**Note:** Resources return point-in-time data. For live/refreshed data, the tools should be used instead.

---

## MCP Server Implementation

### Entry point: `backend/mcp_server.py`

```python
# Pseudocode structure — not final implementation
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("kraken-portfolio")

@server.tool()
async def get_portfolio_summary() -> dict:
    return await asyncio.to_thread(portfolio_service.build_summary)

# ... remaining tools ...

@server.resource("portfolio://summary")
async def portfolio_summary_resource() -> str:
    summary = await asyncio.to_thread(portfolio_service.build_summary)
    return json.dumps(summary, default=str)

# ... remaining resources ...

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)

if __name__ == "__main__":
    asyncio.run(main())
```

### Serialization

Pydantic models (PortfolioSummary, AssetPosition, DCAEntry, etc.) need to be converted to JSON-serializable dicts. Use `.model_dump()` on Pydantic models. Decimal values from Kraken services need `str()` or `float()` conversion — use `float()` for consistency with how Phase 1 already handles this in portfolio_service.

---

## Testing

### Unit tests for tool handlers (`backend/tests/test_mcp_server.py`)

Mock the service layer (kraken_service, portfolio_service, etc.) and verify each tool handler:
- Returns the expected JSON structure
- Passes parameters correctly to services
- Returns structured errors on service failure

Uses `pytest` + `pytest-asyncio`, consistent with Phase 1 test setup.

### Integration smoke test

One test that:
1. Starts the MCP server as a subprocess
2. Sends a `tools/list` JSON-RPC request over stdin
3. Verifies all six tools are registered with correct names and parameter schemas
4. Sends a `resources/list` request
5. Verifies both resources are registered

This confirms the server boots, speaks MCP, and has the expected tool/resource surface area. Does NOT call tools (that would hit live Kraken API).

### No live API tests

The service layer already has live Kraken test coverage from Phase 1. MCP tests only verify the wiring between MCP protocol and services.

---

## Claude Code Configuration

Add to project-level `.claude/settings.json`:

```json
{
  "mcpServers": {
    "kraken-portfolio": {
      "command": "python",
      "args": ["-m", "backend.mcp_server"],
      "cwd": "/Users/benclark/Desktop/kraken-portfolio-tracker"
    }
  }
}
```

Claude Code reads this on startup and spawns the MCP server subprocess automatically. Tools and resources appear in the tool list for the session.

---

## Out of Scope (Phase 2)

- Order placement / trading (Phase 3 — LangGraph agent)
- Conversational agent or multi-step reasoning (Phase 3)
- Embedding/RAG over portfolio history (Phase 4)
- Observability/tracing (Phase 5 — LangSmith)
- Authentication — local-only, single user
- SSE or HTTP transport — stdio is sufficient for local use
- MCP prompt templates — conversational intelligence belongs in Phase 3
