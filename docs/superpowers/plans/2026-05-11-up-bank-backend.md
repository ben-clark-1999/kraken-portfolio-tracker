# UP Bank Integration — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire UP Bank (accounts, transactions, balances) into the backend so the existing FastAPI app exposes UP data via REST and the LangGraph agent can answer cash/spending questions.

**Architecture:** New `up_*` tables and repos parallel to crypto. `portfolio_snapshots` extended with a `source` column so combined net-worth charts come from one query. UP client is async (httpx) with 429/5xx backoff. Sync runs every 15 min on the existing `AsyncIOScheduler`; first run is full backfill, subsequent runs are incremental with a 6-hour overlap to catch HELD→SETTLED. 5 new MCP tools and a new `cash` classifier category route to a dedicated `cash_agent` graph node.

**Tech Stack:** Python 3.12, FastAPI, pydantic, supabase-py (sync), httpx (async), pytest + respx, LangGraph, Anthropic.

**Companion plan:** `2026-05-11-up-bank-frontend.md` (written after this plan executes).

---

## Part 1 — Foundations

### Task 1: Add UP_PAT to Settings

**Files:**
- Modify: `backend/config/settings.py`
- Test: `backend/tests/test_settings_up.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_settings_up.py`:

```python
from backend.config import settings


def test_up_pat_present_and_nonempty():
    assert hasattr(settings, "up_pat")
    assert isinstance(settings.up_pat, str)
    assert len(settings.up_pat) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_settings_up.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'up_pat'`

- [ ] **Step 3: Add the field to Settings**

Modify `backend/config/settings.py`. Find the `Settings` class and add `up_pat: str` next to the other secrets:

```python
class Settings(BaseSettings):
    kraken_api_key: str
    kraken_api_secret: str
    supabase_url: str
    supabase_key: str
    supabase_db_url: str = ""
    anthropic_api_key: str = ""
    app_password_hash: str
    jwt_secret: str
    kraken_live_tests: bool = False
    up_pat: str

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_settings_up.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/config/settings.py backend/tests/test_settings_up.py
git commit -m "feat(config): expose UP_PAT in Settings"
git push
```

---

### Task 2: Create migration 005_up_bank.sql

**Files:**
- Create: `supabase/migrations/005_up_bank.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/005_up_bank.sql`:

```sql
-- UP Bank tables and snapshot source-awareness.

CREATE TABLE up_accounts (
  id              TEXT PRIMARY KEY,
  display_name    TEXT NOT NULL,
  account_type    TEXT NOT NULL,
  ownership_type  TEXT NOT NULL,
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
  status             TEXT NOT NULL,
  description        TEXT NOT NULL,
  message            TEXT,
  raw_text           TEXT,
  amount_value       NUMERIC(20, 2) NOT NULL,
  amount_currency    TEXT NOT NULL DEFAULT 'AUD',
  category_id        TEXT REFERENCES up_categories(id),
  parent_category_id TEXT REFERENCES up_categories(id),
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

ALTER TABLE portfolio_snapshots
  ADD COLUMN source TEXT NOT NULL DEFAULT 'crypto'
  CHECK (source IN ('crypto', 'up'));

CREATE INDEX idx_snapshots_source_captured
  ON portfolio_snapshots(source, captured_at DESC);
```

- [ ] **Step 2: Apply the migration to the live Supabase database**

Run via the Supabase MCP `apply_migration` tool with:
- name: `005_up_bank`
- query: the SQL above

OR if running directly:
```bash
psql "$(grep SUPABASE_DB_URL .env | cut -d= -f2-)" -f supabase/migrations/005_up_bank.sql
```

Expected: no errors. Verify with `\d up_accounts`, `\d up_transactions`, `\d up_sync_log`, and `\d portfolio_snapshots` (last should now show `source` column).

- [ ] **Step 3: Create matching test schema**

Create `supabase/migrations/test_005_up_bank.sql`:

```sql
-- Mirror of 005_up_bank.sql for the `test` schema. Test fixtures
-- truncate these tables between cases.

CREATE TABLE test.up_accounts (LIKE public.up_accounts INCLUDING ALL);
CREATE TABLE test.up_categories (LIKE public.up_categories INCLUDING ALL);
CREATE TABLE test.up_transactions (LIKE public.up_transactions INCLUDING ALL);
CREATE TABLE test.up_sync_log (LIKE public.up_sync_log INCLUDING ALL);

ALTER TABLE test.portfolio_snapshots
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'crypto'
  CHECK (source IN ('crypto', 'up'));
```

Apply to the test schema:
```bash
psql "$(grep SUPABASE_DB_URL .env | cut -d= -f2-)" -f supabase/migrations/test_005_up_bank.sql
```

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/005_up_bank.sql supabase/migrations/test_005_up_bank.sql
git commit -m "feat(db): UP Bank tables + portfolio_snapshots.source"
git push
```

---

### Task 3: Pydantic models for UP resources

**Files:**
- Create: `backend/models/up.py`
- Test: `backend/tests/test_up_models.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_models.py`:

```python
from datetime import datetime, timezone
from backend.models.up import UpAccount, UpCategory, UpTransaction


