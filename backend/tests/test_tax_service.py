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
