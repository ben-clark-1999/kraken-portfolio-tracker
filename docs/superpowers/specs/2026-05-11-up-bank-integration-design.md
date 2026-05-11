# UP Bank Integration — Design

**Date:** 2026-05-11
**Status:** Approved (brainstorming complete; awaiting user review of written spec)

## Goal

Extend the portfolio tracker so it tracks UP Bank cash alongside crypto, exposes
spending insights, and surfaces a combined net-worth view. The agent gains the
ability to answer questions about cash balances, cash flow, and spending
breakdowns.

## Scope

**In scope**

- Sync UP accounts and transactions (all-time history) via polling.
- Persist UP balances and transactions in Postgres alongside the existing
  crypto schema.
- Three navigable pages: `/combined`, `/crypto`, `/up`.
- Agent surface (5 new MCP tools) covering balances, cash flow, and spending
  by category.
- Combined net-worth chart that joins crypto + cash from a shared
  `portfolio_snapshots` table.

**Explicitly out of scope** (each would warrant a separate spec)

- Webhooks (chose polling for simplicity).
- 2Up shared-account accounting beyond display.
- Tags, categorisation edits, attachments.
- Budgets, savings goals.
- Merchant-level analysis, transaction search.
- Multi-currency cash (assumes AUD).
- Push notifications / alerts.

## User-facing decisions (locked)

| Decision | Choice |
|---|---|
| What does the integration do? | Full PFM-style dashboard UI; agent capabilities limited to balances/cash flow + spending breakdown. |
| Sync model | Polling (every 15 minutes). |
| Initial backfill | All available history. |
| Frontend nav | Sidebar with three routes (`/combined`, `/crypto`, `/up`). |
| Combined chart | Three overlaid lines (Total + Crypto + Cash). |
| Spending UI | Donut + ranked category list. |

## Architecture (Approach 3: shared snapshots, parallel everything else)

The single shared concept between crypto and UP is a *time-bucketed value
reading*. Everything else (lots vs transactions, OHLC vs spending categories)
is genuinely different and stays in domain-specific tables.

- `portfolio_snapshots` gains a `source` column (`crypto` | `up`).
- All UP-specific data lives in new `up_*` tables.
- Combined view = a single SQL query over `portfolio_snapshots` that groups
  by timestamp and pivots source values into separate columns
  (`SUM(value) FILTER (WHERE source='crypto') AS crypto`, etc.). No
  application-side stitching.

This keeps the existing crypto code path effectively untouched (one
defaulted column, no logic change) and isolates UP code in its own files.

## Data model

New migration: `supabase/migrations/005_up_bank.sql`.

### New tables

```sql
CREATE TABLE up_accounts (
  id              TEXT PRIMARY KEY,             -- UP UUID
  display_name    TEXT NOT NULL,
  account_type    TEXT NOT NULL,                -- TRANSACTIONAL | SAVER | HOME_LOAN
  ownership_type  TEXT NOT NULL,                -- INDIVIDUAL | JOINT
  balance_value   NUMERIC(20, 2) NOT NULL,
  balance_currency TEXT NOT NULL DEFAULT 'AUD',
  created_at      TIMESTAMPTZ NOT NULL,
  last_synced_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE up_categories (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  parent_id   TEXT REFERENCES up_categories(id)
);

CREATE TABLE up_transactions (
  id                 TEXT PRIMARY KEY,
  account_id         TEXT NOT NULL REFERENCES up_accounts(id),
  status             TEXT NOT NULL,             -- HELD | SETTLED
  description        TEXT NOT NULL,
  message            TEXT,
  raw_text           TEXT,
  amount_value       NUMERIC(20, 2) NOT NULL,   -- signed; negative = outflow
  amount_currency    TEXT NOT NULL DEFAULT 'AUD',
  category_id        TEXT REFERENCES up_categories(id),
  parent_category_id TEXT REFERENCES up_categories(id),  -- denormalised
  created_at         TIMESTAMPTZ NOT NULL,
  settled_at         TIMESTAMPTZ,
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_up_tx_created_at ON up_transactions(created_at DESC);
CREATE INDEX idx_up_tx_category   ON up_transactions(parent_category_id, created_at DESC);
CREATE INDEX idx_up_tx_account    ON up_transactions(account_id, created_at DESC);

CREATE TABLE up_sync_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_tx_at TIMESTAMPTZ,
  status          TEXT NOT NULL CHECK (status IN ('success', 'error', 'in_progress')),
  error_message   TEXT
);
```

