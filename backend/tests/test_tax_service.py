from unittest.mock import MagicMock, patch

import pytest

from backend.models.tax import TaxEntryCreate, TaxEntryKind, TaxEntryUpdate


@pytest.fixture
def mock_supabase():
    """Mock the supabase client. Each table gets an isolated MagicMock so
    .select().eq().execute() chains don't interfere across tables."""
    with patch("backend.services.tax_service.get_supabase") as m:
        client = MagicMock()
        table_mocks: dict[str, MagicMock] = {}

        def _table(name: str) -> MagicMock:
            if name not in table_mocks:
                table_mocks[name] = MagicMock(name=f"table[{name}]")
            return table_mocks[name]

        client.table.side_effect = _table
        # Expose the per-table mocks via a helper so tests can configure them
        client._tables = table_mocks
        m.return_value = client
        yield client


def test_create_deductible_inserts_with_computed_fy(mock_supabase):
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Notion subscription",
        amount_aud=32.0,
        date="2026-03-15",
        type="software",
        notes=None,
        attachment_ids=[],
    )

    inserted_row = {
        "id": "abc-123",
        "description": "Notion subscription",
        "amount_aud": 32.0,
        "date_paid": "2026-03-15",
        "type": "software",
        "notes": None,
        "financial_year": "2025-26",
        "created_at": "2026-03-15T00:00:00+11:00",
        "updated_at": "2026-03-15T00:00:00+11:00",
    }
    deductibles = mock_supabase.table("tax_deductibles")
    deductibles.insert.return_value.execute.return_value.data = [inserted_row]

    result = tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, payload)

    assert result.id == "abc-123"
    assert result.financial_year == "2025-26"
    assert result.attachments == []

    insert_call = deductibles.insert.call_args[0][0]
    assert insert_call["financial_year"] == "2025-26"
    assert insert_call["date_paid"] == "2026-03-15"
    assert insert_call["type"] == "software"


def test_create_income_uses_date_received_column(mock_supabase):
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Acme Corp Mar pay",
        amount_aud=6500.0,
        date="2026-03-28",
        type="salary_wages",
        notes=None,
        attachment_ids=[],
    )
    inserted_row = {
        "id": "inc-1",
        "description": "Acme Corp Mar pay",
        "amount_aud": 6500.0,
        "date_received": "2026-03-28",
        "type": "salary_wages",
        "notes": None,
        "financial_year": "2025-26",
        "created_at": "2026-03-28T00:00:00+11:00",
        "updated_at": "2026-03-28T00:00:00+11:00",
    }
    income = mock_supabase.table("tax_income")
    income.insert.return_value.execute.return_value.data = [inserted_row]

    result = tax_service.create_entry(TaxEntryKind.INCOME, payload)

    assert result.date == "2026-03-28"

    insert_call = income.insert.call_args[0][0]
    assert "date_received" in insert_call
    assert "date_paid" not in insert_call


def test_create_rejects_invalid_type_for_kind(mock_supabase):
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Wrong type",
        amount_aud=10.0,
        date="2026-03-15",
        type="salary_wages",   # income type, not deductible
        notes=None,
        attachment_ids=[],
    )

    with pytest.raises(ValueError, match="Invalid type"):
        tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, payload)


def test_get_entries_filters_by_fy(mock_supabase):
    from backend.services import tax_service

    rows = [
        {"id": "1", "description": "A", "amount_aud": 10.0, "date_paid": "2026-03-01",
         "type": "software", "notes": None, "financial_year": "2025-26",
         "created_at": "2026-03-01T00:00:00+11:00", "updated_at": "2026-03-01T00:00:00+11:00"},
    ]
    deductibles = mock_supabase.table("tax_deductibles")
    chain = deductibles.select.return_value.eq.return_value.order.return_value
    chain.execute.return_value.data = rows

    # Attachments query path returns empty list (no attachments yet).
    attachments = mock_supabase.table("tax_attachments")
    attachments.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []

    result = tax_service.get_entries(TaxEntryKind.DEDUCTIBLE, "2025-26")

    assert len(result) == 1
    assert result[0].financial_year == "2025-26"
    deductibles.select.return_value.eq.assert_called_with("financial_year", "2025-26")


