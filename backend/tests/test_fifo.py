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
