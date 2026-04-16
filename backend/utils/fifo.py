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
