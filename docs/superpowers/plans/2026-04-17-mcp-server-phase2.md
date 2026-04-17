# MCP Server (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the Phase 1 service layer as MCP tools and resources so AI clients (Claude Code, Claude Desktop) can query and interact with the Kraken portfolio.

**Architecture:** Standalone `backend/mcp_server.py` using the `mcp` Python SDK's `FastMCP` class. Six tools (thin async wrappers over existing services via `asyncio.to_thread`) and two resources. stdio transport. Independent from the FastAPI process.

**Tech Stack:** `mcp` (official Python MCP SDK), `FastMCP`, existing `kraken_service`, `portfolio_service`, `snapshot_service`, `sync_service`

**Spec:** `docs/superpowers/specs/2026-04-17-mcp-server-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/services/portfolio_service.py` | Modify | Add `build_summary()` orchestrator |
| `backend/routers/portfolio.py` | Modify | Use `build_summary()` instead of inline orchestration |
| `backend/scheduler.py` | Modify | Use `build_summary()` instead of inline orchestration |
| `backend/services/sync_service.py` | Modify | Fix `upsert_lots` to insert-only-if-new |
| `backend/requirements.txt` | Modify | Add `mcp` dependency |
| `backend/mcp_server.py` | Create | MCP server entry point — tools + resources |
| `backend/tests/test_build_summary.py` | Create | Unit tests for `build_summary()` orchestrator |
| `backend/tests/test_upsert_lots.py` | Create | Unit tests for insert-only-if-new behavior |
| `backend/tests/test_mcp_server.py` | Create | Unit tests for MCP tool handlers |
| `backend/tests/test_mcp_integration.py` | Create | Integration smoke test — server boot + tool listing |
| `.claude/settings.json` | Create | Claude Code MCP server configuration |

---

### Task 1: Extract `build_summary()` helper

**Files:**
- Modify: `backend/services/portfolio_service.py`
- Create: `backend/tests/test_build_summary.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_build_summary.py`:

```python
from decimal import Decimal
from unittest.mock import patch, MagicMock
from backend.models.trade import Lot
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Sydney")


def _lot(asset: str, qty: float, cost_per_unit: float, days_ago: int, trade_id: str) -> Lot:
    acquired_at = (datetime.now(tz=AEST) - timedelta(days=days_ago)).isoformat()
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


@patch("backend.services.portfolio_service.sync_service")
@patch("backend.services.portfolio_service.kraken_service")
def test_build_summary_orchestrates_services(mock_kraken, mock_sync):
    mock_kraken.get_balances.return_value = {"ETH": Decimal("1.0")}
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}
    mock_sync.get_all_lots.return_value = [_lot("ETH", 1.0, 3000.0, 30, "t1")]

    from backend.services.portfolio_service import build_summary

    summary = build_summary()

    mock_kraken.get_balances.assert_called_once()
    mock_kraken.get_ticker_prices.assert_called_once_with(["ETH"])
    mock_sync.get_all_lots.assert_called_once()
    assert summary.total_value_aud == 4000.00
    assert len(summary.positions) == 1
    assert summary.positions[0].asset == "ETH"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_build_summary.py -v`

Expected: FAIL — `build_summary` does not exist yet, `kraken_service` / `sync_service` not imported in `portfolio_service`.

- [ ] **Step 3: Implement `build_summary()`**

Add imports and function to `backend/services/portfolio_service.py`. Add these imports at the top of the file, after the existing imports:

```python
from backend.services import kraken_service
from backend.services import sync_service
```

Add this function after the existing `calculate_summary` function (before `get_dca_history`):

```python
def build_summary() -> PortfolioSummary:
    """Orchestrate balances, prices, lots into a full portfolio summary.

    Single entry point used by the FastAPI router, scheduler, and MCP server.
    """
    balances = kraken_service.get_balances()
    prices = kraken_service.get_ticker_prices(list(balances.keys()))
    lots = sync_service.get_all_lots()
    return calculate_summary(balances, prices, lots)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_build_summary.py -v`

Expected: PASS

- [ ] **Step 5: Update `routers/portfolio.py` to use `build_summary()`**

Replace the entire contents of `backend/routers/portfolio.py` with:

```python
from fastapi import APIRouter, HTTPException
from backend.models.portfolio import PortfolioSummary
from backend.services import portfolio_service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary() -> PortfolioSummary:
    try:
        return portfolio_service.build_summary()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
```

- [ ] **Step 6: Update `scheduler.py` to use `build_summary()`**

Replace the entire contents of `backend/scheduler.py` with:

```python
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services import portfolio_service, snapshot_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _do_snapshot() -> None:
    """Synchronous snapshot composition. Kept separate from the scheduled
    coroutine so it can be offloaded to a worker thread."""
    summary = portfolio_service.build_summary()
    snapshot_service.save_snapshot(summary)


async def _hourly_snapshot() -> None:
    """Hourly snapshot job.

    The work itself is synchronous (kraken-sdk and supabase-py are blocking
    I/O). AsyncIOScheduler runs async jobs directly on the FastAPI event
    loop, so we offload to a worker thread via asyncio.to_thread to avoid
    stalling request handling for the ~5-10s a snapshot takes.
    """
    try:
        await asyncio.to_thread(_do_snapshot)
    except Exception:
        # Log but don't crash the scheduler
        logger.exception("Hourly snapshot failed")


def start_scheduler() -> None:
    scheduler.add_job(_hourly_snapshot, "interval", hours=1, id="hourly_snapshot")
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown()
```

- [ ] **Step 7: Run existing tests to verify no regressions**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_portfolio_service.py backend/tests/test_build_summary.py -v`

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/services/portfolio_service.py backend/routers/portfolio.py backend/scheduler.py backend/tests/test_build_summary.py
git commit -m "refactor: extract build_summary() helper, deduplicate orchestration"
```

---

### Task 2: Fix `upsert_lots` insert-only-if-new

**Files:**
- Modify: `backend/services/sync_service.py`
- Create: `backend/tests/test_upsert_lots.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_upsert_lots.py`:

```python
from unittest.mock import patch, MagicMock


def _make_trade(trade_id: str, asset: str = "ETH") -> dict:
    return {
        "trade_id": trade_id,
        "asset": asset,
        "time": 1700000000.0,
        "price": "3000.00",
        "vol": "0.5",
        "cost": "1500.00",
    }


@patch("backend.services.sync_service.get_supabase")
def test_upsert_lots_skips_existing_trades(mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Simulate t1 already existing in the database
    mock_select = MagicMock()
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"kraken_trade_id": "t1"}]
    )

    # Mock insert chain
    mock_insert = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

    from backend.services.sync_service import upsert_lots

    trades = [_make_trade("t1"), _make_trade("t2")]
    result = upsert_lots(trades)

    # Should return the first trade_id (most recent)
    assert result == "t1"

    # Should only insert t2 (t1 already exists)
    insert_call = mock_db.table.return_value.insert
    insert_call.assert_called_once()
    inserted_rows = insert_call.call_args[0][0]
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["kraken_trade_id"] == "t2"


@patch("backend.services.sync_service.get_supabase")
def test_upsert_lots_all_existing_skips_insert(mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Both trades already exist
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"kraken_trade_id": "t1"}, {"kraken_trade_id": "t2"}]
    )

    from backend.services.sync_service import upsert_lots

    trades = [_make_trade("t1"), _make_trade("t2")]
    result = upsert_lots(trades)

    assert result == "t1"
    # insert should NOT be called — all trades already exist
    mock_db.table.return_value.insert.assert_not_called()


@patch("backend.services.sync_service.get_supabase")
def test_upsert_lots_empty_trades(mock_get_db):
    from backend.services.sync_service import upsert_lots

    result = upsert_lots([])
    assert result is None
    mock_get_db.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_upsert_lots.py -v`

Expected: FAIL — current implementation uses `upsert` not `insert`, no `select` call for existing trade IDs.

- [ ] **Step 3: Implement insert-only-if-new**

Replace the `upsert_lots` function in `backend/services/sync_service.py` with:

```python
def upsert_lots(trades: list[dict]) -> str | None:
    """
    Converts raw trade dicts (from kraken_service.get_trade_history) into lot rows
    and inserts only trades not already in the database.

    Checks existing kraken_trade_id values first to avoid overwriting
    remaining_quantity on lots that may have been partially disposed.

    Returns the trade_id of the first trade in the input (most recent),
    or None if trades is empty.
    """
    if not trades:
        return None

    db = get_supabase()

    # Find which trades already exist
    trade_ids = [t["trade_id"] for t in trades]
    existing = db.table("lots").select("kraken_trade_id").in_("kraken_trade_id", trade_ids).execute()
    existing_ids = {row["kraken_trade_id"] for row in existing.data}

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
        db.table("lots").insert(rows).execute()

    return trades[0]["trade_id"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_upsert_lots.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/sync_service.py backend/tests/test_upsert_lots.py
git commit -m "fix: upsert_lots uses insert-only-if-new to preserve remaining_quantity"
```

---

### Task 3: Add `mcp` SDK dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Install the `mcp` package**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/pip install mcp`

- [ ] **Step 2: Check installed version**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/pip show mcp`

Note the version number from the output (e.g. `1.x.y`).

- [ ] **Step 3: Add to `requirements.txt`**

Add the installed version to `backend/requirements.txt` (append after the last line):

```
mcp==<version from step 2>
```

- [ ] **Step 4: Verify import works**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -c "from mcp.server.fastmcp import FastMCP; print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add mcp SDK dependency"
```

---

### Task 4: MCP server skeleton + `get_portfolio_summary` tool

**Files:**
- Create: `backend/mcp_server.py`
- Create: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_mcp_server.py`:

```python
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.models.portfolio import PortfolioSummary, AssetPosition
from backend.models.trade import Lot

AEST = ZoneInfo("Australia/Sydney")


def _sample_summary() -> PortfolioSummary:
    return PortfolioSummary(
        total_value_aud=4000.00,
        positions=[
            AssetPosition(
                asset="ETH",
                quantity=1.0,
                price_aud=4000.00,
                value_aud=4000.00,
                cost_basis_aud=3000.00,
                unrealised_pnl_aud=1000.00,
                allocation_pct=100.0,
            )
        ],
        captured_at="2026-04-17T10:00:00+10:00",
        next_dca_date="2026-04-24",
    )


@pytest.mark.asyncio
@patch("backend.mcp_server.portfolio_service")
async def test_get_portfolio_summary_tool(mock_portfolio):
    mock_portfolio.build_summary.return_value = _sample_summary()

    from backend.mcp_server import get_portfolio_summary

    result = await get_portfolio_summary()
    data = json.loads(result)

    mock_portfolio.build_summary.assert_called_once()
    assert data["total_value_aud"] == 4000.00
    assert len(data["positions"]) == 1
    assert data["positions"][0]["asset"] == "ETH"
    assert data["captured_at"] == "2026-04-17T10:00:00+10:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py::test_get_portfolio_summary_tool -v`

Expected: FAIL — `backend.mcp_server` does not exist.

- [ ] **Step 3: Create MCP server with `get_portfolio_summary` tool**

Create `backend/mcp_server.py`:

```python
import asyncio
import json

from mcp.server.fastmcp import FastMCP

from backend.services import portfolio_service

mcp = FastMCP("kraken-portfolio")


@mcp.tool()
async def get_portfolio_summary() -> str:
    """Get current portfolio value, per-asset breakdown with quantities, AUD prices, values, cost basis, unrealised P&L, and allocation percentages."""
    summary = await asyncio.to_thread(portfolio_service.build_summary)
    return json.dumps(summary.model_dump(), default=str)


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py::test_get_portfolio_summary_tool -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): server skeleton with get_portfolio_summary tool"
```

---

### Task 5: `get_balances` and `get_prices` tools

**Files:**
- Modify: `backend/mcp_server.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_mcp_server.py`:

```python
@pytest.mark.asyncio
@patch("backend.mcp_server.kraken_service")
async def test_get_balances_tool(mock_kraken):
    mock_kraken.get_balances.return_value = {
        "ETH": Decimal("0.9445"),
        "SOL": Decimal("9.03"),
    }

    from backend.mcp_server import get_balances

    result = await get_balances()
    data = json.loads(result)

    mock_kraken.get_balances.assert_called_once()
    assert data["ETH"] == "0.9445"
    assert data["SOL"] == "9.03"


@pytest.mark.asyncio
@patch("backend.mcp_server.kraken_service")
async def test_get_prices_tool_default_assets(mock_kraken):
    mock_kraken.get_ticker_prices.return_value = {
        "ETH": Decimal("4000.00"),
        "SOL": Decimal("220.50"),
        "ADA": Decimal("0.85"),
    }

    from backend.mcp_server import get_prices

    result = await get_prices()
    data = json.loads(result)

    mock_kraken.get_ticker_prices.assert_called_once_with(["ETH", "SOL", "ADA"])
    assert data["ETH"] == "4000.00"


@pytest.mark.asyncio
@patch("backend.mcp_server.kraken_service")
async def test_get_prices_tool_specific_assets(mock_kraken):
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}

    from backend.mcp_server import get_prices

    result = await get_prices(assets=["ETH"])
    data = json.loads(result)

    mock_kraken.get_ticker_prices.assert_called_once_with(["ETH"])
    assert data["ETH"] == "4000.00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py::test_get_balances_tool backend/tests/test_mcp_server.py::test_get_prices_tool_default_assets backend/tests/test_mcp_server.py::test_get_prices_tool_specific_assets -v`

Expected: FAIL — `get_balances` and `get_prices` not defined.

- [ ] **Step 3: Implement both tools**

Add to `backend/mcp_server.py`, after the existing import block, add:

```python
from backend.services import kraken_service
from backend.services.kraken_service import ASSET_MAP
```

Add after the `get_portfolio_summary` tool:

```python
@mcp.tool()
async def get_balances() -> str:
    """Get current crypto quantities held on Kraken, including staked and bonded positions."""
    balances = await asyncio.to_thread(kraken_service.get_balances)
    return json.dumps({k: str(v) for k, v in balances.items()})


@mcp.tool()
async def get_prices(assets: list[str] | None = None) -> str:
    """Get live AUD prices for tracked crypto assets from Kraken.

    Args:
        assets: Asset names to query (e.g. ["ETH", "SOL"]). Defaults to all tracked assets.
    """
    if assets is None:
        assets = list(ASSET_MAP.keys())
    prices = await asyncio.to_thread(kraken_service.get_ticker_prices, assets)
    return json.dumps({k: str(v) for k, v in prices.items()})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add get_balances and get_prices tools"
```

---

### Task 6: `get_dca_history` and `get_snapshots` tools

**Files:**
- Modify: `backend/mcp_server.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_mcp_server.py`:

```python
from backend.models.trade import DCAEntry
from backend.models.snapshot import PortfolioSnapshot, SnapshotAsset


def _sample_lot(trade_id: str = "t1") -> Lot:
    acquired_at = (datetime.now(tz=AEST) - timedelta(days=30)).isoformat()
    return Lot(
        id="test-id",
        asset="ETH",
        acquired_at=acquired_at,
        quantity=1.0,
        cost_aud=3000.00,
        cost_per_unit_aud=3000.00,
        kraken_trade_id=trade_id,
        remaining_quantity=1.0,
    )


@pytest.mark.asyncio
@patch("backend.mcp_server.sync_service")
@patch("backend.mcp_server.kraken_service")
@patch("backend.mcp_server.portfolio_service")
async def test_get_dca_history_tool(mock_portfolio, mock_kraken, mock_sync):
    mock_sync.get_all_lots.return_value = [_sample_lot()]
    mock_kraken.get_balances.return_value = {"ETH": Decimal("1.0")}
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}
    mock_portfolio.get_dca_history.return_value = [
        DCAEntry(
            lot_id="test-id",
            asset="ETH",
            acquired_at="2026-03-18T10:00:00+11:00",
            quantity=1.0,
            cost_aud=3000.00,
            cost_per_unit_aud=3000.00,
            current_price_aud=4000.00,
            current_value_aud=4000.00,
            unrealised_pnl_aud=1000.00,
        )
    ]

    from backend.mcp_server import get_dca_history

    result = await get_dca_history()
    data = json.loads(result)

    assert len(data) == 1
    assert data[0]["asset"] == "ETH"
    assert data[0]["unrealised_pnl_aud"] == 1000.00


@pytest.mark.asyncio
@patch("backend.mcp_server.snapshot_service")
async def test_get_snapshots_tool_default_range(mock_snapshot):
    mock_snapshot.get_snapshots.return_value = [
        PortfolioSnapshot(
            id="snap-1",
            captured_at="2026-04-16T10:00:00+10:00",
            total_value_aud=4000.00,
            assets={"ETH": SnapshotAsset(quantity=1.0, value_aud=4000.00, price_aud=4000.00)},
        )
    ]

    from backend.mcp_server import get_snapshots

    result = await get_snapshots()
    data = json.loads(result)

    assert len(data) == 1
    assert data[0]["total_value_aud"] == 4000.00
    # Verify from_dt was passed (7 days back)
    call_args = mock_snapshot.get_snapshots.call_args
    assert call_args[1]["from_dt"] is not None
    assert call_args[1]["to_dt"] is None


@pytest.mark.asyncio
@patch("backend.mcp_server.snapshot_service")
async def test_get_snapshots_tool_all_range(mock_snapshot):
    mock_snapshot.get_snapshots.return_value = []

    from backend.mcp_server import get_snapshots

    result = await get_snapshots(time_range="all")
    data = json.loads(result)

    assert data == []
    call_args = mock_snapshot.get_snapshots.call_args
    assert call_args[1]["from_dt"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py::test_get_dca_history_tool backend/tests/test_mcp_server.py::test_get_snapshots_tool_default_range backend/tests/test_mcp_server.py::test_get_snapshots_tool_all_range -v`

Expected: FAIL — `get_dca_history` and `get_snapshots` not defined.

- [ ] **Step 3: Implement both tools**

Add to `backend/mcp_server.py` imports:

```python
from datetime import timedelta

from backend.services import snapshot_service, sync_service
from backend.utils.timezone import now_aest, to_iso
```

Add after the `get_prices` tool:

```python
@mcp.tool()
async def get_dca_history() -> str:
    """Get dollar-cost averaging history showing every individual purchase lot with acquisition date, quantity, cost paid, current value, and unrealised P&L."""
    def _get():
        lots = sync_service.get_all_lots()
        balances = kraken_service.get_balances()
        prices = kraken_service.get_ticker_prices(list(balances.keys()))
        return portfolio_service.get_dca_history(lots, prices)

    entries = await asyncio.to_thread(_get)
    return json.dumps([e.model_dump() for e in entries], default=str)


@mcp.tool()
async def get_snapshots(time_range: str = "7d") -> str:
    """Get historical portfolio value snapshots for charting trends over time.

    Args:
        time_range: Time range — "7d", "30d", or "all". Defaults to "7d".
    """
    from_dt = None
    if time_range != "all":
        days = 7 if time_range == "7d" else 30
        from_dt = to_iso(now_aest() - timedelta(days=days))

    snapshots = await asyncio.to_thread(
        snapshot_service.get_snapshots, from_dt=from_dt, to_dt=None
    )
    return json.dumps([s.model_dump() for s in snapshots], default=str)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add get_dca_history and get_snapshots tools"
```

---

### Task 7: `sync_trades` tool

**Files:**
- Modify: `backend/mcp_server.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_mcp_server.py`:

```python
@pytest.mark.asyncio
@patch("backend.mcp_server.sync_service")
@patch("backend.mcp_server.kraken_service")
async def test_sync_trades_tool(mock_kraken, mock_sync):
    mock_sync.get_last_synced_trade_id.return_value = "old-t1"
    mock_kraken.get_trade_history.return_value = [
        {"trade_id": "t2", "asset": "ETH", "time": 1700000000.0, "price": "3000", "vol": "0.5", "cost": "1500"},
    ]
    mock_sync.upsert_lots.return_value = "t2"

    from backend.mcp_server import sync_trades

    result = await sync_trades()
    data = json.loads(result)

    assert data["status"] == "success"
    assert data["new_trades_count"] == 1
    assert data["last_trade_id"] == "t2"
    mock_sync.record_sync.assert_called_once_with(last_trade_id="t2", status="success")


@pytest.mark.asyncio
@patch("backend.mcp_server.sync_service")
@patch("backend.mcp_server.kraken_service")
async def test_sync_trades_tool_error(mock_kraken, mock_sync):
    mock_sync.get_last_synced_trade_id.return_value = None
    mock_kraken.get_trade_history.side_effect = Exception("Kraken API down")

    from backend.mcp_server import sync_trades

    result = await sync_trades()
    data = json.loads(result)

    assert data["status"] == "error"
    assert "Kraken API down" in data["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py::test_sync_trades_tool backend/tests/test_mcp_server.py::test_sync_trades_tool_error -v`