### Existing-table change

```sql
ALTER TABLE portfolio_snapshots
  ADD COLUMN source TEXT NOT NULL DEFAULT 'crypto'
  CHECK (source IN ('crypto', 'up'));

CREATE INDEX idx_snapshots_source_captured
  ON portfolio_snapshots(source, captured_at DESC);
```

### Design notes

- `parent_category_id` denormalised on `up_transactions` because every
  category-aggregate query needs it; the parent never changes after ingest.
- Amounts stored as signed `NUMERIC(20, 2)` rather than UP's
  `valueInBaseUnits` cents-int — matches existing crypto conventions and
  simplifies SQL aggregation. Conversion happens at the client boundary.
- `up_transactions.id` uses UP's UUID directly so re-ingesting is an
  idempotent UPSERT (`ON CONFLICT (id) DO UPDATE`). HELD → SETTLED is a
  field update on the same row.
- `up_sync_log` mirrors the existing `sync_log` table.

## Sync layer

### New files

- `backend/services/up_client.py` — async HTTP wrapper.
- `backend/services/up_sync_service.py` — orchestrates sync.
- `backend/services/up_snapshot_service.py` — composes UP snapshot rows.
- `backend/repositories/up_accounts_repo.py`
- `backend/repositories/up_transactions_repo.py`
- `backend/repositories/up_categories_repo.py`
- `backend/repositories/up_sync_log_repo.py`

### `UpClient` interface

```python
class UpClient:
    BASE = "https://api.up.com.au/api/v1"

    def __init__(self, token: str): ...

    async def list_accounts(self) -> list[Account]: ...
    async def list_categories(self) -> list[Category]: ...
    async def list_transactions(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        status: Literal["HELD", "SETTLED"] | None = None,
    ) -> AsyncIterator[Transaction]: ...   # walks `next` links
```

Generator that auto-paginates. Honours `Retry-After` on 429 with exponential
backoff (1s, 4s, 16s; 3 retries). Uses `httpx.AsyncClient` with a 30s timeout.

### Sync flow

`up_sync_service.sync()` is a single entrypoint that branches on first-run vs
incremental based on whether `up_sync_log` has any prior successful row.

```python
sync_id = record_sync_start(status='in_progress')        # row visible to UI

try:
    if last_successful_sync is None:
        # FIRST RUN
        accounts = await client.list_accounts()
        upsert_accounts(accounts)
        categories = await client.list_categories()
        upsert_categories(categories)
        async for tx in client.list_transactions():       # all-time
            upsert_transaction(tx)
        finalize_sync(sync_id, success, last_seen_tx_at=newest_tx_created_at)

    else:
        # INCREMENTAL
        accounts = await client.list_accounts()
        upsert_accounts(accounts)
        overlap = last_seen_tx_at - timedelta(hours=6)    # catch HELD→SETTLED
        async for tx in client.list_transactions(since=overlap):
            upsert_transaction(tx)
        finalize_sync(sync_id, success, last_seen_tx_at=max(new_tx_created_at, prior))

except UpClientError as e:
    finalize_sync(sync_id, error, error_message=str(e))
```

The 6-hour overlap exists because a HELD transaction can settle hours after
its `createdAt`. Idempotent UPSERTs make the overlap safe.

The `in_progress` row is what `/api/up/sync/status` reads to drive the UI
banner. Only the most recent `up_sync_log` row is consulted.

### Snapshots

`up_snapshot_service.save_snapshot()` reads current `up_accounts` balances,
sums them, writes one row to `portfolio_snapshots` with `source='up'`. Hooked
into the existing hourly snapshot job in `scheduler.py` so crypto and UP
snapshots share timestamps:

```python
def _do_snapshot() -> None:
    crypto_summary = portfolio_service.build_summary()
    snapshot_service.save_snapshot(crypto_summary)        # source='crypto'
    up_snapshot_service.save_snapshot()                   # source='up'
```

