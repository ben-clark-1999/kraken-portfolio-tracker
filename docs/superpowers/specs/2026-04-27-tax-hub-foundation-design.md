# Tax Hub Foundation — Design Spec

**Status:** Draft for review
**Date:** 2026-04-27
**Sequel to:** Phase 4 (auth gate) — `docs/superpowers/specs/2026-04-26-login-component-design.md`
**Followed by:** Spec 2 — EOFY CGT Engine (separate spec, not yet written)

---

## 1. Overview

A new top-level "Tax" view in the Kraken Portfolio Tracker that serves as a personal tax workspace. The user logs three kinds of records — **income**, **tax paid**, and **deductible expenses** — each with optional file attachments (receipts, payslips, invoices). Records are organized by Australian financial year (Jul 1 → Jun 30) into a collapsible accordion. The tab also surfaces a **read-only summary of Kraken crypto activity** per FY, so the user can see capital deployment and deductibles in one place.

This is **Spec 1 of 2** for the Tax theme. Spec 2 (EOFY CGT Engine) will add FIFO disposal math, a CGT simulator, marginal-rate calculation, and ATO-formatted CSV export. Spec 1 builds the workspace + storage foundation that Spec 2 plugs into.

### Why this exists

The user wants:
- A single place to log and store tax-relevant records throughout the year (subscriptions, hardware, professional services, etc.) instead of fishing through email at EOFY.
- Visibility into Kraken purchases in a tax framing (per-FY AUD spent, per-asset breakdown) — context the existing Dashboard doesn't provide.
- Storage for receipts and supporting documents alongside the records they evidence.
- A foundation that the CGT Engine can plug into later.

---

## 2. Scope

### In scope (Spec 1)

- New `<TaxHub>` page (top-level view) with an FY accordion
- Persistent left **side rail** navigation replacing the current top-right header layout
- Three new entry tables: `tax_deductibles`, `tax_income`, `tax_paid`
- One attachment table: `tax_attachments` (polymorphic FK)
- One Supabase Storage bucket: `tax-attachments` (private, service-role only)
- New backend router: `/api/tax/*` with overview, CRUD, attachment proxy
- Read-only Kraken activity summary per FY (computed from existing `lots`)
- AU FY auto-derivation helper in both Python and TypeScript
- Polished frontend implementation built via the `/impeccable` skill
- Backend unit + integration tests; manual frontend smoke checklist

### Out of scope (deferred to Spec 2 or later)

- FIFO disposal math, realized-gain calculation
- CGT simulator panel ("what if I sold X today")
- Marginal-rate input / estimated tax owed
- ATO-formatted CSV export
- Per-FY disposal grouping for crypto sells
- Tax-deductible percentage (`claim_pct`) — entries are 100% claimable today
- Linking deductible entries to specific crypto lots (capital-acquisition cost basis)
- Recurring-entry templates ("clone this $20/mo subscription")
- Agent integration (no `log_tax_entry` MCP tool yet)
- Real-time bank/payslip imports (manual entry only)
- Soft-delete / audit log
- Frontend automated tests (matches established pattern)
- E2E browser tests (no Playwright/Cypress in repo)

### Design decisions log

| # | Decision | Reasoning |
|---|---|---|
| Q1 | Two-spec split (Foundation → Engine), not one big spec | Risk-stratified: low-stakes uploads ship before high-stakes ATO math. Matches Phase 1–4 cadence. Engine inherits real UX from Foundation. |
| Q2 | Structured entries with optional file attachments, single entry type per kind | "Deductibles" implies structured records, not just receipts. File-optional avoids forced choice between "data only" and "attach later". |
| Q3 | Tax tab shows Kraken activity (FY-framed read-only) + Income + Tax paid + Deductibles | User wants unified workspace. Kraken section is read-only because Dashboard owns the editable view. |
| Q4 | Left side rail (vertical icon-text), not top tabs | User chose more "real product" feel. Acknowledged trade-off: agent panel becomes overlay to avoid layout pinch. |
| Q5 | Fixed enum for deductible categories (6 buckets), not freeform tags | Personal use, single user. Tag freeform → mess over time. Enum editable in code. |
| Q6 | Lean field set: description, amount_aud, date, type, notes, attachments[]. No claim_pct, no asset link, no recurring flag. | YAGNI for Spec 1. Each excluded field has a clear future path if/when needed. |
| Q7 | FY accordion (current FY expanded, older collapsed) | Tax workflow IS the FY workflow. Per-FY totals visible at section headers. Primes the mental model for Spec 2. |
| Q8 | Inside an FY: summary strip + stacked sub-sections | Tab-inside-accordion is one nesting level too many. Stacked allows cross-section glances. |