def test_up_account_construction():
    a = UpAccount(
        id="abc", display_name="Spending", account_type="TRANSACTIONAL",
        ownership_type="INDIVIDUAL", balance_value=42.50, balance_currency="AUD",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert a.balance_value == 42.50


def test_up_category_optional_parent():
    c = UpCategory(id="good-life", name="Good Life")
    assert c.parent_id is None


def test_up_transaction_signed_amount():
    t = UpTransaction(
        id="t1", account_id="a1", status="SETTLED", description="Coffee",
        amount_value=-5.50, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert t.amount_value < 0
    assert t.message is None
    assert t.settled_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.models.up'`

- [ ] **Step 3: Implement the models**

Create `backend/models/up.py`:

```python
"""Pydantic models for UP Bank API resources."""

from datetime import datetime
from pydantic import BaseModel


class UpAccount(BaseModel):
    id: str
    display_name: str
    account_type: str  # TRANSACTIONAL | SAVER | HOME_LOAN
    ownership_type: str  # INDIVIDUAL | JOINT
    balance_value: float  # AUD, signed (positive for assets, negative for HOME_LOAN)
    balance_currency: str = "AUD"
    created_at: datetime


class UpCategory(BaseModel):
    id: str
    name: str
    parent_id: str | None = None


class UpTransaction(BaseModel):
    id: str
    account_id: str
    status: str  # HELD | SETTLED
    description: str
    message: str | None = None
    raw_text: str | None = None
    amount_value: float  # signed; negative = outflow
    amount_currency: str = "AUD"
    category_id: str | None = None
    parent_category_id: str | None = None
    created_at: datetime
    settled_at: datetime | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models/up.py backend/tests/test_up_models.py
git commit -m "feat(models): UP Bank pydantic models"
git push
```

---

### Task 4: UpClient — auth, ping, list_accounts

**Files:**
- Create: `backend/services/up_client.py`
- Test: `backend/tests/test_up_client_basic.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_up_client_basic.py`:

```python
import pytest
import respx
from httpx import Response
from backend.services.up_client import UpClient, UpAuthError


@pytest.mark.asyncio
@respx.mock
async def test_list_accounts_parses_response():
    respx.get("https://api.up.com.au/api/v1/accounts").mock(return_value=Response(
        200,
        json={
            "data": [{
                "type": "accounts",
                "id": "acct-1",
                "attributes": {
                    "displayName": "Spending",
                    "accountType": "TRANSACTIONAL",
                    "ownershipType": "INDIVIDUAL",
                    "balance": {"currencyCode": "AUD", "value": "100.00", "valueInBaseUnits": 10000},
                    "createdAt": "2026-01-01T00:00:00+10:00",
                },
            }],
            "links": {"prev": None, "next": None},
        },
    ))
    client = UpClient("up:test:token")
    accounts = await client.list_accounts()
    assert len(accounts) == 1
    assert accounts[0].id == "acct-1"
    assert accounts[0].display_name == "Spending"
    assert accounts[0].balance_value == 100.00


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_auth_error():
    respx.get("https://api.up.com.au/api/v1/accounts").mock(return_value=Response(401, json={"errors": []}))
    client = UpClient("up:test:bad")
    with pytest.raises(UpAuthError):
        await client.list_accounts()
```

- [ ] **Step 2: Install respx if not present**

```bash
backend/.venv/bin/pip install respx
backend/.venv/bin/pip freeze | grep respx >> backend/requirements.txt
# Then dedupe requirements.txt manually if needed
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/test_up_client_basic.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement UpClient (basic)**

Create `backend/services/up_client.py`:

```python
"""Async HTTP client for the UP Bank API.

Handles authentication, pagination, retries (429 with Retry-After,
5xx with exponential backoff). Generators auto-walk `next` links.
"""

import asyncio
import logging
from datetime import datetime
from typing import AsyncIterator, Literal

import httpx

from backend.models.up import UpAccount, UpCategory, UpTransaction

logger = logging.getLogger(__name__)


class UpClientError(Exception):
    """Base exception for UP client failures."""


class UpAuthError(UpClientError):
    """401 — token revoked or invalid."""


class UpRateLimitError(UpClientError):
    """429 — exceeded rate limit even after retry."""


class UpServerError(UpClientError):
    """5xx — UP API down or returning errors."""


class UpClient:
    BASE = "https://api.up.com.au/api/v1"
    BACKOFFS = (1.0, 4.0, 16.0)

    def __init__(self, token: str, *, timeout: float = 30.0):
        self._headers = {"Authorization": f"Bearer {token}"}
        self._timeout = timeout

    async def _request(self, url: str, params: dict | None = None) -> dict:
        """Single request with retry on 429/5xx."""
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            for attempt, backoff in enumerate([0.0, *self.BACKOFFS]):
                if backoff > 0:
                    await asyncio.sleep(backoff)
                resp = await http.get(url, headers=self._headers, params=params)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 401:
                    raise UpAuthError("UP API returned 401 — token invalid or revoked")
                if resp.status_code == 429:
                    if attempt == len(self.BACKOFFS):
                        raise UpRateLimitError("UP API 429 — exhausted retries")
                    retry_after = float(resp.headers.get("Retry-After", backoff or 1))
                    await asyncio.sleep(retry_after)
                    continue
                if 500 <= resp.status_code < 600:
                    if attempt == len(self.BACKOFFS):
                        raise UpServerError(f"UP API {resp.status_code} — exhausted retries")
                    continue
                raise UpClientError(f"Unexpected UP API status {resp.status_code}: {resp.text[:200]}")
            raise UpClientError("UP request loop exited unexpectedly")

    async def list_accounts(self) -> list[UpAccount]:
        url = f"{self.BASE}/accounts"
        out: list[UpAccount] = []
        while url:
            payload = await self._request(url)
            for row in payload["data"]:
                attrs = row["attributes"]
                out.append(UpAccount(
                    id=row["id"],
                    display_name=attrs["displayName"],
                    account_type=attrs["accountType"],
                    ownership_type=attrs["ownershipType"],
                    balance_value=float(attrs["balance"]["value"]),
                    balance_currency=attrs["balance"]["currencyCode"],
                    created_at=datetime.fromisoformat(attrs["createdAt"]),
                ))
            url = payload.get("links", {}).get("next")
        return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_up_client_basic.py -v`
Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add backend/services/up_client.py backend/tests/test_up_client_basic.py backend/requirements.txt
git commit -m "feat(up): UpClient with auth, retries, list_accounts"
git push
```

---

### Task 5: UpClient — list_categories

**Files:**
- Modify: `backend/services/up_client.py`
- Test: `backend/tests/test_up_client_categories.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_client_categories.py`:

```python
import pytest
import respx
from httpx import Response
from backend.services.up_client import UpClient


@pytest.mark.asyncio
@respx.mock
async def test_list_categories_with_parents():
    respx.get("https://api.up.com.au/api/v1/categories").mock(return_value=Response(
        200,
        json={
            "data": [
                {
                    "type": "categories",
                    "id": "good-life",
                    "attributes": {"name": "Good Life"},
                    "relationships": {"parent": {"data": None}},
                },
                {
                    "type": "categories",
                    "id": "restaurants-and-cafes",
                    "attributes": {"name": "Restaurants and Cafes"},
                    "relationships": {"parent": {"data": {"type": "categories", "id": "good-life"}}},
                },
            ],
        },
    ))
    client = UpClient("up:test:tok")
    cats = await client.list_categories()
    assert len(cats) == 2
    parent = next(c for c in cats if c.id == "good-life")
    child = next(c for c in cats if c.id == "restaurants-and-cafes")
    assert parent.parent_id is None
    assert child.parent_id == "good-life"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_client_categories.py -v`
Expected: FAIL with `AttributeError: 'UpClient' object has no attribute 'list_categories'`

- [ ] **Step 3: Implement list_categories**

Append to `backend/services/up_client.py` inside the `UpClient` class:

```python
    async def list_categories(self) -> list[UpCategory]:
        payload = await self._request(f"{self.BASE}/categories")
        out: list[UpCategory] = []
        for row in payload["data"]:
            parent_data = row.get("relationships", {}).get("parent", {}).get("data")
            out.append(UpCategory(
                id=row["id"],
                name=row["attributes"]["name"],
                parent_id=parent_data["id"] if parent_data else None,
            ))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_client_categories.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/up_client.py backend/tests/test_up_client_categories.py
git commit -m "feat(up): UpClient.list_categories"
git push
```

---

### Task 6: UpClient — list_transactions (paginated async generator)

**Files:**
- Modify: `backend/services/up_client.py`
- Test: `backend/tests/test_up_client_transactions.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_client_transactions.py`:

```python
from datetime import datetime, timezone

import pytest
import respx
from httpx import Response
from backend.services.up_client import UpClient


def _tx_row(tx_id: str, status: str = "SETTLED", category_id: str | None = "restaurants-and-cafes"):
    rels = {
        "account": {"data": {"type": "accounts", "id": "acct-1"}},
        "category": {"data": {"type": "categories", "id": category_id}} if category_id else {"data": None},
        "parentCategory": {"data": {"type": "categories", "id": "good-life"}} if category_id else {"data": None},
    }
    return {
        "type": "transactions", "id": tx_id,
        "attributes": {
            "status": status, "rawText": "RAW", "description": "Coffee", "message": None,
            "isCategorizable": True, "holdInfo": None, "roundUp": None, "cashback": None,
            "amount": {"currencyCode": "AUD", "value": "-5.50", "valueInBaseUnits": -550},
            "foreignAmount": None, "cardPurchaseMethod": None,
            "settledAt": None if status == "HELD" else "2026-04-01T10:00:00+10:00",
            "createdAt": "2026-04-01T09:55:00+10:00",
        },
        "relationships": rels,
    }


@pytest.mark.asyncio
@respx.mock
async def test_list_transactions_paginates_and_parses():
    respx.get("https://api.up.com.au/api/v1/transactions").mock(return_value=Response(
        200,
        json={"data": [_tx_row("t1"), _tx_row("t2")],
              "links": {"prev": None, "next": "https://api.up.com.au/api/v1/transactions?page%5Bafter%5D=cursor1"}},
    ))
    respx.get("https://api.up.com.au/api/v1/transactions", params={"page[after]": "cursor1"}).mock(return_value=Response(
        200,
        json={"data": [_tx_row("t3", status="HELD", category_id=None)],
              "links": {"prev": None, "next": None}},
    ))

    client = UpClient("up:test:tok")
    collected = [tx async for tx in client.list_transactions()]
    assert [tx.id for tx in collected] == ["t1", "t2", "t3"]
    assert collected[0].account_id == "acct-1"
    assert collected[0].amount_value == -5.50
    assert collected[0].parent_category_id == "good-life"
    assert collected[2].status == "HELD"
    assert collected[2].settled_at is None
    assert collected[2].category_id is None


@pytest.mark.asyncio
@respx.mock
async def test_list_transactions_passes_since_filter():
    route = respx.get("https://api.up.com.au/api/v1/transactions").mock(return_value=Response(
        200, json={"data": [], "links": {"prev": None, "next": None}},
    ))
    client = UpClient("up:test:tok")
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _ = [tx async for tx in client.list_transactions(since=since)]
    assert "filter[since]" in route.calls.last.request.url.params
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/test_up_client_transactions.py -v`
Expected: FAIL with `AttributeError: 'UpClient' object has no attribute 'list_transactions'`

- [ ] **Step 3: Implement list_transactions**

Append to `backend/services/up_client.py` inside the `UpClient` class:

```python
    async def list_transactions(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        status: Literal["HELD", "SETTLED"] | None = None,
    ) -> AsyncIterator[UpTransaction]:
        url = f"{self.BASE}/transactions"
        params: dict[str, str] = {}
        if since:
            params["filter[since]"] = since.isoformat()
        if until:
            params["filter[until]"] = until.isoformat()
        if status:
            params["filter[status]"] = status

        first_page = True
        while url:
            payload = await self._request(url, params=params if first_page else None)
            first_page = False
            for row in payload["data"]:
                attrs = row["attributes"]
                rels = row.get("relationships", {})
                category_data = rels.get("category", {}).get("data")
                parent_data = rels.get("parentCategory", {}).get("data")
                account_data = rels.get("account", {}).get("data") or {}
                yield UpTransaction(
                    id=row["id"],
                    account_id=account_data.get("id", ""),
                    status=attrs["status"],
                    description=attrs["description"],
                    message=attrs.get("message"),
                    raw_text=attrs.get("rawText"),
                    amount_value=float(attrs["amount"]["value"]),
                    amount_currency=attrs["amount"]["currencyCode"],
                    category_id=category_data["id"] if category_data else None,
                    parent_category_id=parent_data["id"] if parent_data else None,
                    created_at=datetime.fromisoformat(attrs["createdAt"]),
                    settled_at=datetime.fromisoformat(attrs["settledAt"]) if attrs.get("settledAt") else None,
                )
            url = payload.get("links", {}).get("next")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_up_client_transactions.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/up_client.py backend/tests/test_up_client_transactions.py
git commit -m "feat(up): UpClient.list_transactions paginated async generator"
git push
```

---

### Task 7: UpClient retry — 429 with Retry-After

**Files:**
- Test: `backend/tests/test_up_client_retries.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_client_retries.py`:

```python
import pytest
import respx
from httpx import Response
from backend.services.up_client import UpClient, UpRateLimitError, UpServerError


@pytest.mark.asyncio
@respx.mock
async def test_429_then_200_recovers(monkeypatch):
    sleeps: list[float] = []
    async def fake_sleep(s): sleeps.append(s)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    route = respx.get("https://api.up.com.au/api/v1/accounts")
    route.side_effect = [
        Response(429, headers={"Retry-After": "2"}, json={"errors": []}),
        Response(200, json={"data": [], "links": {"prev": None, "next": None}}),
    ]
    accounts = await UpClient("up:test:tok").list_accounts()
    assert accounts == []
    assert 2 in sleeps   # honoured Retry-After


@pytest.mark.asyncio
@respx.mock
async def test_persistent_429_raises(monkeypatch):
    async def fake_sleep(_): return None
    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    respx.get("https://api.up.com.au/api/v1/accounts").mock(return_value=Response(
        429, headers={"Retry-After": "1"}, json={"errors": []},
    ))
    with pytest.raises(UpRateLimitError):
        await UpClient("up:test:tok").list_accounts()


@pytest.mark.asyncio
@respx.mock
async def test_persistent_5xx_raises(monkeypatch):
    async def fake_sleep(_): return None
    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    respx.get("https://api.up.com.au/api/v1/accounts").mock(return_value=Response(503, json={"errors": []}))
    with pytest.raises(UpServerError):
        await UpClient("up:test:tok").list_accounts()
```

- [ ] **Step 2: Run tests to verify behaviour**

Run: `backend/.venv/bin/pytest backend/tests/test_up_client_retries.py -v`
Expected: PASS (UpClient already implements retries from Task 4). If any test fails, fix `_request` to honour `Retry-After` precisely (already in Task 4's implementation).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_up_client_retries.py
git commit -m "test(up): UpClient 429/5xx retry behaviour"
git push
```

---

## Part 2 — Sync layer

### Task 8: up_categories_repo

**Files:**
- Create: `backend/repositories/up_categories_repo.py`
- Test: `backend/tests/test_up_categories_repo.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_categories_repo.py`:

```python
import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpCategory
from backend.repositories import up_categories_repo

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_categories").delete().neq("id", "").execute()
    yield
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_categories").delete().neq("id", "").execute()


def test_upsert_and_get_all():
    parents = [UpCategory(id="good-life", name="Good Life")]
    children = [UpCategory(id="restaurants-and-cafes", name="Restaurants & Cafes", parent_id="good-life")]
    up_categories_repo.upsert_many(parents + children, schema=SCHEMA)
    rows = up_categories_repo.get_all(schema=SCHEMA)
    assert {r.id for r in rows} == {"good-life", "restaurants-and-cafes"}


def test_upsert_is_idempotent():
    cat = UpCategory(id="good-life", name="Good Life")
    up_categories_repo.upsert_many([cat], schema=SCHEMA)
    up_categories_repo.upsert_many([cat], schema=SCHEMA)
    rows = up_categories_repo.get_all(schema=SCHEMA)
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_categories_repo.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the repo**

Create `backend/repositories/up_categories_repo.py`:

```python
"""Data access for `up_categories`."""

from backend.db.supabase_client import get_supabase
from backend.models.up import UpCategory


def upsert_many(categories: list[UpCategory], schema: str = "public") -> None:
    if not categories:
        return
    db = get_supabase()
    rows = [
        {"id": c.id, "name": c.name, "parent_id": c.parent_id}
        for c in categories
    ]
    db.schema(schema).table("up_categories").upsert(rows).execute()


def get_all(schema: str = "public") -> list[UpCategory]:
    db = get_supabase()
    result = db.schema(schema).table("up_categories").select("*").execute()
    return [UpCategory(**row) for row in result.data]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_categories_repo.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add backend/repositories/up_categories_repo.py backend/tests/test_up_categories_repo.py
git commit -m "feat(repo): up_categories_repo with idempotent upsert"
git push
```

---

### Task 9: up_accounts_repo

**Files:**
- Create: `backend/repositories/up_accounts_repo.py`
- Test: `backend/tests/test_up_accounts_repo.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_accounts_repo.py`:

```python
from datetime import datetime, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount
from backend.repositories import up_accounts_repo

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    yield


def _acct(id: str = "a1", balance: float = 100.0) -> UpAccount:
    return UpAccount(
        id=id, display_name="Spending", account_type="TRANSACTIONAL",
        ownership_type="INDIVIDUAL", balance_value=balance,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_upsert_and_list():
    up_accounts_repo.upsert_many([_acct("a1", 100), _acct("a2", 200)], schema=SCHEMA)
    rows = up_accounts_repo.list_all(schema=SCHEMA)
    assert {r.id for r in rows} == {"a1", "a2"}


def test_upsert_updates_balance():
    up_accounts_repo.upsert_many([_acct("a1", 100)], schema=SCHEMA)
    up_accounts_repo.upsert_many([_acct("a1", 250)], schema=SCHEMA)
    rows = up_accounts_repo.list_all(schema=SCHEMA)
    assert len(rows) == 1
    assert rows[0].balance_value == 250.0


def test_total_balance():
    up_accounts_repo.upsert_many([_acct("a1", 100), _acct("a2", 50.5)], schema=SCHEMA)
    assert up_accounts_repo.total_balance(schema=SCHEMA) == 150.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_accounts_repo.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the repo**

Create `backend/repositories/up_accounts_repo.py`:

```python
"""Data access for `up_accounts`."""

from datetime import datetime, timezone

from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount


def upsert_many(accounts: list[UpAccount], schema: str = "public") -> None:
    if not accounts:
        return
    db = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [{
        "id": a.id,
        "display_name": a.display_name,
        "account_type": a.account_type,
        "ownership_type": a.ownership_type,
        "balance_value": a.balance_value,
        "balance_currency": a.balance_currency,
        "created_at": a.created_at.isoformat(),
        "last_synced_at": now_iso,
    } for a in accounts]
    db.schema(schema).table("up_accounts").upsert(rows).execute()


def list_all(schema: str = "public") -> list[UpAccount]:
    db = get_supabase()
    result = db.schema(schema).table("up_accounts").select("*").execute()
    out: list[UpAccount] = []
    for row in result.data:
        out.append(UpAccount(
            id=row["id"],
            display_name=row["display_name"],
            account_type=row["account_type"],
            ownership_type=row["ownership_type"],
            balance_value=float(row["balance_value"]),
            balance_currency=row["balance_currency"],
            created_at=row["created_at"],
        ))
    return out


def total_balance(schema: str = "public") -> float:
    return sum(a.balance_value for a in list_all(schema=schema))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_accounts_repo.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/repositories/up_accounts_repo.py backend/tests/test_up_accounts_repo.py
git commit -m "feat(repo): up_accounts_repo"
git push
```

---

### Task 10: up_transactions_repo

**Files:**
- Create: `backend/repositories/up_transactions_repo.py`
- Test: `backend/tests/test_up_transactions_repo.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_transactions_repo.py`:

```python
from datetime import datetime, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount, UpCategory, UpTransaction
from backend.repositories import up_accounts_repo, up_categories_repo, up_transactions_repo

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _seed():
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_categories").delete().neq("id", "").execute()
    up_accounts_repo.upsert_many([UpAccount(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)
    up_categories_repo.upsert_many([
        UpCategory(id="good-life", name="Good Life"),
        UpCategory(id="restaurants-and-cafes", name="Restaurants", parent_id="good-life"),
    ], schema=SCHEMA)
    yield


def _tx(id="t1", amount=-5.5, status="SETTLED", category="restaurants-and-cafes", parent="good-life"):
    return UpTransaction(
        id=id, account_id="acct-1", status=status, description="Coffee",
        amount_value=amount, category_id=category, parent_category_id=parent,
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        settled_at=datetime(2026, 4, 1, 1, tzinfo=timezone.utc) if status == "SETTLED" else None,
    )


def test_upsert_idempotent():
    up_transactions_repo.upsert_many([_tx("t1")], schema=SCHEMA)
    up_transactions_repo.upsert_many([_tx("t1")], schema=SCHEMA)
    assert len(up_transactions_repo.list_recent(limit=10, schema=SCHEMA)) == 1


def test_held_to_settled_updates_row():
    up_transactions_repo.upsert_many([_tx("t1", status="HELD")], schema=SCHEMA)
    up_transactions_repo.upsert_many([_tx("t1", status="SETTLED")], schema=SCHEMA)
    rows = up_transactions_repo.list_recent(limit=10, schema=SCHEMA)
    assert len(rows) == 1
    assert rows[0].status == "SETTLED"
    assert rows[0].settled_at is not None


def test_max_created_at():
    up_transactions_repo.upsert_many([
        _tx("t1"),
        UpTransaction(
            id="t2", account_id="acct-1", status="SETTLED", description="Other",
            amount_value=-1.0, category_id=None, parent_category_id=None,
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            settled_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        ),
    ], schema=SCHEMA)
    latest = up_transactions_repo.max_created_at(schema=SCHEMA)
    assert latest is not None and latest.month == 5


def test_spending_by_parent_category_excludes_inflows():
    up_transactions_repo.upsert_many([
        _tx("t1", amount=-10),                             # outflow good-life
        _tx("t2", amount=-5),                              # outflow good-life
        _tx("t3", amount=200, category=None, parent=None), # inflow (salary), no category
    ], schema=SCHEMA)
    breakdown = up_transactions_repo.spending_by_parent_category(
        since=datetime(2026, 3, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 1, tzinfo=timezone.utc),
        schema=SCHEMA,
    )
    assert breakdown == {"good-life": 15.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_transactions_repo.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the repo**

Create `backend/repositories/up_transactions_repo.py`:

```python
"""Data access for `up_transactions`."""

from collections import defaultdict
from datetime import datetime

from backend.db.supabase_client import get_supabase
from backend.models.up import UpTransaction


def upsert_many(txs: list[UpTransaction], schema: str = "public") -> None:
    if not txs:
        return
    db = get_supabase()
    rows = [{
        "id": t.id,
        "account_id": t.account_id,
        "status": t.status,
        "description": t.description,
        "message": t.message,
        "raw_text": t.raw_text,
        "amount_value": t.amount_value,
        "amount_currency": t.amount_currency,
        "category_id": t.category_id,
        "parent_category_id": t.parent_category_id,
        "created_at": t.created_at.isoformat(),
        "settled_at": t.settled_at.isoformat() if t.settled_at else None,
    } for t in txs]
    db.schema(schema).table("up_transactions").upsert(rows).execute()


def _row_to_tx(row: dict) -> UpTransaction:
    return UpTransaction(
        id=row["id"], account_id=row["account_id"], status=row["status"],
        description=row["description"], message=row.get("message"), raw_text=row.get("raw_text"),
        amount_value=float(row["amount_value"]), amount_currency=row["amount_currency"],
        category_id=row.get("category_id"), parent_category_id=row.get("parent_category_id"),
        created_at=row["created_at"],
        settled_at=row.get("settled_at"),
    )


def list_recent(
    *, limit: int = 50, since: datetime | None = None, schema: str = "public",
) -> list[UpTransaction]:
    db = get_supabase()
    q = db.schema(schema).table("up_transactions").select("*").order("created_at", desc=True).limit(limit)
    if since:
        q = q.gte("created_at", since.isoformat())
    return [_row_to_tx(r) for r in q.execute().data]


def max_created_at(schema: str = "public") -> datetime | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("up_transactions")
        .select("created_at").order("created_at", desc=True).limit(1).execute()
    )
    if not result.data:
        return None
    return datetime.fromisoformat(result.data[0]["created_at"])


def spending_by_parent_category(
    *, since: datetime, until: datetime, schema: str = "public",
) -> dict[str, float]:
    """Sum of |amount| for negative-amount transactions per parent category."""
    db = get_supabase()
    result = (
        db.schema(schema).table("up_transactions")
        .select("parent_category_id,amount_value")
        .gte("created_at", since.isoformat())
        .lte("created_at", until.isoformat())
        .lt("amount_value", 0)
        .execute()
    )
    out: dict[str, float] = defaultdict(float)
    for row in result.data:
        cat = row.get("parent_category_id") or "uncategorised"
        out[cat] += abs(float(row["amount_value"]))
    return dict(out)


def cashflow_by_period(
    *, since: datetime, until: datetime, granularity: str = "month", schema: str = "public",
) -> list[dict]:
    """List of {period, income, expense} from `since` to `until`.

    Bucketed in Python (not SQL) so we don't depend on Postgres date_trunc
    via supabase-py — keeps the repo backend-agnostic.
    """
    rows = list_recent(limit=10_000, since=since, schema=schema)
    rows = [r for r in rows if r.created_at <= until]
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for r in rows:
        key = _bucket_key(r.created_at, granularity)
        if r.amount_value >= 0:
            buckets[key]["income"] += r.amount_value
        else:
            buckets[key]["expense"] += abs(r.amount_value)
    return [
        {"period": k, "income": round(v["income"], 2), "expense": round(v["expense"], 2)}
        for k, v in sorted(buckets.items())
    ]


def _bucket_key(dt: datetime, granularity: str) -> str:
    if granularity == "day":
        return dt.date().isoformat()
    if granularity == "week":
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return f"{dt.year:04d}-{dt.month:02d}"  # month
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_up_transactions_repo.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/repositories/up_transactions_repo.py backend/tests/test_up_transactions_repo.py
git commit -m "feat(repo): up_transactions_repo with spending+cashflow aggregations"
git push
```

---

### Task 11: up_sync_log_repo

**Files:**
- Create: `backend/repositories/up_sync_log_repo.py`
- Test: `backend/tests/test_up_sync_log_repo.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_sync_log_repo.py`:

```python
from datetime import datetime, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.repositories import up_sync_log_repo

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _truncate():
    get_supabase().schema(SCHEMA).table("up_sync_log").delete().neq(
        "id", "00000000-0000-0000-0000-000000000001"
    ).execute()
    yield


def test_record_start_then_finalize_success():
    sync_id = up_sync_log_repo.record_start(schema=SCHEMA)
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    assert latest["status"] == "in_progress"
    up_sync_log_repo.finalize_success(
        sync_id, last_seen_tx_at=datetime(2026, 4, 1, tzinfo=timezone.utc), schema=SCHEMA,
    )
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    assert latest["status"] == "success"
    assert latest["last_seen_tx_at"] is not None


def test_record_start_then_finalize_error():
    sync_id = up_sync_log_repo.record_start(schema=SCHEMA)
    up_sync_log_repo.finalize_error(sync_id, error_message="boom", schema=SCHEMA)
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    assert latest["status"] == "error"
    assert latest["error_message"] == "boom"


def test_last_successful_returns_none_when_empty():
    assert up_sync_log_repo.last_successful_seen_tx_at(schema=SCHEMA) is None


def test_last_successful_returns_latest_seen_tx_at():
    sid = up_sync_log_repo.record_start(schema=SCHEMA)
    up_sync_log_repo.finalize_success(
        sid, last_seen_tx_at=datetime(2026, 4, 1, tzinfo=timezone.utc), schema=SCHEMA,
    )
    sid2 = up_sync_log_repo.record_start(schema=SCHEMA)
    up_sync_log_repo.finalize_success(
        sid2, last_seen_tx_at=datetime(2026, 5, 1, tzinfo=timezone.utc), schema=SCHEMA,
    )
    last = up_sync_log_repo.last_successful_seen_tx_at(schema=SCHEMA)
    assert last is not None and last.month == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_sync_log_repo.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the repo**

Create `backend/repositories/up_sync_log_repo.py`:

```python
"""Data access for `up_sync_log` (sync state bookmark)."""

from datetime import datetime

from backend.db.supabase_client import get_supabase


def record_start(schema: str = "public") -> str:
    db = get_supabase()
    result = db.schema(schema).table("up_sync_log").insert({
        "status": "in_progress",
    }).execute()
    return result.data[0]["id"]


def finalize_success(sync_id: str, *, last_seen_tx_at: datetime | None, schema: str = "public") -> None:
    db = get_supabase()
    db.schema(schema).table("up_sync_log").update({
        "status": "success",
        "last_seen_tx_at": last_seen_tx_at.isoformat() if last_seen_tx_at else None,
    }).eq("id", sync_id).execute()


def finalize_error(sync_id: str, *, error_message: str, schema: str = "public") -> None:
    db = get_supabase()
    db.schema(schema).table("up_sync_log").update({
        "status": "error",
        "error_message": error_message,
    }).eq("id", sync_id).execute()


def latest(schema: str = "public") -> dict | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("up_sync_log").select("*")
        .order("synced_at", desc=True).limit(1).execute()
    )
    return result.data[0] if result.data else None


def last_successful_seen_tx_at(schema: str = "public") -> datetime | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("up_sync_log").select("last_seen_tx_at")
        .eq("status", "success")
        .order("synced_at", desc=True).limit(1).execute()
    )
    if not result.data:
        return None
    val = result.data[0]["last_seen_tx_at"]
    return datetime.fromisoformat(val) if val else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_up_sync_log_repo.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/repositories/up_sync_log_repo.py backend/tests/test_up_sync_log_repo.py
git commit -m "feat(repo): up_sync_log_repo"
git push
```

---

### Task 12: up_sync_service — first-run + incremental orchestration

**Files:**
- Create: `backend/services/up_sync_service.py`
- Test: `backend/tests/test_up_sync_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_up_sync_service.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount, UpCategory, UpTransaction
from backend.repositories import (
    up_accounts_repo, up_categories_repo, up_sync_log_repo, up_transactions_repo,
)
from backend.services import up_sync_service

SCHEMA = "test"


class FakeUpClient:
    def __init__(self, *, accounts=None, categories=None, transactions=None, raise_on_tx=None):
        self._accounts = accounts or []
        self._categories = categories or []
        self._transactions = transactions or []
        self._raise = raise_on_tx
        self.calls: list[tuple[str, dict]] = []

    async def list_accounts(self):
        self.calls.append(("accounts", {}))
        return list(self._accounts)

    async def list_categories(self):
        self.calls.append(("categories", {}))
        return list(self._categories)

    async def list_transactions(self, *, since=None, until=None, status=None):
        self.calls.append(("transactions", {"since": since, "until": until, "status": status}))
        if self._raise:
            raise self._raise
        for tx in self._transactions:
            if since and tx.created_at < since:
                continue
            yield tx


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    for t in ["up_transactions", "up_sync_log", "up_accounts", "up_categories"]:
        db.schema(SCHEMA).table(t).delete().neq("id", "00000000-0000-0000-0000-000000000001" if t == "up_sync_log" else "").execute()
    yield


def _acct():
    return UpAccount(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=100.0, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _tx(id, days_ago):
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    return UpTransaction(
        id=id, account_id="acct-1", status="SETTLED", description="x",
        amount_value=-1.0, category_id=None, parent_category_id=None,
        created_at=base - timedelta(days=days_ago),
        settled_at=base - timedelta(days=days_ago),
    )


@pytest.mark.asyncio
async def test_first_run_full_backfill():
    client = FakeUpClient(
        accounts=[_acct()],
        categories=[UpCategory(id="good-life", name="Good Life")],
        transactions=[_tx("t1", 30), _tx("t2", 10), _tx("t3", 1)],
    )
    await up_sync_service.sync(client=client, schema=SCHEMA)
    assert {a.id for a in up_accounts_repo.list_all(schema=SCHEMA)} == {"acct-1"}
    assert {c.id for c in up_categories_repo.get_all(schema=SCHEMA)} == {"good-life"}
    assert len(up_transactions_repo.list_recent(limit=10, schema=SCHEMA)) == 3
    last = up_sync_log_repo.last_successful_seen_tx_at(schema=SCHEMA)
    assert last is not None
    # First-run call to transactions should NOT pass `since`
    tx_call = next(c for c in client.calls if c[0] == "transactions")
    assert tx_call[1]["since"] is None


@pytest.mark.asyncio
async def test_incremental_uses_overlap_window():
    # Seed first run
    client1 = FakeUpClient(
        accounts=[_acct()], categories=[],
        transactions=[_tx("t1", 30)],
    )
    await up_sync_service.sync(client=client1, schema=SCHEMA)

    # Incremental
    client2 = FakeUpClient(
        accounts=[_acct()], categories=[],
        transactions=[_tx("t2", 1)],
    )
    await up_sync_service.sync(client=client2, schema=SCHEMA)
    tx_call = next(c for c in client2.calls if c[0] == "transactions")
    since = tx_call[1]["since"]
    last_seen = datetime(2026, 5, 1, tzinfo=timezone.utc) - timedelta(days=30)
    # Overlap window subtracts 6h
    assert since == last_seen - timedelta(hours=6)


@pytest.mark.asyncio
async def test_error_records_failure_log():
    client = FakeUpClient(accounts=[_acct()], raise_on_tx=Exception("boom"))
    with pytest.raises(Exception):
        await up_sync_service.sync(client=client, schema=SCHEMA)
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    assert latest["status"] == "error"
    assert "boom" in (latest["error_message"] or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_sync_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the sync service**

Create `backend/services/up_sync_service.py`:

```python
"""Orchestrates UP Bank sync: first-run backfill + incremental updates."""

import logging
from datetime import datetime, timedelta

from backend.config import settings
from backend.repositories import (
    up_accounts_repo, up_categories_repo, up_sync_log_repo, up_transactions_repo,
)
from backend.services.up_client import UpClient

logger = logging.getLogger(__name__)

OVERLAP = timedelta(hours=6)


def _make_client() -> UpClient:
    return UpClient(settings.up_pat)


async def sync(*, client: UpClient | None = None, schema: str = "public") -> None:
    """Run a sync cycle. First run backfills all-time; subsequent runs are
    incremental with an overlap window that catches HELD→SETTLED."""
    client = client or _make_client()
    sync_id = up_sync_log_repo.record_start(schema=schema)
    last_seen_prior = up_sync_log_repo.last_successful_seen_tx_at(schema=schema)

    try:
        accounts = await client.list_accounts()
        up_accounts_repo.upsert_many(accounts, schema=schema)

        if last_seen_prior is None:
            categories = await client.list_categories()
            up_categories_repo.upsert_many(categories, schema=schema)
            since = None
            logger.info("[UpSync] First run — full backfill")
        else:
            since = last_seen_prior - OVERLAP
            logger.info("[UpSync] Incremental — since=%s", since.isoformat())

        max_seen = last_seen_prior
        batch: list = []
        async for tx in client.list_transactions(since=since):
            batch.append(tx)
            if len(batch) >= 100:
                up_transactions_repo.upsert_many(batch, schema=schema)
                batch = []
            if max_seen is None or tx.created_at > max_seen:
                max_seen = tx.created_at
        if batch:
            up_transactions_repo.upsert_many(batch, schema=schema)

        up_sync_log_repo.finalize_success(sync_id, last_seen_tx_at=max_seen, schema=schema)
        logger.info("[UpSync] Success — last_seen_tx_at=%s", max_seen)
    except Exception as exc:
        up_sync_log_repo.finalize_error(sync_id, error_message=str(exc), schema=schema)
        logger.exception("[UpSync] Failed")
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_up_sync_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/up_sync_service.py backend/tests/test_up_sync_service.py
git commit -m "feat(up): up_sync_service with first-run + incremental + overlap"
git push
```

---

### Task 13: up_snapshot_service + extend snapshots_repo with source

**Files:**
- Create: `backend/services/up_snapshot_service.py`
- Modify: `backend/repositories/snapshots_repo.py`
- Test: `backend/tests/test_up_snapshot_service.py`

- [ ] **Step 1: Inspect existing snapshots_repo to find the insert function**

```bash
backend/.venv/bin/grep -n "def " backend/repositories/snapshots_repo.py
```

Locate the function that inserts a snapshot row (likely `save` or similar).

- [ ] **Step 2: Add a `source` parameter to the existing insert function**

In `backend/repositories/snapshots_repo.py`, find the function that inserts to `portfolio_snapshots`. Add a `source: str = "crypto"` parameter and include it in the row dict. Existing crypto callers continue to work because of the default.

For a new generic insert helper, add this function:

```python
def insert_source_snapshot(
    *,
    captured_at: str,
    total_value_aud: float,
    source: str,
    assets: dict | None = None,
    schema: str = "public",
) -> None:
    """Insert a portfolio_snapshots row tagged with `source`.

    For crypto, callers pass the existing `assets` JSON. For UP, `assets` is
    None — we record only the total. The column is NOT NULL in the schema, so
    we pass `{}` as the empty default.
    """
    db = get_supabase()
    db.schema(schema).table("portfolio_snapshots").insert({
        "captured_at": captured_at,
        "total_value_aud": total_value_aud,
        "source": source,
        "assets": assets if assets is not None else {},
    }).execute()
```

- [ ] **Step 3: Write the failing test**

Create `backend/tests/test_up_snapshot_service.py`:

```python
from datetime import datetime, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount
from backend.repositories import up_accounts_repo
from backend.services import up_snapshot_service

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("portfolio_snapshots").delete().neq(
        "id", "00000000-0000-0000-0000-000000000001"
    ).execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    yield


def test_save_snapshot_writes_total_balance_with_source_up():
    up_accounts_repo.upsert_many([
        UpAccount(id="a1", display_name="X", account_type="TRANSACTIONAL",
                  ownership_type="INDIVIDUAL", balance_value=100.0,
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        UpAccount(id="a2", display_name="Y", account_type="SAVER",
                  ownership_type="INDIVIDUAL", balance_value=250.50,
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ], schema=SCHEMA)

    up_snapshot_service.save_snapshot(schema=SCHEMA)

    rows = (
        get_supabase().schema(SCHEMA).table("portfolio_snapshots")
        .select("*").eq("source", "up").execute().data
    )
    assert len(rows) == 1
    assert float(rows[0]["total_value_aud"]) == 350.50
```

- [ ] **Step 4: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_snapshot_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 5: Implement up_snapshot_service**

Create `backend/services/up_snapshot_service.py`:

```python
"""Composes a portfolio_snapshots row tagged source='up' from current UP balances."""

from datetime import datetime, timezone

from backend.repositories import snapshots_repo, up_accounts_repo


def save_snapshot(schema: str = "public") -> None:
    total = up_accounts_repo.total_balance(schema=schema)
    snapshots_repo.insert_source_snapshot(
        captured_at=datetime.now(timezone.utc).isoformat(),
        total_value_aud=total,
        source="up",
        assets={},
        schema=schema,
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_snapshot_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/up_snapshot_service.py backend/repositories/snapshots_repo.py backend/tests/test_up_snapshot_service.py
git commit -m "feat(up): up_snapshot_service + source-aware snapshots insert"
git push
```

---

### Task 14: Hook UP into the existing hourly snapshot job

**Files:**
- Modify: `backend/scheduler.py`

- [ ] **Step 1: Read the current snapshot job**

```bash
backend/.venv/bin/cat backend/scheduler.py
```

Identify `_do_snapshot` and the existing structure.

- [ ] **Step 2: Extend `_do_snapshot` to also write a UP snapshot**

Modify `backend/scheduler.py`. Update the imports and the `_do_snapshot` body:

```python
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services import portfolio_service, snapshot_service, up_snapshot_service, up_sync_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _do_snapshot() -> None:
    """Synchronous snapshot composition for both crypto and UP."""
    summary = portfolio_service.build_summary()
    snapshot_service.save_snapshot(summary)
    try:
        up_snapshot_service.save_snapshot()
    except Exception:
        logger.exception("UP snapshot failed (crypto snapshot was saved)")


async def _hourly_snapshot() -> None:
    try:
        await asyncio.to_thread(_do_snapshot)
    except Exception:
        logger.exception("Hourly snapshot failed")


async def _up_sync_tick() -> None:
    try:
        await up_sync_service.sync()
    except Exception:
        logger.exception("UP sync tick failed")


def start_scheduler() -> None:
    scheduler.add_job(_hourly_snapshot, "interval", hours=1, id="hourly_snapshot")
    scheduler.add_job(_up_sync_tick, "interval", minutes=15, id="up_sync", next_run_time=None)
    scheduler.start()
    # Kick off first UP sync immediately (in background) so first-run backfill starts
    asyncio.get_event_loop().create_task(_up_sync_tick())


def stop_scheduler() -> None:
    scheduler.shutdown()
```

- [ ] **Step 3: Manual smoke test**

Restart uvicorn:
```bash
backend/.venv/bin/uvicorn backend.main:app --reload
```
Watch the logs. Within ~30s you should see:
- `[UpSync] First run — full backfill`
- `[UpSync] Success — last_seen_tx_at=...` (after backfill completes)

If first run fails (401), confirm `UP_PAT` is correct in `.env`.

- [ ] **Step 4: Commit**

```bash
git add backend/scheduler.py
git commit -m "feat(scheduler): hook UP snapshot + 15min UP sync into scheduler"
git push
```

---

## Part 3 — REST API

### Task 15: GET /api/up/accounts

**Files:**
- Create: `backend/routers/up.py`
- Modify: `backend/main.py` (router registration)
- Modify: `backend/tests/conftest.py` (add `bypass_auth` fixture)
- Test: `backend/tests/test_up_router.py`

- [ ] **Step 1: Add `bypass_auth` fixture to conftest.py**

Append to `backend/tests/conftest.py`:

```python
@pytest.fixture
def bypass_auth():
    """Override the require_auth dependency for FastAPI tests so we don't
    need a real JWT cookie. Restores the dependency on teardown."""
    from backend.auth.dependencies import require_auth
    from backend.main import app

    app.dependency_overrides[require_auth] = lambda: None
    yield
    app.dependency_overrides.pop(require_auth, None)
```

- [ ] **Step 2: Write failing test**

Create `backend/tests/test_up_router.py`:

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from backend.db.supabase_client import get_supabase
from backend.main import app
from backend.models.up import UpAccount
from backend.repositories import up_accounts_repo

SCHEMA = "test"
_SENTINEL = "00000000-0000-0000-0000-000000000001"
client = TestClient(app)


def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()


def test_list_accounts_returns_seeded_accounts(monkeypatch, bypass_auth):
    _truncate()
    monkeypatch.setattr("backend.routers.up.SCHEMA", SCHEMA)
    up_accounts_repo.upsert_many([
        UpAccount(id="a1", display_name="Spending", account_type="TRANSACTIONAL",
                  ownership_type="INDIVIDUAL", balance_value=100.0,
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ], schema=SCHEMA)
    resp = client.get("/api/up/accounts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "a1"
    assert data[0]["balance_value"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_up_router.py -v`
Expected: FAIL — `404 Not Found` because router not yet mounted.

- [ ] **Step 3: Create router**

Create `backend/routers/up.py`:

```python
"""REST endpoints for UP Bank data."""

from fastapi import APIRouter, Depends

from backend.auth.dependencies import require_auth
from backend.repositories import up_accounts_repo

router = APIRouter(prefix="/api/up", tags=["up"], dependencies=[Depends(require_auth)])

SCHEMA = "public"


@router.get("/accounts")
async def list_accounts() -> list[dict]:
    accounts = up_accounts_repo.list_all(schema=SCHEMA)
    return [a.model_dump(mode="json") for a in accounts]
```

- [ ] **Step 4: Mount router in main**

Modify `backend/main.py`. Find where existing routers are included (search for `app.include_router`) and add:

```python
from backend.routers import up as up_router
app.include_router(up_router.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_up_router.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/up.py backend/main.py backend/tests/test_up_router.py
git commit -m "feat(api): GET /api/up/accounts"
git push
```

---

### Task 16: GET /api/up/transactions, /spending/summary, /cashflow

**Files:**
- Modify: `backend/routers/up.py`
- Test: extend `backend/tests/test_up_router.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_up_router.py`:

```python
from datetime import timedelta
from backend.models.up import UpCategory, UpTransaction
from backend.repositories import up_categories_repo, up_transactions_repo


def _seed_with_tx(monkeypatch, bypass_auth):
    _truncate()
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_categories").delete().neq("id", "").execute()
    monkeypatch.setattr("backend.routers.up.SCHEMA", SCHEMA)

    up_accounts_repo.upsert_many([UpAccount(
        id="a1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)
    up_categories_repo.upsert_many([
        UpCategory(id="good-life", name="Good Life"),
    ], schema=SCHEMA)

    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    txs = [
        UpTransaction(id=f"t{i}", account_id="a1", status="SETTLED",
                      description="Coffee", amount_value=-amt, parent_category_id="good-life",
                      created_at=base - timedelta(days=i),
                      settled_at=base - timedelta(days=i))
        for i, amt in enumerate([5, 10, 15], start=1)
    ]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)


def test_list_transactions(monkeypatch, bypass_auth):
    _seed_with_tx(monkeypatch, bypass_auth)
    resp = client.get("/api/up/transactions?limit=10")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_spending_summary(monkeypatch, bypass_auth):
    _seed_with_tx(monkeypatch, bypass_auth)
    resp = client.get(
        "/api/up/spending/summary?since=2026-04-01T00:00:00Z&until=2026-06-01T00:00:00Z",
        ,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"good-life": 30.0}


def test_cashflow(monkeypatch, bypass_auth):
    _seed_with_tx(monkeypatch, bypass_auth)
    resp = client.get(
        "/api/up/cashflow?since=2026-04-01T00:00:00Z&until=2026-06-01T00:00:00Z&granularity=month",
        ,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body[-1]["expense"] == 30.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/test_up_router.py -v`
Expected: FAIL — endpoints don't exist yet.

- [ ] **Step 3: Add endpoints**

Append to `backend/routers/up.py`:

```python
from datetime import datetime, timezone
from fastapi import Query
from backend.repositories import up_transactions_repo


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@router.get("/transactions")
async def list_transactions(
    limit: int = Query(50, ge=1, le=500),
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    since_dt = _parse_iso(since) if since else None
    txs = up_transactions_repo.list_recent(limit=limit, since=since_dt, schema=SCHEMA)
    if until:
        until_dt = _parse_iso(until)
        txs = [t for t in txs if t.created_at <= until_dt]
    return [t.model_dump(mode="json") for t in txs]


@router.get("/spending/summary")
async def spending_summary(since: str, until: str) -> dict[str, float]:
    return up_transactions_repo.spending_by_parent_category(
        since=_parse_iso(since),
        until=_parse_iso(until),
        schema=SCHEMA,
    )


@router.get("/cashflow")
async def cashflow(since: str, until: str, granularity: str = "month") -> list[dict]:
    return up_transactions_repo.cashflow_by_period(
        since=_parse_iso(since),
        until=_parse_iso(until),
        granularity=granularity,
        schema=SCHEMA,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_up_router.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/routers/up.py backend/tests/test_up_router.py
git commit -m "feat(api): UP /transactions, /spending/summary, /cashflow"
git push
```

---

### Task 17: GET /api/up/sync/status + POST /api/up/sync/retry

**Files:**
- Modify: `backend/routers/up.py`
- Test: extend `backend/tests/test_up_router.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_up_router.py`:

```python
def test_sync_status_returns_latest(monkeypatch, bypass_auth):
    monkeypatch.setattr("backend.routers.up.SCHEMA", SCHEMA)
    db = get_supabase()
    db.schema(SCHEMA).table("up_sync_log").delete().neq(
        "id", "00000000-0000-0000-0000-000000000001"
    ).execute()
    from backend.repositories import up_sync_log_repo
    sid = up_sync_log_repo.record_start(schema=SCHEMA)
    resp = client.get("/api/up/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "syncing"
    up_sync_log_repo.finalize_success(sid, last_seen_tx_at=None, schema=SCHEMA)
    resp = client.get("/api/up/sync/status")
    assert resp.json()["state"] == "ready"


def test_sync_retry_returns_202(monkeypatch, bypass_auth):
    captured: list[bool] = []

    async def fake_sync():
        captured.append(True)

    monkeypatch.setattr("backend.routers.up.up_sync_service.sync", fake_sync)
    resp = client.post("/api/up/sync/retry")
    assert resp.status_code == 202
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/test_up_router.py -v`
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Add endpoints**

Append to `backend/routers/up.py`:

```python
import asyncio
from fastapi import BackgroundTasks, status
from backend.repositories import up_sync_log_repo
from backend.services import up_sync_service


_STATE_MAP = {"in_progress": "syncing", "success": "ready", "error": "error"}


@router.get("/sync/status")
async def sync_status() -> dict:
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    if latest is None:
        return {"state": "ready", "last_synced_at": None, "error": None}
    return {
        "state": _STATE_MAP.get(latest["status"], "ready"),
        "last_synced_at": latest.get("synced_at"),
        "error": latest.get("error_message"),
    }


@router.post("/sync/retry", status_code=status.HTTP_202_ACCEPTED)
async def sync_retry(background: BackgroundTasks) -> dict:
    background.add_task(asyncio.create_task, up_sync_service.sync())
    return {"queued": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_up_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/up.py backend/tests/test_up_router.py
git commit -m "feat(api): UP /sync/status + /sync/retry"
git push
```

---

### Task 18: Combined router (snapshots + summary)

**Files:**
- Create: `backend/routers/combined.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_combined_router.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_combined_router.py`:

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from backend.db.supabase_client import get_supabase
from backend.main import app
from backend.repositories import snapshots_repo

SCHEMA = "test"
client = TestClient(app)


def _truncate():
    get_supabase().schema(SCHEMA).table("portfolio_snapshots").delete().neq(
        "id", "00000000-0000-0000-0000-000000000001"
    ).execute()


def test_combined_snapshots_pivots_sources(monkeypatch, bypass_auth):
    _truncate()
    monkeypatch.setattr("backend.routers.combined.SCHEMA", SCHEMA)

    ts = "2026-05-01T00:00:00+00:00"
    snapshots_repo.insert_source_snapshot(
        captured_at=ts, total_value_aud=10000.0, source="crypto", schema=SCHEMA,
    )
    snapshots_repo.insert_source_snapshot(
        captured_at=ts, total_value_aud=2000.0, source="up", schema=SCHEMA,
    )
    resp = client.get("/api/combined/snapshots")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["crypto"] == 10000.0
    assert body[0]["up"] == 2000.0
    assert body[0]["total"] == 12000.0


def test_combined_summary_uses_latest_each_source(monkeypatch, bypass_auth):
    _truncate()
    monkeypatch.setattr("backend.routers.combined.SCHEMA", SCHEMA)
    snapshots_repo.insert_source_snapshot(
        captured_at="2026-04-01T00:00:00+00:00", total_value_aud=8000.0, source="crypto", schema=SCHEMA,
    )
    snapshots_repo.insert_source_snapshot(
        captured_at="2026-05-01T00:00:00+00:00", total_value_aud=10000.0, source="crypto", schema=SCHEMA,
    )
    snapshots_repo.insert_source_snapshot(
        captured_at="2026-05-01T00:00:00+00:00", total_value_aud=2000.0, source="up", schema=SCHEMA,
    )
    resp = client.get("/api/combined/summary")
    body = resp.json()
    assert body == {"crypto": 10000.0, "up": 2000.0, "total": 12000.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_combined_router.py -v`
Expected: FAIL — router doesn't exist.

- [ ] **Step 3: Add a "list by source" helper to snapshots_repo**

Append to `backend/repositories/snapshots_repo.py`:

```python
def list_by_source(
    *, source: str | None = None, since: str | None = None, schema: str = "public",
) -> list[dict]:
    """Raw rows by source, optionally filtered by captured_at >= since."""
    db = get_supabase()
    q = db.schema(schema).table("portfolio_snapshots").select(
        "captured_at,total_value_aud,source"
    ).order("captured_at", desc=False)
    if source:
        q = q.eq("source", source)
    if since:
        q = q.gte("captured_at", since)
    return q.execute().data
```

- [ ] **Step 4: Create the router**

Create `backend/routers/combined.py`:

```python
"""Combined view across crypto + UP."""

from collections import defaultdict

from fastapi import APIRouter, Depends

from backend.auth.dependencies import require_auth
from backend.repositories import snapshots_repo

router = APIRouter(prefix="/api/combined", tags=["combined"], dependencies=[Depends(require_auth)])

SCHEMA = "public"


@router.get("/snapshots")
async def snapshots(since: str | None = None) -> list[dict]:
    rows = snapshots_repo.list_by_source(since=since, schema=SCHEMA)
    by_ts: dict[str, dict[str, float]] = defaultdict(lambda: {"crypto": 0.0, "up": 0.0})
    for r in rows:
        by_ts[r["captured_at"]][r["source"]] += float(r["total_value_aud"])
    out: list[dict] = []
    for ts in sorted(by_ts.keys()):
        crypto = by_ts[ts]["crypto"]
        up = by_ts[ts]["up"]
        out.append({"captured_at": ts, "crypto": crypto, "up": up, "total": crypto + up})
    return out


@router.get("/summary")
async def summary() -> dict:
    rows = snapshots_repo.list_by_source(schema=SCHEMA)
    latest_by_source: dict[str, float] = {}
    for r in rows:
        # rows are ordered ascending by captured_at; later overwrites earlier
        latest_by_source[r["source"]] = float(r["total_value_aud"])
    crypto = latest_by_source.get("crypto", 0.0)
    up = latest_by_source.get("up", 0.0)
    return {"crypto": crypto, "up": up, "total": crypto + up}
```

- [ ] **Step 5: Mount in main.py**

Add to `backend/main.py` near the other `include_router` calls:

```python
from backend.routers import combined as combined_router
app.include_router(combined_router.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_combined_router.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/routers/combined.py backend/repositories/snapshots_repo.py backend/main.py backend/tests/test_combined_router.py
git commit -m "feat(api): /api/combined/{snapshots,summary} pivoted by source"
git push
```

---

## Part 4 — Agent integration

### Task 19: 5 new MCP tools in mcp_server.py

**Files:**
- Modify: `backend/mcp_server.py`
- Test: `backend/tests/test_mcp_up_tools.py`

- [ ] **Step 1: Inspect existing MCP tool patterns**

```bash
backend/.venv/bin/grep -n "@mcp.tool" backend/mcp_server.py | head
```

Read 1-2 existing tool implementations to match the return-string convention and any helper formatters.

- [ ] **Step 2: Write failing test**

Create `backend/tests/test_mcp_up_tools.py`:

```python
"""Smoke tests for new UP MCP tools — direct function invocation,
bypassing the MCP transport layer."""

import importlib

from datetime import datetime, timezone

from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount
from backend.repositories import up_accounts_repo

SCHEMA = "test"


def _truncate():
    get_supabase().schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()


def test_get_up_balance_returns_total(monkeypatch):
    _truncate()
    import backend.mcp_server as mcp_module
    monkeypatch.setattr(mcp_module, "UP_SCHEMA", SCHEMA)
    up_accounts_repo.upsert_many([
        UpAccount(id="a1", display_name="X", account_type="TRANSACTIONAL",
                  ownership_type="INDIVIDUAL", balance_value=150.0,
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ], schema=SCHEMA)
    out = mcp_module.get_up_balance()
    assert "150" in out
    assert "AUD" in out


def test_get_combined_net_worth(monkeypatch):
    import backend.mcp_server as mcp_module
    monkeypatch.setattr(mcp_module, "UP_SCHEMA", SCHEMA)
    monkeypatch.setattr(mcp_module, "_crypto_value", lambda: 10_000.0)
    out = mcp_module.get_combined_net_worth()
    assert "10" in out  # mentions crypto component
    assert "AUD" in out
```

- [ ] **Step 3: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_mcp_up_tools.py -v`
Expected: FAIL — `AttributeError: module 'backend.mcp_server' has no attribute 'get_up_balance'`

- [ ] **Step 4: Add the 5 tools to mcp_server.py**

Append to `backend/mcp_server.py`:

```python
from datetime import datetime, timezone
from backend.repositories import (
    up_accounts_repo,
    up_transactions_repo,
)
from backend.services import portfolio_service

UP_SCHEMA = "public"


def _crypto_value() -> float:
    """Latest computed crypto portfolio value in AUD."""
    return portfolio_service.build_summary().total_value_aud


@mcp.tool()
def get_up_balance() -> str:
    """Current total cash across all UP accounts. Returns AUD figure with
    per-account breakdown."""
    accounts = up_accounts_repo.list_all(schema=UP_SCHEMA)
    if not accounts:
        return "No UP accounts found yet — sync may still be in progress."
    total = sum(a.balance_value for a in accounts)
    lines = [f"Total UP cash: ${total:,.2f} AUD"]
    for a in sorted(accounts, key=lambda x: -x.balance_value):
        lines.append(f"  - {a.display_name} ({a.account_type}): ${a.balance_value:,.2f}")
    return "\n".join(lines)


@mcp.tool()
def get_up_spending_by_category(since: str, until: str) -> str:
    """Total spend (negative-amount transactions only) per parent category in
    the given date range. ISO dates (YYYY-MM-DD or full ISO 8601)."""
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
    breakdown = up_transactions_repo.spending_by_parent_category(
        since=since_dt, until=until_dt, schema=UP_SCHEMA,
    )
    if not breakdown:
        return f"No spending recorded between {since} and {until}."
    total = sum(breakdown.values())
    lines = [f"Total spending {since} → {until}: ${total:,.2f} AUD"]
    for cat, amt in sorted(breakdown.items(), key=lambda x: -x[1]):
        lines.append(f"  - {cat}: ${amt:,.2f}")
    return "\n".join(lines)


@mcp.tool()
def get_up_cashflow(since: str, until: str, granularity: str = "month") -> str:
    """Income vs expense per period. granularity: day | week | month."""
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
    rows = up_transactions_repo.cashflow_by_period(
        since=since_dt, until=until_dt, granularity=granularity, schema=UP_SCHEMA,
    )
    if not rows:
        return "No cashflow data in that period."
    lines = [f"Cashflow {since} → {until} ({granularity}):"]
    for r in rows:
        lines.append(f"  {r['period']}: +${r['income']:,.2f} / -${r['expense']:,.2f}")
    return "\n".join(lines)


@mcp.tool()
def get_up_recent_transactions(limit: int = 10, since: str | None = None) -> str:
    """Most recent transactions across accounts — for grounding context.
    Not intended for transaction search."""
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else None
    txs = up_transactions_repo.list_recent(limit=limit, since=since_dt, schema=UP_SCHEMA)
    if not txs:
        return "No transactions found."
    lines = [f"Most recent {len(txs)} transactions:"]
    for t in txs:
        sign = "-" if t.amount_value < 0 else "+"
        lines.append(
            f"  {t.created_at[:10] if isinstance(t.created_at, str) else t.created_at.date()}  "
            f"{sign}${abs(t.amount_value):,.2f}  {t.description}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_combined_net_worth() -> str:
    """Total net worth across crypto + UP cash. Returns AUD with breakdown."""
    crypto = _crypto_value()
    up_total = sum(a.balance_value for a in up_accounts_repo.list_all(schema=UP_SCHEMA))
    total = crypto + up_total
    return (
        f"Total net worth: ${total:,.2f} AUD\n"
        f"  Crypto: ${crypto:,.2f}\n"
        f"  UP cash: ${up_total:,.2f}"
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_mcp_up_tools.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server.py backend/tests/test_mcp_up_tools.py
git commit -m "feat(mcp): 5 UP/combined tools (balance, spending, cashflow, recent, combined)"
git push
```

---

### Task 20: Classifier — add `cash` category

**Files:**
- Modify: `backend/agent/classifier.py`
- Modify: `backend/agent/prompts.py`
- Modify: `backend/agent/agent_config.py`
- Test: `backend/tests/test_classifier_cash.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_classifier_cash.py`:

```python
import pytest
from langchain_core.messages import HumanMessage
from backend.agent.classifier import classify, route_query


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "How much cash do I have?",
    "How much did I spend on takeaway last month?",
    "What's my income vs expense for May?",
])
async def test_classifies_as_cash(question):
    out = await classify([HumanMessage(content=question)])
    assert out.primary_category == "cash"
    assert route_query(out) == "cash_agent"
```

> **Note:** these tests hit the live Anthropic API. They're marked under
> the existing `eval` marker pattern if you have one, or skip them in
> default runs and run manually.

- [ ] **Step 2: Run test to confirm it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_classifier_cash.py -v -s`
Expected: FAIL — classifier returns one of the existing categories.

- [ ] **Step 3: Update CLASSIFIER_PROMPT in prompts.py**

In `backend/agent/prompts.py`, find `CLASSIFIER_PROMPT` and add a `cash` line + tweak the description:

```python
CLASSIFIER_PROMPT = """\
Classify the user's portfolio question into exactly one primary category. \
Only include secondary_categories if another category is clearly relevant \
(confidence >= 0.5).

Categories:
- quick: Simple factual lookups about crypto holdings — portfolio value, \
balances, next DCA date, total spent on an asset. Single tool call, instant answer.
- analysis: Crypto performance trends, strategy assessment, period comparisons, \
best/worst performers. May need 2-3 tool calls.
- tax: Anything involving CGT, tax, ATO rules, discount eligibility, \
financial year. Even if phrased casually.
- comparison: Counterfactual questions — "would I have been better off", \
"what if I'd done X instead", DCA vs lump-sum, buy-and-hold comparisons.
- cash: Bank balances, cash flow, spending, "how much did I spend on X", \
"how much money do I have", net worth across crypto + cash.
- open: Vague, conversational, or cross-category — "what's going on", \
"anything I should know", "give me the quick version".

Respond with JSON only.\
"""
```

Also update the `ClassifierOutput` field description in `backend/agent/classifier.py` to include `cash`:

```python
class ClassifierOutput(BaseModel):
    primary_category: str = Field(
        description="One of: quick, analysis, tax, comparison, cash, open"
    )
    confidence: float = Field(description="Confidence in primary classification, 0-1")
    secondary_categories: list[str] = Field(
        default_factory=list,
        description="Other relevant categories (only if confidence >= 0.5)",
    )
```

- [ ] **Step 4: Add cash → cash_agent mapping**

In `backend/agent/agent_config.py`, find `CATEGORY_TO_NODE` and add the mapping:

```python
CATEGORY_TO_NODE = {
    "quick": "quick_agent",
    "analysis": "analysis_agent",
    "tax": "tax_agent",
    "comparison": "comparison_agent",
    "cash": "cash_agent",
    "open": "general_agent",
}
```

Also add a `TOOL_SUBSETS["cash"]` entry listing the 5 new tool names + `get_combined_net_worth`:

```python
TOOL_SUBSETS = {
    # ... existing entries ...
    "cash": [
        "get_up_balance",
        "get_up_spending_by_category",
        "get_up_cashflow",
        "get_up_recent_transactions",
        "get_combined_net_worth",
    ],
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/test_classifier_cash.py -v -s`
Expected: PASS (all 3 parametrized cases)

- [ ] **Step 6: Commit**

```bash
git add backend/agent/classifier.py backend/agent/prompts.py backend/agent/agent_config.py backend/tests/test_classifier_cash.py
git commit -m "feat(agent): add 'cash' classifier category + tool subset"
git push
```

---

### Task 21: graph.py — add cash_agent node

**Files:**
- Modify: `backend/agent/graph.py`
- Modify: `backend/agent/prompts.py` (CASH_APPENDIX)
- Test: `backend/tests/test_graph_cash_node.py`

- [ ] **Step 1: Add CASH_APPENDIX to prompts.py**

In `backend/agent/prompts.py`, add after the existing `*_APPENDIX` definitions:

```python
CASH_APPENDIX = """\

You are answering questions about the user's UP Bank cash position and \
spending. Tools available:
- get_up_balance — current total cash + per-account breakdown.
- get_up_spending_by_category — outflows by parent category in a date range.
- get_up_cashflow — income vs expense per period (day/week/month).
- get_up_recent_transactions — recent activity for grounding.
- get_combined_net_worth — crypto + cash total.

Rules:
- Spending figures are always over a date range. If the user doesn't specify \
one, default to the current calendar month and say so.
- Cash balances are point-in-time, not a "return". Never compute % gains on \
cash.
- Don't speculate about transactions older than the data we have. If a query \
is outside the available history, say so plainly.
"""

CASH_PROMPT = BASE_PROMPT + CASH_APPENDIX
```

- [ ] **Step 2: Write failing test**

Create `backend/tests/test_graph_cash_node.py`:

```python
"""Smoke test: the compiled graph has a cash_agent node and routing reaches it."""

import pytest
from backend.agent.graph import build_graph


class _StubChk:
    pass


def test_graph_has_cash_agent_node():
    graph = build_graph(all_tools=[], checkpointer=_StubChk())
    nodes = set(graph.get_graph().nodes)
    assert "cash_agent" in nodes
```

- [ ] **Step 3: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/test_graph_cash_node.py -v`
Expected: FAIL — `cash_agent` not in nodes.

- [ ] **Step 4: Add cash_agent to build_graph**

In `backend/agent/graph.py`:

1. Add import at top:
```python
from backend.agent.prompts import (
    # ... existing ...
    CASH_PROMPT,
)
```

2. Inside `build_graph`, alongside the existing `quick_agent`, `analysis_agent`, etc. inner functions, add:

```python
    cash_tools = filter_tools(all_tools, "cash")

    async def cash_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(
            state, config, cash_tools, CASH_PROMPT, hitl_mode="none"
        )
```

3. Add the node and conditional-edge entry:

```python
    builder.add_node("cash_agent", cash_agent)
```

Add to the `add_conditional_edges` mapping:

```python
    builder.add_conditional_edges(
        "classify_query",
        route_after_classify,
        {
            "quick_agent": "quick_agent",
            "analysis_agent": "analysis_agent",
            "tax_agent": "tax_agent",
            "comparison_agent": "comparison_agent",
            "cash_agent": "cash_agent",
            "general_agent": "general_agent",
        },
    )
```

And the terminal edge:

```python
    builder.add_edge("cash_agent", END)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `backend/.venv/bin/pytest backend/tests/test_graph_cash_node.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/agent/graph.py backend/agent/prompts.py backend/tests/test_graph_cash_node.py
git commit -m "feat(agent): cash_agent node + CASH_PROMPT appendix"
git push
```

---

## Part 5 — Evals & polish

### Task 22: Extend eval golden set

**Files:**
- Modify: `backend/evals/golden_set.yaml`

- [ ] **Step 1: Read existing golden set structure**

```bash
backend/.venv/bin/cat backend/evals/golden_set.yaml | head -60
```

Note the YAML schema — fields like `id`, `query`, `expected_category`, `expected_tools`, etc.

- [ ] **Step 2: Add 5 cash-category entries**

Append to `backend/evals/golden_set.yaml` (matching the existing schema; substitute `expected_*` field names with whatever the file uses):

```yaml
# UP Bank / cash — added in Phase 6
- id: q036
  query: "How much cash do I have right now?"
  expected_category: cash
  expected_tools: [get_up_balance]

- id: q037
  query: "How much did I spend on Good Life last month?"
  expected_category: cash
  expected_tools: [get_up_spending_by_category]

- id: q038
  query: "What was my income vs expense in April?"
  expected_category: cash
  expected_tools: [get_up_cashflow]

- id: q039
  query: "What's my total net worth across crypto and bank?"
  expected_category: cash
  expected_tools: [get_combined_net_worth]

- id: q040
  query: "Show me my last few transactions."
  expected_category: cash
  expected_tools: [get_up_recent_transactions]
```

- [ ] **Step 3: Run the eval suite to validate**

```bash
EVAL_JUDGE_MODEL=claude-haiku-4-5 backend/.venv/bin/pytest backend/tests/test_evals.py -m eval -v -s
```

Expected: New cases run; classification rate may dip slightly with the new category. Acceptable if all 5 new entries route to `cash` correctly. If any fail, iterate on `CLASSIFIER_PROMPT`.

- [ ] **Step 4: Commit**

```bash
git add backend/evals/golden_set.yaml backend/evals/results/
git commit -m "test(evals): 5 cash-category golden-set queries"
git push
```

---

### Task 23: End-to-end smoke

**Files:** none (manual verification)

- [ ] **Step 1: Restart the backend**

```bash
backend/.venv/bin/uvicorn backend.main:app --reload
```

Expected log lines:
- `[Startup] MCP tools loaded: N` (where N includes the 5 new tools)
- `[Startup] Agent graph compiled`
- `[UpSync] First run — full backfill` (within 30s)
- `[UpSync] Success — last_seen_tx_at=...` (after backfill)

- [ ] **Step 2: Curl the endpoints**

```bash
COOKIE="$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"YOUR_PASSWORD"}' -c - | grep auth_session | awk '{print $7}')"

curl -s -b "auth_session=$COOKIE" http://localhost:8000/api/up/accounts | head -c 400
curl -s -b "auth_session=$COOKIE" "http://localhost:8000/api/up/spending/summary?since=2026-01-01T00:00:00Z&until=2026-12-31T00:00:00Z" | head -c 400
curl -s -b "auth_session=$COOKIE" http://localhost:8000/api/combined/summary
```

Expected: JSON responses with real data from your UP account.

- [ ] **Step 3: Test the agent via WebSocket**

Either via the existing frontend chat (if running) or with `wscat`:

```bash
wscat -c "ws://localhost:8000/api/agent/ws?token=..."
> {"type":"user","content":"How much cash do I have right now?"}
```

Expected: agent routes to `cash_agent`, calls `get_up_balance`, returns a cash total.

- [ ] **Step 4: Final commit (if any clean-up needed)**

If any minor fixes were needed during smoke testing, commit them:

```bash
git add -p
git commit -m "fix(up): post-smoke adjustments"
git push
```

If everything worked first try, no commit needed.

---

## Spec coverage check

| Spec section | Implemented in |
|---|---|
| Data model (new tables + source column) | Task 2 |
| `up_*` repos | Tasks 8–11 |
| UpClient (auth, retries, list_*) | Tasks 4–7 |
| Sync service (first-run + incremental + overlap) | Task 12 |
| up_snapshot_service + scheduler hook | Tasks 13, 14 |
| 15-min UP sync schedule | Task 14 |
| `/api/up/accounts` | Task 15 |
| `/api/up/transactions` | Task 16 |
| `/api/up/spending/summary` | Task 16 |
| `/api/up/cashflow` | Task 16 |
| `/api/up/sync/status` + retry | Task 17 |
| `/api/combined/snapshots` + summary | Task 18 |
| 5 MCP tools | Task 19 |
| Classifier `cash` category | Task 20 |
| `cash_agent` node + CASH_PROMPT | Task 21 |
| Eval extension | Task 22 |
| Error handling at UP boundary | Task 4 (UpClient) + Task 12 (sync_service catch) |
| Security (UP_PAT not logged) | Task 1 (Settings only); covered by existing log discipline |
| Testing (unit + repo + integration + eval) | Throughout |
| Migration safety | Task 2 |
| Frontend | **Plan B** (separate document, written after this plan executes) |

All backend spec requirements covered.

---

## Execution

Plan complete and saved to `docs/superpowers/plans/2026-05-11-up-bank-backend.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
