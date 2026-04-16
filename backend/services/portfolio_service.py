from decimal import Decimal
from datetime import datetime, timedelta, date

from backend.models.portfolio import AssetPosition, PortfolioSummary
from backend.models.trade import Lot, DCAEntry
from backend.utils.fifo import calculate_cost_basis, LotInput
from backend.utils.timezone import to_iso, now_aest


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