---

## 3. Architecture

```
┌─────────────────────────┐    ┌─────────────────────────┐    ┌──────────────────────────┐
│ Frontend (React)        │    │ Backend (FastAPI)       │    │ Supabase                 │
│                         │    │                         │    │                          │
│ App.tsx                 │    │ main.py                 │    │ Postgres                 │
│  ├ auth state           │    │  ├ existing routers     │    │  ├ existing tables       │
│  ├ view: 'dashboard'    │    │  └ routers/tax.py NEW   │    │  ├ tax_deductibles NEW   │
│  │       | 'tax' NEW    │    │     ├ require_auth dep  │    │  ├ tax_income NEW        │
│  ├ <SideRail/> NEW      │    │     ├ /overview         │    │  ├ tax_paid NEW          │
│  ├ <Dashboard/>         │    │     ├ /{kind} CRUD      │    │  └ tax_attachments NEW   │
│  └ <TaxHub/> NEW        │    │     └ /attachments/*    │    │                          │
│     ├ <FYAccordion/>    │    │                         │    │ Storage                  │
│     └ <EntryDrawer/>    │    │ services/               │    │  └ tax-attachments NEW   │
│                         │    │  ├ tax_service.py NEW   │    │     (private bucket)     │
│ Cmd+K → AgentPanel      │    │  └ storage_service NEW  │    │                          │
│  (overlay, not push)    │    │                         │    │                          │
└────────────┬────────────┘    └────────────┬────────────┘    └──────────────────────────┘
             │ apiFetch (JWT cookie)         │ supabase-py + Storage SDK         ▲
             └───────────────────────────────┴────────────────────────────────────┘
```

**Key design points:**

- **Auth surface unchanged.** Every `/api/tax/*` endpoint uses the existing `Depends(require_auth)` dependency from Phase 4 (JWT cookie). No new auth code.
- **Frontend never talks to Supabase Storage directly.** All file ops go through the backend, which holds the service-role key. Files are returned to the browser via short-lived (5-minute) signed URLs.
- **Kraken activity is computed, not stored.** The Tax tab's read-only Kraken section reads `sync_service.get_all_lots()` and groups by FY in Python. No new Kraken API calls; no new tables for crypto data.
- **No new global state.** React `useState`/`useReducer` inside `<TaxHub>`, plus a `useTaxData()` hook for fetch+cache. Matches the existing app pattern.
- **No React Router.** App.tsx state machine extends from `auth` (existing) to also track `view`. Two views today, room for ~4 before this gets uncomfortable. If/when URLs need to reflect the active tab, revisit.

---

## 4. Data model

### Migration: `supabase/migrations/003_tax_hub.sql`

```sql
CREATE TABLE tax_deductibles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  description TEXT NOT NULL,
  amount_aud NUMERIC(20, 2) NOT NULL CHECK (amount_aud > 0),
  date_paid DATE NOT NULL,
  type TEXT NOT NULL CHECK (type IN (
    'software', 'hardware', 'professional_development',
    'professional_services', 'crypto_related', 'other'
  )),
  notes TEXT,
  financial_year TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_deductibles_fy ON tax_deductibles(financial_year, date_paid DESC);

CREATE TABLE tax_income (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  description TEXT NOT NULL,
  amount_aud NUMERIC(20, 2) NOT NULL CHECK (amount_aud > 0),
  date_received DATE NOT NULL,
  type TEXT NOT NULL CHECK (type IN (
    'salary_wages', 'freelance', 'interest', 'dividends', 'other'
  )),
  notes TEXT,
  financial_year TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_income_fy ON tax_income(financial_year, date_received DESC);

CREATE TABLE tax_paid (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  description TEXT NOT NULL,
  amount_aud NUMERIC(20, 2) NOT NULL CHECK (amount_aud > 0),
  date_paid DATE NOT NULL,
  type TEXT NOT NULL CHECK (type IN (
    'payg_withholding', 'payg_installment', 'bas_payment', 'other'
  )),
  notes TEXT,
  financial_year TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_paid_fy ON tax_paid(financial_year, date_paid DESC);

CREATE TABLE tax_attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_kind TEXT NOT NULL CHECK (parent_kind IN ('deductible', 'income', 'tax_paid')),
  parent_id UUID,                       -- NULL = pending upload not yet bound to an entry
  storage_path TEXT NOT NULL,           -- e.g. 'deductibles/2025-26/{uuid}.pdf' or 'PENDING/{uuid}.pdf'
  filename TEXT NOT NULL,               -- user-provided original name
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_attachments_parent ON tax_attachments(parent_kind, parent_id)
  WHERE parent_id IS NOT NULL;
CREATE INDEX idx_tax_attachments_pending ON tax_attachments(uploaded_at)
  WHERE parent_id IS NULL;
```

