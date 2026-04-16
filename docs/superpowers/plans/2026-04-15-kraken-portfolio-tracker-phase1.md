# Kraken Portfolio Dashboard — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local portfolio dashboard that connects to the Kraken API to display real-time AUD values, per-lot FIFO P&L, allocation charts, and DCA history for ETH/SOL/ADA.

**Architecture:** Service layer pattern — FastAPI routers are thin wrappers over pure-Python service functions. The same service functions become MCP tools in Phase 2 without refactoring. APScheduler runs inside FastAPI for hourly snapshots.

**Tech Stack:** Python 3.12, FastAPI, python-kraken-sdk, supabase-py v2, APScheduler 3.x, React 18, TypeScript 5, Vite 5, Recharts, Tailwind CSS 3.

---

## File Map

```
kraken-portfolio-tracker/
├── backend/
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── config.py
│   ├── main.py
│   ├── scheduler.py
│   ├── db/
│   │   └── supabase_client.py
│   ├── models/
│   │   ├── portfolio.py
│   │   ├── trade.py
│   │   └── snapshot.py
│   ├── utils/
│   │   ├── aud.py
│   │   ├── timezone.py
│   │   └── fifo.py
│   ├── services/
│   │   ├── kraken_service.py
│   │   ├── portfolio_service.py
│   │   ├── snapshot_service.py
│   │   └── sync_service.py
│   ├── routers/
│   │   ├── portfolio.py
│   │   ├── history.py
│   │   └── sync.py
│   └── tests/
│       ├── conftest.py
│       ├── test_fifo.py
│       ├── test_portfolio_service.py
│       └── test_snapshot_service.py
├── supabase/
│   └── migrations/
│       ├── 001_create_tables.sql
│       └── 002_create_test_schema.sql
└── frontend/
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── postcss.config.js
    └── src/
        ├── main.tsx
        ├── globals.css
        ├── types/
        │   └── index.ts
        ├── api/
        │   └── portfolio.ts
        ├── utils/
        │   └── pnl.ts
        ├── components/
        │   ├── SummaryBar.tsx
        │   ├── AllocationPieChart.tsx
        │   ├── PortfolioLineChart.tsx
        │   ├── AssetBreakdown.tsx
        │   └── DCAHistoryTable.tsx
        └── pages/
            └── Dashboard.tsx
```

**Note on `sync_service.py`:** The spec lists 3 services. `sync_service.py` is added here to house trade→lot conversion and upsert logic, keeping the sync router thin and making Phase 2 MCP exposure clean.

---

## Task 1: Backend scaffolding & dependencies

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Create backend directory structure**

```bash
mkdir -p backend/{db,models,utils,services,routers,tests}
touch backend/__init__.py backend/db/__init__.py backend/models/__init__.py
touch backend/utils/__init__.py backend/services/__init__.py backend/routers/__init__.py
touch backend/tests/__init__.py
```

- [ ] **Step 2: Create `backend/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-kraken-sdk==3.2.7
supabase==2.7.0
apscheduler==3.10.4
pydantic==2.7.0
pydantic-settings==2.3.0
python-dotenv==1.0.0
pytest==8.2.0
pytest-asyncio==0.23.0
httpx==0.27.0
```

- [ ] **Step 3: Create `backend/pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Create virtual environment and install**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: No errors. `pip list` shows fastapi, kraken, supabase, apscheduler.

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: backend scaffolding and dependencies"
```

---

## Task 2: Supabase schema migrations

**Files:**
- Create: `supabase/migrations/001_create_tables.sql`
- Create: `supabase/migrations/002_create_test_schema.sql`

- [ ] **Step 1: Create `supabase/migrations/001_create_tables.sql`**

```sql
CREATE TABLE lots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset TEXT NOT NULL,
  acquired_at TIMESTAMPTZ NOT NULL,
  quantity NUMERIC(20, 8) NOT NULL,
  cost_aud NUMERIC(20, 8) NOT NULL,
  cost_per_unit_aud NUMERIC(20, 8) NOT NULL,
  kraken_trade_id TEXT UNIQUE NOT NULL,
  remaining_quantity NUMERIC(20, 8) NOT NULL
);

CREATE TABLE portfolio_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  captured_at TIMESTAMPTZ NOT NULL,
  total_value_aud NUMERIC(20, 2) NOT NULL,
  assets JSONB NOT NULL
);

CREATE TABLE sync_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_trade_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('success', 'error')),
  error_message TEXT
);

CREATE TABLE prices (
  asset TEXT PRIMARY KEY,
  price_aud NUMERIC(20, 2) NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lots_asset ON lots(asset);
CREATE INDEX idx_lots_acquired_at ON lots(acquired_at DESC);
CREATE INDEX idx_snapshots_captured_at ON portfolio_snapshots(captured_at DESC);
```

- [ ] **Step 2: Create `supabase/migrations/002_create_test_schema.sql`**

```sql
CREATE SCHEMA IF NOT EXISTS test;

CREATE TABLE test.lots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset TEXT NOT NULL,
  acquired_at TIMESTAMPTZ NOT NULL,
  quantity NUMERIC(20, 8) NOT NULL,
  cost_aud NUMERIC(20, 8) NOT NULL,
  cost_per_unit_aud NUMERIC(20, 8) NOT NULL,
  kraken_trade_id TEXT UNIQUE NOT NULL,
  remaining_quantity NUMERIC(20, 8) NOT NULL
);

CREATE TABLE test.portfolio_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  captured_at TIMESTAMPTZ NOT NULL,
  total_value_aud NUMERIC(20, 2) NOT NULL,
  assets JSONB NOT NULL
);

CREATE TABLE test.sync_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_trade_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('success', 'error')),
  error_message TEXT
);

CREATE TABLE test.prices (
  asset TEXT PRIMARY KEY,
  price_aud NUMERIC(20, 2) NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- [ ] **Step 3: Run migrations in Supabase**

Open the Supabase dashboard → SQL Editor. Run `001_create_tables.sql` first, then `002_create_test_schema.sql`. Verify all tables appear under both `public` and `test` schemas in the Table Editor.

- [ ] **Step 4: Commit**

```bash
git add supabase/
git commit -m "feat: Supabase schema migrations"
```

---

## Task 3: Config & Supabase client

**Files:**
- Create: `backend/config.py`
- Create: `backend/db/supabase_client.py`

- [ ] **Step 1: Create `backend/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kraken_api_key: str
    kraken_api_secret: str
    supabase_url: str
    supabase_key: str
    kraken_live_tests: bool = False

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 2: Create `backend/db/supabase_client.py`**

```python
from supabase import create_client, Client
from backend.config import settings

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client
```

- [ ] **Step 3: Verify config loads from .env**

```bash
cd backend
source .venv/bin/activate
python -c "from backend.config import settings; print(settings.supabase_url)"
```

Expected: prints your Supabase project URL (not an error).

- [ ] **Step 4: Commit**

```bash
git add backend/config.py backend/db/
git commit -m "feat: config and Supabase client"
```

---

## Task 4: Pydantic response models