### Schedule

- Existing hourly snapshot job → extended in place. No new schedule entry.
- New job: `up_sync_service.sync()` every **15 minutes**. Decoupled from
  the snapshot job so a long backfill cannot block snapshots.

UP sync runs on the same `AsyncIOScheduler`. UP HTTP I/O is async
(`httpx.AsyncClient`); the DB repo calls follow the existing crypto pattern
— sync `supabase-py` calls wrapped in `asyncio.to_thread` to avoid stalling
the event loop. (The async-native LangGraph checkpointer is the exception,
not a precedent we need to extend.) Implementation chooses the wrap point;
the requirement is that no scheduler tick blocks for more than a few
hundred ms on the loop thread.

### Initial backfill UX

First sync may take several minutes. To avoid blocking startup or the
scheduler thread:

- First sync runs in the background on the first scheduler tick (not in
  `lifespan`).
- `up_sync_log.status='in_progress'` lets the frontend display a banner
  while data streams in.

## REST API

`backend/routers/up.py`:

```
GET /api/up/accounts                              → list with current balances
GET /api/up/transactions?since,until,category,
    account,limit,cursor                          → paginated list
GET /api/up/spending/summary?since,until          → per-parent-category totals
GET /api/up/cashflow?since,until,granularity     → income/expense per period
GET /api/up/sync/status                           → {state, last_synced_at}
POST /api/up/sync/retry                           → manual retry trigger
```

`backend/routers/combined.py`:

```
GET /api/combined/snapshots?since                 → [{captured_at, crypto, up, total}]
GET /api/combined/summary                         → {crypto, up, total}
```

All routes gated by existing `require_auth`. No write endpoints other than
`/sync/retry` (which only enqueues a sync, doesn't accept data).

## Agent surface

### New MCP tools (`backend/mcp_server.py`)

```python
@mcp.tool()
def get_up_balance() -> str:
    """Current total cash across all UP accounts. AUD with per-account breakdown."""

@mcp.tool()
def get_up_spending_by_category(since: str, until: str) -> str:
    """Total spend (negative-amount transactions only) per parent category in
    the given date range. ISO dates."""

@mcp.tool()
def get_up_cashflow(since: str, until: str, granularity: str = "month") -> str:
    """Income vs expense per period. granularity: day | week | month."""

@mcp.tool()
def get_up_recent_transactions(limit: int = 10, since: str | None = None) -> str:
    """Most recent transactions across accounts — for grounding context.
    Not for transaction search."""

@mcp.tool()
def get_combined_net_worth() -> str:
    """Total net worth across crypto + UP cash. AUD with breakdown."""
```

Five tools total. Surface deliberately tight to keep agent prompt budget
contained.

### Classifier change

Add a new category to `backend/agent/classifier.py` and `prompts.py`:

```
cash: Anything about bank balances, spending, cash flow, "how much did
I spend on X", "how much money do I have", net worth across everything.
```

Routes to a new `cash_agent` node in `backend/agent/graph.py`. The node
loads only the 5 UP-related tools above. Existing crypto agents'
tool budgets unchanged.

The router's existing safety nets (low confidence → general; multiple
categories → general) automatically handle hybrid questions like "what's my
net worth and how did my crypto do this week" by falling through to the
generalist, which has every tool.

### Prompt extensions

- Small extension to `BASE_PROMPT` acknowledging UP cash as part of the
  user's broader financial picture.
- New `CASH_APPENDIX` with rules:
  - Spending figures are always over a date range; default to current
    calendar month if unspecified.
  - Don't speculate about transactions older than the sync horizon.
  - Cash balances are point-in-time, not a "return" — never compute %
    gains on cash.

## Frontend

### Routing

Add `react-router-dom`. Restructure `App.tsx`:

```tsx
<BrowserRouter>
  <AuthGate>
    <AppLayout>
      <Routes>
        <Route path="/"          element={<Navigate to="/combined" />} />
        <Route path="/combined"  element={<CombinedPage />} />
        <Route path="/crypto"    element={<CryptoPage />} />
        <Route path="/up"        element={<UpPage />} />
      </Routes>
    </AppLayout>
  </AuthGate>
</BrowserRouter>
```

