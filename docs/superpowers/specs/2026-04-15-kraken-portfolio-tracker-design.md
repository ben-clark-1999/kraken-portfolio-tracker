# Kraken Portfolio Dashboard — Phase 1 Design Spec

**Date:** 2026-04-15
**Scope:** Phase 1 — Core portfolio tracker (local, read-only)
**Future phases:** MCP Server (2), LangGraph Agent (3), pgvector RAG (4), LangSmith (5)

---

## Overview

A personal crypto investment dashboard that connects to the Kraken exchange API to monitor and visualise an ETH/SOL/ADA portfolio in real-time. All values in AUD. Runs locally. Read-only — no order placement.

**Key decisions:**
- Cost basis: per-lot FIFO (supports future CGT calculations in Phase 4)
- Snapshots: hourly via APScheduler + on page load fallback
- Historical data: pulled via Kraken API on first run, then incrementally
- Backend architecture: service layer pattern (Phase 2 MCP reuse without refactoring)
- Deployment: local only (`localhost`)

---

## Architecture

### Runtime Topology

```
Browser (React/Vite :5173)
       ↕ HTTP (Vite proxy — no CORS config needed)
FastAPI (:8000)
  ├── Routers         (thin HTTP layer)
  ├── Services        (business logic)
  ├── APScheduler     (hourly snapshots, runs inside FastAPI process)
  └── Supabase client (PostgreSQL, ap-southeast-2)
       ↕
Kraken REST API (python-kraken-sdk)
```

### Project Structure

```
kraken-portfolio-tracker/
├── backend/
│   ├── main.py                    # FastAPI app, scheduler startup
│   ├── config.py                  # Env vars, settings
│   ├── scheduler.py               # APScheduler setup
│   ├── models/
│   │   ├── portfolio.py           # PortfolioSummary, AssetPosition, Allocation
│   │   ├── trade.py               # Trade, Lot, DCAEntry
│   │   └── snapshot.py            # PortfolioSnapshot
│   ├── services/
│   │   ├── kraken_service.py      # Balances, trades, tickers
│   │   ├── portfolio_service.py   # P&L, allocation %, cost basis
│   │   └── snapshot_service.py    # Supabase reads/writes
│   ├── routers/
│   │   ├── portfolio.py           # GET /api/portfolio/summary
│   │   ├── history.py             # GET /api/history/snapshots, /trades
│   │   └── sync.py                # POST /api/sync
│   ├── utils/
│   │   ├── aud.py                 # AUD formatting helpers
│   │   ├── timezone.py            # AEST/AEDT conversion
│   │   └── fifo.py                # Per-lot FIFO cost basis logic
│   └── db/
│       └── supabase_client.py     # Supabase client singleton
├── frontend/
│   ├── src/
│   │   ├── api/                   # Typed fetch wrappers
│   │   ├── components/            # UI components
│   │   ├── pages/
│   │   │   └── Dashboard.tsx      # Single page for Phase 1
│   │   ├── types/                 # TypeScript interfaces (mirror Pydantic models)
│   │   └── utils/
│   │       └── pnl.ts             # getPnlClass(value: number) helper
│   └── vite.config.ts             # Proxy: /api/* → localhost:8000
└── .env                           # API keys, Supabase credentials
```

---

## Data Model (Supabase)

### `lots`
One row per individual purchase. The FIFO backbone for all P&L and future CGT.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| asset | text | ETH, SOL, ADA |
| acquired_at | timestamptz | AEST |
| quantity | numeric | |
| cost_aud | numeric | Total AUD paid |
| cost_per_unit_aud | numeric | |
| kraken_trade_id | text UNIQUE | Prevents duplicate imports |
| remaining_quantity | numeric | Decremented on disposal |

### `portfolio_snapshots`
Append-only time-series. Never updated, only inserted.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| captured_at | timestamptz | AEST |
| total_value_aud | numeric | |
| assets | jsonb | `{ETH: {quantity, value_aud, price_aud}, ...}` |

### `sync_log`
Tracks API sync runs to support incremental syncing.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| synced_at | timestamptz | |
| last_trade_id | text | Resume point for next incremental sync |
| status | text | "success" or "error" |
| error_message | text | Null on success |

### `prices`
Cache of last-fetched ticker prices.

| Column | Type | Notes |
|--------|------|-------|
| asset | text PK | |
| price_aud | numeric | |
| fetched_at | timestamptz | |

---

## Backend Services

### `kraken_service.py`
Three async functions, each independently callable (Phase 2 MCP tools):

- `get_balances()` — current ETH/SOL/ADA quantities
- `get_ticker_prices(assets)` — live AUD prices (XETHZAUD, XSOLZAUD, ADAAUD pairs)
- `get_trade_history(since_trade_id=None)` — paginated trade history; full pull on first run, incremental after

On first run, `get_trade_history()` loops all pages. On subsequent runs, starts from `sync_log.last_trade_id`. If pagination fails mid-way, the last successfully processed `trade_id` is checkpointed — next sync resumes rather than restarts.

### `portfolio_service.py`
Pure calculation logic, no I/O:

- `calculate_summary(balances, prices, lots)` → `PortfolioSummary` — total AUD value, per-asset breakdown, allocation %, unrealised P&L (current value vs FIFO cost basis of remaining lots)
- `get_dca_history(lots, prices)` → list of `DCAEntry` — each lot with acquisition date, quantity, cost paid, current value, P&L

### `snapshot_service.py`
Supabase reads and writes:

- `save_snapshot(summary)` — inserts one row into `portfolio_snapshots`
- `get_snapshots(from_dt, to_dt)` — time-series data for line chart
- `should_snapshot()` — returns False if a snapshot already exists in the last hour (prevents duplicate on page load if scheduler already ran)

