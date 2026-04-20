from decimal import Decimal
from unittest.mock import patch
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
