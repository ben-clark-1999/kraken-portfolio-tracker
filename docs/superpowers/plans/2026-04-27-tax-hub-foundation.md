# Tax Hub Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Tax Hub Foundation (Phase 5 / Spec 1) — a new top-level "Tax" view with FY-grouped income/tax-paid/deductibles tracking, file attachments via Supabase Storage, side rail navigation, and a read-only Kraken activity summary per FY.

**Architecture:** Backend-first. Three parallel entry tables + one polymorphic attachment table + one Supabase Storage bucket. Service layer (`tax_service`, `storage_service`) holds business logic; thin FastAPI router translates to HTTP. Frontend adds a `<SideRail>` to `App.tsx`, a new `<TaxHub>` page with FY accordion, and an `<EntryDrawer>` for create/edit. All visual work invokes `/impeccable`. Per-task push-to-main per established workflow.

**Tech stack:** Python 3.13, FastAPI, supabase-py, supabase-storage SDK, APScheduler, pytest, React 19, TypeScript, Tailwind v3.

**Spec:** `docs/superpowers/specs/2026-04-27-tax-hub-foundation-design.md`

**Frontend NFR:** Every task that creates or modifies a *visual* component MUST start by invoking the `/impeccable` skill. Mechanical-only edits may skip it.

**Per-task workflow:** every task ends with `git add <files>` → `git commit` → `git push origin main`. The user reviews each commit on GitHub.

---

## File map

### Created

**Backend**
- `supabase/migrations/003_tax_hub.sql`
- `supabase/migrations/test_003_tax_hub.sql`
- `backend/models/tax.py`
- `backend/utils/financial_year.py`
- `backend/services/tax_service.py`
- `backend/services/storage_service.py`
- `backend/routers/tax.py`
- `backend/tests/test_financial_year.py`
- `backend/tests/test_tax_service.py`
- `backend/tests/test_storage_service.py`
- `backend/tests/test_tax_router.py`
- `backend/tests/test_tax_integration.py`

**Frontend**
- `frontend/src/utils/financialYear.ts`
- `frontend/src/api/tax.ts`
- `frontend/src/types/tax.ts`
- `frontend/src/hooks/useTaxData.ts`
- `frontend/src/components/SideRail.tsx`
- `frontend/src/components/Toast.tsx`
- `frontend/src/pages/TaxHub.tsx`
- `frontend/src/components/tax/FYAccordion.tsx`
- `frontend/src/components/tax/FYSection.tsx`
- `frontend/src/components/tax/FYSummaryStrip.tsx`
- `frontend/src/components/tax/KrakenActivityRow.tsx`
- `frontend/src/components/tax/EntryList.tsx`
- `frontend/src/components/tax/EntryDrawer.tsx`
- `frontend/src/components/tax/FileDropZone.tsx`
- `frontend/src/components/tax/AttachmentChip.tsx`

### Modified

- `backend/main.py` (include tax router)
- `backend/scheduler.py` (add sweep job)
- `frontend/src/App.tsx` (view state, render SideRail, switch between Dashboard/TaxHub)
- `frontend/src/pages/Dashboard.tsx` (drop SignOutButton from header)
- `frontend/src/components/AgentPanel.tsx` (overlay positioning)

---

## Pre-flight (one-time)

Before starting Task 1, the implementer must create the Supabase Storage bucket. This is a one-time UI action, not a code task:

1. In Supabase Dashboard → Storage → New bucket
2. Name: `tax-attachments`
3. Public: **OFF** (private)
4. File size limit: 10 MB
5. Allowed MIME types: `image/jpeg`, `image/png`, `image/webp`, `application/pdf`
6. Service-role-only access (default for private buckets)

If the bucket already exists, continue.

---

## Task 1: Migration — create tax tables

**Files:**
- Create: `supabase/migrations/003_tax_hub.sql`
- Create: `supabase/migrations/test_003_tax_hub.sql`

- [ ] **Step 1: Write the prod migration**

`supabase/migrations/003_tax_hub.sql`:
```sql
-- Tax Hub Foundation (Phase 5 / Spec 1)
-- Three parallel entry tables + one polymorphic attachment table.

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
  storage_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tax_attachments_parent ON tax_attachments(parent_kind, parent_id)
  WHERE parent_id IS NOT NULL;
CREATE INDEX idx_tax_attachments_pending ON tax_attachments(uploaded_at)
  WHERE parent_id IS NULL;
```

- [ ] **Step 2: Write the test-schema mirror**

`supabase/migrations/test_003_tax_hub.sql` — same DDL but each `CREATE TABLE` becomes `CREATE TABLE test.<name>` and indexes become `idx_test_<name>` (matches existing pattern in `002_create_test_schema.sql`):

```sql
-- Test-schema mirror for tax tables
CREATE TABLE test.tax_deductibles (
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
CREATE INDEX idx_test_tax_deductibles_fy ON test.tax_deductibles(financial_year, date_paid DESC);

CREATE TABLE test.tax_income (
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
CREATE INDEX idx_test_tax_income_fy ON test.tax_income(financial_year, date_received DESC);

CREATE TABLE test.tax_paid (
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
CREATE INDEX idx_test_tax_paid_fy ON test.tax_paid(financial_year, date_paid DESC);

CREATE TABLE test.tax_attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_kind TEXT NOT NULL CHECK (parent_kind IN ('deductible', 'income', 'tax_paid')),
  parent_id UUID,
  storage_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_test_tax_attachments_parent ON test.tax_attachments(parent_kind, parent_id)
  WHERE parent_id IS NOT NULL;
CREATE INDEX idx_test_tax_attachments_pending ON test.tax_attachments(uploaded_at)
  WHERE parent_id IS NULL;
```

- [ ] **Step 3: Apply both migrations via Supabase SQL editor**