### Test schema mirror

`supabase/migrations/test_003_tax_hub.sql` creates the same four tables in the `test.*` schema for the integration test fixture. Mirrors the existing Phase 1 pattern.

### Pydantic models — `backend/models/tax.py`

```python
from enum import Enum
from pydantic import BaseModel, Field

class TaxEntryKind(str, Enum):
    DEDUCTIBLE = "deductible"
    INCOME = "income"
    TAX_PAID = "tax_paid"

class DeductibleType(str, Enum):
    SOFTWARE = "software"
    HARDWARE = "hardware"
    PROFESSIONAL_DEVELOPMENT = "professional_development"
    PROFESSIONAL_SERVICES = "professional_services"
    CRYPTO_RELATED = "crypto_related"
    OTHER = "other"

class IncomeType(str, Enum):
    SALARY_WAGES = "salary_wages"
    FREELANCE = "freelance"
    INTEREST = "interest"
    DIVIDENDS = "dividends"
    OTHER = "other"

class TaxPaidType(str, Enum):
    PAYG_WITHHOLDING = "payg_withholding"
    PAYG_INSTALLMENT = "payg_installment"
    BAS_PAYMENT = "bas_payment"
    OTHER = "other"

class TaxAttachment(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: str

class TaxEntry(BaseModel):
    id: str
    description: str
    amount_aud: float
    date: str          # date_paid or date_received, normalized
    type: str          # one of the enums above (string for cross-kind compat)
    notes: str | None
    financial_year: str
    attachments: list[TaxAttachment]
    created_at: str
    updated_at: str

class TaxEntryCreate(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    amount_aud: float = Field(gt=0)
    date: str          # ISO date
    type: str          # validated against the right enum in service layer
    notes: str | None = Field(default=None, max_length=4000)
    attachment_ids: list[str] = []

class TaxEntryUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=200)
    amount_aud: float | None = Field(default=None, gt=0)
    date: str | None = None
    type: str | None = None
    notes: str | None = Field(default=None, max_length=4000)

class KrakenFYActivity(BaseModel):
    total_aud_invested: float
    total_buys: int
    per_asset: dict[str, dict]   # {ETH: {aud_spent, buy_count, current_value_aud}, ...}

class FYOverview(BaseModel):
    financial_year: str
    income_total_aud: float
    tax_paid_total_aud: float
    deductibles_total_aud: float
    kraken_activity: KrakenFYActivity
```

### Storage bucket layout

```
tax-attachments/
├ deductibles/
│  ├ 2024-25/
│  │  ├ {uuid}.pdf
│  │  └ {uuid}.png
│  └ 2025-26/
│     └ ...
├ income/
│  └ {fy}/...
├ tax_paid/
│  └ {fy}/...
└ PENDING/                ← in-flight uploads, swept after 24h
   └ {uuid}.{ext}
```

---

## 5. Backend

### Endpoints — `backend/routers/tax.py`