**Files:**
- Create: `backend/models/portfolio.py`
- Create: `backend/models/trade.py`
- Create: `backend/models/snapshot.py`

- [ ] **Step 1: Create `backend/models/portfolio.py`**

```python
from pydantic import BaseModel


class AssetPosition(BaseModel):
    asset: str
    quantity: float
    price_aud: float
    value_aud: float
    cost_basis_aud: float
    unrealised_pnl_aud: float
    allocation_pct: float


class PortfolioSummary(BaseModel):
    total_value_aud: float
    positions: list[AssetPosition]
    captured_at: str   # ISO datetime string, AEST
    next_dca_date: str | None  # ISO date string
```

- [ ] **Step 2: Create `backend/models/trade.py`**

```python
from pydantic import BaseModel


class Lot(BaseModel):
    id: str
    asset: str
    acquired_at: str   # ISO datetime string, AEST
    quantity: float
    cost_aud: float
    cost_per_unit_aud: float
    kraken_trade_id: str
    remaining_quantity: float


class DCAEntry(BaseModel):
    lot_id: str
    asset: str
    acquired_at: str
    quantity: float
    cost_aud: float
    cost_per_unit_aud: float
    current_price_aud: float
    current_value_aud: float
    unrealised_pnl_aud: float
```

- [ ] **Step 3: Create `backend/models/snapshot.py`**

```python
from pydantic import BaseModel


class SnapshotAsset(BaseModel):
    quantity: float
    value_aud: float
    price_aud: float


class PortfolioSnapshot(BaseModel):
    id: str
    captured_at: str
    total_value_aud: float
    assets: dict[str, SnapshotAsset]
```

- [ ] **Step 4: Verify models import cleanly**

```bash
python -c "from backend.models.portfolio import PortfolioSummary; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/models/
git commit -m "feat: Pydantic response models"
```

---

## Task 5: FIFO cost basis utility (TDD)

**Files:**
- Create: `backend/utils/fifo.py`
- Create: `backend/tests/test_fifo.py`

- [ ] **Step 1: Write failing tests in `backend/tests/test_fifo.py`**

```python
from decimal import Decimal
from backend.utils.fifo import calculate_cost_basis, LotInput


def test_single_lot_full_remaining():
    lots = [LotInput(quantity=Decimal("1.0"), cost_per_unit_aud=Decimal("3000.00"), remaining_quantity=Decimal("1.0"))]
    result = calculate_cost_basis(lots)
    assert result == Decimal("3000.00")


def test_multiple_lots_all_remaining():
    lots = [
        LotInput(quantity=Decimal("1.0"), cost_per_unit_aud=Decimal("3000.00"), remaining_quantity=Decimal("1.0")),
        LotInput(quantity=Decimal("2.0"), cost_per_unit_aud=Decimal("3500.00"), remaining_quantity=Decimal("2.0")),
    ]
    result = calculate_cost_basis(lots)
    assert result == Decimal("10000.00")  # 3000 + 7000


def test_lot_with_zero_remaining_excluded():
    lots = [
        LotInput(quantity=Decimal("1.0"), cost_per_unit_aud=Decimal("3000.00"), remaining_quantity=Decimal("0.0")),
        LotInput(quantity=Decimal("2.0"), cost_per_unit_aud=Decimal("3500.00"), remaining_quantity=Decimal("2.0")),
    ]
    result = calculate_cost_basis(lots)
    assert result == Decimal("7000.00")  # only second lot


def test_partial_remaining_quantity():
    lots = [
        LotInput(quantity=Decimal("2.0"), cost_per_unit_aud=Decimal("3000.00"), remaining_quantity=Decimal("0.5")),
    ]
    result = calculate_cost_basis(lots)
    assert result == Decimal("1500.00")  # 0.5 * 3000


def test_empty_lots_returns_zero():
    result = calculate_cost_basis([])
    assert result == Decimal("0.00")


def test_mixed_assets_independent():
    eth_lots = [LotInput(quantity=Decimal("1.0"), cost_per_unit_aud=Decimal("3000.00"), remaining_quantity=Decimal("1.0"))]
    sol_lots = [LotInput(quantity=Decimal("10.0"), cost_per_unit_aud=Decimal("200.00"), remaining_quantity=Decimal("10.0"))]
    eth_basis = calculate_cost_basis(eth_lots)
    sol_basis = calculate_cost_basis(sol_lots)
    assert eth_basis == Decimal("3000.00")
    assert sol_basis == Decimal("2000.00")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
source .venv/bin/activate
pytest tests/test_fifo.py -v
```

Expected: `ModuleNotFoundError` — `backend.utils.fifo` does not exist yet.

- [ ] **Step 3: Create `backend/utils/fifo.py`**

```python
from decimal import Decimal
from typing import NamedTuple


class LotInput(NamedTuple):
    quantity: Decimal
    cost_per_unit_aud: Decimal
    remaining_quantity: Decimal


def calculate_cost_basis(lots: list[LotInput]) -> Decimal:
    """
    Returns total AUD cost basis of all lots with remaining_quantity > 0.
    Each lot's contribution = remaining_quantity * cost_per_unit_aud.
    For Phase 1 (no sells), remaining_quantity == quantity for all lots.
    Phase 4 will decrement remaining_quantity on disposal events.
    """
    return sum(
        (lot.remaining_quantity * lot.cost_per_unit_aud for lot in lots if lot.remaining_quantity > 0),
        Decimal("0"),
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_fifo.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/utils/fifo.py backend/tests/test_fifo.py
git commit -m "feat: FIFO cost basis utility with tests"
```

---

## Task 6: AUD formatting & timezone utilities

**Files:**
- Create: `backend/utils/aud.py`
- Create: `backend/utils/timezone.py`

- [ ] **Step 1: Create `backend/utils/aud.py`**

```python
def format_aud(value: float) -> str:
    """Format a float as AUD string: '$1,234.56'"""
    return f"${value:,.2f}"


def format_pct(value: float) -> str:
    """Format as percentage string: '42.31%'"""
    return f"{value:.2f}%"
```

- [ ] **Step 2: Create `backend/utils/timezone.py`**

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Sydney")


def now_aest() -> datetime:
    """Current time in AEST/AEDT (handles DST automatically)."""
    return datetime.now(tz=AEST)