Open Supabase Dashboard → SQL Editor → paste the contents of `003_tax_hub.sql`, run. Repeat for `test_003_tax_hub.sql`. (Same manual pattern as Phase 1's migrations.)

- [ ] **Step 4: Verify tables exist**

In the SQL editor, run:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name LIKE 'tax_%'
ORDER BY table_name;
```
Expected output: 4 rows — `tax_attachments`, `tax_deductibles`, `tax_income`, `tax_paid`.

Repeat for `table_schema = 'test'`. Same 4 rows expected.

- [ ] **Step 5: Commit + push**

```bash
git add supabase/migrations/003_tax_hub.sql supabase/migrations/test_003_tax_hub.sql
git commit -m "feat(tax): add tax_hub migration (3 entry tables + attachments)"
git push origin main
```

---

## Task 2: Pydantic models

**Files:**
- Create: `backend/models/tax.py`

- [ ] **Step 1: Write the models**

`backend/models/tax.py`:
```python
"""Pydantic models for the Tax Hub feature.

Three parallel entry kinds (deductible, income, tax_paid) share a TaxEntry
shape. The `type` field carries a kind-specific enum, validated at the
service layer.
"""

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
    date: str             # date_paid or date_received, normalized
    type: str             # one of the kind-specific enums (string for cross-kind compat)
    notes: str | None
    financial_year: str
    attachments: list[TaxAttachment]
    created_at: str
    updated_at: str


class TaxEntryCreate(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    amount_aud: float = Field(gt=0)
    date: str            # ISO date YYYY-MM-DD
    type: str            # validated against the right enum in service layer
    notes: str | None = Field(default=None, max_length=4000)
    attachment_ids: list[str] = []


class TaxEntryUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=200)
    amount_aud: float | None = Field(default=None, gt=0)
    date: str | None = None
    type: str | None = None
    notes: str | None = Field(default=None, max_length=4000)


class KrakenAssetActivity(BaseModel):
    aud_spent: float
    buy_count: int
    current_value_aud: float


class KrakenFYActivity(BaseModel):
    total_aud_invested: float
    total_buys: int
    per_asset: dict[str, KrakenAssetActivity]


class FYOverview(BaseModel):
    financial_year: str
    income_total_aud: float
    tax_paid_total_aud: float
    deductibles_total_aud: float
    kraken_activity: KrakenFYActivity
```

- [ ] **Step 2: Verify imports cleanly**

Run: `cd backend && python -c "from models.tax import TaxEntry, TaxEntryCreate, FYOverview, KrakenFYActivity"`

Expected: silent success (no output, no error).

- [ ] **Step 3: Commit + push**

```bash
git add backend/models/tax.py
git commit -m "feat(tax): add Pydantic models for tax entries and FY overview"
git push origin main
```

---

## Task 3: Financial year helper + tests

**Files:**
- Create: `backend/utils/financial_year.py`
- Create: `backend/tests/test_financial_year.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_financial_year.py`:
```python
from datetime import date

import pytest

from backend.utils.financial_year import financial_year_from


@pytest.mark.parametrize("input_date,expected", [
    # Standard mid-year dates
    (date(2025, 8, 15), "2025-26"),
    (date(2025, 12, 31), "2025-26"),
    (date(2026, 1, 1), "2025-26"),
    (date(2026, 5, 30), "2025-26"),
    # Boundary: July 1 (FY starts)
    (date(2025, 7, 1), "2025-26"),
    # Boundary: June 30 (FY ends)
    (date(2026, 6, 30), "2025-26"),
    # Next FY starts July 1
    (date(2026, 7, 1), "2026-27"),
    # Distant past
    (date(2000, 7, 1), "2000-01"),
    (date(2000, 6, 30), "1999-00"),
    # Leap year (Feb 29 in FY 2023-24)
    (date(2024, 2, 29), "2023-24"),
    # Year ending in 99 → 00 short suffix
    (date(1999, 7, 1), "1999-00"),
    (date(2099, 7, 1), "2099-00"),
])
def test_financial_year_from_returns_expected(input_date: date, expected: str) -> None:
    assert financial_year_from(input_date) == expected
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && pytest tests/test_financial_year.py -v`
Expected: ImportError / ModuleNotFoundError on `backend.utils.financial_year`.

- [ ] **Step 3: Implement the helper**

`backend/utils/financial_year.py`:
```python
"""Australian financial year helper.

The AU FY runs July 1 → June 30. A date in [Jul 1 YYYY, Jun 30 YYYY+1]
belongs to FY 'YYYY-YY' (e.g. '2025-26').
"""

from datetime import date


def financial_year_from(d: date) -> str:
    """Return the AU financial year string (e.g. '2025-26') for a given date."""
    if d.month >= 7:
        start = d.year
    else:
        start = d.year - 1
    end_short = (start + 1) % 100
    return f"{start}-{end_short:02d}"
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && pytest tests/test_financial_year.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit + push**

```bash
git add backend/utils/financial_year.py backend/tests/test_financial_year.py
git commit -m "feat(tax): add financial_year_from helper with FY boundary tests"
git push origin main
```

---

## Task 4: tax_service — per-kind CRUD + tests

**Files:**
- Create: `backend/services/tax_service.py`
- Create: `backend/tests/test_tax_service.py`

This task implements `create_entry`, `get_entry`, `get_entries(kind, fy)`, `update_entry`, and `delete_entry` (without attachment cascade — that's Task 8). All operations are mocked at the supabase client.

- [ ] **Step 1: Write failing tests for create_entry**

`backend/tests/test_tax_service.py`:
```python
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from backend.models.tax import TaxEntryCreate, TaxEntryKind, TaxEntryUpdate


@pytest.fixture
def mock_supabase():
    """Mock the supabase client used by tax_service."""
    with patch("backend.services.tax_service.get_supabase") as m:
        client = MagicMock()
        m.return_value = client
        yield client


def test_create_deductible_inserts_with_computed_fy(mock_supabase):
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Notion subscription",
        amount_aud=32.0,
        date="2026-03-15",
        type="software",
        notes=None,
        attachment_ids=[],
    )

    inserted_row = {
        "id": "abc-123",
        "description": "Notion subscription",
        "amount_aud": 32.0,
        "date_paid": "2026-03-15",
        "type": "software",
        "notes": None,
        "financial_year": "2025-26",
        "created_at": "2026-03-15T00:00:00+11:00",
        "updated_at": "2026-03-15T00:00:00+11:00",
    }
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [inserted_row]

    result = tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, payload)

    assert result.id == "abc-123"
    assert result.financial_year == "2025-26"
    assert result.attachments == []

    insert_call = mock_supabase.table.return_value.insert.call_args[0][0]
    assert insert_call["financial_year"] == "2025-26"
    assert insert_call["date_paid"] == "2026-03-15"
    assert insert_call["type"] == "software"


def test_create_income_uses_date_received_column(mock_supabase):
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Acme Corp Mar pay",
        amount_aud=6500.0,
        date="2026-03-28",
        type="salary_wages",
        notes=None,
        attachment_ids=[],
    )
    inserted_row = {
        "id": "inc-1",
        "description": "Acme Corp Mar pay",
        "amount_aud": 6500.0,
        "date_received": "2026-03-28",
        "type": "salary_wages",
        "notes": None,
        "financial_year": "2025-26",
        "created_at": "2026-03-28T00:00:00+11:00",
        "updated_at": "2026-03-28T00:00:00+11:00",
    }
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [inserted_row]

    result = tax_service.create_entry(TaxEntryKind.INCOME, payload)

    assert result.date == "2026-03-28"

    insert_call = mock_supabase.table.return_value.insert.call_args[0][0]
    assert "date_received" in insert_call
    assert "date_paid" not in insert_call


def test_create_rejects_invalid_type_for_kind(mock_supabase):
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Wrong type",
        amount_aud=10.0,
        date="2026-03-15",
        type="salary_wages",   # income type, not deductible
        notes=None,
        attachment_ids=[],
    )

    with pytest.raises(ValueError, match="Invalid type"):
        tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, payload)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && pytest tests/test_tax_service.py -v`
Expected: ImportError / ModuleNotFoundError on `backend.services.tax_service`.

- [ ] **Step 3: Implement service skeleton + create_entry**

`backend/services/tax_service.py`:
```python
"""Service layer for the Tax Hub feature.

Encapsulates DB operations for tax_deductibles, tax_income, tax_paid and
their attachments. Routers are thin wrappers over this module.

Date column naming differs by table:
  - tax_deductibles → date_paid
  - tax_income      → date_received
  - tax_paid        → date_paid

The service normalizes to a single `date` field in the API response
(TaxEntry).
"""

from datetime import date as date_t, datetime

from backend.db.supabase_client import get_supabase
from backend.models.tax import (
    DeductibleType,
    IncomeType,
    TaxAttachment,
    TaxEntry,
    TaxEntryCreate,
    TaxEntryKind,
    TaxEntryUpdate,
    TaxPaidType,
)
from backend.utils.financial_year import financial_year_from


class TaxServiceError(Exception):
    pass


class EntryNotFoundError(TaxServiceError):
    pass


# ── Kind metadata ────────────────────────────────────────────────

_KIND_TABLE = {
    TaxEntryKind.DEDUCTIBLE: "tax_deductibles",
    TaxEntryKind.INCOME: "tax_income",
    TaxEntryKind.TAX_PAID: "tax_paid",
}

_KIND_DATE_COLUMN = {
    TaxEntryKind.DEDUCTIBLE: "date_paid",
    TaxEntryKind.INCOME: "date_received",
    TaxEntryKind.TAX_PAID: "date_paid",
}

_KIND_TYPE_ENUM = {
    TaxEntryKind.DEDUCTIBLE: DeductibleType,
    TaxEntryKind.INCOME: IncomeType,
    TaxEntryKind.TAX_PAID: TaxPaidType,
}


def _validate_type(kind: TaxEntryKind, type_value: str) -> None:
    enum_class = _KIND_TYPE_ENUM[kind]
    valid = {e.value for e in enum_class}
    if type_value not in valid:
        raise ValueError(
            f"Invalid type '{type_value}' for kind '{kind.value}'. "
            f"Valid: {sorted(valid)}"
        )


def _row_to_entry(kind: TaxEntryKind, row: dict, attachments: list[TaxAttachment] | None = None) -> TaxEntry:
    date_col = _KIND_DATE_COLUMN[kind]
    return TaxEntry(
        id=row["id"],
        description=row["description"],
        amount_aud=float(row["amount_aud"]),
        date=row[date_col],
        type=row["type"],
        notes=row.get("notes"),
        financial_year=row["financial_year"],
        attachments=attachments or [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── CRUD ─────────────────────────────────────────────────────────

def create_entry(kind: TaxEntryKind, payload: TaxEntryCreate) -> TaxEntry:
    _validate_type(kind, payload.type)

    parsed_date = date_t.fromisoformat(payload.date)
    fy = financial_year_from(parsed_date)
    date_col = _KIND_DATE_COLUMN[kind]
    table = _KIND_TABLE[kind]

    insert_row = {
        "description": payload.description.strip(),
        "amount_aud": payload.amount_aud,
        date_col: payload.date,
        "type": payload.type,
        "notes": payload.notes,
        "financial_year": fy,
    }

    db = get_supabase()
    result = db.table(table).insert(insert_row).execute()
    if not result.data:
        raise TaxServiceError(f"Insert returned no data for kind={kind.value}")

    return _row_to_entry(kind, result.data[0])
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && pytest tests/test_tax_service.py -v`
Expected: 3 passed.

- [ ] **Step 5: Add tests for get_entry / get_entries / update / delete**

Append to `backend/tests/test_tax_service.py`:
```python
def test_get_entries_filters_by_fy(mock_supabase):
    from backend.services import tax_service

    rows = [
        {"id": "1", "description": "A", "amount_aud": 10.0, "date_paid": "2026-03-01",
         "type": "software", "notes": None, "financial_year": "2025-26",
         "created_at": "2026-03-01T00:00:00+11:00", "updated_at": "2026-03-01T00:00:00+11:00"},
    ]
    chain = mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value
    chain.execute.return_value.data = rows

    # No attachments query path (Task 8 will add it). For now return [] always.
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []

    result = tax_service.get_entries(TaxEntryKind.DEDUCTIBLE, "2025-26")

    assert len(result) == 1
    assert result[0].financial_year == "2025-26"
    mock_supabase.table.return_value.select.return_value.eq.assert_called_with("financial_year", "2025-26")


def test_get_entry_returns_single(mock_supabase):
    from backend.services import tax_service

    row = {"id": "abc", "description": "X", "amount_aud": 5.0, "date_paid": "2026-03-01",
           "type": "software", "notes": None, "financial_year": "2025-26",
           "created_at": "2026-03-01T00:00:00+11:00", "updated_at": "2026-03-01T00:00:00+11:00"}
    chain = mock_supabase.table.return_value.select.return_value.eq.return_value
    chain.execute.return_value.data = [row]
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []

    result = tax_service.get_entry(TaxEntryKind.DEDUCTIBLE, "abc")

    assert result.id == "abc"


def test_get_entry_missing_raises(mock_supabase):
    from backend.services import tax_service
    from backend.services.tax_service import EntryNotFoundError

    chain = mock_supabase.table.return_value.select.return_value.eq.return_value
    chain.execute.return_value.data = []

    with pytest.raises(EntryNotFoundError):
        tax_service.get_entry(TaxEntryKind.DEDUCTIBLE, "nope")


def test_update_entry_recomputes_fy_when_date_changes(mock_supabase):
    from backend.services import tax_service

    # First the existing-row fetch returns an entry in FY 2024-25
    existing = {"id": "abc", "description": "Old", "amount_aud": 10.0, "date_paid": "2025-03-01",
                "type": "software", "notes": None, "financial_year": "2024-25",
                "created_at": "2025-03-01T00:00:00+11:00", "updated_at": "2025-03-01T00:00:00+11:00"}

    # The .update().eq().execute() returns the patched row in FY 2025-26
    patched = {**existing, "date_paid": "2025-09-01", "financial_year": "2025-26"}

    select_chain = mock_supabase.table.return_value.select.return_value.eq.return_value
    select_chain.execute.return_value.data = [existing]
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []

    update_chain = mock_supabase.table.return_value.update.return_value.eq.return_value
    update_chain.execute.return_value.data = [patched]

    patch = TaxEntryUpdate(date="2025-09-01")
    result = tax_service.update_entry(TaxEntryKind.DEDUCTIBLE, "abc", patch)

    assert result.financial_year == "2025-26"
    update_call = mock_supabase.table.return_value.update.call_args[0][0]
    assert update_call["date_paid"] == "2025-09-01"
    assert update_call["financial_year"] == "2025-26"


def test_delete_entry_calls_delete(mock_supabase):
    from backend.services import tax_service

    delete_chain = mock_supabase.table.return_value.delete.return_value.eq.return_value
    delete_chain.execute.return_value.data = [{"id": "abc"}]

    # No attachments yet (cascade tested in Task 8)
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    tax_service.delete_entry(TaxEntryKind.DEDUCTIBLE, "abc")

    mock_supabase.table.return_value.delete.return_value.eq.assert_called_with("id", "abc")
```

- [ ] **Step 6: Run tests, verify failures**

Run: `cd backend && pytest tests/test_tax_service.py -v`
Expected: 3 passed (existing), 5 failed/erroring (new — `get_entries`, `get_entry`, `update_entry`, `delete_entry` don't exist yet).

- [ ] **Step 7: Implement the missing service functions**

Append to `backend/services/tax_service.py`:
```python
def _get_attachments_for(parent_kind: TaxEntryKind, ids: list[str]) -> dict[str, list[TaxAttachment]]:
    """Fetch attachments grouped by parent_id. Empty dict if no ids."""
    if not ids:
        return {}
    db = get_supabase()
    result = (
        db.table("tax_attachments")
        .select("*")
        .eq("parent_kind", parent_kind.value)
        .in_("parent_id", ids)
        .execute()
    )
    grouped: dict[str, list[TaxAttachment]] = {}
    for row in result.data or []:
        att = TaxAttachment(
            id=row["id"],
            filename=row["filename"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            uploaded_at=row["uploaded_at"],
        )
        grouped.setdefault(row["parent_id"], []).append(att)
    return grouped


def get_entries(kind: TaxEntryKind, fy: str) -> list[TaxEntry]:
    table = _KIND_TABLE[kind]
    date_col = _KIND_DATE_COLUMN[kind]

    db = get_supabase()
    result = (
        db.table(table)
        .select("*")
        .eq("financial_year", fy)
        .order(date_col, desc=True)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return []

    attachments_by_parent = _get_attachments_for(kind, [r["id"] for r in rows])
    return [_row_to_entry(kind, r, attachments_by_parent.get(r["id"], [])) for r in rows]


def get_entry(kind: TaxEntryKind, id: str) -> TaxEntry:
    table = _KIND_TABLE[kind]
    db = get_supabase()
    result = db.table(table).select("*").eq("id", id).execute()
    rows = result.data or []
    if not rows:
        raise EntryNotFoundError(f"{kind.value} entry not found: {id}")

    attachments_by_parent = _get_attachments_for(kind, [id])
    return _row_to_entry(kind, rows[0], attachments_by_parent.get(id, []))


def update_entry(kind: TaxEntryKind, id: str, patch: TaxEntryUpdate) -> TaxEntry:
    if patch.type is not None:
        _validate_type(kind, patch.type)

    # Need existing row to know whether date changed (for FY recompute)
    existing = get_entry(kind, id)

    update_row: dict = {}
    if patch.description is not None:
        update_row["description"] = patch.description.strip()
    if patch.amount_aud is not None:
        update_row["amount_aud"] = patch.amount_aud
    if patch.type is not None:
        update_row["type"] = patch.type
    if patch.notes is not None:
        update_row["notes"] = patch.notes
    if patch.date is not None:
        date_col = _KIND_DATE_COLUMN[kind]
        update_row[date_col] = patch.date
        update_row["financial_year"] = financial_year_from(date_t.fromisoformat(patch.date))

    if not update_row:
        return existing  # no-op patch

    update_row["updated_at"] = datetime.now().isoformat()

    table = _KIND_TABLE[kind]
    db = get_supabase()
    result = db.table(table).update(update_row).eq("id", id).execute()
    rows = result.data or []
    if not rows:
        raise EntryNotFoundError(f"{kind.value} entry not found: {id}")

    attachments_by_parent = _get_attachments_for(kind, [id])
    return _row_to_entry(kind, rows[0], attachments_by_parent.get(id, []))


def delete_entry(kind: TaxEntryKind, id: str) -> None:
    """Hard-delete an entry. Attachment cascade is added in Task 8."""
    db = get_supabase()
    table = _KIND_TABLE[kind]
    result = db.table(table).delete().eq("id", id).execute()
    if not result.data:
        raise EntryNotFoundError(f"{kind.value} entry not found: {id}")
```

- [ ] **Step 8: Run tests, verify all pass**

Run: `cd backend && pytest tests/test_tax_service.py -v`
Expected: 8 passed.

- [ ] **Step 9: Commit + push**

```bash
git add backend/services/tax_service.py backend/tests/test_tax_service.py
git commit -m "feat(tax): add per-kind CRUD in tax_service with FY recompute"
git push origin main
```

---

## Task 5: tax_service — get_overview aggregation + tests

**Files:**
- Modify: `backend/services/tax_service.py` (add `get_overview`)
- Modify: `backend/tests/test_tax_service.py` (add tests)

`get_overview()` returns a `list[FYOverview]` — one row per FY that has any data across the 3 entry tables. Kraken activity is wired in Task 6 (this task uses a placeholder).

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_tax_service.py`:
```python
def test_get_overview_aggregates_per_fy(mock_supabase):
    from backend.services import tax_service

    deductibles_rows = [
        {"financial_year": "2025-26", "amount_aud": 32.0},
        {"financial_year": "2025-26", "amount_aud": 28.0},
        {"financial_year": "2024-25", "amount_aud": 100.0},
    ]
    income_rows = [
        {"financial_year": "2025-26", "amount_aud": 6500.0},
        {"financial_year": "2024-25", "amount_aud": 6000.0},
    ]
    paid_rows = [
        {"financial_year": "2025-26", "amount_aud": 1840.0},
    ]

    def table_side_effect(name):
        m = MagicMock()
        if name == "tax_deductibles":
            m.select.return_value.execute.return_value.data = deductibles_rows
        elif name == "tax_income":
            m.select.return_value.execute.return_value.data = income_rows
        elif name == "tax_paid":
            m.select.return_value.execute.return_value.data = paid_rows
        return m

    mock_supabase.table.side_effect = table_side_effect

    # Patch the Kraken activity call to return empty for both FYs
    with patch("backend.services.tax_service.get_kraken_activity_by_fy") as kraken_mock:
        kraken_mock.return_value = {
            "2025-26": {"total_aud_invested": 0.0, "total_buys": 0, "per_asset": {}},
            "2024-25": {"total_aud_invested": 0.0, "total_buys": 0, "per_asset": {}},
        }
        result = tax_service.get_overview()

    fys = [r.financial_year for r in result]
    assert "2025-26" in fys and "2024-25" in fys

    fy_2526 = next(r for r in result if r.financial_year == "2025-26")
    assert fy_2526.deductibles_total_aud == 60.0
    assert fy_2526.income_total_aud == 6500.0
    assert fy_2526.tax_paid_total_aud == 1840.0


def test_get_overview_returns_empty_when_no_data(mock_supabase):
    from backend.services import tax_service

    def table_side_effect(name):
        m = MagicMock()
        m.select.return_value.execute.return_value.data = []
        return m
    mock_supabase.table.side_effect = table_side_effect

    with patch("backend.services.tax_service.get_kraken_activity_by_fy") as kraken_mock:
        kraken_mock.return_value = {}
        result = tax_service.get_overview()

    assert result == []
```

- [ ] **Step 2: Run tests, verify failures**

Run: `cd backend && pytest tests/test_tax_service.py::test_get_overview_aggregates_per_fy backend/tests/test_tax_service.py::test_get_overview_returns_empty_when_no_data -v`
Expected: 2 errors (function doesn't exist).

- [ ] **Step 3: Implement get_overview**

Append to `backend/services/tax_service.py`:
```python
from collections import defaultdict

from backend.models.tax import FYOverview, KrakenAssetActivity, KrakenFYActivity


def get_overview() -> list[FYOverview]:
    """Aggregate totals per FY across all three entry tables, plus Kraken activity.

    Returns one FYOverview per FY that has *any* data (entry rows in any table
    OR Kraken activity for that FY). Sorted by FY descending (newest first).
    """
    db = get_supabase()

    deductibles_by_fy: dict[str, float] = defaultdict(float)
    income_by_fy: dict[str, float] = defaultdict(float)
    tax_paid_by_fy: dict[str, float] = defaultdict(float)

    for row in db.table("tax_deductibles").select("financial_year, amount_aud").execute().data or []:
        deductibles_by_fy[row["financial_year"]] += float(row["amount_aud"])
    for row in db.table("tax_income").select("financial_year, amount_aud").execute().data or []:
        income_by_fy[row["financial_year"]] += float(row["amount_aud"])
    for row in db.table("tax_paid").select("financial_year, amount_aud").execute().data or []:
        tax_paid_by_fy[row["financial_year"]] += float(row["amount_aud"])

    kraken_by_fy = get_kraken_activity_by_fy()

    all_fys = (
        set(deductibles_by_fy)
        | set(income_by_fy)
        | set(tax_paid_by_fy)
        | set(kraken_by_fy)
    )

    overviews: list[FYOverview] = []
    for fy in sorted(all_fys, reverse=True):
        kraken = kraken_by_fy.get(fy, {"total_aud_invested": 0.0, "total_buys": 0, "per_asset": {}})
        overviews.append(FYOverview(
            financial_year=fy,
            income_total_aud=round(income_by_fy[fy], 2),
            tax_paid_total_aud=round(tax_paid_by_fy[fy], 2),
            deductibles_total_aud=round(deductibles_by_fy[fy], 2),
            kraken_activity=KrakenFYActivity(
                total_aud_invested=kraken["total_aud_invested"],
                total_buys=kraken["total_buys"],
                per_asset={
                    asset: KrakenAssetActivity(**vals) for asset, vals in kraken["per_asset"].items()
                },
            ),
        ))
    return overviews


def get_kraken_activity_by_fy() -> dict[str, dict]:
    """Stub — implementation lands in Task 6."""
    return {}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && pytest tests/test_tax_service.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit + push**

```bash
git add backend/services/tax_service.py backend/tests/test_tax_service.py
git commit -m "feat(tax): add get_overview aggregation across the three entry tables"
git push origin main
```

---

## Task 6: tax_service — Kraken activity per FY + tests

**Files:**
- Modify: `backend/services/tax_service.py` (replace stub)
- Modify: `backend/tests/test_tax_service.py` (add tests)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_tax_service.py`:
```python
def test_get_kraken_activity_groups_lots_by_fy(mock_supabase):
    from decimal import Decimal
    from backend.services import tax_service

    fake_lots = [
        # FY 2025-26 (Jul 2025 onward)
        MagicMock(asset="ETH", acquired_at="2026-03-15T10:00:00+11:00",
                  cost_aud=Decimal("500"), remaining_quantity=Decimal("0.1")),
        MagicMock(asset="ETH", acquired_at="2026-03-22T10:00:00+11:00",
                  cost_aud=Decimal("520"), remaining_quantity=Decimal("0.1")),
        MagicMock(asset="SOL", acquired_at="2026-03-15T10:00:00+11:00",
                  cost_aud=Decimal("200"), remaining_quantity=Decimal("1.0")),
        # FY 2024-25
        MagicMock(asset="ETH", acquired_at="2025-03-15T10:00:00+11:00",
                  cost_aud=Decimal("400"), remaining_quantity=Decimal("0.1")),
    ]

    with patch("backend.services.tax_service.sync_service.get_all_lots") as lots_mock, \
         patch("backend.services.tax_service.kraken_service.get_ticker_prices") as prices_mock:
        lots_mock.return_value = fake_lots
        prices_mock.return_value = {"ETH": Decimal("5000"), "SOL": Decimal("250")}

        result = tax_service.get_kraken_activity_by_fy()

    assert "2025-26" in result
    assert "2024-25" in result
    assert result["2025-26"]["total_aud_invested"] == 1220.0  # 500 + 520 + 200
    assert result["2025-26"]["total_buys"] == 3
    assert result["2025-26"]["per_asset"]["ETH"]["aud_spent"] == 1020.0
    assert result["2025-26"]["per_asset"]["ETH"]["buy_count"] == 2
    assert result["2025-26"]["per_asset"]["ETH"]["current_value_aud"] == 1000.0  # 0.2 * 5000


def test_get_kraken_activity_empty_when_no_lots(mock_supabase):
    from backend.services import tax_service

    with patch("backend.services.tax_service.sync_service.get_all_lots") as lots_mock, \
         patch("backend.services.tax_service.kraken_service.get_ticker_prices") as prices_mock:
        lots_mock.return_value = []
        prices_mock.return_value = {}
        result = tax_service.get_kraken_activity_by_fy()

    assert result == {}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && pytest tests/test_tax_service.py::test_get_kraken_activity_groups_lots_by_fy -v`
Expected: assertion failure (stub returns `{}`).

- [ ] **Step 3: Replace the stub with real implementation**

In `backend/services/tax_service.py`, find:
```python
def get_kraken_activity_by_fy() -> dict[str, dict]:
    """Stub — implementation lands in Task 6."""
    return {}
```

Replace with:
```python
from datetime import datetime
from decimal import Decimal

from backend.services import kraken_service, sync_service


def get_kraken_activity_by_fy() -> dict[str, dict]:
    """Group Kraken lots by financial year, summing AUD spent and buy counts.

    Reads existing lots from sync_service. Current value is computed using
    fresh ticker prices. Excludes nothing — every lot counts as a buy in
    the FY it was acquired.
    """
    lots = sync_service.get_all_lots()
    if not lots:
        return {}

    prices = kraken_service.get_ticker_prices(list({lot.asset for lot in lots}))

    by_fy: dict[str, dict] = {}
    for lot in lots:
        acquired_dt = datetime.fromisoformat(lot.acquired_at)
        fy = financial_year_from(acquired_dt.date())

        bucket = by_fy.setdefault(fy, {
            "total_aud_invested": 0.0,
            "total_buys": 0,
            "per_asset": {},
        })
        bucket["total_aud_invested"] += float(lot.cost_aud)
        bucket["total_buys"] += 1

        asset_bucket = bucket["per_asset"].setdefault(lot.asset, {
            "aud_spent": 0.0,
            "buy_count": 0,
            "current_value_aud": 0.0,
        })
        asset_bucket["aud_spent"] += float(lot.cost_aud)
        asset_bucket["buy_count"] += 1

    # Fill current_value_aud from remaining_quantity * current price
    for lot in lots:
        fy = financial_year_from(datetime.fromisoformat(lot.acquired_at).date())
        price = prices.get(lot.asset, Decimal("0"))
        contribution = float(Decimal(str(lot.remaining_quantity)) * price)
        by_fy[fy]["per_asset"][lot.asset]["current_value_aud"] += contribution

    return by_fy
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && pytest tests/test_tax_service.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit + push**

```bash
git add backend/services/tax_service.py backend/tests/test_tax_service.py
git commit -m "feat(tax): add get_kraken_activity_by_fy from existing lots"
git push origin main
```

---

## Task 7: storage_service — upload + signed URL + delete + tests

**Files:**
- Create: `backend/services/storage_service.py`
- Create: `backend/tests/test_storage_service.py`

This task adds file storage. All Supabase Storage SDK calls are mocked.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_storage_service.py`:
```python
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile


@pytest.fixture
def mock_supabase():
    with patch("backend.services.storage_service.get_supabase") as m:
        client = MagicMock()
        m.return_value = client
        yield client


def _make_upload_file(filename: str, content_type: str, body: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(body), headers={"content-type": content_type})


def test_upload_rejects_oversized_file(mock_supabase):
    from backend.services import storage_service
    from backend.services.storage_service import AttachmentValidationError

    huge_body = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
    file = _make_upload_file("big.pdf", "application/pdf", huge_body)

    with pytest.raises(AttachmentValidationError, match="size"):
        storage_service.upload_attachment("deductible", None, file)


def test_upload_rejects_disallowed_content_type(mock_supabase):
    from backend.services import storage_service
    from backend.services.storage_service import AttachmentValidationError

    file = _make_upload_file("evil.exe", "application/x-msdownload", b"MZ...")

    with pytest.raises(AttachmentValidationError, match="content-type"):
        storage_service.upload_attachment("deductible", None, file)


def test_upload_pending_inserts_with_null_parent_id(mock_supabase):
    from backend.services import storage_service

    file = _make_upload_file("receipt.pdf", "application/pdf", b"%PDF-1.4 ...")

    inserted = {
        "id": "att-1",
        "filename": "receipt.pdf",
        "content_type": "application/pdf",
        "size_bytes": 12,
        "uploaded_at": "2026-03-15T00:00:00+11:00",
    }
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [inserted]
    mock_supabase.storage.from_.return_value.upload.return_value = None

    result = storage_service.upload_attachment("deductible", None, file)

    assert result.id == "att-1"
    insert_call = mock_supabase.table.return_value.insert.call_args[0][0]
    assert insert_call["parent_id"] is None
    assert insert_call["storage_path"].startswith("PENDING/")
    assert insert_call["storage_path"].endswith(".pdf")


def test_create_signed_url_calls_storage_sdk(mock_supabase):
    from backend.services import storage_service

    fetch_chain = mock_supabase.table.return_value.select.return_value.eq.return_value
    fetch_chain.execute.return_value.data = [{
        "id": "att-1",
        "storage_path": "deductibles/2025-26/abc.pdf",
    }]
    mock_supabase.storage.from_.return_value.create_signed_url.return_value = {
        "signedURL": "https://signed.example/abc",
    }

    url, expires = storage_service.create_signed_url("att-1")

    assert url == "https://signed.example/abc"
    mock_supabase.storage.from_.return_value.create_signed_url.assert_called_once()


def test_delete_removes_storage_object_then_row(mock_supabase):
    from backend.services import storage_service

    fetch_chain = mock_supabase.table.return_value.select.return_value.eq.return_value
    fetch_chain.execute.return_value.data = [{
        "id": "att-1",
        "storage_path": "deductibles/2025-26/abc.pdf",
    }]
    delete_chain = mock_supabase.table.return_value.delete.return_value.eq.return_value
    delete_chain.execute.return_value.data = [{"id": "att-1"}]

    storage_service.delete_attachment("att-1")

    mock_supabase.storage.from_.return_value.remove.assert_called_once_with(["deductibles/2025-26/abc.pdf"])
    mock_supabase.table.return_value.delete.return_value.eq.assert_called_with("id", "att-1")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && pytest tests/test_storage_service.py -v`
Expected: 5 errors / failures (module doesn't exist).

- [ ] **Step 3: Implement storage_service**

`backend/services/storage_service.py`:
```python
"""Service layer for tax attachment file storage on Supabase Storage.

All file operations go through this module — never the Supabase Storage
SDK directly from anywhere else. Frontend never receives storage paths
or URLs except through `create_signed_url`, which mints 5-minute signed
URLs that the browser uses to read the object directly from Storage.
"""

import os
import uuid
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from fastapi import UploadFile

from backend.db.supabase_client import get_supabase
from backend.models.tax import TaxAttachment


BUCKET = "tax-attachments"
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}
MAX_FILE_BYTES = 10 * 1024 * 1024
SIGNED_URL_TTL_SECONDS = 300  # 5 minutes


class StorageServiceError(Exception):
    pass


class AttachmentValidationError(StorageServiceError):
    """413 / 415 — file too large or wrong content-type."""


class StorageBackendError(StorageServiceError):
    """502 — Supabase Storage rejected the request."""


def _ext_from_content_type(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }[content_type]


def _read_into_memory(file: UploadFile) -> bytes:
    """Read the upload into memory. Tax-attachment uploads are <10 MB."""
    return file.file.read()


def upload_attachment(
    parent_kind: str,
    parent_id: str | None,
    file: UploadFile,
) -> TaxAttachment:
    """Validate, upload to Storage, and insert a tax_attachments row.

    parent_id=None means a pending upload (entry not yet created); the
    storage path lives under PENDING/ until the entry-create endpoint
    rebinds it.
    """
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise AttachmentValidationError(
            f"content-type '{content_type}' not allowed. "
            f"Permitted: {sorted(ALLOWED_CONTENT_TYPES)}"
        )

    body = _read_into_memory(file)
    if len(body) > MAX_FILE_BYTES:
        raise AttachmentValidationError(
            f"file size {len(body)} bytes exceeds {MAX_FILE_BYTES}"
        )
    if len(body) == 0:
        raise AttachmentValidationError("file is empty")

    ext = _ext_from_content_type(content_type)
    storage_filename = f"{uuid.uuid4()}{ext}"
    # All uploads land under PENDING/. tax_service.create_entry rebinds them
    # to the kind/{fy}/ namespace once the entry exists. Direct upload to a
    # known parent is not used in Spec 1.
    storage_path = f"PENDING/{storage_filename}"

    db = get_supabase()
    try:
        db.storage.from_(BUCKET).upload(
            storage_path,
            body,
            {"content-type": content_type},
        )
    except Exception as e:
        raise StorageBackendError(f"Supabase Storage upload failed: {e}") from e

    insert_row = {
        "parent_kind": parent_kind,
        "parent_id": parent_id,
        "storage_path": storage_path,
        "filename": file.filename or "untitled",
        "content_type": content_type,
        "size_bytes": len(body),
    }
    result = db.table("tax_attachments").insert(insert_row).execute()
    if not result.data:
        # Roll back the upload
        try:
            db.storage.from_(BUCKET).remove([storage_path])
        except Exception:
            pass
        raise StorageServiceError("Insert into tax_attachments returned no data")

    row = result.data[0]
    return TaxAttachment(
        id=row["id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        uploaded_at=row["uploaded_at"],
    )


def create_signed_url(attachment_id: str) -> tuple[str, datetime]:
    db = get_supabase()
    rows = db.table("tax_attachments").select("storage_path").eq("id", attachment_id).execute().data or []
    if not rows:
        raise StorageServiceError(f"Attachment not found: {attachment_id}")

    storage_path = rows[0]["storage_path"]
    try:
        signed = db.storage.from_(BUCKET).create_signed_url(storage_path, SIGNED_URL_TTL_SECONDS)
    except Exception as e:
        raise StorageBackendError(f"Failed to mint signed URL: {e}") from e

    url = signed.get("signedURL") or signed.get("signed_url")
    if not url:
        raise StorageBackendError(f"Storage SDK returned no URL: {signed!r}")

    expires_at = datetime.utcnow() + timedelta(seconds=SIGNED_URL_TTL_SECONDS)
    return url, expires_at


def delete_attachment(attachment_id: str) -> None:
    """Delete the storage object first, then the DB row.

    If the storage delete fails, do NOT delete the DB row — the orphaned
    object is recoverable; an orphaned row pointing nowhere is not.
    """
    db = get_supabase()
    rows = db.table("tax_attachments").select("storage_path").eq("id", attachment_id).execute().data or []
    if not rows:
        return  # idempotent

    storage_path = rows[0]["storage_path"]
    try:
        db.storage.from_(BUCKET).remove([storage_path])
    except Exception as e:
        raise StorageBackendError(f"Failed to delete storage object {storage_path}: {e}") from e

    db.table("tax_attachments").delete().eq("id", attachment_id).execute()


def sweep_pending_attachments(older_than_hours: int = 24) -> int:
    """Delete attachments with parent_id IS NULL older than `older_than_hours`.

    Returns the count of swept items. Called from the APScheduler job.
    """
    cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)

    db = get_supabase()
    rows = (
        db.table("tax_attachments")
        .select("id, storage_path")
        .is_("parent_id", "null")
        .lt("uploaded_at", cutoff.isoformat())
        .execute()
        .data
        or []
    )

    swept = 0
    for row in rows:
        try:
            db.storage.from_(BUCKET).remove([row["storage_path"]])
            db.table("tax_attachments").delete().eq("id", row["id"]).execute()
            swept += 1
        except Exception:
            # Log-and-continue; sweep will retry next run
            continue

    return swept
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && pytest tests/test_storage_service.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit + push**

```bash
git add backend/services/storage_service.py backend/tests/test_storage_service.py
git commit -m "feat(tax): add storage_service with upload/signed-url/delete/sweep"
git push origin main
```

---

## Task 8: tax_service — entry-attachment lifecycle + tests

**Files:**
- Modify: `backend/services/tax_service.py` (extend create + delete to handle attachments)
- Modify: `backend/tests/test_tax_service.py` (add tests)

This task wires the attachment cascade and PENDING rebind into create/delete.

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_tax_service.py`:
```python
def test_create_entry_rebinds_pending_attachments(mock_supabase):
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Notion sub",
        amount_aud=32.0,
        date="2026-03-15",
        type="software",
        notes=None,
        attachment_ids=["att-1", "att-2"],
    )

    inserted_entry = {
        "id": "entry-1", "description": "Notion sub", "amount_aud": 32.0,
        "date_paid": "2026-03-15", "type": "software", "notes": None,
        "financial_year": "2025-26",
        "created_at": "2026-03-15T00:00:00+11:00",
        "updated_at": "2026-03-15T00:00:00+11:00",
    }
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [inserted_entry]

    pending_attachments = [
        {"id": "att-1", "storage_path": "PENDING/abc.pdf", "filename": "a.pdf",
         "content_type": "application/pdf", "size_bytes": 100, "uploaded_at": "2026-03-15T00:00:00+11:00"},
        {"id": "att-2", "storage_path": "PENDING/def.pdf", "filename": "b.pdf",
         "content_type": "application/pdf", "size_bytes": 200, "uploaded_at": "2026-03-15T00:00:00+11:00"},
    ]
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = pending_attachments

    update_chain = mock_supabase.table.return_value.update.return_value.in_.return_value
    update_chain.execute.return_value.data = pending_attachments
    mock_supabase.storage.from_.return_value.move.return_value = None

    result = tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, payload)

    assert result.id == "entry-1"
    assert len(result.attachments) == 2

    # Storage objects moved from PENDING to deductibles/{fy}/...
    assert mock_supabase.storage.from_.return_value.move.call_count == 2