def test_get_entry_returns_single(mock_supabase):
    from backend.services import tax_service

    row = {"id": "abc", "description": "X", "amount_aud": 5.0, "date_paid": "2026-03-01",
           "type": "software", "notes": None, "financial_year": "2025-26",
           "created_at": "2026-03-01T00:00:00+11:00", "updated_at": "2026-03-01T00:00:00+11:00"}
    deductibles = mock_supabase.table("tax_deductibles")
    chain = deductibles.select.return_value.eq.return_value
    chain.execute.return_value.data = [row]

    attachments = mock_supabase.table("tax_attachments")
    attachments.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []

    result = tax_service.get_entry(TaxEntryKind.DEDUCTIBLE, "abc")

    assert result.id == "abc"


def test_get_entry_missing_raises(mock_supabase):
    from backend.services import tax_service
    from backend.services.tax_service import EntryNotFoundError

    deductibles = mock_supabase.table("tax_deductibles")
    chain = deductibles.select.return_value.eq.return_value
    chain.execute.return_value.data = []

    with pytest.raises(EntryNotFoundError):
        tax_service.get_entry(TaxEntryKind.DEDUCTIBLE, "nope")


def test_update_entry_recomputes_fy_when_date_changes(mock_supabase):
    from backend.services import tax_service

    # First the existing-row fetch returns an entry in FY 2024-25
    existing = {"id": "abc", "description": "Old", "amount_aud": 10.0, "date_paid": "2025-03-01",
                "type": "software", "notes": None, "financial_year": "2024-25",
                "created_at": "2025-03-01T00:00:00+11:00", "updated_at": "2025-03-01T00:00:00+11:00"}

    # The .update().eq().execute() returns the patched row in FY 2025-26
    patched = {**existing, "date_paid": "2025-09-01", "financial_year": "2025-26"}

    deductibles = mock_supabase.table("tax_deductibles")
    select_chain = deductibles.select.return_value.eq.return_value
    select_chain.execute.return_value.data = [existing]

    attachments = mock_supabase.table("tax_attachments")
    attachments.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []

    update_chain = deductibles.update.return_value.eq.return_value
    update_chain.execute.return_value.data = [patched]

    patch = TaxEntryUpdate(date="2025-09-01")
    result = tax_service.update_entry(TaxEntryKind.DEDUCTIBLE, "abc", patch)

    assert result.financial_year == "2025-26"
    update_call = deductibles.update.call_args[0][0]
    assert update_call["date_paid"] == "2025-09-01"
    assert update_call["financial_year"] == "2025-26"


def test_delete_entry_calls_delete(mock_supabase):
    from backend.services import tax_service

    deductibles = mock_supabase.table("tax_deductibles")
    delete_chain = deductibles.delete.return_value.eq.return_value
    delete_chain.execute.return_value.data = [{"id": "abc"}]

    tax_service.delete_entry(TaxEntryKind.DEDUCTIBLE, "abc")

    deductibles.delete.return_value.eq.assert_called_with("id", "abc")