def utc_to_aest(dt: datetime) -> datetime:
    """Convert a UTC datetime to AEST/AEDT."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(AEST)


def unix_to_aest(timestamp: float) -> datetime:
    """Convert a Unix timestamp (float) to AEST/AEDT datetime."""
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.astimezone(AEST)


def to_iso(dt: datetime) -> str:
    """Serialize a datetime to ISO 8601 string."""
    return dt.isoformat()
```

- [ ] **Step 3: Verify both modules import**

```bash
python -c "from backend.utils.aud import format_aud; from backend.utils.timezone import now_aest; print(format_aud(1234.5), now_aest())"
```

Expected: `$1,234.50` followed by current AEST datetime.

- [ ] **Step 4: Commit**

```bash
git add backend/utils/aud.py backend/utils/timezone.py
git commit -m "feat: AUD formatting and AEST timezone utilities"
```

---

## Task 7: Kraken service

**Files:**
- Create: `backend/services/kraken_service.py`

Kraken pair names used here: `XETHZAUD` (ETH/AUD), `SOLAUD` (SOL/AUD), `ADAAUD` (ADA/AUD).
Kraken balance keys: `XETH` (ETH), `SOL` (SOL), `ADA` (ADA).
Verify these against your account by calling `get_account_balance()` directly if needed.

- [ ] **Step 1: Create `backend/services/kraken_service.py`**

```python
from decimal import Decimal
from kraken.spot import User, Market
from backend.config import settings

# Mapping from Kraken balance key → display asset name → AUD pair
ASSET_MAP: dict[str, dict[str, str]] = {
    "XETH": {"name": "ETH", "pair": "XETHZAUD"},
    "SOL":  {"name": "SOL", "pair": "SOLAUD"},
    "ADA":  {"name": "ADA", "pair": "ADAAUD"},
}

# Mapping from Kraken pair name → display asset name (for trade history)
PAIR_TO_ASSET: dict[str, str] = {
    "XETHZAUD": "ETH",
    "SOLAUD":   "SOL",
    "ADAAUD":   "ADA",
}

_user: User | None = None
_market: Market | None = None


def _get_user() -> User:
    global _user
    if _user is None:
        _user = User(key=settings.kraken_api_key, secret=settings.kraken_api_secret)
    return _user


def _get_market() -> Market:
    global _market
    if _market is None:
        _market = Market()
    return _market


def get_balances() -> dict[str, Decimal]:
    """
    Returns current balances for tracked assets.
    Result: {"ETH": Decimal("1.5"), "SOL": Decimal("10.0"), "ADA": Decimal("1000.0")}
    """
    raw = _get_user().get_account_balance()
    result: dict[str, Decimal] = {}
    for kraken_key, info in ASSET_MAP.items():
        raw_balance = raw.get(kraken_key, "0")
        balance = Decimal(str(raw_balance))
        if balance > 0:
            result[info["name"]] = balance
    return result


def get_ticker_prices(assets: list[str]) -> dict[str, Decimal]:
    """
    Returns live AUD prices for given asset names (e.g. ["ETH", "SOL", "ADA"]).
    Result: {"ETH": Decimal("3000.00"), "SOL": Decimal("220.50"), ...}
    """
    # Build reverse lookup: asset name → pair
    name_to_pair = {info["name"]: info["pair"] for info in ASSET_MAP.values()}
    pairs = [name_to_pair[a] for a in assets if a in name_to_pair]
    if not pairs:
        return {}

    pair_str = ",".join(pairs)
    raw = _get_market().get_ticker(pair=pair_str)

    result: dict[str, Decimal] = {}
    pair_to_name = {info["pair"]: info["name"] for info in ASSET_MAP.values()}
    for pair, data in raw.items():
        asset_name = pair_to_name.get(pair)
        if asset_name:
            # 'c' is last trade price: [price, lot_volume]
            result[asset_name] = Decimal(str(data["c"][0]))
    return result


def get_trade_history(since_trade_id: str | None = None) -> list[dict]:
    """
    Returns all buy trades for tracked asset pairs.
    Paginates through all pages on first run (since_trade_id=None).
    On subsequent runs, pass the last known trade_id to fetch only new trades.

    Each returned dict contains:
      trade_id, asset, time (float unix), price (str), vol (str), cost (str)
    """
    user = _get_user()
    trades: list[dict] = []
    offset = 0
    page_size = 50

    while True:
        result = user.get_trades_history(ofs=offset)
        raw_trades: dict = result.get("trades", {})
        count: int = result.get("count", 0)

        for trade_id, trade in raw_trades.items():
            # Stop if we've reached a trade we already processed
            if since_trade_id and trade_id == since_trade_id:
                return trades

            pair = trade.get("pair", "")
            asset = PAIR_TO_ASSET.get(pair)
            if not asset:
                continue  # skip non-tracked pairs
            if trade.get("type") != "buy":
                continue  # skip sells for Phase 1

            trades.append({
                "trade_id": trade_id,
                "asset": asset,
                "time": float(trade["time"]),
                "price": str(trade["price"]),
                "vol": str(trade["vol"]),
                "cost": str(trade["cost"]),
            })

        offset += page_size
        if offset >= count:
            break

    return trades
```

- [ ] **Step 2: Smoke test (requires live API — only if `KRAKEN_LIVE_TESTS=true`)**

```bash
KRAKEN_LIVE_TESTS=true python -c "
from backend.services.kraken_service import get_balances, get_ticker_prices
balances = get_balances()
print('Balances:', balances)
prices = get_ticker_prices(list(balances.keys()))
print('Prices:', prices)
"
```

Expected: prints your ETH/SOL/ADA balances and current AUD prices. If pair names are wrong, update `ASSET_MAP` and `PAIR_TO_ASSET` in the service.

- [ ] **Step 3: Commit**

```bash
git add backend/services/kraken_service.py
git commit -m "feat: Kraken service (balances, prices, trade history)"
```

---

## Task 8: Portfolio service (TDD)

**Files:**
- Create: `backend/services/portfolio_service.py`
- Create: `backend/tests/test_portfolio_service.py`

- [ ] **Step 1: Write failing tests in `backend/tests/test_portfolio_service.py`**

```python
from decimal import Decimal
from backend.services.portfolio_service import calculate_summary, get_dca_history, calculate_next_dca_date
from backend.models.trade import Lot, DCAEntry
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Sydney")


def _lot(asset: str, qty: float, cost_per_unit: float, acquired_days_ago: int, trade_id: str) -> Lot:
    acquired_at = (datetime.now(tz=AEST) - timedelta(days=acquired_days_ago)).isoformat()
    return Lot(
        id="test-id",
        asset=asset,
        acquired_at=acquired_at,
        quantity=qty,
        cost_aud=qty * cost_per_unit,
        cost_per_unit_aud=cost_per_unit,
        kraken_trade_id=trade_id,
        remaining_quantity=qty,
    )


def test_calculate_summary_single_asset():
    balances = {"ETH": Decimal("1.0")}
    prices = {"ETH": Decimal("4000.00")}
    lots = [_lot("ETH", 1.0, 3000.00, 30, "t1")]

    summary = calculate_summary(balances, prices, lots)

    assert summary.total_value_aud == 4000.00
    assert len(summary.positions) == 1
    eth = summary.positions[0]
    assert eth.asset == "ETH"
    assert eth.value_aud == 4000.00
    assert eth.cost_basis_aud == 3000.00
    assert abs(eth.unrealised_pnl_aud - 1000.00) < 0.01
    assert eth.allocation_pct == 100.0


def test_calculate_summary_allocation_pct():
    balances = {"ETH": Decimal("1.0"), "SOL": Decimal("10.0")}
    prices = {"ETH": Decimal("2000.00"), "SOL": Decimal("200.00")}
    lots = [
        _lot("ETH", 1.0, 1800.00, 30, "t1"),
        _lot("SOL", 10.0, 150.00, 20, "t2"),
    ]

    summary = calculate_summary(balances, prices, lots)

    assert summary.total_value_aud == 4000.00  # 2000 ETH + 2000 SOL
    eth = next(p for p in summary.positions if p.asset == "ETH")
    sol = next(p for p in summary.positions if p.asset == "SOL")
    assert eth.allocation_pct == 50.0
    assert sol.allocation_pct == 50.0


def test_calculate_summary_negative_pnl():
    balances = {"ETH": Decimal("1.0")}
    prices = {"ETH": Decimal("2000.00")}
    lots = [_lot("ETH", 1.0, 3000.00, 30, "t1")]

    summary = calculate_summary(balances, prices, lots)

    eth = summary.positions[0]
    assert eth.unrealised_pnl_aud < 0
    assert abs(eth.unrealised_pnl_aud - (-1000.00)) < 0.01


def test_get_dca_history():
    prices = {"ETH": Decimal("4000.00")}
    lots = [
        _lot("ETH", 0.5, 2000.00, 60, "t1"),
        _lot("ETH", 0.5, 3000.00, 30, "t2"),
    ]

    entries = get_dca_history(lots, prices)

    assert len(entries) == 2
    assert all(e.asset == "ETH" for e in entries)
    first = entries[0]  # oldest first
    assert first.current_value_aud == 0.5 * 4000.00
    assert abs(first.unrealised_pnl_aud - (2000.00 - 1000.00)) < 0.01


def test_calculate_next_dca_date():
    lots = [
        _lot("ETH", 1.0, 3000.00, 14, "t1"),
        _lot("SOL", 10.0, 200.00, 7, "t2"),   # most recent: 7 days ago
    ]
    next_date = calculate_next_dca_date(lots)
    expected = (datetime.now(tz=AEST) - timedelta(days=7) + timedelta(days=7)).date()
    assert next_date == expected  # most recent lot + 7 days = today


def test_calculate_next_dca_date_empty():
    assert calculate_next_dca_date([]) is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_portfolio_service.py -v
```

Expected: `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Create `backend/services/portfolio_service.py`**

```python
from decimal import Decimal
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from backend.models.portfolio import AssetPosition, PortfolioSummary
from backend.models.trade import Lot, DCAEntry
from backend.utils.fifo import calculate_cost_basis, LotInput
from backend.utils.timezone import to_iso, now_aest

AEST = ZoneInfo("Australia/Sydney")


def calculate_summary(
    balances: dict[str, Decimal],
    prices: dict[str, Decimal],
    lots: list[Lot],
) -> PortfolioSummary:
    total_value = sum(
        balances.get(asset, Decimal("0")) * prices.get(asset, Decimal("0"))
        for asset in balances
    )

    positions: list[AssetPosition] = []
    for asset, quantity in balances.items():
        price = prices.get(asset, Decimal("0"))
        value = quantity * price

        asset_lots = [
            LotInput(
                quantity=Decimal(str(lot.quantity)),
                cost_per_unit_aud=Decimal(str(lot.cost_per_unit_aud)),
                remaining_quantity=Decimal(str(lot.remaining_quantity)),
            )
            for lot in lots
            if lot.asset == asset
        ]
        cost_basis = calculate_cost_basis(asset_lots)
        unrealised_pnl = value - cost_basis
        allocation_pct = (value / total_value * 100) if total_value else Decimal("0")

        positions.append(AssetPosition(
            asset=asset,
            quantity=float(quantity),
            price_aud=float(price),
            value_aud=float(value),
            cost_basis_aud=float(cost_basis),
            unrealised_pnl_aud=float(unrealised_pnl),
            allocation_pct=float(allocation_pct),
        ))

    return PortfolioSummary(
        total_value_aud=float(total_value),
        positions=sorted(positions, key=lambda p: p.value_aud, reverse=True),
        captured_at=to_iso(now_aest()),
        next_dca_date=calculate_next_dca_date(lots).isoformat() if calculate_next_dca_date(lots) else None,
    )


def get_dca_history(lots: list[Lot], prices: dict[str, Decimal]) -> list[DCAEntry]:
    entries: list[DCAEntry] = []
    for lot in sorted(lots, key=lambda l: l.acquired_at):
        price = prices.get(lot.asset, Decimal("0"))
        current_value = Decimal(str(lot.remaining_quantity)) * price
        cost = Decimal(str(lot.remaining_quantity)) * Decimal(str(lot.cost_per_unit_aud))
        entries.append(DCAEntry(
            lot_id=lot.id,
            asset=lot.asset,
            acquired_at=lot.acquired_at,
            quantity=lot.quantity,
            cost_aud=lot.cost_aud,
            cost_per_unit_aud=lot.cost_per_unit_aud,
            current_price_aud=float(price),
            current_value_aud=float(current_value),
            unrealised_pnl_aud=float(current_value - cost),
        ))
    return entries


def calculate_next_dca_date(lots: list[Lot]) -> date | None:
    if not lots:
        return None
    latest = max(lots, key=lambda l: l.acquired_at)
    acquired = datetime.fromisoformat(latest.acquired_at)
    return (acquired + timedelta(days=7)).date()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_portfolio_service.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/portfolio_service.py backend/tests/test_portfolio_service.py
git commit -m "feat: portfolio service with P&L and DCA calculations"
```

---

## Task 9: Sync service (trade → lots)

**Files:**
- Create: `backend/services/sync_service.py`

- [ ] **Step 1: Create `backend/services/sync_service.py`**

```python
from decimal import Decimal
from backend.db.supabase_client import get_supabase
from backend.utils.timezone import unix_to_aest, to_iso


def get_last_synced_trade_id() -> str | None:
    """Returns the most recently synced trade_id from sync_log, or None."""
    db = get_supabase()
    result = (
        db.table("sync_log")
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


def upsert_lots(trades: list[dict]) -> str | None:
    """
    Converts raw trade dicts (from kraken_service.get_trade_history) into lot rows
    and upserts them into the lots table.
    Returns the trade_id of the first trade processed (most recent),
    or None if trades is empty.
    """
    if not trades:
        return None

    db = get_supabase()
    rows = []
    for trade in trades:
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

    db.table("lots").upsert(rows, on_conflict="kraken_trade_id").execute()
    return trades[0]["trade_id"]


def record_sync(last_trade_id: str | None, status: str, error_message: str | None = None) -> None:
    """Writes a row to sync_log."""
    db = get_supabase()
    db.table("sync_log").insert({
        "last_trade_id": last_trade_id,
        "status": status,
        "error_message": error_message,
    }).execute()


def get_all_lots() -> list[dict]:
    """Returns all lots from Supabase ordered oldest first."""
    db = get_supabase()
    result = db.table("lots").select("*").order("acquired_at", desc=False).execute()
    return result.data
```

- [ ] **Step 2: Verify import**

```bash
python -c "from backend.services.sync_service import get_last_synced_trade_id; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/services/sync_service.py
git commit -m "feat: sync service (trade history to lots upsert)"
```

---

## Task 10: Snapshot service (TDD with test schema)

**Files:**
- Create: `backend/services/snapshot_service.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_snapshot_service.py`

- [ ] **Step 1: Create `backend/tests/conftest.py`**

```python
import pytest
from supabase import create_client, Client
from backend.config import settings

TEST_TABLES = ["lots", "portfolio_snapshots", "sync_log", "prices"]
# UUID that will never exist — used to match all rows via neq
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="session")
def test_db() -> Client:
    return create_client(settings.supabase_url, settings.supabase_key)


@pytest.fixture(autouse=True)
def clean_test_tables(test_db: Client):
    """Truncate all test schema tables before and after each test."""
    def _clean():
        for table in ["lots", "portfolio_snapshots", "sync_log"]:
            test_db.schema("test").table(table).delete().neq("id", _SENTINEL_UUID).execute()
        # prices table uses asset (text) as PK
        test_db.schema("test").table("prices").delete().neq("asset", "__sentinel__").execute()

    _clean()
    yield
    _clean()
```

- [ ] **Step 2: Write failing tests in `backend/tests/test_snapshot_service.py`**

```python
from decimal import Decimal
from backend.services.snapshot_service import save_snapshot, get_snapshots, should_snapshot
from backend.models.portfolio import PortfolioSummary, AssetPosition
from backend.utils.timezone import now_aest, to_iso
from datetime import timedelta


def _make_summary() -> PortfolioSummary:
    return PortfolioSummary(
        total_value_aud=5000.00,
        positions=[
            AssetPosition(
                asset="ETH",
                quantity=1.0,
                price_aud=5000.00,
                value_aud=5000.00,
                cost_basis_aud=3000.00,
                unrealised_pnl_aud=2000.00,
                allocation_pct=100.0,
            )
        ],
        captured_at=to_iso(now_aest()),
        next_dca_date=None,
    )


def test_save_and_retrieve_snapshot(test_db):
    save_snapshot(_make_summary(), schema="test")
    snapshots = get_snapshots(schema="test")
    assert len(snapshots) == 1
    assert snapshots[0].total_value_aud == 5000.00
    assert "ETH" in snapshots[0].assets


def test_should_snapshot_true_when_no_recent_snapshot(test_db):
    assert should_snapshot(schema="test") is True


def test_should_snapshot_false_when_recent_snapshot_exists(test_db):
    save_snapshot(_make_summary(), schema="test")
    assert should_snapshot(schema="test") is False


def test_get_snapshots_returns_time_range(test_db):
    save_snapshot(_make_summary(), schema="test")
    from_dt = to_iso(now_aest() - timedelta(hours=1))
    to_dt = to_iso(now_aest() + timedelta(hours=1))
    snapshots = get_snapshots(from_dt=from_dt, to_dt=to_dt, schema="test")
    assert len(snapshots) == 1
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
pytest tests/test_snapshot_service.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Create `backend/services/snapshot_service.py`**

```python
from datetime import timedelta
from backend.db.supabase_client import get_supabase
from backend.models.portfolio import PortfolioSummary
from backend.models.snapshot import PortfolioSnapshot, SnapshotAsset
from backend.utils.timezone import now_aest, to_iso


def save_snapshot(summary: PortfolioSummary, schema: str = "public") -> None:
    db = get_supabase()
    assets_json = {
        pos.asset: {
            "quantity": pos.quantity,
            "value_aud": pos.value_aud,
            "price_aud": pos.price_aud,
        }
        for pos in summary.positions
    }
    db.schema(schema).table("portfolio_snapshots").insert({
        "captured_at": summary.captured_at,
        "total_value_aud": summary.total_value_aud,
        "assets": assets_json,
    }).execute()


def get_snapshots(
    from_dt: str | None = None,
    to_dt: str | None = None,
    schema: str = "public",
) -> list[PortfolioSnapshot]:
    db = get_supabase()
    query = db.schema(schema).table("portfolio_snapshots").select("*").order("captured_at", desc=False)
    if from_dt:
        query = query.gte("captured_at", from_dt)
    if to_dt:
        query = query.lte("captured_at", to_dt)
    result = query.execute()
    return [
        PortfolioSnapshot(
            id=row["id"],
            captured_at=row["captured_at"],
            total_value_aud=float(row["total_value_aud"]),
            assets={
                asset: SnapshotAsset(**data)
                for asset, data in row["assets"].items()
            },
        )
        for row in result.data
    ]


def should_snapshot(schema: str = "public") -> bool:
    """Returns True if no snapshot exists in the last hour."""
    db = get_supabase()
    one_hour_ago = to_iso(now_aest() - timedelta(hours=1))
    result = (
        db.schema(schema).table("portfolio_snapshots")
        .select("id")
        .gte("captured_at", one_hour_ago)
        .limit(1)
        .execute()
    )
    return len(result.data) == 0
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_snapshot_service.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/snapshot_service.py backend/tests/conftest.py backend/tests/test_snapshot_service.py
git commit -m "feat: snapshot service with test schema isolation"
```

---

## Task 11: Routers

**Files:**
- Create: `backend/routers/portfolio.py`
- Create: `backend/routers/history.py`
- Create: `backend/routers/sync.py`

- [ ] **Step 1: Create `backend/routers/portfolio.py`**

```python
from fastapi import APIRouter, HTTPException
from backend.models.portfolio import PortfolioSummary
from backend.models.trade import Lot
from backend.services import kraken_service, portfolio_service, snapshot_service
from backend.services.sync_service import get_all_lots

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary() -> PortfolioSummary:
    try:
        balances = kraken_service.get_balances()
        prices = kraken_service.get_ticker_prices(list(balances.keys()))
        raw_lots = get_all_lots()
        lots = [Lot(**row) for row in raw_lots]
        summary = portfolio_service.calculate_summary(balances, prices, lots)

        if snapshot_service.should_snapshot():
            snapshot_service.save_snapshot(summary)

        return summary
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
```

- [ ] **Step 2: Create `backend/routers/history.py`**

```python
from fastapi import APIRouter, HTTPException, Query
from backend.models.snapshot import PortfolioSnapshot
from backend.models.trade import DCAEntry, Lot
from backend.services import snapshot_service, portfolio_service, kraken_service
from backend.services.sync_service import get_all_lots

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/snapshots", response_model=list[PortfolioSnapshot])
async def get_snapshots(
    from_dt: str | None = Query(default=None),
    to_dt: str | None = Query(default=None),
) -> list[PortfolioSnapshot]:
    try:
        return snapshot_service.get_snapshots(from_dt=from_dt, to_dt=to_dt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/trades", response_model=list[DCAEntry])
async def get_dca_history() -> list[DCAEntry]:
    try:
        raw_lots = get_all_lots()
        lots = [Lot(**row) for row in raw_lots]
        balances = kraken_service.get_balances()
        prices = kraken_service.get_ticker_prices(list(balances.keys()))
        return portfolio_service.get_dca_history(lots, prices)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
```

- [ ] **Step 3: Create `backend/routers/sync.py`**

```python
from fastapi import APIRouter, HTTPException
from backend.services import kraken_service
from backend.services.sync_service import (
    get_last_synced_trade_id,
    upsert_lots,
    record_sync,
)

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("")
async def trigger_sync() -> dict:
    try:
        last_trade_id = get_last_synced_trade_id()
        trades = kraken_service.get_trade_history(since_trade_id=last_trade_id)
        new_last_id = upsert_lots(trades)
        record_sync(last_trade_id=new_last_id or last_trade_id, status="success")
        return {"synced": len(trades), "last_trade_id": new_last_id}
    except Exception as e:
        record_sync(last_trade_id=None, status="error", error_message=str(e))
        raise HTTPException(status_code=502, detail=str(e))
```

- [ ] **Step 4: Commit**

```bash
git add backend/routers/
git commit -m "feat: FastAPI routers (portfolio, history, sync)"
```

---

## Task 12: Scheduler & main.py

**Files:**
- Create: `backend/scheduler.py`
- Create: `backend/main.py`

- [ ] **Step 1: Create `backend/scheduler.py`**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.services import kraken_service, portfolio_service, snapshot_service
from backend.services.sync_service import get_all_lots
from backend.models.trade import Lot

scheduler = AsyncIOScheduler()


async def _hourly_snapshot() -> None:
    try:
        balances = kraken_service.get_balances()
        prices = kraken_service.get_ticker_prices(list(balances.keys()))
        raw_lots = get_all_lots()
        lots = [Lot(**row) for row in raw_lots]
        summary = portfolio_service.calculate_summary(balances, prices, lots)
        snapshot_service.save_snapshot(summary)
    except Exception as e:
        # Log but don't crash the scheduler
        print(f"[scheduler] Snapshot failed: {e}")


def start_scheduler() -> None:
    scheduler.add_job(_hourly_snapshot, "interval", hours=1, id="hourly_snapshot")
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown()
```

- [ ] **Step 2: Create `backend/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.scheduler import start_scheduler, stop_scheduler
from backend.routers import portfolio, history, sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Kraken Portfolio Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router)
app.include_router(history.router)
app.include_router(sync.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 3: Start the backend and verify**

```bash
cd backend
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

In a second terminal:
```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Trigger a full sync to populate lots table**

```bash
curl -X POST http://localhost:8000/api/sync
```

Expected: `{"synced": <N>, "last_trade_id": "<id>"}` — N is your total historical trade count.

- [ ] **Step 5: Verify portfolio summary endpoint**

```bash
curl http://localhost:8000/api/portfolio/summary | python -m json.tool
```

Expected: JSON with `total_value_aud`, `positions` array, `captured_at`.

- [ ] **Step 6: Commit**

```bash
git add backend/scheduler.py backend/main.py
git commit -m "feat: APScheduler and FastAPI app entrypoint"
```

---

## Task 13: Frontend scaffold

**Files:**
- Create: `frontend/` (Vite project)
- Modify: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/src/globals.css`

- [ ] **Step 1: Scaffold Vite + React + TypeScript project**

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

- [ ] **Step 2: Install dependencies**

```bash
npm install recharts
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 3: Replace `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 4: Replace `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {},
  },
  plugins: [],
}
```

- [ ] **Step 5: Replace `frontend/src/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html {
    @apply bg-gray-900 text-gray-100;
  }
}
```

- [ ] **Step 6: Update `frontend/src/main.tsx` to apply dark mode**

```typescript
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './globals.css'
import Dashboard from './pages/Dashboard'

document.documentElement.classList.add('dark')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Dashboard />
  </StrictMode>,
)
```

- [ ] **Step 7: Verify Vite dev server starts**

```bash
npm run dev
```

Expected: `VITE v5.x ready` at `http://localhost:5173`. Browser shows dark background.

- [ ] **Step 8: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat: Vite + React + TypeScript + Tailwind scaffold"
```

---

## Task 14: TypeScript types & API fetch wrappers

**Files:**
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/api/portfolio.ts`
- Create: `frontend/src/utils/pnl.ts`

- [ ] **Step 1: Create `frontend/src/types/index.ts`**

```typescript
export interface AssetPosition {
  asset: string
  quantity: number
  price_aud: number
  value_aud: number
  cost_basis_aud: number
  unrealised_pnl_aud: number
  allocation_pct: number
}

export interface PortfolioSummary {
  total_value_aud: number
  positions: AssetPosition[]
  captured_at: string
  next_dca_date: string | null
}

export interface SnapshotAsset {
  quantity: number
  value_aud: number
  price_aud: number
}

export interface PortfolioSnapshot {
  id: string
  captured_at: string
  total_value_aud: number
  assets: Record<string, SnapshotAsset>
}

export interface DCAEntry {
  lot_id: string
  asset: string
  acquired_at: string
  quantity: number
  cost_aud: number
  cost_per_unit_aud: number
  current_price_aud: number
  current_value_aud: number
  unrealised_pnl_aud: number
}
```

- [ ] **Step 2: Create `frontend/src/api/portfolio.ts`**

```typescript
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} returned ${res.status}`)
  return res.json() as Promise<T>
}

export async function fetchPortfolioSummary(): Promise<PortfolioSummary> {
  return fetchJSON<PortfolioSummary>('/api/portfolio/summary')
}

export async function fetchSnapshots(from?: string, to?: string): Promise<PortfolioSnapshot[]> {
  const params = new URLSearchParams()
  if (from) params.set('from_dt', from)
  if (to) params.set('to_dt', to)
  const qs = params.toString() ? `?${params.toString()}` : ''
  return fetchJSON<PortfolioSnapshot[]>(`/api/history/snapshots${qs}`)
}

export async function fetchDCAHistory(): Promise<DCAEntry[]> {
  return fetchJSON<DCAEntry[]>('/api/history/trades')
}
```

- [ ] **Step 3: Create `frontend/src/utils/pnl.ts`**

```typescript
export function getPnlClass(value: number): string {
  if (value > 0) return 'text-green-400'
  if (value < 0) return 'text-red-400'
  return 'text-gray-400'
}

export function formatAUD(value: number): string {
  return new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency: 'AUD',
    minimumFractionDigits: 2,
  }).format(value)
}

export function formatPct(value: number): string {
  return `${value.toFixed(2)}%`
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/ frontend/src/api/ frontend/src/utils/
git commit -m "feat: TypeScript types, API fetch wrappers, and P&L utilities"
```

---

## Task 15: SummaryBar component

**Files:**
- Create: `frontend/src/components/SummaryBar.tsx`

- [ ] **Step 1: Create `frontend/src/components/SummaryBar.tsx`**

```typescript
import { formatAUD } from '../utils/pnl'
import type { PortfolioSummary } from '../types'

interface Props {
  summary: PortfolioSummary
  onRefresh: () => void
  refreshing: boolean
}

export default function SummaryBar({ summary, onRefresh, refreshing }: Props) {
  const lastUpdated = new Date(summary.captured_at).toLocaleString('en-AU', {
    timeZone: 'Australia/Sydney',
    dateStyle: 'short',
    timeStyle: 'short',
  })

  const nextDCA = summary.next_dca_date
    ? new Date(summary.next_dca_date).toLocaleDateString('en-AU', {
        timeZone: 'Australia/Sydney',
        dateStyle: 'medium',
      })
    : '—'

  return (
    <div className="flex items-center justify-between px-6 py-4 bg-gray-800 border-b border-gray-700">
      <div>
        <p className="text-sm text-gray-400">Portfolio Value</p>
        <p className="text-3xl font-bold text-white">{formatAUD(summary.total_value_aud)}</p>
      </div>
      <div className="flex items-center gap-8">
        <div className="text-right">
          <p className="text-sm text-gray-400">Next DCA</p>
          <p className="text-white font-medium">{nextDCA}</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-gray-400">Last updated</p>
          <p className="text-white font-medium">{lastUpdated}</p>
        </div>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SummaryBar.tsx
git commit -m "feat: SummaryBar component"
```

---

## Task 16: AllocationPieChart component

**Files:**
- Create: `frontend/src/components/AllocationPieChart.tsx`

- [ ] **Step 1: Create `frontend/src/components/AllocationPieChart.tsx`**

```typescript
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { AssetPosition } from '../types'
import { formatPct, formatAUD } from '../utils/pnl'

interface Props {
  positions: AssetPosition[]
}

const COLORS: Record<string, string> = {
  ETH: '#627EEA',
  SOL: '#9945FF',
  ADA: '#0033AD',
}
const DEFAULT_COLOR = '#6B7280'

export default function AllocationPieChart({ positions }: Props) {
  const data = positions.map((p) => ({
    name: p.asset,
    value: p.allocation_pct,
    value_aud: p.value_aud,
  }))

  return (
    <div className="bg-gray-800 rounded-xl p-6">
      <h2 className="text-lg font-semibold text-white mb-4">Allocation</h2>
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={70}
            outerRadius={110}
            dataKey="value"
            label={({ name, value }) => `${name} ${formatPct(value)}`}
            labelLine={false}
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={COLORS[entry.name] ?? DEFAULT_COLOR} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number, name: string, props) => [
              `${formatPct(value)} (${formatAUD(props.payload.value_aud)})`,
              name,
            ]}
            contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
            labelStyle={{ color: '#F9FAFB' }}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AllocationPieChart.tsx
git commit -m "feat: AllocationPieChart component"
```

---

## Task 17: PortfolioLineChart component

**Files:**
- Create: `frontend/src/components/PortfolioLineChart.tsx`

- [ ] **Step 1: Create `frontend/src/components/PortfolioLineChart.tsx`**

```typescript
import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { PortfolioSnapshot } from '../types'
import { formatAUD } from '../utils/pnl'

interface Props {
  snapshots: PortfolioSnapshot[]
}

type View = 'total' | 'per-asset'
type Range = '7d' | '30d' | 'all'

const ASSET_COLORS: Record<string, string> = {
  ETH: '#627EEA',
  SOL: '#9945FF',
  ADA: '#0033AD',
}

function filterByRange(snapshots: PortfolioSnapshot[], range: Range): PortfolioSnapshot[] {
  if (range === 'all') return snapshots
  const days = range === '7d' ? 7 : 30
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snapshots.filter((s) => new Date(s.captured_at) >= cutoff)
}

export default function PortfolioLineChart({ snapshots }: Props) {
  const [view, setView] = useState<View>('total')
  const [range, setRange] = useState<Range>('30d')

  const filtered = filterByRange(snapshots, range)
  const data = filtered.map((s) => {
    const row: Record<string, number | string> = {
      date: new Date(s.captured_at).toLocaleDateString('en-AU', { timeZone: 'Australia/Sydney' }),
      total: s.total_value_aud,
    }
    for (const [asset, info] of Object.entries(s.assets)) {
      row[asset] = info.value_aud
    }
    return row
  })

  const assets = snapshots.length > 0 ? Object.keys(snapshots[0].assets) : []

  return (
    <div className="bg-gray-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Portfolio Value</h2>
        <div className="flex gap-2">
          {(['7d', '30d', 'all'] as Range[]).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                range === r ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {r}
            </button>
          ))}
          <div className="w-px bg-gray-600 mx-1" />
          {(['total', 'per-asset'] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                view === v ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {v === 'total' ? 'Total' : 'Per Asset'}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="date" stroke="#9CA3AF" tick={{ fontSize: 12 }} />
          <YAxis
            stroke="#9CA3AF"
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
          />
          <Tooltip
            formatter={(value: number) => [formatAUD(value)]}
            contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
            labelStyle={{ color: '#F9FAFB' }}
          />
          <Legend />
          {view === 'total' ? (
            <Line type="monotone" dataKey="total" name="Total" stroke="#60A5FA" dot={false} strokeWidth={2} />
          ) : (
            assets.map((asset) => (
              <Line
                key={asset}
                type="monotone"
                dataKey={asset}
                name={asset}
                stroke={ASSET_COLORS[asset] ?? '#6B7280'}
                dot={false}
                strokeWidth={2}
              />
            ))
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/PortfolioLineChart.tsx
git commit -m "feat: PortfolioLineChart with total/per-asset toggle and 7d/30d/all range"
```

---

## Task 18: AssetBreakdown component

**Files:**
- Create: `frontend/src/components/AssetBreakdown.tsx`

- [ ] **Step 1: Create `frontend/src/components/AssetBreakdown.tsx`**

```typescript
import type { AssetPosition } from '../types'
import { formatAUD, formatPct, getPnlClass } from '../utils/pnl'

interface Props {
  positions: AssetPosition[]
}

export default function AssetBreakdown({ positions }: Props) {
  return (
    <div className="bg-gray-800 rounded-xl p-6">
      <h2 className="text-lg font-semibold text-white mb-4">Asset Breakdown</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-400 border-b border-gray-700">
            <th className="text-left pb-3">Asset</th>
            <th className="text-right pb-3">Qty</th>
            <th className="text-right pb-3">Price</th>
            <th className="text-right pb-3">Value</th>
            <th className="text-right pb-3">Allocation</th>
            <th className="text-right pb-3">Cost Basis</th>
            <th className="text-right pb-3">Unrealised P&L</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.asset} className="border-b border-gray-700 hover:bg-gray-750">
              <td className="py-3 font-medium text-white">{p.asset}</td>
              <td className="py-3 text-right text-gray-300">{p.quantity.toFixed(4)}</td>
              <td className="py-3 text-right text-gray-300">{formatAUD(p.price_aud)}</td>
              <td className="py-3 text-right text-white font-medium">{formatAUD(p.value_aud)}</td>
              <td className="py-3 text-right text-gray-300">{formatPct(p.allocation_pct)}</td>
              <td className="py-3 text-right text-gray-300">{formatAUD(p.cost_basis_aud)}</td>
              <td className={`py-3 text-right font-medium ${getPnlClass(p.unrealised_pnl_aud)}`}>
                {formatAUD(p.unrealised_pnl_aud)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AssetBreakdown.tsx
git commit -m "feat: AssetBreakdown table with green/red P&L"
```

---

## Task 19: DCAHistoryTable component

**Files:**
- Create: `frontend/src/components/DCAHistoryTable.tsx`

- [ ] **Step 1: Create `frontend/src/components/DCAHistoryTable.tsx`**

```typescript
import type { DCAEntry } from '../types'
import { formatAUD, getPnlClass } from '../utils/pnl'

interface Props {
  entries: DCAEntry[]
}

export default function DCAHistoryTable({ entries }: Props) {
  return (
    <div className="bg-gray-800 rounded-xl p-6">
      <h2 className="text-lg font-semibold text-white mb-4">DCA History</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-700">
              <th className="text-left pb-3">Date</th>
              <th className="text-left pb-3">Asset</th>
              <th className="text-right pb-3">Qty</th>
              <th className="text-right pb-3">Buy Price</th>
              <th className="text-right pb-3">Cost Paid</th>
              <th className="text-right pb-3">Current Value</th>
              <th className="text-right pb-3">P&L</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => {
              const date = new Date(e.acquired_at).toLocaleDateString('en-AU', {
                timeZone: 'Australia/Sydney',
                dateStyle: 'medium',
              })
              return (
                <tr key={e.lot_id} className="border-b border-gray-700 hover:bg-gray-750">
                  <td className="py-3 text-gray-300">{date}</td>
                  <td className="py-3 font-medium text-white">{e.asset}</td>
                  <td className="py-3 text-right text-gray-300">{e.quantity.toFixed(4)}</td>
                  <td className="py-3 text-right text-gray-300">{formatAUD(e.cost_per_unit_aud)}</td>
                  <td className="py-3 text-right text-gray-300">{formatAUD(e.cost_aud)}</td>
                  <td className="py-3 text-right text-white font-medium">{formatAUD(e.current_value_aud)}</td>
                  <td className={`py-3 text-right font-medium ${getPnlClass(e.unrealised_pnl_aud)}`}>
                    {formatAUD(e.unrealised_pnl_aud)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/DCAHistoryTable.tsx
git commit -m "feat: DCAHistoryTable with per-lot P&L"
```

---

## Task 20: Dashboard page (wire everything)

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`
- Delete: `frontend/src/App.tsx` (replace with Dashboard)

- [ ] **Step 1: Create `frontend/src/pages/Dashboard.tsx`**

```typescript
import { useState, useEffect, useCallback } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'
import SummaryBar from '../components/SummaryBar'
import AllocationPieChart from '../components/AllocationPieChart'
import PortfolioLineChart from '../components/PortfolioLineChart'
import AssetBreakdown from '../components/AssetBreakdown'
import DCAHistoryTable from '../components/DCAHistoryTable'

interface DashboardState {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  dcaHistory: DCAEntry[]
  errors: { summary?: string; snapshots?: string; dca?: string }
}

export default function Dashboard() {
  const [state, setState] = useState<DashboardState>({
    summary: null,
    snapshots: [],
    dcaHistory: [],
    errors: {},
  })
  const [refreshing, setRefreshing] = useState(false)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const errors: DashboardState['errors'] = {}

    const [summaryResult, snapshotsResult, dcaResult] = await Promise.allSettled([
      fetchPortfolioSummary(),
      fetchSnapshots(),
      fetchDCAHistory(),
    ])

    const summary =
      summaryResult.status === 'fulfilled' ? summaryResult.value : null
    if (summaryResult.status === 'rejected') errors.summary = (summaryResult.reason as Error).message

    const snapshots =
      snapshotsResult.status === 'fulfilled' ? snapshotsResult.value : []
    if (snapshotsResult.status === 'rejected') errors.snapshots = (snapshotsResult.reason as Error).message

    const dcaHistory =
      dcaResult.status === 'fulfilled' ? dcaResult.value : []
    if (dcaResult.status === 'rejected') errors.dca = (dcaResult.reason as Error).message

    setState((prev) => ({
      ...prev,
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

  const { summary, snapshots, dcaHistory, errors } = state

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100">
      {summary ? (
        <SummaryBar summary={summary} onRefresh={refresh} refreshing={refreshing} />
      ) : (
        <div className="px-6 py-4 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
          <p className="text-gray-400">{errors.summary ?? 'Loading portfolio…'}</p>
          <button
            onClick={refresh}
            disabled={refreshing}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50"
          >
            {refreshing ? 'Loading…' : 'Retry'}
          </button>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            {summary ? (
              <AllocationPieChart positions={summary.positions} />
            ) : (
              <div className="bg-gray-800 rounded-xl p-6 text-gray-400">
                {errors.summary ?? 'Loading…'}
              </div>
            )}
          </div>
          <div className="lg:col-span-2">
            {snapshots.length > 0 ? (
              <PortfolioLineChart snapshots={snapshots} />
            ) : (
              <div className="bg-gray-800 rounded-xl p-6 text-gray-400">
                {errors.snapshots ?? 'No snapshot history yet — check back after the first hourly snapshot.'}
              </div>
            )}
          </div>
        </div>

        {summary ? (
          <AssetBreakdown positions={summary.positions} />
        ) : (
          <div className="bg-gray-800 rounded-xl p-6 text-gray-400">
            {errors.summary ?? 'Loading…'}
          </div>
        )}

        {dcaHistory.length > 0 ? (
          <DCAHistoryTable entries={dcaHistory} />
        ) : (
          <div className="bg-gray-800 rounded-xl p-6 text-gray-400">
            {errors.dca ?? 'No DCA history found. Run POST /api/sync to import trade history.'}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles cleanly**

```bash
cd frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Run full stack and open browser**

Terminal 1 (backend):
```bash
cd backend && source .venv/bin/activate && uvicorn backend.main:app --reload --port 8000
```

Terminal 2 (frontend):
```bash
cd frontend && npm run dev
```

Open `http://localhost:5173`. Expected: dark dashboard with portfolio value, allocation chart, and tables populated from your Kraken account.

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: Dashboard page — Phase 1 complete"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Kraken API: balances, tickers, trade history → Tasks 7, 9
- ✅ AUD prices → kraken_service.get_ticker_prices
- ✅ Portfolio value, allocation %, unrealised P&L → Task 8
- ✅ Trade/ledger history → Task 9 (sync_service)
- ✅ Supabase snapshots → Task 10
- ✅ Portfolio summary card → Task 15 (SummaryBar) + Task 18 (AssetBreakdown)
- ✅ Allocation pie chart → Task 16
- ✅ Portfolio value line chart → Task 17
- ✅ DCA history table → Task 19
- ✅ P&L per asset → AssetBreakdown + DCAHistoryTable
- ✅ Hourly snapshots via APScheduler → Task 12
- ✅ Page-load snapshot fallback → portfolio router
- ✅ Per-lot FIFO cost basis → Task 5
- ✅ API-only historical sync → Task 9 + sync router
- ✅ Dark mode → Task 13
- ✅ Green/red P&L → getPnlClass in Tasks 18, 19
- ✅ Per-asset chart toggle → Task 17
- ✅ Manual refresh button → Task 15 + Dashboard
- ✅ Next DCA date (weekly) → portfolio_service + SummaryBar
- ✅ Test schema with teardown → Task 10 conftest
- ✅ FIFO unit tests → Task 5
- ✅ Portfolio service unit tests → Task 8
- ✅ AEST timestamps everywhere → utils/timezone.py