`CryptoPage` is the existing `Dashboard.tsx` moved + lightly renamed.
The agent chat panel lives in `AppLayout` so it stays accessible across all
routes — the same conversation thread regardless of which view is active.

### New files

```
frontend/src/
  pages/
    CombinedPage.tsx      # KPI tiles + 3-line chart + sync status
    CryptoPage.tsx        # = current Dashboard, renamed
    UpPage.tsx            # accounts, donut, transactions
  components/
    AppLayout.tsx         # sidebar + main content + chat panel
    SidebarNav.tsx        # 3 links + active state
    up/
      AccountList.tsx
      SpendingDonut.tsx
      TransactionList.tsx
      SyncStatusBanner.tsx
    combined/
      NetWorthChart.tsx
      KpiTiles.tsx
  api/
    up.ts
    combined.ts
  hooks/
    useUpSyncStatus.ts    # polls /api/up/sync/status while syncing
```

All new files use the existing `apiFetch` from `api/client.ts`. No new auth
wiring.

### Loading & empty states

- **First-load skeleton** — same pattern as existing dashboard.
- **Sync in progress** — `SyncStatusBanner` shown when
  `/api/up/sync/status` returns `syncing`. UP page shows partial data as it
  streams in. `useUpSyncStatus` polls every ~10s while in this state.
- **Sync error** — banner with retry button hitting
  `POST /api/up/sync/retry`.

### Visual polish — separate concern

Structure and data flow defined here. Visual treatment (colours, spacing,
typography, chart styling, hover states, animations) handled by the
`impeccable` skill at implementation time, per project convention. The
mockups selected during brainstorming are layout direction only.

## Configuration

`backend/config/settings.py`:

```python
class Settings(BaseSettings):
    # ... existing fields ...
    up_pat: str
```

`UP_PAT` already present in `.env`.

## Error handling

| UP response | Handling |
|---|---|
| 200 | Process page, continue. |
| 401 | Token revoked/expired. Mark sync error, log, stop retrying. UI shows reconnect prompt. |
| 429 | Honour `Retry-After`. Sleep, retry once. If still 429, defer to next tick. |
| 5xx | Exponential backoff: 1s, 4s, 16s. After 3 tries, record error, defer. |
| Network timeout | Same as 5xx. |

`UpClient` raises typed exceptions per case. `up_sync_service` catches them,
records to `up_sync_log`, never lets them escape to the scheduler.

## Security

- `UP_PAT` loaded only via `Settings`. Never logged, never returned in any
  API response, never serialised into agent context. Add scrubbing in
  `error_handlers.py` to strip the token from any traceback.
- All `/api/up/*` and `/api/combined/*` routes gated by existing
  `require_auth`.
- No inbound webhook endpoint (polling chosen) → no signature verification
  needed.

## Testing

| Layer | File | Coverage |
|---|---|---|
| Unit | `backend/tests/test_up_client.py` | `httpx` mocked with `respx`. Pagination, 429 backoff, 401, parsing edges (HELD with no `settledAt`, foreign currency, transfers between own accounts). |
| Repository | `backend/tests/test_up_repos.py` | Test schema. UPSERT idempotency, HELD→SETTLED, sync-log bookmark. |
| Integration | `backend/tests/test_up_sync_service.py` | Full sync against mocked `UpClient`. First-run vs incremental branching, overlap window correctness. |
| Eval | `backend/evals/golden_set.yaml` | ~5 questions for the new `cash` category. Tests classifier accuracy + answer quality. |
| Frontend | `frontend/src/**/*.test.tsx` | API hooks (`useUpSyncStatus` polling), `CombinedPage` smoke render with mocked endpoints. |

## Migration safety

`005_up_bank.sql` only adds new tables and one defaulted column — no data
mutated. Rollback is `DROP` per table + `DROP COLUMN
portfolio_snapshots.source`. Existing crypto code has zero awareness of
`source` (queries without filtering pick up only crypto rows by virtue of
crypto being the only writer of that source).

## Open questions

None at present — all design decisions resolved during brainstorming.