def test_get_overview_aggregates_per_fy(mock_supabase):
    from backend.services import tax_service

    deductibles_rows = [
        {"financial_year": "2025-26", "amount_aud": 32.0},
        {"financial_year": "2025-26", "amount_aud": 28.0},
        {"financial_year": "2024-25", "amount_aud": 100.0},
    ]
    income_rows = [
        {"financial_year": "2025-26", "amount_aud": 6500.0},
        {"financial_year": "2024-25", "amount_aud": 6000.0},
    ]
    paid_rows = [
        {"financial_year": "2025-26", "amount_aud": 1840.0},
    ]

    mock_supabase.table("tax_deductibles").select.return_value.execute.return_value.data = deductibles_rows
    mock_supabase.table("tax_income").select.return_value.execute.return_value.data = income_rows
    mock_supabase.table("tax_paid").select.return_value.execute.return_value.data = paid_rows

    # Patch Kraken activity so this test stays focused on aggregation
    with patch("backend.services.tax_service.get_kraken_activity_by_fy") as kraken_mock:
        kraken_mock.return_value = {
            "2025-26": {"total_aud_invested": 0.0, "total_buys": 0, "per_asset": {}},
            "2024-25": {"total_aud_invested": 0.0, "total_buys": 0, "per_asset": {}},
        }
        result = tax_service.get_overview()

    fys = [r.financial_year for r in result]
    assert "2025-26" in fys and "2024-25" in fys
    # Sorted descending
    assert fys == sorted(fys, reverse=True)

    fy_2526 = next(r for r in result if r.financial_year == "2025-26")
    assert fy_2526.deductibles_total_aud == 60.0
    assert fy_2526.income_total_aud == 6500.0
    assert fy_2526.tax_paid_total_aud == 1840.0


def test_get_overview_returns_empty_when_no_data(mock_supabase):
    from backend.services import tax_service

    mock_supabase.table("tax_deductibles").select.return_value.execute.return_value.data = []
    mock_supabase.table("tax_income").select.return_value.execute.return_value.data = []
    mock_supabase.table("tax_paid").select.return_value.execute.return_value.data = []

    with patch("backend.services.tax_service.get_kraken_activity_by_fy") as kraken_mock:
        kraken_mock.return_value = {}
        result = tax_service.get_overview()

    assert result == []


def test_get_kraken_activity_groups_lots_by_fy(mock_supabase):
    from decimal import Decimal
    from backend.services import tax_service

    fake_lots = [
        # FY 2025-26 (Jul 2025 onward)
        MagicMock(asset="ETH", acquired_at="2026-03-15T10:00:00+11:00",
                  cost_aud=Decimal("500"), remaining_quantity=Decimal("0.1")),
        MagicMock(asset="ETH", acquired_at="2026-03-22T10:00:00+11:00",
                  cost_aud=Decimal("520"), remaining_quantity=Decimal("0.1")),
        MagicMock(asset="SOL", acquired_at="2026-03-15T10:00:00+11:00",
                  cost_aud=Decimal("200"), remaining_quantity=Decimal("1.0")),
        # FY 2024-25
        MagicMock(asset="ETH", acquired_at="2025-03-15T10:00:00+11:00",
                  cost_aud=Decimal("400"), remaining_quantity=Decimal("0.1")),
    ]

    with patch("backend.services.tax_service.sync_service.get_all_lots") as lots_mock, \
         patch("backend.services.tax_service.kraken_service.get_ticker_prices") as prices_mock:
        lots_mock.return_value = fake_lots
        prices_mock.return_value = {"ETH": Decimal("5000"), "SOL": Decimal("250")}

        result = tax_service.get_kraken_activity_by_fy()

    assert "2025-26" in result
    assert "2024-25" in result
    assert result["2025-26"]["total_aud_invested"] == 1220.0  # 500 + 520 + 200
    assert result["2025-26"]["total_buys"] == 3
    assert result["2025-26"]["per_asset"]["ETH"]["aud_spent"] == 1020.0
    assert result["2025-26"]["per_asset"]["ETH"]["buy_count"] == 2
    assert result["2025-26"]["per_asset"]["ETH"]["current_value_aud"] == 1000.0  # 0.2 * 5000


def test_get_kraken_activity_empty_when_no_lots(mock_supabase):
    from backend.services import tax_service

    with patch("backend.services.tax_service.sync_service.get_all_lots") as lots_mock, \
         patch("backend.services.tax_service.kraken_service.get_ticker_prices") as prices_mock:
        lots_mock.return_value = []
        prices_mock.return_value = {}
        result = tax_service.get_kraken_activity_by_fy()

    assert result == {}