def test_delete_entry_cascades_attachments(mock_supabase):
    from backend.services import tax_service

    attachments = [
        {"id": "att-1", "storage_path": "deductibles/2025-26/abc.pdf",
         "filename": "a.pdf", "content_type": "application/pdf",
         "size_bytes": 100, "uploaded_at": "2026-03-15T00:00:00+11:00"},
        {"id": "att-2", "storage_path": "deductibles/2025-26/def.pdf",
         "filename": "b.pdf", "content_type": "application/pdf",
         "size_bytes": 200, "uploaded_at": "2026-03-15T00:00:00+11:00"},
    ]

    select_chain = mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value
    select_chain.execute.return_value.data = attachments

    delete_chain = mock_supabase.table.return_value.delete.return_value.eq.return_value
    delete_chain.execute.return_value.data = [{"id": "entry-1"}]

    tax_service.delete_entry(TaxEntryKind.DEDUCTIBLE, "entry-1")

    mock_supabase.storage.from_.return_value.remove.assert_called_once()
    removed_paths = mock_supabase.storage.from_.return_value.remove.call_args[0][0]
    assert "deductibles/2025-26/abc.pdf" in removed_paths
    assert "deductibles/2025-26/def.pdf" in removed_paths
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && pytest tests/test_tax_service.py::test_create_entry_rebinds_pending_attachments tests/test_tax_service.py::test_delete_entry_cascades_attachments -v`
Expected: 2 failures (rebind + cascade not implemented).

- [ ] **Step 3: Replace create_entry to add rebind logic**

In `backend/services/tax_service.py`, replace the existing `create_entry` and `delete_entry` functions:

```python
from backend.services import storage_service  # add to imports


