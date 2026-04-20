import json
import pytest
from decimal import Decimal
from unittest.mock import patch

from backend.models.analytics import BalanceChange, DCAAnalysis, DCAAnalysisAsset
from backend.models.portfolio import PortfolioSummary, AssetPosition
from backend.models.trade import Lot, DCAEntry
from backend.models.snapshot import PortfolioSnapshot, SnapshotAsset
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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


@pytest.mark.asyncio
@patch("backend.mcp_server.portfolio_service")
async def test_get_balance_change_tool(mock_portfolio):
    mock_portfolio.get_balance_change.return_value = BalanceChange(
        timeframe="1M",
        start_value_aud=4000.00,
        end_value_aud=5000.00,
        change_aud=1000.00,
        change_pct=25.00,
        start_date="2026-03-20T10:00:00+10:00",
        end_date="2026-04-20T10:00:00+10:00",
        note=None,
    )

    from backend.mcp_server import get_balance_change

    result = await get_balance_change(timeframe="1M")
    data = json.loads(result)

    mock_portfolio.get_balance_change.assert_called_once_with("1M")
    assert data["timeframe"] == "1M"
    assert data["change_aud"] == 1000.00
    assert data["change_pct"] == 25.00


@pytest.mark.asyncio
@patch("backend.mcp_server.portfolio_service")
async def test_get_dca_analysis_tool(mock_portfolio):
    mock_portfolio.get_dca_analysis.return_value = DCAAnalysis(
        assets=[
            DCAAnalysisAsset(
                asset="ETH",
                total_invested_aud=4500.00,
                average_cost_basis_aud=3000.00,
                lot_count=3,
                average_days_between_buys=7.0,
                last_buy_date="2026-04-13",
                next_expected_buy_date="2026-04-20",
                cadence_deviation_days=0.0,
            )
        ],
        overall={"total_invested_aud": 4500.00, "average_cadence_days": 7.0},
    )

    from backend.mcp_server import get_dca_analysis

    result = await get_dca_analysis()
    data = json.loads(result)

    mock_portfolio.get_dca_analysis.assert_called_once()
    assert len(data["assets"]) == 1
    assert data["assets"][0]["asset"] == "ETH"
    assert data["overall"]["total_invested_aud"] == 4500.00


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