### `utils/fifo.py`
Isolated FIFO cost basis logic. Given a list of lots ordered by `acquired_at`, returns remaining quantity and total cost basis. Used by `portfolio_service.py` for unrealised P&L and by Phase 4 for CGT calculations.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio/summary` | Live balances + prices + P&L. Saves snapshot if `should_snapshot()` is True. |
| GET | `/api/history/snapshots` | Time-series rows. Query params: `from`, `to` (ISO timestamps). |
| GET | `/api/history/trades` | DCA history table data (all lots with current P&L). |
| POST | `/api/sync` | Manual trigger: pull latest trades from Kraken, upsert lots table. |

---

## Scheduler

`AsyncIOScheduler` starts inside `main.py` on FastAPI startup. One job runs every hour:

1. `kraken_service.get_ticker_prices()`
2. `portfolio_service.calculate_summary()`
3. `snapshot_service.save_snapshot()`

Failures are caught, logged, and written to `sync_log` with `status: "error"`. The scheduler continues running regardless.

---

## Frontend

### Components

**`Dashboard.tsx`** — fetches all three endpoints in parallel on mount via `Promise.allSettled` (so one failure doesn't block the others). Exposes `refreshDashboard()` called both on mount and on manual refresh.

| Component | Data source | Notes |
|-----------|-------------|-------|
| `SummaryBar` | `fetchPortfolioSummary()` | Total AUD, last updated, manual refresh button, next DCA date |
| `AllocationPieChart` | `fetchPortfolioSummary()` | Per-asset % (Recharts PieChart) |
| `PortfolioLineChart` | `fetchSnapshots(from, to)` | Toggle: total value vs per-asset lines. 7d/30d/all selector. |
| `AssetBreakdown` | `fetchPortfolioSummary()` | Asset, qty, price, value AUD, unrealised P&L (green/red) |
| `DCAHistoryTable` | `fetchDCAHistory()` | Date, asset, qty, cost paid, current value, P&L per lot (green/red) |

### Data Fetching

Three typed wrappers in `api/`:
- `fetchPortfolioSummary()` → `GET /api/portfolio/summary`
- `fetchSnapshots(from, to)` → `GET /api/history/snapshots`
- `fetchDCAHistory()` → `GET /api/history/trades`

TypeScript interfaces in `types/` mirror Pydantic models — kept flat, no complex generics.

### UX Details

- **Dark mode by default** — `dark` class on `<html>`, `bg-gray-900`/`text-gray-100` base
- **P&L colour coding** — `text-green-400` (positive) / `text-red-400` (negative). Shared `getPnlClass(value: number)` in `frontend/src/utils/pnl.ts`
- **Refresh button** — in `SummaryBar`, disables during fetch, shows spinner. Stale data remains visible while refreshing.
- **Next DCA date** — derived from `max(acquired_at) + 7 days` across DCA history data already in memory (weekly DCA cadence). Displayed in `SummaryBar`.
- **Chart toggle** — `PortfolioLineChart` local state: `"total"` renders one `<Line>`, `"per-asset"` renders three `<Line>` components (ETH/SOL/ADA). Per-asset data already present in snapshot JSONB.
- **Failed endpoint isolation** — one failed fetch in `Promise.allSettled` shows an inline error state for that section only; other sections render normally.

### Charting & Styling

- **Recharts** — PieChart for allocation, LineChart for portfolio value. Straightforward TypeScript support, minimal config.
- **Tailwind CSS** — utility classes, one `globals.css` for base styles, no per-component CSS files.

---

## Error Handling

### Backend

- Kraken API errors (rate limits, auth failures, timeouts) caught in `kraken_service.py`, raised as `KrakenServiceError`. Routers return structured JSON error responses — no raw stack traces.
- Supabase write failures in `snapshot_service.py` are logged and swallowed — portfolio data is still served. Persistence failure is non-fatal.
- Scheduler jobs wrap logic in try/except, write failures to `sync_log`. Scheduler keeps running.
- Mid-pagination sync failure checkpoints the last successful `trade_id` for resume on next run.

### Frontend

- `Promise.allSettled` fetches the three endpoints in parallel — one failure doesn't blank the dashboard or block the others.
- Failed sections show inline error state with retry option.
- Refresh button disables during fetch; stale data remains visible during refresh.

---

## Testing

### Backend

**`utils/fifo.py`** — thorough unit tests (pure logic, no I/O, errors silently corrupt all P&L):
- Single lot
- Multiple lots, partial remaining quantity
- Zero remaining quantity
- Mixed assets

**`portfolio_service.py`** — unit tests with mocked Kraken/Supabase responses. Verifies P&L, allocation %, and summary calculations.

**`kraken_service.py`** — one integration smoke test against live API, gated behind `KRAKEN_LIVE_TESTS=true`. Confirms auth and expected assets.

**Supabase tests** — run against a dedicated `test` schema. Each test run truncates all tables before starting and tears down on completion. No accumulating test data.

**Tooling:** `pytest` + `pytest-asyncio`

### Frontend

No component unit tests for Phase 1 — TypeScript strict mode provides compile-time correctness. Manual verification sufficient for the simple UI.

---

## Environment Variables

```
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
SUPABASE_URL=
SUPABASE_KEY=
KRAKEN_LIVE_TESTS=false   # Set to true to run live API integration tests
```

---

## Out of Scope (Phase 1)

- Order placement or any write operations to Kraken
- Authentication / multi-user support
- Mobile layout
- CSV import (API-only historical sync)
- Realised P&L / tax event tracking (Phase 4)
- MCP tools (Phase 2)
- Conversational agent (Phase 3)