def _rebind_pending_attachments(
    kind: TaxEntryKind,
    entry_id: str,
    fy: str,
    attachment_ids: list[str],
) -> list[TaxAttachment]:
    """Bind PENDING attachments to a newly-created entry and move objects
    from PENDING/{file} to {kind}s/{fy}/{file}.
    """
    if not attachment_ids:
        return []

    db = get_supabase()
    pending_rows = (
        db.table("tax_attachments")
        .select("*")
        .in_("id", attachment_ids)
        .execute()
        .data
        or []
    )
    if not pending_rows:
        return []

    _STORAGE_NAMESPACE = {
        TaxEntryKind.DEDUCTIBLE: "deductibles",
        TaxEntryKind.INCOME: "income",
        TaxEntryKind.TAX_PAID: "tax_paid",
    }
    namespace = _STORAGE_NAMESPACE[kind]

    moved_paths: list[tuple[str, str]] = []  # (old, new)
    for row in pending_rows:
        old_path = row["storage_path"]
        filename = old_path.split("/")[-1]
        new_path = f"{namespace}/{fy}/{filename}"
        try:
            db.storage.from_(storage_service.BUCKET).move(old_path, new_path)
        except Exception as e:
            raise storage_service.StorageBackendError(
                f"Failed to move {old_path} → {new_path}: {e}"
            ) from e
        moved_paths.append((row["id"], new_path))

    # Update DB rows: set parent_id and new storage_path
    for att_id, new_path in moved_paths:
        db.table("tax_attachments").update({
            "parent_id": entry_id,
            "storage_path": new_path,
            "parent_kind": kind.value,
        }).eq("id", att_id).execute()

    # Re-fetch to return current shape
    fresh = (
        db.table("tax_attachments")
        .select("*")
        .in_("id", attachment_ids)
        .execute()
        .data
        or []
    )
    return [TaxAttachment(
        id=r["id"],
        filename=r["filename"],
        content_type=r["content_type"],
        size_bytes=r["size_bytes"],
        uploaded_at=r["uploaded_at"],
    ) for r in fresh]


def create_entry(kind: TaxEntryKind, payload: TaxEntryCreate) -> TaxEntry:
    _validate_type(kind, payload.type)

    parsed_date = date_t.fromisoformat(payload.date)
    fy = financial_year_from(parsed_date)
    date_col = _KIND_DATE_COLUMN[kind]
    table = _KIND_TABLE[kind]

    insert_row = {
        "description": payload.description.strip(),
        "amount_aud": payload.amount_aud,
        date_col: payload.date,
        "type": payload.type,
        "notes": payload.notes,
        "financial_year": fy,
    }

    db = get_supabase()
    result = db.table(table).insert(insert_row).execute()
    if not result.data:
        raise TaxServiceError(f"Insert returned no data for kind={kind.value}")

    entry_row = result.data[0]
    attachments = _rebind_pending_attachments(kind, entry_row["id"], fy, payload.attachment_ids)
    return _row_to_entry(kind, entry_row, attachments)


def delete_entry(kind: TaxEntryKind, id: str) -> None:
    """Hard-delete an entry and cascade its attachments (DB + Storage)."""
    db = get_supabase()

    attachment_rows = (
        db.table("tax_attachments")
        .select("id, storage_path")
        .eq("parent_kind", kind.value)
        .eq("parent_id", id)
        .execute()
        .data
        or []
    )

    if attachment_rows:
        paths = [r["storage_path"] for r in attachment_rows]
        try:
            db.storage.from_(storage_service.BUCKET).remove(paths)
        except Exception as e:
            raise storage_service.StorageBackendError(
                f"Failed to delete storage objects for entry {id}: {e}"
            ) from e
        db.table("tax_attachments").delete().eq("parent_kind", kind.value).eq("parent_id", id).execute()

    table = _KIND_TABLE[kind]
    result = db.table(table).delete().eq("id", id).execute()
    if not result.data:
        raise EntryNotFoundError(f"{kind.value} entry not found: {id}")
```

- [ ] **Step 4: Run all tax_service tests, verify they pass**

Run: `cd backend && pytest tests/test_tax_service.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit + push**

```bash
git add backend/services/tax_service.py backend/tests/test_tax_service.py
git commit -m "feat(tax): wire entry-attachment cascade delete and PENDING rebind"
git push origin main
```

---

## Task 9: routers/tax.py — endpoints + tests + main.py wiring

**Files:**
- Create: `backend/routers/tax.py`
- Create: `backend/tests/test_tax_router.py`
- Modify: `backend/main.py` (include tax router)

- [ ] **Step 1: Write failing tests**

`backend/tests/test_tax_router.py`:
```python
"""Router tests for /api/tax/*. Services are mocked.

Auth is bypassed via the same dependency_overrides pattern Phase 4 used
in test_auth_router.py.
"""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.auth.dependencies import require_auth


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_auth] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_overview_returns_summary(client):
    fake_overview = [{
        "financial_year": "2025-26",
        "income_total_aud": 6500.0,
        "tax_paid_total_aud": 1840.0,
        "deductibles_total_aud": 60.0,
        "kraken_activity": {
            "total_aud_invested": 1220.0,
            "total_buys": 3,
            "per_asset": {"ETH": {"aud_spent": 1020.0, "buy_count": 2, "current_value_aud": 1000.0}},
        },
    }]

    with patch("backend.routers.tax.tax_service.get_overview") as m:
        m.return_value = [MagicMock(model_dump=lambda: fake_overview[0])]
        response = client.get("/api/tax/overview")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["financial_year"] == "2025-26"


def test_create_deductible_returns_201_shape(client):
    created = {
        "id": "abc", "description": "Notion", "amount_aud": 32.0, "date": "2026-03-15",
        "type": "software", "notes": None, "financial_year": "2025-26",
        "attachments": [],
        "created_at": "2026-03-15T00:00:00+11:00",
        "updated_at": "2026-03-15T00:00:00+11:00",
    }
    with patch("backend.routers.tax.tax_service.create_entry") as m:
        m.return_value = MagicMock(model_dump=lambda: created)
        response = client.post("/api/tax/deductibles", json={
            "description": "Notion", "amount_aud": 32.0, "date": "2026-03-15",
            "type": "software", "notes": None, "attachment_ids": [],
        })

    assert response.status_code == 200
    assert response.json()["id"] == "abc"


def test_unknown_entry_returns_404(client):
    from backend.services.tax_service import EntryNotFoundError
    with patch("backend.routers.tax.tax_service.get_entry") as m:
        m.side_effect = EntryNotFoundError("not found")
        response = client.patch("/api/tax/deductibles/missing", json={"description": "x"})

    assert response.status_code == 404


def test_attachment_upload_too_large_returns_413(client):
    from backend.services.storage_service import AttachmentValidationError
    with patch("backend.routers.tax.storage_service.upload_attachment") as m:
        m.side_effect = AttachmentValidationError("file size 11000000 exceeds 10485760")
        response = client.post(
            "/api/tax/attachments",
            data={"parent_kind": "deductible"},
            files={"file": ("big.pdf", b"x" * 100, "application/pdf")},
        )

    assert response.status_code == 413


def test_attachment_upload_wrong_type_returns_415(client):
    from backend.services.storage_service import AttachmentValidationError
    with patch("backend.routers.tax.storage_service.upload_attachment") as m:
        m.side_effect = AttachmentValidationError("content-type 'application/x-msdownload' not allowed")
        response = client.post(
            "/api/tax/attachments",
            data={"parent_kind": "deductible"},
            files={"file": ("evil.exe", b"x", "application/x-msdownload")},
        )

    assert response.status_code == 415


def test_signed_url_returns_url_and_expiry(client):
    from datetime import datetime, timedelta
    expires = datetime.utcnow() + timedelta(seconds=300)
    with patch("backend.routers.tax.storage_service.create_signed_url") as m:
        m.return_value = ("https://signed.example/abc", expires)
        response = client.get("/api/tax/attachments/att-1/url")

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "https://signed.example/abc"
    assert "expires_at" in body
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && pytest tests/test_tax_router.py -v`
Expected: import errors / 404s on the routes.

- [ ] **Step 3: Implement routers/tax.py**

