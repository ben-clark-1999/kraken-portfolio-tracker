from decimal import Decimal
from datetime import datetime, timedelta, date

from backend.models.portfolio import AssetPosition, PortfolioSummary
from backend.models.trade import Lot, DCAEntry
from backend.utils.fifo import calculate_cost_basis, LotInput
from backend.utils.timezone import to_iso, now_aest
from backend.models.analytics import BalanceChange
from backend.services import kraken_service
from backend.services import snapshot_service
from backend.services import sync_service


TIMEFRAME_DAYS = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
}


def _parse_timeframe_days(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_DAYS:
        raise ValueError(
            f"Invalid timeframe: {timeframe}. Valid: {', '.join(TIMEFRAME_DAYS)} or ALL"
        )
    return TIMEFRAME_DAYS[timeframe]


def calculate_summary(
    balances: dict[str, Decimal],
    prices: dict[str, Decimal],
    lots: list[Lot],
) -> PortfolioSummary:
    total_value = sum(
        (balances.get(asset, Decimal("0")) * prices.get(asset, Decimal("0"))
         for asset in balances),
        Decimal("0"),
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

    next_dca = calculate_next_dca_date(lots)
    return PortfolioSummary(
        total_value_aud=float(total_value),
        positions=sorted(positions, key=lambda p: p.value_aud, reverse=True),
        captured_at=to_iso(now_aest()),
        next_dca_date=next_dca.isoformat() if next_dca else None,
    )


def build_summary() -> PortfolioSummary:
    """Orchestrate balances, prices, lots into a full portfolio summary.

    Single entry point used by the FastAPI router, scheduler, and MCP server.
    """
    balances = kraken_service.get_balances()
    prices = kraken_service.get_ticker_prices(list(balances.keys()))
    lots = sync_service.get_all_lots()
    return calculate_summary(balances, prices, lots)


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


def get_balance_change(timeframe: str) -> BalanceChange:
    """Compare current portfolio value against a historical snapshot.

    Accepts "1W", "1M", "3M", "6M", "1Y", or "ALL".
    """
    summary = build_summary()
    end_value = summary.total_value_aud
    end_date = summary.captured_at

    note = None

    if timeframe == "ALL":
        start_snap = snapshot_service.get_oldest_snapshot()
    else:
        days = _parse_timeframe_days(timeframe)
        target_dt = to_iso(now_aest() - timedelta(days=days))
        start_snap = snapshot_service.get_nearest_snapshot(target_dt)
        if start_snap is None:
            start_snap = snapshot_service.get_oldest_snapshot()
            if start_snap is not None:
                note = (
                    f"No snapshot found for {timeframe} lookback. "
                    f"Using oldest available from {start_snap.captured_at[:10]}."
                )

    if start_snap is None:
        return BalanceChange(
            timeframe=timeframe,
            start_value_aud=0,
            end_value_aud=end_value,
            change_aud=end_value,
            change_pct=0,
            start_date="",
            end_date=end_date,
            note="No historical snapshots available.",
        )

    start_value = start_snap.total_value_aud
    change_aud = end_value - start_value
    change_pct = (change_aud / start_value * 100) if start_value else 0

    return BalanceChange(
        timeframe=timeframe,
        start_value_aud=start_value,
        end_value_aud=round(end_value, 2),
        change_aud=round(change_aud, 2),
        change_pct=round(change_pct, 2),
        start_date=start_snap.captured_at,
        end_date=end_date,
        note=note,
    )