All endpoints have `Depends(require_auth)` at router level (matches Phase 4 pattern).

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `GET` | `/api/tax/overview` | — | `list[FYOverview]` (one per FY with any data) |
| `GET` | `/api/tax/deductibles` | `?fy=2025-26` | `list[TaxEntry]` |
| `GET` | `/api/tax/income` | `?fy=2025-26` | `list[TaxEntry]` |
| `GET` | `/api/tax/paid` | `?fy=2025-26` | `list[TaxEntry]` |
| `POST` | `/api/tax/deductibles` | `TaxEntryCreate` | `TaxEntry` |
| `POST` | `/api/tax/income` | `TaxEntryCreate` | `TaxEntry` |
| `POST` | `/api/tax/paid` | `TaxEntryCreate` | `TaxEntry` |
| `PATCH` | `/api/tax/deductibles/{id}` | `TaxEntryUpdate` | `TaxEntry` |
| `PATCH` | `/api/tax/income/{id}` | `TaxEntryUpdate` | `TaxEntry` |
| `PATCH` | `/api/tax/paid/{id}` | `TaxEntryUpdate` | `TaxEntry` |
| `DELETE` | `/api/tax/deductibles/{id}` | — | `204` |
| `DELETE` | `/api/tax/income/{id}` | — | `204` |
| `DELETE` | `/api/tax/paid/{id}` | — | `204` |
| `POST` | `/api/tax/attachments` | multipart: `parent_kind`, `parent_id` (optional — omit for pending), `file` | `TaxAttachment` |
| `GET` | `/api/tax/attachments/{id}/url` | — | `{url: str, expires_at: str}` |
| `DELETE` | `/api/tax/attachments/{id}` | — | `204` |

### Service layer

**`backend/services/tax_service.py`**
```python
def get_overview() -> list[FYOverview]: ...
def get_entries(kind: TaxEntryKind, fy: str) -> list[TaxEntry]: ...
def get_entry(kind: TaxEntryKind, id: str) -> TaxEntry: ...   # raises EntryNotFoundError
def create_entry(kind: TaxEntryKind, payload: TaxEntryCreate) -> TaxEntry: ...
def update_entry(kind: TaxEntryKind, id: str, patch: TaxEntryUpdate) -> TaxEntry: ...
def delete_entry(kind: TaxEntryKind, id: str) -> None: ...     # cascades attachments
def get_kraken_activity_by_fy() -> dict[str, KrakenFYActivity]: ...
```

`get_kraken_activity_by_fy()` reads `sync_service.get_all_lots()`, groups by `financial_year_from(lot.acquired_at)`, sums per-asset, and pulls current prices from `kraken_service.get_ticker_prices()` for `current_value_aud`.

**`backend/services/storage_service.py`**
```python
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB

def upload_attachment(parent_kind: str, parent_id: str | None, file: UploadFile) -> TaxAttachment: ...
def create_signed_url(attachment_id: str) -> tuple[str, datetime]: ...
def delete_attachment(attachment_id: str) -> None: ...
def sweep_pending_attachments(older_than_hours: int = 24) -> int: ...   # APScheduler job
```

`upload_attachment` validates size + content-type, generates a UUID filename + extension, uploads to Supabase Storage, then inserts the `tax_attachments` row. If the entry doesn't exist yet, `parent_id` is `NULL` and the storage path lives under `PENDING/`; the entry-create endpoint rebinds `parent_id` and moves the storage object to its final FY-namespaced path.

### FY helper — `backend/utils/financial_year.py`

```python
from datetime import date

def financial_year_from(d: date) -> str:
    """AU FY: starts July 1. Date in [Jul 1 YYYY, Jun 30 YYYY+1] -> 'YYYY-YY'."""
    if d.month >= 7:
        start = d.year
    else:
        start = d.year - 1
    end_short = (start + 1) % 100
    return f"{start}-{end_short:02d}"
```

### Scheduler addition — `backend/scheduler.py`

Add one APScheduler job:
- `storage_service.sweep_pending_attachments` — runs every 6 hours, deletes orphan PENDING attachments older than 24 hours

### Custom exceptions

```python
# backend/services/tax_service.py
class TaxServiceError(Exception): ...
class EntryNotFoundError(TaxServiceError): ...

# backend/services/storage_service.py
class StorageServiceError(Exception): ...
class AttachmentValidationError(StorageServiceError): ...   # 413 / 415
class StorageBackendError(StorageServiceError): ...          # 502
```

Routers translate exceptions to HTTPException; uncaught → 500.

---

## 6. Frontend

> **Non-functional requirement (NFR):** All frontend implementation tasks in this spec MUST be executed via the `/impeccable` skill. The `/impeccable` skill produces distinctive, production-grade UI that avoids generic AI aesthetics — kraken-purple accents, atmospheric dark mode, thoughtful micro-interactions, polish on hover/focus/transitions. Do not write raw Tailwind/React for visual components without invoking `/impeccable` first.