`backend/routers/tax.py`:
```python
"""HTTP layer for /api/tax/*. All logic lives in tax_service / storage_service."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, UploadFile, File

from backend.models.tax import (
    FYOverview,
    TaxAttachment,
    TaxEntry,
    TaxEntryCreate,
    TaxEntryKind,
    TaxEntryUpdate,
)
from backend.services import storage_service, tax_service
from backend.services.tax_service import EntryNotFoundError
from backend.services.storage_service import (
    AttachmentValidationError,
    StorageBackendError,
)

router = APIRouter(prefix="/api/tax", tags=["tax"])


_KIND_PATH = {
    "deductibles": TaxEntryKind.DEDUCTIBLE,
    "income": TaxEntryKind.INCOME,
    "paid": TaxEntryKind.TAX_PAID,
}


def _kind_or_404(path_kind: str) -> TaxEntryKind:
    if path_kind not in _KIND_PATH:
        raise HTTPException(404, f"Unknown kind path: {path_kind}")
    return _KIND_PATH[path_kind]


# ── Overview ───────────────────────────────────────────────────

@router.get("/overview", response_model=list[FYOverview])
async def get_overview() -> list[FYOverview]:
    return tax_service.get_overview()


# ── Per-kind list / CRUD ───────────────────────────────────────

@router.get("/{path_kind}", response_model=list[TaxEntry])
async def list_entries(path_kind: str, fy: str) -> list[TaxEntry]:
    kind = _kind_or_404(path_kind)
    return tax_service.get_entries(kind, fy)


@router.post("/{path_kind}", response_model=TaxEntry)
async def create_entry(path_kind: str, payload: TaxEntryCreate) -> TaxEntry:
    kind = _kind_or_404(path_kind)
    try:
        return tax_service.create_entry(kind, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/{path_kind}/{id}", response_model=TaxEntry)
async def update_entry(path_kind: str, id: str, patch: TaxEntryUpdate) -> TaxEntry:
    kind = _kind_or_404(path_kind)
    try:
        return tax_service.update_entry(kind, id, patch)
    except EntryNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{path_kind}/{id}", status_code=204)
async def delete_entry(path_kind: str, id: str) -> None:
    kind = _kind_or_404(path_kind)
    try:
        tax_service.delete_entry(kind, id)
    except EntryNotFoundError as e:
        raise HTTPException(404, str(e))
    except StorageBackendError as e:
        raise HTTPException(502, str(e))


# ── Attachments ─────────────────────────────────────────────────

@router.post("/attachments", response_model=TaxAttachment)
async def upload_attachment(
    parent_kind: str = Form(...),
    parent_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
) -> TaxAttachment:
    if parent_kind not in {"deductible", "income", "tax_paid"}:
        raise HTTPException(400, f"Invalid parent_kind: {parent_kind}")
    try:
        return storage_service.upload_attachment(parent_kind, parent_id, file)
    except AttachmentValidationError as e:
        message = str(e)
        if "size" in message:
            raise HTTPException(413, message)
        raise HTTPException(415, message)
    except StorageBackendError as e:
        raise HTTPException(502, str(e))


@router.get("/attachments/{id}/url")
async def get_attachment_url(id: str) -> dict:
    try:
        url, expires = storage_service.create_signed_url(id)
    except StorageBackendError as e:
        raise HTTPException(502, str(e))
    return {"url": url, "expires_at": expires.isoformat()}


@router.delete("/attachments/{id}", status_code=204)
async def delete_attachment(id: str) -> None:
    try:
        storage_service.delete_attachment(id)
    except StorageBackendError as e:
        raise HTTPException(502, str(e))
```

- [ ] **Step 4: Wire router into main.py**

In `backend/main.py`, find the section that includes routers (around line 75):
```python
app.include_router(portfolio.router, dependencies=[Depends(require_auth)])
app.include_router(history.router, dependencies=[Depends(require_auth)])
app.include_router(sync.router, dependencies=[Depends(require_auth)])
```

Add:
```python
from backend.routers import tax

app.include_router(tax.router, dependencies=[Depends(require_auth)])
```

(Add `tax` to the imports at the top of the file.)

- [ ] **Step 5: Run all router tests, verify they pass**

Run: `cd backend && pytest tests/test_tax_router.py -v`
Expected: 6 passed.

- [ ] **Step 6: Smoke-check the running app**

Start the backend: `cd backend && uvicorn main:app --reload`
In another terminal: `curl -i http://localhost:8000/api/tax/overview`
Expected: `HTTP/1.1 401` (auth required — confirms the router is wired).

Stop uvicorn.

- [ ] **Step 7: Commit + push**

```bash
git add backend/routers/tax.py backend/tests/test_tax_router.py backend/main.py
git commit -m "feat(tax): add /api/tax/* router with CRUD and attachment endpoints"
git push origin main
```

---

## Task 10: Sweep job + scheduler integration + tests

**Files:**
- Modify: `backend/scheduler.py` (add sweep job)
- Create: `backend/tests/test_pending_sweep.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_pending_sweep.py`:
```python
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


def test_sweep_pending_attachments_removes_old_orphans():
    from backend.services import storage_service

    with patch("backend.services.storage_service.get_supabase") as m:
        client = MagicMock()
        m.return_value = client

        old_orphan = {
            "id": "att-old",
            "storage_path": "PENDING/old.pdf",
        }
        chain = client.table.return_value.select.return_value.is_.return_value.lt.return_value
        chain.execute.return_value.data = [old_orphan]
        client.storage.from_.return_value.remove.return_value = None
        client.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = [{"id": "att-old"}]

        count = storage_service.sweep_pending_attachments(older_than_hours=24)

    assert count == 1
    client.storage.from_.return_value.remove.assert_called_once_with(["PENDING/old.pdf"])


def test_sweep_returns_zero_when_no_orphans():
    from backend.services import storage_service

    with patch("backend.services.storage_service.get_supabase") as m:
        client = MagicMock()
        m.return_value = client
        chain = client.table.return_value.select.return_value.is_.return_value.lt.return_value
        chain.execute.return_value.data = []

        count = storage_service.sweep_pending_attachments()

    assert count == 0
```

- [ ] **Step 2: Run tests, verify they pass**

`storage_service.sweep_pending_attachments` was already added in Task 7. Run:

`cd backend && pytest tests/test_pending_sweep.py -v`
Expected: 2 passed.

- [ ] **Step 3: Wire sweep job into scheduler**

Modify `backend/scheduler.py`. Add at the top with other imports:
```python
from backend.services import storage_service
```

Add after the existing `_hourly_snapshot` function:
```python
def _do_pending_sweep() -> None:
    """Synchronous pending-attachment sweep."""
    swept = storage_service.sweep_pending_attachments(older_than_hours=24)
    if swept > 0:
        logger.info("Pending-attachment sweep removed %d orphans", swept)


async def _pending_sweep_job() -> None:
    """6-hourly sweep for orphan tax attachments."""
    try:
        await asyncio.to_thread(_do_pending_sweep)
    except Exception:
        logger.exception("Pending-attachment sweep failed")
```

In `start_scheduler()`, add a third `add_job` call after the hourly snapshot:
```python
    scheduler.add_job(
        _pending_sweep_job,
        "interval",
        hours=6,
        id="pending_sweep",
    )
```

- [ ] **Step 4: Verify scheduler imports cleanly**

Run: `cd backend && python -c "from scheduler import start_scheduler, _pending_sweep_job"`
Expected: silent success.

- [ ] **Step 5: Commit + push**

```bash
git add backend/scheduler.py backend/tests/test_pending_sweep.py
git commit -m "feat(tax): schedule 6-hourly sweep of pending tax attachments"
git push origin main
```

---

## Task 11: Backend integration test

**Files:**
- Create: `backend/tests/test_tax_integration.py`

This task verifies the full backend stack against a real Supabase test schema.

- [ ] **Step 1: Update conftest.py to clean tax tables**

Modify `backend/tests/conftest.py` — extend the `_clean()` function inside `clean_test_tables`:
```python
def _clean():
    for table in ["lots", "portfolio_snapshots", "sync_log",
                  "tax_deductibles", "tax_income", "tax_paid",
                  "tax_attachments"]:
        test_db.schema("test").table(table).delete().neq("id", _SENTINEL_UUID).execute()
    # prices table uses asset (text) as PK
    test_db.schema("test").table("prices").delete().neq("asset", "__sentinel__").execute()
```

- [ ] **Step 2: Write the integration test**

`backend/tests/test_tax_integration.py`:
```python
"""Integration tests for tax_service against the real Supabase test schema.

Uses the clean_test_tables fixture (opt-in) to run migrations-created
tables in test.* schema. Storage service is *not* exercised here — those
remain mock-only since the SDK contract is stable and real Storage tests
would be flaky.
"""

import os
import pytest

from backend.models.tax import TaxEntryCreate, TaxEntryKind, TaxEntryUpdate


def _override_schema_to_test(monkeypatch):
    """Repoint get_supabase().table(name) to test.<name>.

    The conftest test_db fixture already creates a client; we patch the
    service-layer `get_supabase()` so it returns a test-schema-prefixed
    client.
    """
    from supabase import create_client
    from backend.config import settings

    def _test_client():
        client = create_client(settings.supabase_url, settings.supabase_key)
        original_table = client.table

        def schemed_table(name):
            return client.schema("test").from_(name)

        client.table = schemed_table
        return client

    monkeypatch.setattr("backend.services.tax_service.get_supabase", _test_client)


@pytest.mark.usefixtures("clean_test_tables")
def test_create_then_get_then_delete_deductible(monkeypatch, test_db):
    _override_schema_to_test(monkeypatch)
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Notion subscription",
        amount_aud=32.50,
        date="2026-03-15",
        type="software",
        notes="March 2026",
        attachment_ids=[],
    )

    created = tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, payload)
    assert created.financial_year == "2025-26"
    assert created.amount_aud == 32.50

    fetched = tax_service.get_entry(TaxEntryKind.DEDUCTIBLE, created.id)
    assert fetched.id == created.id
    assert fetched.description == "Notion subscription"

    tax_service.delete_entry(TaxEntryKind.DEDUCTIBLE, created.id)


@pytest.mark.usefixtures("clean_test_tables")
def test_overview_aggregates_across_kinds(monkeypatch, test_db):
    _override_schema_to_test(monkeypatch)
    from backend.services import tax_service

    tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, TaxEntryCreate(
        description="A", amount_aud=10.0, date="2026-03-01",
        type="software", notes=None, attachment_ids=[],
    ))
    tax_service.create_entry(TaxEntryKind.INCOME, TaxEntryCreate(
        description="B", amount_aud=6500.0, date="2026-03-01",
        type="salary_wages", notes=None, attachment_ids=[],
    ))
    tax_service.create_entry(TaxEntryKind.TAX_PAID, TaxEntryCreate(
        description="C", amount_aud=1500.0, date="2026-03-01",
        type="payg_withholding", notes=None, attachment_ids=[],
    ))

    overview = tax_service.get_overview()

    fy_2526 = next((o for o in overview if o.financial_year == "2025-26"), None)
    assert fy_2526 is not None
    assert fy_2526.deductibles_total_aud == 10.0
    assert fy_2526.income_total_aud == 6500.0
    assert fy_2526.tax_paid_total_aud == 1500.0
```

- [ ] **Step 3: Run the integration test**

Run: `cd backend && pytest tests/test_tax_integration.py -v`
Expected: 2 passed (assuming the test schema migration was applied in Task 1).

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && pytest -v`
Expected: every existing test passes + the new tests pass. **No regressions.**

- [ ] **Step 5: Commit + push**

```bash
git add backend/tests/test_tax_integration.py backend/tests/conftest.py
git commit -m "feat(tax): add integration test against test.* schema"
git push origin main
```

**Backend complete.** Restart the backend (`uvicorn` in dev) and verify `/api/tax/overview` returns 401 without a cookie and `[]` (empty list) with a valid cookie.

---

## Task 12: financialYear.ts — frontend mirror

**Files:**
- Create: `frontend/src/utils/financialYear.ts`

(No `/impeccable` — pure utility.)

- [ ] **Step 1: Write the helper**

`frontend/src/utils/financialYear.ts`:
```typescript
/**
 * Australian financial year helper. Mirrors backend/utils/financial_year.py.
 * AU FY runs July 1 → June 30. Returns 'YYYY-YY' (e.g. '2025-26').
 */
export function financialYearFrom(d: Date): string {
  const month = d.getMonth() + 1 // JS months are 0-indexed
  const year = d.getFullYear()
  const start = month >= 7 ? year : year - 1
  const endShort = (start + 1) % 100
  return `${start}-${endShort.toString().padStart(2, '0')}`
}

/**
 * Returns the FY for "today" in the user's local timezone.
 * Useful for default-select on add-entry forms.
 */