Expected: FAIL — `sync_trades` not defined.

- [ ] **Step 3: Implement `sync_trades` tool**

Add after the `get_snapshots` tool in `backend/mcp_server.py`:

```python
@mcp.tool()
async def sync_trades() -> str:
    """Pull latest trades from Kraken and sync to the database. Returns the number of new trades imported."""
    def _sync():
        last_trade_id = sync_service.get_last_synced_trade_id()
        trades = kraken_service.get_trade_history(since_trade_id=last_trade_id)
        new_last_id = sync_service.upsert_lots(trades)
        sync_service.record_sync(
            last_trade_id=new_last_id or last_trade_id, status="success"
        )
        return {
            "new_trades_count": len(trades),
            "last_trade_id": new_last_id,
            "status": "success",
        }

    try:
        result = await asyncio.to_thread(_sync)
        return json.dumps(result)
    except Exception as e:
        try:
            sync_service.record_sync(
                last_trade_id=None, status="error", error_message=str(e)
            )
        except Exception:
            pass
        return json.dumps({"status": "error", "error": str(e)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add sync_trades tool"
```

---

### Task 8: MCP resources

**Files:**
- Modify: `backend/mcp_server.py`
- Modify: `backend/tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_mcp_server.py`:

```python
@pytest.mark.asyncio
@patch("backend.mcp_server.portfolio_service")
async def test_portfolio_summary_resource(mock_portfolio):
    mock_portfolio.build_summary.return_value = _sample_summary()

    from backend.mcp_server import portfolio_summary_resource

    result = await portfolio_summary_resource()
    data = json.loads(result)

    assert data["total_value_aud"] == 4000.00
    assert len(data["positions"]) == 1


@pytest.mark.asyncio
@patch("backend.mcp_server.snapshot_service")
async def test_snapshots_7d_resource(mock_snapshot):
    mock_snapshot.get_snapshots.return_value = [
        PortfolioSnapshot(
            id="snap-1",
            captured_at="2026-04-16T10:00:00+10:00",
            total_value_aud=4000.00,
            assets={"ETH": SnapshotAsset(quantity=1.0, value_aud=4000.00, price_aud=4000.00)},
        )
    ]

    from backend.mcp_server import snapshots_7d_resource

    result = await snapshots_7d_resource()
    data = json.loads(result)

    assert len(data) == 1
    assert data[0]["total_value_aud"] == 4000.00
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py::test_portfolio_summary_resource backend/tests/test_mcp_server.py::test_snapshots_7d_resource -v`

Expected: FAIL — resource functions not defined.

- [ ] **Step 3: Implement resources**

Add after all tool definitions in `backend/mcp_server.py`:

```python
@mcp.resource("portfolio://summary")
async def portfolio_summary_resource() -> str:
    """Current portfolio summary — total value, positions, P&L, allocations."""
    summary = await asyncio.to_thread(portfolio_service.build_summary)
    return json.dumps(summary.model_dump(), default=str)


@mcp.resource("portfolio://snapshots/7d")
async def snapshots_7d_resource() -> str:
    """Portfolio value snapshots from the last 7 days."""
    from_dt = to_iso(now_aest() - timedelta(days=7))
    snapshots = await asyncio.to_thread(
        snapshot_service.get_snapshots, from_dt=from_dt, to_dt=None
    )
    return json.dumps([s.model_dump() for s in snapshots], default=str)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_server.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server.py backend/tests/test_mcp_server.py
git commit -m "feat(mcp): add portfolio summary and snapshots resources"
```