### Component tree

```
App.tsx (existing — modified)
├ <SideRail />                          NEW
└ <main>
   ├ <Dashboard />                      existing — drop SignOutButton from header
   └ <TaxHub />                         NEW
      ├ <FYAccordion />                 NEW
      │  └ <FYSection /> × N            NEW
      │     ├ <FYSummaryStrip />        NEW
      │     ├ <KrakenActivityRow />     NEW
      │     └ <EntryList kind={...} /> × 3   NEW
      └ <EntryDrawer />                 NEW
         ├ <FileDropZone />             NEW
         └ <AttachmentChip /> × N       NEW
   <AgentPanel />                       existing — repositioned to overlay
```

### File layout

```
frontend/src/
├ pages/
│  └ TaxHub.tsx                         NEW
├ components/
│  ├ SideRail.tsx                       NEW
│  └ tax/                               NEW dir
│     ├ FYAccordion.tsx
│     ├ FYSection.tsx
│     ├ FYSummaryStrip.tsx
│     ├ KrakenActivityRow.tsx
│     ├ EntryList.tsx
│     ├ EntryDrawer.tsx
│     ├ FileDropZone.tsx
│     ├ AttachmentChip.tsx
│     └ Toast.tsx                       NEW (general — not tax-specific, but no other consumer yet)
├ hooks/
│  └ useTaxData.ts                      NEW
├ api/
│  └ tax.ts                             NEW
└ utils/
   └ financialYear.ts                   NEW (mirrors backend helper)
```

### Modified existing components

- **`App.tsx`** — add `view: 'dashboard' | 'tax'` state, render `<SideRail>` whenever authenticated, switch between `<Dashboard>` and `<TaxHub>`.
- **`Dashboard.tsx`** — remove `<SignOutButton>` from header (relocates to side rail). Agent input pill stays.
- **`AgentPanel.tsx`** — change positioning from "slide-in pushing content" to "fixed overlay above content" so it doesn't compete with the side rail.

### Right-side panel coexistence

Two right-side panels exist after this spec: the agent panel (overlay) and the entry drawer (slide-in for create/edit). They are **mutually exclusive**: opening one closes the other. State is held in `App.tsx` so both panels see each other:

- Cmd+K opens agent panel → if drawer is open, it closes first (with a "Discard N uploaded files?" prompt if there are unsaved attachments)
- Clicking "+ Add" opens entry drawer → if agent panel is open, it closes
- Both share `z-50`; only one ever rendered at a time. No layered stacking.

### Side rail

- Width: 200px, persistent, always shown when authenticated
- Top: small "Kraken" wordmark in kraken-purple
- Items: `Dashboard`, `Tax` — each is icon + label, vertical stack
- Bottom: relocated `<SignOutButton>`
- Active state: kraken-purple-tinted background + left-edge accent
- All visual treatment via `/impeccable`

### State

`<TaxHub>` owns:
- `overview: FYOverview[] | null`
- `entriesByFY: Record<fy, {deductibles?, income?, tax_paid?}>` (lazy-loaded on accordion expand)
- `expandedFYs: Set<string>` (current FY auto-included on first render)
- `drawer: { open: boolean, mode: 'create' | 'edit', kind: TaxEntryKind, entryId?: string }`

`useTaxData()` hook encapsulates fetch + cache + revalidate-on-mutation.

### API client — `frontend/src/api/tax.ts`

Wraps `apiFetch` (Phase 4 wrapper) for all endpoints. Multipart uploads use `FormData`. Handles `UNAUTHORIZED_EVENT` automatically via the wrapper.

### Empty states

- **No FYs with any data**: TaxHub-level "First-run" card with CTA to add an entry (kind picker)
- **Empty FY sub-section**: "No income for FY 2025–26 · + Add" inline link
- **Loading**: skeleton rows in `<EntryList>`, shimmer on summary strip

---

## 7. Data flow

Three flows worth detailing. Standard CRUD elided.

### Flow A — Initial Tax tab load

1. User clicks "Tax" in `<SideRail>` → `setView('tax')`
2. `<TaxHub>` mounts → `fetchOverview()` immediately
3. Backend issues 3 GROUP-BY queries (one per entry table, summing by FY) + 1 query against `lots` for Kraken activity
4. Frontend renders `<FYAccordion>`, all FYs collapsed
5. Current FY auto-expands → triggers `fetchEntries()` × 3 in parallel
6. Entry lists render

