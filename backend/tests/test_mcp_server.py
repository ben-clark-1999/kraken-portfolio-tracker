import json
import pytest
from decimal import Decimal
from unittest.mock import patch

from backend.models.portfolio import PortfolioSummary, AssetPosition


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