---

### Task 9: Integration smoke test

**Files:**
- Create: `backend/tests/test_mcp_integration.py`

- [ ] **Step 1: Write the integration test**

Create `backend/tests/test_mcp_integration.py`:

```python
import subprocess
import json
import pytest


def _send_jsonrpc(process, method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """Send a JSON-RPC request to the MCP server and read the response."""
    request = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params is not None:
        request["params"] = params

    msg = json.dumps(request)
    # MCP uses Content-Length header framing
    frame = f"Content-Length: {len(msg)}\r\n\r\n{msg}"
    process.stdin.write(frame)
    process.stdin.flush()

    # Read response header
    header = ""
    while True:
        line = process.stdout.readline()
        if line.strip() == "":
            break
        header += line
    content_length = int(header.split("Content-Length:")[1].strip())
    body = process.stdout.read(content_length)
    return json.loads(body)


@pytest.fixture
def mcp_process():
    """Start the MCP server as a subprocess."""
    proc = subprocess.Popen(
        ["backend/.venv/bin/python", "-m", "backend.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd="/Users/benclark/Desktop/kraken-portfolio-tracker",
    )
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


def test_mcp_server_lists_tools(mcp_process):
    # Initialize the session first
    init_response = _send_jsonrpc(mcp_process, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0.0"},
    })
    assert "result" in init_response

    # Send initialized notification (no id = notification)
    notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    frame = f"Content-Length: {len(notif)}\r\n\r\n{notif}"
    mcp_process.stdin.write(frame)
    mcp_process.stdin.flush()

    # List tools
    tools_response = _send_jsonrpc(mcp_process, "tools/list", {}, req_id=2)
    tools = tools_response["result"]["tools"]
    tool_names = {t["name"] for t in tools}

    assert tool_names == {
        "get_portfolio_summary",
        "get_balances",
        "get_prices",
        "get_dca_history",
        "get_snapshots",
        "sync_trades",
    }


def test_mcp_server_lists_resources(mcp_process):
    # Initialize
    _send_jsonrpc(mcp_process, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0.0"},
    })
    notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    frame = f"Content-Length: {len(notif)}\r\n\r\n{notif}"
    mcp_process.stdin.write(frame)
    mcp_process.stdin.flush()

    # List resources
    resources_response = _send_jsonrpc(mcp_process, "resources/list", {}, req_id=2)
    resources = resources_response["result"]["resources"]
    resource_uris = {r["uri"] for r in resources}

    assert resource_uris == {
        "portfolio://summary",
        "portfolio://snapshots/7d",
    }
```

- [ ] **Step 2: Run the integration test**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_mcp_integration.py -v`

Expected: PASS — server boots, lists all 6 tools and 2 resources.

Note: If the test hangs or times out, the JSON-RPC framing may need adjustment based on the actual `mcp` SDK version. Debug by running the server manually and sending requests:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | backend/.venv/bin/python -m backend.mcp_server
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_mcp_integration.py
git commit -m "test(mcp): integration smoke test — tool and resource listing"
```

---

### Task 10: Claude Code configuration + end-to-end verification

**Files:**
- Create: `.claude/settings.json`

- [ ] **Step 1: Create Claude Code MCP configuration**

Create `.claude/settings.json`:

```json
{
  "mcpServers": {
    "kraken-portfolio": {
      "command": "/Users/benclark/Desktop/kraken-portfolio-tracker/backend/.venv/bin/python",
      "args": ["-m", "backend.mcp_server"],
      "cwd": "/Users/benclark/Desktop/kraken-portfolio-tracker"
    }
  }
}
```

Note: Uses the full venv Python path so the MCP server uses the correct virtualenv with all dependencies installed.

- [ ] **Step 2: Run all tests**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/ -v`

Expected: All PASS

- [ ] **Step 3: Manual end-to-end verification**

Restart Claude Code (or start a new session) so it picks up the MCP config. Then test by asking Claude: "What tools do you have from kraken-portfolio?"

Claude should list the six tools. Then try: "What is my portfolio worth?" — Claude should call `get_portfolio_summary` and return live data.

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "feat(mcp): Claude Code MCP server configuration"
```