### Flow B — Create deductible with attachment(s)

1. User clicks "+ Add" on Deductibles section → drawer slides in, kind preselected
2. User drags PDF onto `<FileDropZone>` → upload starts immediately:
   - `POST /api/tax/attachments` with `parent_kind=deductible`, no `parent_id`, `file`
   - Backend validates size + content-type. Invalid → 413 / 415. Frontend shows inline error.
   - Backend uploads to `tax-attachments/PENDING/{uuid}.pdf`, inserts `tax_attachments` row with `parent_id = NULL`, returns `TaxAttachment`
   - Frontend stores attachment in component state, renders `<AttachmentChip>` with progress→done state
3. User fills the form, clicks Save
4. Frontend: `POST /api/tax/deductibles` with payload including `attachment_ids: [id1, id2, ...]`
5. Backend service:
   - Computes `financial_year` from `date_paid`
   - INSERT into `tax_deductibles` → returns new `id`
   - UPDATE `tax_attachments SET parent_id={new_id} WHERE id IN (...) AND parent_id IS NULL`
   - For each rebound attachment: move Storage object from `PENDING/{uuid}.ext` to `deductibles/{fy}/{uuid}.ext`, update `storage_path`
   - Return full entry with attachments
6. Frontend closes drawer, prepends entry to list, fires success toast

**Why upload-before-save:** validation feedback is instant; user doesn't lose upload progress if they hesitate on the form; sweep job cleans up abandoned NULL-parent uploads after 24h.

### Flow C — Viewing an attachment

1. User clicks `<AttachmentChip>`
2. Frontend: `GET /api/tax/attachments/{id}/url`
3. Backend: validates JWT, calls Supabase Storage SDK to mint a 5-minute signed URL, returns `{url, expires_at}`
4. Frontend: `window.open(url, '_blank')` — works for both PDFs and images

---

## 8. Error handling

### Backend

- **Error response**: existing `HTTPException(detail=...)` pattern; no new envelope
- **Service errors**: `EntryNotFoundError → 404`, `AttachmentValidationError → 413/415`, `StorageBackendError → 502`
- **Logging**: INFO on success (method, path, ids), WARN on validation failure, ERROR on uncaught with traceback
- **Sweep job**: logs INFO with count of swept items each run

### Frontend

- **`<Toast>` component (NEW)**: bottom-right, auto-dismiss after 4s, kraken-purple for success, loss-red for error. Built via `/impeccable`.
- **Triggers**: entry created/updated/deleted (success), network failure (error with retry CTA), reverted optimistic delete (error)
- **Inline errors**: form validation errors render next to their field, not as toasts
- **Skeleton failures**: list-fetch failure → "Couldn't load — retry" button in section header (Dashboard pattern)
- **No global error boundary** in Spec 1 — matches existing app, deferred enhancement

### Specific error scenarios

| Scenario | Behavior |
|---|---|
| JWT expired mid-session | `apiFetch` fires `UNAUTHORIZED_EVENT`, App.tsx returns to Login |
| Network drop during upload | `<AttachmentChip>` shows error state with retry button; entry can still save without it |
| Drawer closed with pending uploads | Confirm dialog "Discard N uploaded files?" → if discard, backend hard-deletes pending attachments |
| Save fails after attachments uploaded | Drawer stays open, attachments remain unbound (`parent_id IS NULL`); sweep job cleans up if abandoned |
| Edit changes date across FY boundary | Service layer recomputes `financial_year`; frontend refetches affected FY sections |
| Delete entry | Service layer fetches attachments, deletes Storage objects in batch, then DB rows, then entry — single transactional service function |
| Storage upload to Supabase fails | Backend catches `StorageException`, returns 502; frontend retries with exponential backoff up to 3 tries |

---

## 9. Testing

### Backend unit tests (`backend/tests/`)

- **`test_financial_year.py`** — boundary cases (Jul 1, Jun 30, Dec 31, Jan 1), leap year, distant past/future
- **`test_tax_service.py`** — mocked `get_supabase()`. Covers create/update/delete per kind, FY recompute on date change, cascade-delete attachment behavior, overview aggregation, Kraken activity grouping
- **`test_storage_service.py`** — mocked Supabase Storage SDK. Covers size + content-type validation, storage-path construction, signed-URL minting, delete ordering with rollback
- **`test_tax_router.py`** — FastAPI `TestClient` with mocked services. Covers auth requirement, CRUD round-trips per kind, multipart attachment handling, cascade-delete