export function currentFinancialYear(): string {
  return financialYearFrom(new Date())
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit + push**

```bash
git add frontend/src/utils/financialYear.ts
git commit -m "feat(tax): add financialYearFrom frontend utility"
git push origin main
```

---

## Task 13: tax.ts — frontend API client

**Files:**
- Create: `frontend/src/types/tax.ts`
- Create: `frontend/src/api/tax.ts`

(No `/impeccable` — types and API client.)

- [ ] **Step 1: Write the types**

`frontend/src/types/tax.ts`:
```typescript
export type TaxEntryKind = 'deductible' | 'income' | 'tax_paid'

export type DeductibleType =
  | 'software' | 'hardware'
  | 'professional_development' | 'professional_services'
  | 'crypto_related' | 'other'

export type IncomeType = 'salary_wages' | 'freelance' | 'interest' | 'dividends' | 'other'
export type TaxPaidType = 'payg_withholding' | 'payg_installment' | 'bas_payment' | 'other'

export interface TaxAttachment {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  uploaded_at: string
}

export interface TaxEntry {
  id: string
  description: string
  amount_aud: number
  date: string
  type: string
  notes: string | null
  financial_year: string
  attachments: TaxAttachment[]
  created_at: string
  updated_at: string
}

export interface TaxEntryCreate {
  description: string
  amount_aud: number
  date: string
  type: string
  notes?: string | null
  attachment_ids?: string[]
}

export interface TaxEntryUpdate {
  description?: string
  amount_aud?: number
  date?: string
  type?: string
  notes?: string | null
}

export interface KrakenAssetActivity {
  aud_spent: number
  buy_count: number
  current_value_aud: number
}

export interface KrakenFYActivity {
  total_aud_invested: number
  total_buys: number
  per_asset: Record<string, KrakenAssetActivity>
}

export interface FYOverview {
  financial_year: string
  income_total_aud: number
  tax_paid_total_aud: number
  deductibles_total_aud: number
  kraken_activity: KrakenFYActivity
}

export const KIND_TO_PATH: Record<TaxEntryKind, string> = {
  deductible: 'deductibles',
  income: 'income',
  tax_paid: 'paid',
}

export const DEDUCTIBLE_TYPES: DeductibleType[] = [
  'software',
  'hardware',
  'professional_development',
  'professional_services',
  'crypto_related',
  'other',
]

export const INCOME_TYPES: IncomeType[] = [
  'salary_wages',
  'freelance',
  'interest',
  'dividends',
  'other',
]

export const TAX_PAID_TYPES: TaxPaidType[] = [
  'payg_withholding',
  'payg_installment',
  'bas_payment',
  'other',
]

export const TYPE_LABELS: Record<string, string> = {
  // deductible
  software: 'Software & subscriptions',
  hardware: 'Hardware & equipment',
  professional_development: 'Professional development',
  professional_services: 'Professional services',
  crypto_related: 'Crypto-related',
  other: 'Other',
  // income
  salary_wages: 'Salary / wages',
  freelance: 'Freelance',
  interest: 'Interest',
  dividends: 'Dividends',
  // tax_paid
  payg_withholding: 'PAYG withholding',
  payg_installment: 'PAYG installment',
  bas_payment: 'BAS payment',
}
```

- [ ] **Step 2: Write the API client**

`frontend/src/api/tax.ts`:
```typescript
import { apiFetch } from './client'
import type {
  FYOverview,
  TaxAttachment,
  TaxEntry,
  TaxEntryCreate,
  TaxEntryKind,
  TaxEntryUpdate,
} from '../types/tax'
import { KIND_TO_PATH } from '../types/tax'

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    throw new Error(`${response.status}: ${text}`)
  }
  return response.json() as Promise<T>
}

export async function fetchOverview(): Promise<FYOverview[]> {
  const r = await apiFetch('/api/tax/overview')
  return jsonOrThrow<FYOverview[]>(r)
}

export async function fetchEntries(kind: TaxEntryKind, fy: string): Promise<TaxEntry[]> {
  const path = KIND_TO_PATH[kind]
  const r = await apiFetch(`/api/tax/${path}?fy=${encodeURIComponent(fy)}`)
  return jsonOrThrow<TaxEntry[]>(r)
}

export async function createEntry(kind: TaxEntryKind, payload: TaxEntryCreate): Promise<TaxEntry> {
  const path = KIND_TO_PATH[kind]
  const r = await apiFetch(`/api/tax/${path}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return jsonOrThrow<TaxEntry>(r)
}