### Backend integration tests

- **`test_tax_integration.py`** — real Supabase connection, `test.*` schema (Phase 1 pattern with `clean_test_tables` fixture). Covers full create-read-update-delete on each entry table; multi-FY overview aggregation; migration applies cleanly

Storage SDK is **not** integration-tested — mocked-only. Real Storage tests are flaky and the SDK contract is stable.

### Frontend tests

No automated frontend tests for Spec 1 — matches the existing pattern. Manual smoke checklist in the implementation plan, run on the live app before each task is marked complete:

1. Side rail renders, both items click and switch view
2. Empty Tax tab shows the first-load card
3. + Add deductible → drawer opens → fill form (no file) → save → row appears
4. Edit that entry → change amount → save → row updates
5. Add attachment → upload, chip shows, save persists; refresh page → still there
6. Click attachment chip → opens in new tab with valid 5-min URL
7. Delete entry → row disappears immediately; reload confirms gone
8. Add entries across 2+ FYs → both sections appear with correct totals
9. Older FY collapsed by default, expand → entries load
10. Switch to Dashboard and back to Tax preserves expanded-FY state
11. Cmd+K opens agent panel as overlay (not a slide-in pushing content)
12. Sign out from side rail returns to login
13. Wrong-type upload (e.g., .exe) → inline error
14. Oversized upload (>10 MB) → inline error
15. Income and Tax-paid sections behave parallel to Deductibles

---

## 10. Non-functional requirements

- **Frontend implementation MUST use `/impeccable`** for any visual/interactive component. Distinctive design quality, no generic AI aesthetics.
- **Currency**: AUD throughout (matches existing app)
- **Timezone**: AEST/AEDT via `Australia/Sydney` IANA zone (matches existing app); but FY logic is date-only so timezone is largely incidental
- **Auth**: JWT cookie, existing `require_auth` dependency on every endpoint
- **File constraints**: 10 MB per file max, content-type whitelist (image/jpeg, image/png, image/webp, application/pdf)
- **Signed URL lifetime**: 5 minutes
- **Pending-upload sweep**: every 6 hours, deletes orphans older than 24 hours
- **Migration order**: `003_tax_hub.sql` follows `001_create_tables.sql` and `002_create_test_schema.sql`. Test-schema mirror is `test_003_tax_hub.sql`.
- **Per-task push**: every implementation task ends with a `git push` to `origin/main` so the user can review each commit (established workflow)

---

## 11. Future work — Spec 2 preview

Not part of this spec, but the Foundation is shaped to accommodate:

- **CGT engine**: a new `tax_disposals` table (or virtual disposals computed from a future `lots.disposals` extension). `get_unrealised_cgt()` already exists and works on the existing `lots` schema.
- **Simulator panel**: lives in a new "Disposals" sub-section in each FY accordion (or its own page — that decision is for Spec 2's brainstorming, not this spec)
- **Marginal-rate calc**: a single user setting (their AU bracket) plus computed taxable amount
- **ATO CSV export**: a backend endpoint emitting per-FY CSV grouped by lot
- **Linking deductibles to crypto cost basis**: optional `linked_lot_id` on `tax_deductibles` rows (additive migration)
- **Recurring entry templates**, **agent integration** (`log_tax_entry` MCP tool), and **bank/payslip import** are still further out

Spec 2 will be brainstormed and written as a separate cycle once Spec 1 is shipped and lived-with.

---

## 12. Deferred to implementation plan

Resolved by `writing-plans`, not by this spec:

- **Task decomposition and ordering.** The expected shape is backend-first (migration → service → router → scheduler) then frontend (App routing → side rail → TaxHub shell → FYAccordion → EntryDrawer → upload flow → polish). Final granularity is a planning decision.
- **`<Toast>` task placement.** Either the first frontend task (preliminary infrastructure) or bundled with whichever component first triggers a toast.
- **Side rail icon source.** `/impeccable` chooses during implementation — Lucide, Heroicons, or hand-built SVG depending on what fits the aesthetic best.

---

**End of spec.**