export async function updateEntry(kind: TaxEntryKind, id: string, patch: TaxEntryUpdate): Promise<TaxEntry> {
  const path = KIND_TO_PATH[kind]
  const r = await apiFetch(`/api/tax/${path}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
  return jsonOrThrow<TaxEntry>(r)
}

export async function deleteEntry(kind: TaxEntryKind, id: string): Promise<void> {
  const path = KIND_TO_PATH[kind]
  const r = await apiFetch(`/api/tax/${path}/${id}`, { method: 'DELETE' })
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    throw new Error(`${r.status}: ${text}`)
  }
}

export async function uploadAttachment(
  parentKind: TaxEntryKind,
  parentId: string | null,
  file: File,
): Promise<TaxAttachment> {
  const form = new FormData()
  form.append('parent_kind', parentKind)
  if (parentId) form.append('parent_id', parentId)
  form.append('file', file)

  // FormData uploads must NOT set Content-Type — browser builds the boundary
  const r = await fetch('/api/tax/attachments', {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  return jsonOrThrow<TaxAttachment>(r)
}

export async function fetchAttachmentUrl(id: string): Promise<{ url: string; expires_at: string }> {
  const r = await apiFetch(`/api/tax/attachments/${id}/url`)
  return jsonOrThrow<{ url: string; expires_at: string }>(r)
}

export async function deleteAttachment(id: string): Promise<void> {
  const r = await apiFetch(`/api/tax/attachments/${id}`, { method: 'DELETE' })
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    throw new Error(`${r.status}: ${text}`)
  }
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit + push**

```bash
git add frontend/src/types/tax.ts frontend/src/api/tax.ts
git commit -m "feat(tax): add frontend types and tax API client"
git push origin main
```

---

## Task 14: Existing-component cleanup (AgentPanel + Dashboard)

**Files:**
- Modify: `frontend/src/components/AgentPanel.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

(Mechanical edits — no `/impeccable`.)

- [ ] **Step 1: Read current AgentPanel to identify positioning**

Run: `cat frontend/src/components/AgentPanel.tsx | head -40`
Note the current root `<div>` className — it likely uses something like `fixed inset-y-0 right-0 w-[400px]` already. The change is to ensure it uses `z-50` and does NOT cause the Dashboard content to shift.

- [ ] **Step 2: Update AgentPanel root container**

Find the root container element of `<AgentPanel>` (the outermost `<div>` returned). Ensure it has classes that make it overlay-only:
```tsx
className="fixed inset-y-0 right-0 w-[420px] bg-surface border-l border-surface-border z-50 shadow-2xl"
```
(Adjust width to match the existing value if different. Key additions: `fixed`, `z-50`, `shadow-2xl`.)

If `<AgentPanel>` was previously rendered next to `<main>` via flex, it now sits as a sibling that floats above. The `<Dashboard>` doesn't need to know about it.

- [ ] **Step 3: Update Dashboard to drop SignOutButton from header**

Open `frontend/src/pages/Dashboard.tsx`. Find:
```tsx
import SignOutButton from '../components/SignOutButton'
```
Remove that import.

Find the header block:
```tsx
<div className="max-w-7xl mx-auto flex items-center justify-end gap-4">
  <div className="border border-surface-border rounded-md px-3 py-1.5 hover:border-kraken/50 transition-colors">
    <AgentInput ... />
  </div>
  <SignOutButton onSignedOut={onSignedOut} />
</div>
```

Replace with (drop SignOutButton; the side rail will own it):
```tsx
<div className="max-w-7xl mx-auto flex items-center justify-end">
  <div className="border border-surface-border rounded-md px-3 py-1.5 hover:border-kraken/50 transition-colors">
    <AgentInput
      onSubmit={handleAgentSubmit}
      onFocus={() => setPanelOpen(true)}
      panelOpen={panelOpen}
    />
  </div>
</div>
```

The `onSignedOut` prop on Dashboard becomes unused — DO NOT remove it from `DashboardProps` interface yet. Task 16 wires sign-out into the side rail and we'll need the prop threaded through `App.tsx` accordingly.

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors. (`onSignedOut` is unused but typed; not an error in this project's tsconfig.)

- [ ] **Step 5: Smoke-test the running app**

Start backend (`cd backend && uvicorn main:app --reload`) + frontend (`cd frontend && npm run dev`). Sign in.

Verify:
1. Dashboard header shows ONLY the agent input pill (no Sign out button visible).
2. Cmd+K opens the agent panel as an overlay floating over content (right-aligned, ~420px wide).
3. The Dashboard body doesn't shift when the panel opens.

Stop dev servers.

- [ ] **Step 6: Commit + push**

```bash
git add frontend/src/components/AgentPanel.tsx frontend/src/pages/Dashboard.tsx
git commit -m "refactor(frontend): AgentPanel as overlay; remove SignOutButton from Dashboard"
git push origin main
```

---

## Task 15: SideRail component

**Files:**
- Create: `frontend/src/components/SideRail.tsx`

This task is the first of the **frontend visual** tasks. Per the spec NFR, invoke `/impeccable` to generate the implementation.

- [ ] **Step 1: Invoke `/impeccable` with the following prompt**

```
Build a SideRail component for the Kraken Portfolio Tracker — a personal crypto portfolio dashboard with an existing distinctive visual identity (kraken-purple #9d7aff accent, dark mode, atmospheric, Tailwind v3).

File: frontend/src/components/SideRail.tsx

Contract:
  type View = 'dashboard' | 'tax'
  interface SideRailProps {
    view: View
    onChangeView: (view: View) => void
    onSignedOut: () => void
  }
  export default function SideRail(props: SideRailProps): JSX.Element

Requirements:
- 200px wide, persistent left rail, full viewport height
- Dark surface matching the existing app (use existing tailwind tokens: surface, surface-border, txt-primary, txt-muted, kraken)
- Top: small "Kraken" wordmark in kraken-purple (#9d7aff). Subtle but premium typography.
- Items list: { Dashboard, Tax } with `lucide-react` icons (install via `npm install lucide-react` if not yet in package.json — pick icons that match the destinations, e.g. LayoutDashboard for Dashboard, Receipt for Tax). Vertical stack, comfortable padding.
- Active item: distinctive kraken-purple background tint + 2px left-edge accent in kraken-purple. Subtle hover state for inactive items. Smooth transitions.
- Bottom of rail: relocated SignOutButton (import from '../components/SignOutButton' and pass onSignedOut={onSignedOut})
- Type-safe View union
- Accessibility: aria-current="page" on active item, keyboard-navigable (Tab + Enter switches view)

Existing tailwind tokens are defined in frontend/tailwind.config.js — read that first to use the right tokens. The existing Dashboard uses `bg-surface`, `border-surface-border`, `text-txt-primary`, `text-txt-muted`, `text-kraken`, `hover:border-kraken/50`.

Your job is to deliver a finished, polished component that fits the atmospheric login + dashboard aesthetic. Avoid generic AI patterns: no plain rounded-lg gray cards, no bland icon-text rows. Make it feel like a real product.

When you're done, the App.tsx will render <SideRail view={view} onChangeView={setView} onSignedOut={onSignedOut} /> alongside the main content.
```

- [ ] **Step 2: Install lucide-react (if added by /impeccable)**

If the generated component imports from `lucide-react` and the package isn't already installed:

Run: `cd frontend && npm install lucide-react`

If `/impeccable` chose another approach (custom SVG, no library), skip this step.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Smoke-test in isolation**

Temporarily render `<SideRail view="dashboard" onChangeView={() => {}} onSignedOut={() => {}} />` somewhere visible (e.g., wrap `<Dashboard>` in `<div className="flex"><SideRail .../><div className="flex-1">{...}</div></div>`).

Start dev servers. Verify visually:
1. Rail is 200px wide on the left
2. "Kraken" wordmark visible at top in kraken-purple
3. Two items (Dashboard, Tax) stacked, Dashboard active
4. Click Tax → onChangeView fires (verify with console.log or React DevTools)
5. Sign out at bottom triggers signed-out flow

Revert the temporary App.tsx wiring before commit (Task 16 does it properly).

Stop dev servers.

- [ ] **Step 5: Commit + push**

```bash
git add frontend/src/components/SideRail.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(tax): add SideRail component (left vertical nav)"
git push origin main
```

---

## Task 16: App.tsx integration — view state + render SideRail + TaxHub placeholder

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/TaxHub.tsx` (placeholder; full implementation in Task 18)

(Mostly mechanical; light visual polish only. `/impeccable` not strictly required, but if the layout shell needs styling judgment, invoke it.)

- [ ] **Step 1: Create TaxHub placeholder**

`frontend/src/pages/TaxHub.tsx`:
```tsx
export default function TaxHub() {
  return (
    <main className="flex-1 min-w-0 p-6">
      <p className="text-txt-muted">TaxHub placeholder — full implementation in Task 18.</p>
    </main>
  )
}
```

- [ ] **Step 2: Update App.tsx to add view state**

Open `frontend/src/App.tsx`. Add to imports:
```tsx
import TaxHub from './pages/TaxHub'
import SideRail from './components/SideRail'
```

Inside the `App` component (where `auth` state lives), add:
```tsx
const [view, setView] = useState<'dashboard' | 'tax'>('dashboard')
```

In the `authenticated` branch of the render (currently renders `<Dashboard onSignedOut={...} />`), replace with:
```tsx
return (
  <div className="flex min-h-screen bg-surface">
    <SideRail view={view} onChangeView={setView} onSignedOut={onSignedOut} />
    {view === 'dashboard' ? (
      <Dashboard onSignedOut={onSignedOut} />
    ) : (
      <TaxHub />
    )}
  </div>
)
```

(Keep `onSignedOut` flowing through Dashboard for now; the Dashboard prop is unused after Task 14 but typed.)

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Smoke-test the running app**

Start dev servers. Sign in.

Verify:
1. Side rail visible on the left, Dashboard active
2. Click Tax → side rail updates active state, content area shows the placeholder
3. Click Dashboard → returns to existing Dashboard
4. Cmd+K still opens the agent panel as overlay
5. Sign out works

Stop dev servers.

- [ ] **Step 5: Commit + push**

```bash
git add frontend/src/App.tsx frontend/src/pages/TaxHub.tsx
git commit -m "feat(tax): wire SideRail into App.tsx with view state machine"
git push origin main
```

---

## Task 17: Toast component

**Files:**
- Create: `frontend/src/components/Toast.tsx`
- Modify: `frontend/src/App.tsx` (mount the toast container)

This is reusable infrastructure. Invoke `/impeccable`.

- [ ] **Step 1: Invoke `/impeccable` with the following prompt**

```
Build a Toast component + provider for the Kraken Portfolio Tracker. Existing aesthetic: kraken-purple accent, dark mode, atmospheric, Tailwind v3.

Files:
- frontend/src/components/Toast.tsx (the component + a useToast hook + a ToastContainer that App.tsx mounts)

Contract:
  type ToastVariant = 'success' | 'error'
  interface ToastOptions { variant: ToastVariant; message: string; duration?: number }

  // Hook for consumers to fire toasts
  export function useToast(): { showToast: (opts: ToastOptions) => void }

  // Container — App.tsx mounts this once at the root
  export function ToastContainer(): JSX.Element

Requirements:
- ToastContainer fixed at bottom-right, z-50, stacks multiple toasts vertically
- Auto-dismiss after duration (default 4000ms)
- Success variant: kraken-purple-tinted accent + checkmark icon
- Error variant: loss-red (existing token) accent + warning icon
- Smooth enter/exit animation (subtle, not jarring — slide-up + fade)
- Click-to-dismiss
- Use a singleton event bus (CustomEvent on window OR a tiny Zustand-like store) so any component can fire toasts via useToast() without prop-drilling. Keep it simple: a module-level subscriber list works.
- Accessibility: role="status" on each toast, polite aria-live region

Avoid generic AI Toast patterns: don't make it look like a Tailwind UI demo. Premium, distinctive, fits the atmospheric login aesthetic.

Existing tailwind tokens to use: surface, surface-border, txt-primary, txt-muted, kraken, kraken-light, loss.
```

- [ ] **Step 2: Mount ToastContainer in App.tsx**

Open `frontend/src/App.tsx`. Add to imports:
```tsx
import { ToastContainer } from './components/Toast'
```

Inside the root `<div>` of the authenticated branch (the one wrapping SideRail + content), add `<ToastContainer />` as the last child:
```tsx
return (
  <div className="flex min-h-screen bg-surface">
    <SideRail ... />
    {view === 'dashboard' ? <Dashboard ... /> : <TaxHub />}
    <ToastContainer />
  </div>
)
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Smoke-test**

In `TaxHub.tsx` placeholder, temporarily add a button that fires a toast:
```tsx
import { useToast } from '../components/Toast'
const { showToast } = useToast()
// in render:
<button onClick={() => showToast({ variant: 'success', message: 'It works' })}>Test toast</button>
```

Verify in browser:
1. Click "Test toast" → toast appears bottom-right with kraken-purple accent
2. Auto-dismisses after 4s
3. Try error variant → loss-red accent
4. Multiple toasts stack vertically

Revert the test button before commit.

- [ ] **Step 5: Commit + push**

```bash
git add frontend/src/components/Toast.tsx frontend/src/App.tsx
git commit -m "feat(tax): add Toast component with success/error variants"
git push origin main
```

---

## Task 18: TaxHub shell + useTaxData hook + first-load empty state

**Files:**
- Create: `frontend/src/hooks/useTaxData.ts`
- Modify: `frontend/src/pages/TaxHub.tsx` (replace placeholder)

Visual task — invoke `/impeccable`.

- [ ] **Step 1: Write useTaxData hook**

`frontend/src/hooks/useTaxData.ts`:
```typescript
import { useCallback, useEffect, useState } from 'react'
import {
  fetchOverview,
  fetchEntries,
  createEntry as apiCreate,
  updateEntry as apiUpdate,
  deleteEntry as apiDelete,
} from '../api/tax'
import type {
  FYOverview,
  TaxEntry,
  TaxEntryCreate,
  TaxEntryKind,
  TaxEntryUpdate,
} from '../types/tax'

interface UseTaxDataState {
  overview: FYOverview[] | null
  overviewError: string | null
  entriesByFY: Record<string, Partial<Record<TaxEntryKind, TaxEntry[]>>>
}

export function useTaxData() {
  const [state, setState] = useState<UseTaxDataState>({
    overview: null,
    overviewError: null,
    entriesByFY: {},
  })

  const refreshOverview = useCallback(async () => {
    try {
      const data = await fetchOverview()
      setState((s) => ({ ...s, overview: data, overviewError: null }))
    } catch (e) {
      setState((s) => ({ ...s, overviewError: e instanceof Error ? e.message : String(e) }))
    }
  }, [])

  useEffect(() => {
    void refreshOverview()
  }, [refreshOverview])

  const loadEntries = useCallback(async (kind: TaxEntryKind, fy: string): Promise<void> => {
    const entries = await fetchEntries(kind, fy)
    setState((s) => ({
      ...s,
      entriesByFY: {
        ...s.entriesByFY,
        [fy]: { ...s.entriesByFY[fy], [kind]: entries },
      },
    }))
  }, [])

  const createEntry = useCallback(async (kind: TaxEntryKind, payload: TaxEntryCreate): Promise<TaxEntry> => {
    const entry = await apiCreate(kind, payload)
    // Prepend to existing list, refresh overview
    setState((s) => {
      const fyBucket = s.entriesByFY[entry.financial_year] ?? {}
      const list = fyBucket[kind] ?? []
      return {
        ...s,
        entriesByFY: {
          ...s.entriesByFY,
          [entry.financial_year]: { ...fyBucket, [kind]: [entry, ...list] },
        },
      }
    })
    void refreshOverview()
    return entry
  }, [refreshOverview])

  const updateEntry = useCallback(async (kind: TaxEntryKind, id: string, patch: TaxEntryUpdate): Promise<TaxEntry> => {
    const entry = await apiUpdate(kind, id, patch)
    setState((s) => {
      // Replace in old FY's list, insert into new FY's list if FY changed
      const newByFY = { ...s.entriesByFY }
      for (const fy of Object.keys(newByFY)) {
        const list = newByFY[fy][kind]
        if (!list) continue
        newByFY[fy] = {
          ...newByFY[fy],
          [kind]: list.filter((e) => e.id !== id),
        }
      }
      const fyBucket = newByFY[entry.financial_year] ?? {}
      const list = fyBucket[kind] ?? []
      newByFY[entry.financial_year] = { ...fyBucket, [kind]: [entry, ...list] }
      return { ...s, entriesByFY: newByFY }
    })
    void refreshOverview()
    return entry
  }, [refreshOverview])

  const deleteEntry = useCallback(async (kind: TaxEntryKind, id: string, fy: string): Promise<void> => {
    // Optimistic remove
    let snapshot: TaxEntry[] | undefined
    setState((s) => {
      const fyBucket = s.entriesByFY[fy] ?? {}
      snapshot = fyBucket[kind]
      return {
        ...s,
        entriesByFY: {
          ...s.entriesByFY,
          [fy]: { ...fyBucket, [kind]: (snapshot ?? []).filter((e) => e.id !== id) },
        },
      }
    })
    try {
      await apiDelete(kind, id)
      void refreshOverview()
    } catch (e) {
      // Restore
      setState((s) => ({
        ...s,
        entriesByFY: {
          ...s.entriesByFY,
          [fy]: { ...s.entriesByFY[fy], [kind]: snapshot ?? [] },
        },
      }))
      throw e
    }
  }, [refreshOverview])

  return {
    overview: state.overview,
    overviewError: state.overviewError,
    entriesByFY: state.entriesByFY,
    refreshOverview,
    loadEntries,
    createEntry,
    updateEntry,
    deleteEntry,
  }
}
```

- [ ] **Step 2: Invoke `/impeccable` for the TaxHub shell**

```
Build the TaxHub page shell for the Kraken Portfolio Tracker. Existing aesthetic: kraken-purple #9d7aff accent, dark mode, atmospheric, Tailwind v3. Existing pages: Dashboard.tsx (single-page, hero portfolio value, line chart, asset breakdown).

File: frontend/src/pages/TaxHub.tsx (replace existing placeholder)

Contract:
  export default function TaxHub(): JSX.Element

Behavior:
- Calls useTaxData() hook (frontend/src/hooks/useTaxData.ts) on mount
- Renders one of three states based on overview data:
  1. Loading (overview === null, no error) → atmospheric skeleton/shimmer
  2. Empty (overview === [], no error) → first-run empty card centered:
     - Title: "Your tax workspace"
     - Subtitle: "Track income, tax paid, and deductibles in one place. Drop in receipts, screenshots, anything tax-related."
     - "+ Add your first entry" CTA button
     - When clicked: open EntryDrawer (state for now: just console.log — Task 21 wires it)
  3. Has data (overview.length > 0, no error) → render <FYAccordion> placeholder for now (Task 19 builds it)
  4. Error → centered error card with retry button

Layout:
- Use existing pattern: <main className="flex-1 min-w-0">
- Top of page: "Tax" page title, large but tasteful
- The page should NOT have an agent input pill (Spec 1 keeps the agent on Dashboard only)
- Maximum content width matches Dashboard (max-w-7xl mx-auto px-6)

This is the FIRST visual surface of the Tax tab. Make it impressive — it sets the tone for everything else. Atmospheric, distinctive, premium feel. The empty state in particular should make the user excited to start logging things.

Use existing tokens: bg-surface, border-surface-border, text-txt-primary, text-txt-muted, text-kraken. The site already imports react-markdown and uses recharts; you have free rein on lucide icons (already installed in Task 15).

Stub-out the FYAccordion placeholder for now (Task 19 replaces it) — render a simple <div> showing the overview totals as a JSON dump, with a comment indicating Task 19 replaces it.
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Smoke-test**

Start dev servers. Sign in. Click Tax in side rail.

Verify:
1. Loading state shows briefly while fetch is in flight
2. With no data: empty card renders with CTA
3. With data: page renders the placeholder FYAccordion stub
4. Error state: stop the backend, click Tax → error card appears with retry button

Stop dev servers.

- [ ] **Step 5: Commit + push**

```bash
git add frontend/src/hooks/useTaxData.ts frontend/src/pages/TaxHub.tsx
git commit -m "feat(tax): TaxHub shell + useTaxData hook + first-load empty state"
git push origin main
```

---

## Task 19: FYAccordion + FYSection + FYSummaryStrip

**Files:**
- Create: `frontend/src/components/tax/FYAccordion.tsx`
- Create: `frontend/src/components/tax/FYSection.tsx`
- Create: `frontend/src/components/tax/FYSummaryStrip.tsx`
- Modify: `frontend/src/pages/TaxHub.tsx` (replace placeholder with `<FYAccordion>`)

Visual task — invoke `/impeccable`.

- [ ] **Step 1: Invoke `/impeccable` with the following prompt**

```
Build the FY accordion machinery for the Tax Hub. Three components, all kraken-purple/dark/atmospheric Tailwind v3.

Files:
- frontend/src/components/tax/FYAccordion.tsx
- frontend/src/components/tax/FYSection.tsx
- frontend/src/components/tax/FYSummaryStrip.tsx

Contract:

  // FYAccordion.tsx
  interface FYAccordionProps {
    overview: FYOverview[]                              // from types/tax
    expandedFYs: Set<string>
    onToggleFY: (fy: string) => void
    renderFYContent: (fy: string) => React.ReactNode    // injected by parent — what shows inside an open FY
  }
  export default function FYAccordion(props: FYAccordionProps): JSX.Element

  // FYSection.tsx — one section per FY
  interface FYSectionProps {
    fy: string
    overview: FYOverview                                // for the header total
    expanded: boolean
    onToggle: () => void
    children: React.ReactNode                           // rendered inside when expanded
  }
  export default function FYSection(props: FYSectionProps): JSX.Element

  // FYSummaryStrip.tsx — the 4-totals strip at top of an open FY
  interface FYSummaryStripProps {
    overview: FYOverview                                // contains income/tax_paid/deductibles totals + kraken_activity
  }
  export default function FYSummaryStrip(props: FYSummaryStripProps): JSX.Element

Behavior:
- FYAccordion renders one <FYSection> per fy, descending order (current FY first)
- Current FY is the one matching `currentFinancialYear()` from utils/financialYear.ts. Auto-include in expandedFYs by default (parent handles via initial state).
- Clicking an FY header toggles expanded; smooth height transition
- Section header shows "FY 2025-26" left, "Net total" right (computed: income - deductibles for now; tax_paid is informational, not subtracted)
- Use kraken-purple for active/expanded states, subdued tones for collapsed
- FYSummaryStrip renders 4 stat cards in a horizontal row (responsive — stack on narrow): Income, Tax paid, Deductibles, Crypto invested. Each shows "label" + "$amount" in monospace
- Premium typography, smooth transitions, distinctive look

This is the SPINE of the Tax tab — make it impressive. Atmospheric, tasteful, scannable at EOFY-glance distance.

Modify TaxHub.tsx to:
- Manage `expandedFYs: Set<string>` state, initialized to {currentFinancialYear()}
- Render <FYAccordion overview={overview} expandedFYs={expandedFYs} onToggleFY={...} renderFYContent={(fy) => /* placeholder div for Task 20 — return JSON stringify of entries */} />
- Stub the renderFYContent until Task 20

Existing tokens: bg-surface, border-surface-border, text-txt-primary, text-txt-muted, text-kraken, kraken-light, surface-elevated (if exists — otherwise bg-surface/80).
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Smoke-test**

Start dev servers. Sign in. Tax tab.

Verify (with seed data — manually insert via SQL editor a couple of test rows in `tax_deductibles` if needed):
1. Current FY auto-expanded
2. Older FYs collapsed by default
3. Click a collapsed FY header → smoothly expands, shows summary strip + placeholder content
4. Click again → collapses
5. Per-FY total in header matches sum of section totals

Stop dev servers.

- [ ] **Step 4: Commit + push**

```bash
git add frontend/src/components/tax/FYAccordion.tsx frontend/src/components/tax/FYSection.tsx frontend/src/components/tax/FYSummaryStrip.tsx frontend/src/pages/TaxHub.tsx
git commit -m "feat(tax): FY accordion with summary strip and expand/collapse"
git push origin main
```

---

## Task 20: KrakenActivityRow + EntryList

**Files:**
- Create: `frontend/src/components/tax/KrakenActivityRow.tsx`
- Create: `frontend/src/components/tax/EntryList.tsx`
- Modify: `frontend/src/pages/TaxHub.tsx` (wire renderFYContent to render the four sub-sections)

Visual task — invoke `/impeccable`.

- [ ] **Step 1: Invoke `/impeccable` with the following prompt**

```
Build the inside-an-open-FY content components for the Tax Hub.

Files:
- frontend/src/components/tax/KrakenActivityRow.tsx (slim read-only summary row)
- frontend/src/components/tax/EntryList.tsx (list of entries for one kind in one FY)

Contract:

  // KrakenActivityRow.tsx
  interface KrakenActivityRowProps {
    activity: KrakenFYActivity     // from types/tax
  }
  export default function KrakenActivityRow(props: KrakenActivityRowProps): JSX.Element

  // EntryList.tsx
  interface EntryListProps {
    kind: TaxEntryKind
    fy: string
    entries: TaxEntry[] | undefined  // undefined = not yet loaded
    onAdd: () => void                 // open create drawer
    onEdit: (entry: TaxEntry) => void
    onDelete: (entry: TaxEntry) => void
    onViewAttachment: (attachmentId: string) => void
  }
  export default function EntryList(props: EntryListProps): JSX.Element

Behavior:

KrakenActivityRow:
- Slim horizontal row (no add button, read-only)
- Shows: "Crypto activity · {total_buys} buys · ${total_aud_invested} invested"
- Per-asset chips below: ETH $X · SOL $Y · ADA $Z (use existing asset color util if present, otherwise plain text)
- Empty state: "No crypto buys this FY"
- Smaller / quieter visual weight than EntryList

EntryList:
- Section header: "Income · {count} · ${total}" (sum the entries) + "+ Add" button (top right of section)
- Filter dropdown: "All categories ▾" — filters by entry.type (use TYPE_LABELS from types/tax)
- Search box: filters by description (case-insensitive ILIKE-style on the client)
- Top 5 entries shown by default; "Show all (N)" link at bottom expands
- Each row: date · description · type label (subtle) · amount monospace (right-aligned) · attachments (chips), and a kebab menu (Edit / Delete)
- Optimistic delete: clicking Delete fires onDelete (parent handles undo via toast on error)
- Empty state: "No income for FY 2025-26 · + Add"
- Loading state (entries === undefined): atmospheric skeleton rows

Premium typography, smooth state transitions.

Modify TaxHub.tsx:
- Replace renderFYContent stub with a function that:
  1. On expand, calls loadEntries(kind, fy) for all 3 kinds if not already loaded (use useTaxData's entriesByFY)
  2. Returns: <FYSummaryStrip /> + <EntryList kind="income" /> + <EntryList kind="tax_paid" /> + <EntryList kind="deductible" /> + <KrakenActivityRow />
  3. onAdd/onEdit/onDelete/onViewAttachment callbacks: stub with console.log for now (Task 21 wires onAdd/onEdit; Task 22 wires onViewAttachment)

Existing tokens, plus consider using a subtle alternating-row treatment or a vertical accent stripe for visual rhythm.
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Smoke-test**

Start dev servers. Add a few test rows via SQL editor across multiple FYs and kinds. Sign in. Tax tab.

Verify:
1. Expanding an FY loads entries for all three kinds
2. Each section shows top 5 entries, "Show all" link if >5
3. Filter dropdown narrows to one type
4. Search filters by description
5. Kebab menu shows Edit/Delete options
6. Delete fires the optimistic-remove path (entry vanishes immediately)
7. Kraken activity row shows total + per-asset breakdown if there's any lot data
8. Empty FY (no entries of a given kind) shows empty state

Stop dev servers.

- [ ] **Step 4: Commit + push**

```bash
git add frontend/src/components/tax/KrakenActivityRow.tsx frontend/src/components/tax/EntryList.tsx frontend/src/pages/TaxHub.tsx
git commit -m "feat(tax): EntryList + KrakenActivityRow with filter/search/optimistic delete"
git push origin main
```

---

## Task 21: EntryDrawer + form (no file upload yet)

**Files:**
- Create: `frontend/src/components/tax/EntryDrawer.tsx`
- Modify: `frontend/src/pages/TaxHub.tsx` (wire drawer state, onAdd/onEdit handlers)

Visual task — invoke `/impeccable`.

- [ ] **Step 1: Invoke `/impeccable` with the following prompt**

```
Build the EntryDrawer for the Tax Hub — a slide-in form for create/edit.

File: frontend/src/components/tax/EntryDrawer.tsx

Contract:
  type DrawerMode = 'create' | 'edit' | null
  interface EntryDrawerProps {
    open: boolean
    mode: DrawerMode
    kind: TaxEntryKind | null     // null only when open is false
    initialEntry?: TaxEntry        // present in edit mode
    onClose: () => void
    onSave: (kind: TaxEntryKind, payload: TaxEntryCreate, isEdit: boolean, id?: string) => Promise<void>
  }
  export default function EntryDrawer(props: EntryDrawerProps): JSX.Element

Behavior:
- Slide-in from right, fixed inset-y-0 right-0 w-[480px], z-50, dark surface
- IMPORTANT: agent panel (Cmd+K) and this drawer are mutually exclusive. The drawer being open means the agent panel must close. App.tsx coordinates via state — your job here is just "this is a fixed right-side overlay with z-50".
- On Escape: onClose
- On click outside drawer (backdrop): onClose
- Form fields:
  - Description (text, required, max 200)
  - Amount AUD (number, required, > 0, step 0.01)
  - Date (date input, required, defaults to today in create mode)
  - Type (dropdown — populated from DEDUCTIBLE_TYPES / INCOME_TYPES / TAX_PAID_TYPES based on kind, with TYPE_LABELS for display)
  - Notes (textarea, optional, max 4000)
  - File drop zone — STUB IT for Task 22, render a placeholder "Files (coming in Task 22)" pill
- Inline validation errors next to fields on blur or save attempt
- Save button: kraken-purple, full-width-ish, with loading spinner + disabled while in flight
- Save success: fire success toast via useToast(), call onClose
- Save failure: stay open, error toast via useToast()
- Cancel/close button at top right of drawer

Edit mode pre-fills from initialEntry; the title is "Edit deductible" / "Edit income" / etc. Create mode title is "Add deductible" / etc.

Polish: smooth slide-in animation (transform, not width). Premium typography. The form should feel like a focused, calm capture surface — not bureaucratic.

Modify TaxHub.tsx:
- Add drawer state: { open, mode, kind, initialEntry }
- Wire onAdd(kind) → set state to {open: true, mode: 'create', kind}
- Wire onEdit(kind, entry) → set state to {open: true, mode: 'edit', kind, initialEntry: entry}
- Wire onSave: call createEntry/updateEntry from useTaxData, then close drawer
- Render <EntryDrawer ...state /> at the page root
- The existing "+ Add your first entry" button on the empty state opens the drawer with a kind picker
  - Drawer kind picker: when kind is null in create mode, show a 3-card picker first (Income / Tax paid / Deductible), then proceed to the form. /impeccable should design this nicely.
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Smoke-test**

Start dev servers. Sign in. Tax tab.

Verify:
1. Click "+ Add" on Deductibles section header → drawer slides in, form ready, kind preselected
2. Fill fields, click Save → drawer closes, new row appears at top of list, success toast fires
3. Open the kebab menu on a row → click Edit → drawer slides in pre-filled
4. Edit a field, save → row updates in place
5. Validation: try amount=0 → inline error on the field
6. Validation: clear description → inline error
7. Cancel button closes drawer without saving
8. Escape closes drawer
9. Click the empty-state CTA → drawer opens with kind picker
10. Cmd+K while drawer open: if there are no pending uploads, drawer auto-closes and agent panel opens. If there are pending uploads, a "Discard N uploaded files?" confirm dialog appears first. (Per spec Section 6 "Right-side panel coexistence".)

Stop dev servers.

- [ ] **Step 4: Commit + push**

```bash
git add frontend/src/components/tax/EntryDrawer.tsx frontend/src/pages/TaxHub.tsx
git commit -m "feat(tax): EntryDrawer with create/edit form and validation"
git push origin main
```

---

## Task 22: FileDropZone + AttachmentChip + upload/view flow

**Files:**
- Create: `frontend/src/components/tax/FileDropZone.tsx`
- Create: `frontend/src/components/tax/AttachmentChip.tsx`
- Modify: `frontend/src/components/tax/EntryDrawer.tsx` (replace stub with real drop zone)
- Modify: `frontend/src/components/tax/EntryList.tsx` (wire onViewAttachment to fetch signed URL)
- Modify: `frontend/src/pages/TaxHub.tsx` (handle attachment view via window.open)

Visual task — invoke `/impeccable`.

- [ ] **Step 1: Invoke `/impeccable` with the following prompt**

```
Build the file upload + attachment view flow for the Tax Hub.

Files:
- frontend/src/components/tax/FileDropZone.tsx (drag-drop + click-to-pick)
- frontend/src/components/tax/AttachmentChip.tsx (rendered chip per attached file with progress/done/error states + click-to-view)

Contract:

  // FileDropZone.tsx
  interface FileDropZoneProps {
    parentKind: TaxEntryKind
    onUploaded: (attachment: TaxAttachment) => void
    onError: (message: string) => void
  }
  export default function FileDropZone(props: FileDropZoneProps): JSX.Element

  // AttachmentChip.tsx
  type ChipState = { kind: 'uploading'; progress: number } | { kind: 'done' } | { kind: 'error'; message: string }
  interface AttachmentChipProps {
    attachment: TaxAttachment
    state?: ChipState                // if undefined → done
    onView: () => void
    onRemove: () => void              // detach (does NOT delete the entry)
  }
  export default function AttachmentChip(props: AttachmentChipProps): JSX.Element

Behavior:

FileDropZone:
- Click-to-pick OR drag-drop
- Multi-file support
- Per-file: call api/tax.uploadAttachment(parentKind, null, file) — note parentId is null for pending uploads
- Validation client-side first: reject files >10MB or wrong type with onError("...")
- During upload: show progress (or indeterminate spinner if XMLHttpRequest progress isn't easy)
- On success: call onUploaded(attachment)
- Visual: large dashed-border drop zone when empty, compact chip stack when has files; smooth transition
- Atmospheric, kraken-purple accent on hover/drop

AttachmentChip:
- Compact pill: filename · file-size · state indicator
- Click chip → onView (parent fetches signed URL and opens new tab)
- X icon to remove → onRemove (just detaches from this in-progress entry; if entry hasn't been saved, the file remains as PENDING and the sweep job cleans it up after 24h)
- Done state: subtle kraken-purple tint
- Uploading: subtle progress fill or pulse
- Error: loss-red border with the error message shown below the chip (no automatic retry in Spec 1; user removes the failed chip and re-drops the file)

Modifications:

EntryDrawer.tsx:
- Replace the FileDropZone stub with the real component
- Track local state: `attachments: TaxAttachment[]` and `attachmentStates: Record<string, ChipState>`
- onUploaded → append to attachments
- onError → fire error toast
- On Save: pass `attachment_ids: attachments.map(a => a.id)` in the TaxEntryCreate payload
- On drawer close with pending uploads: confirm dialog "Discard N uploaded files?" — if yes, call deleteAttachment for each

EntryList.tsx:
- Render <AttachmentChip> for each entry.attachments[] item, click → onViewAttachment(att.id)

TaxHub.tsx:
- onViewAttachment handler: call api/tax.fetchAttachmentUrl(id) → window.open(url, '_blank')

This is the LAST major component. Polish bar is high. Smooth, premium, never feels like an afterthought form. Drag-drop should feel responsive and joyful.
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Run the full manual smoke checklist**

Start dev servers. Sign in. Tax tab.

Run through every item from spec Section 9:

1. ✅ Side rail renders, both items click and switch view
2. ✅ Empty Tax tab shows the first-load card (sign in to a fresh DB to verify, or temporarily clear the tax tables)
3. ✅ + Add deductible → drawer opens → fill form (no file) → save → row appears
4. ✅ Edit that entry → change amount → save → row updates with new amount
5. ✅ Add an attachment → file uploads, chip shows, save persists, refresh page → attachment chip still there
6. ✅ Click attachment chip → opens in new tab with valid 5-min URL
7. ✅ Delete entry → row disappears immediately; reload page confirms it's actually gone
8. ✅ Add entries across 2+ FYs → both FY sections appear in accordion with correct totals
9. ✅ Older FY collapsed by default, expand → entries load
10. ✅ Switch to Dashboard tab and back to Tax preserves expanded-FY state
11. ✅ Cmd+K opens agent panel as overlay (not a slide-in pushing content)
12. ✅ Sign out from side rail returns to login
13. ✅ Wrong-type upload (try .exe) → inline error (toast)
14. ✅ Oversized upload (try 15MB file) → inline error (toast)
15. ✅ Income and Tax-paid sections behave parallel to Deductibles (try adding an income entry with attachment, edit, delete)

Any failed item → fix before commit, possibly invoking `/impeccable` again.

Stop dev servers.

- [ ] **Step 4: Final commit + push**

```bash
git add frontend/src/components/tax/FileDropZone.tsx frontend/src/components/tax/AttachmentChip.tsx frontend/src/components/tax/EntryDrawer.tsx frontend/src/components/tax/EntryList.tsx frontend/src/pages/TaxHub.tsx
git commit -m "feat(tax): file upload + attachment chips + view flow with signed URLs"
git push origin main
```

**Spec 1 complete.** Save a Phase 5 status memory describing what shipped, any non-obvious gotchas discovered during implementation, and what's left for Spec 2 (CGT engine). Pattern matches the existing `project_kraken_phase4.md` memory.

---

## Final smoke + project memory

After Task 22, run the full smoke checklist one more time on the deployed/built version, then:

- [ ] Save `project_kraken_phase5.md` memory with what shipped, gotchas, and Spec 2 backlog
- [ ] Update `MEMORY.md` index with the new memory pointer
- [ ] Optionally: post in user's GitHub issue tracker that Spec 1 is done

---

## Notes for the implementer

- **Per-task push is mandatory.** Don't batch commits — the user reviews each one on GitHub.
- **`/impeccable` is mandatory** for visual frontend tasks (every task labeled "Visual task — invoke `/impeccable`"). Don't write Tailwind by hand on those.
- **TDD discipline**: write the test first, run it, see it fail, then implement. Don't skip the "see it fail" step.
- **No mocking of the database in integration tests** — the `test_tax_integration.py` file uses the real Supabase test schema via `clean_test_tables`.
- **Backend-first ordering matters**: tasks 1-11 must complete before tasks 14+ since the frontend exercises real endpoints in smoke tests.
- **Migration is manual.** The user runs `003_tax_hub.sql` and `test_003_tax_hub.sql` in the Supabase SQL editor. Same convention as Phase 1.
- **Storage bucket is also manual** (see Pre-flight section). One-time setup.
- **Existing test pattern**: `pytest -v` from `backend/`, mocks at `backend.services.<module>.get_supabase` and `backend.services.<module>.<other_dep>`, see `test_portfolio_service.py` for the canonical example.
