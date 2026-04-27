"""Integration tests for tax_service against the real Supabase test schema.

Uses the clean_test_tables fixture (opt-in) to run against migrations-created
tables in test.* schema. Storage service is *not* exercised here — those
remain mock-only since the SDK contract is stable and real Storage tests
would be flaky.
"""

import pytest

from backend.models.tax import TaxEntryCreate, TaxEntryKind, TaxEntryUpdate


def _override_schema_to_test(monkeypatch):
    """Repoint tax_service.get_supabase() so .table(name) hits test.<name>.

    Wrapper class proxies the supabase client's .table() to .schema("test").from_()
    while leaving .storage untouched (Storage has no schema concept).
    """
    from supabase import create_client
    from backend.config import settings

    real_client = create_client(settings.supabase_url, settings.supabase_key)

    class _TestSchemaClient:
        def table(self, name):
            return real_client.schema("test").from_(name)

        @property
        def storage(self):
            return real_client.storage

    monkeypatch.setattr("backend.services.tax_service.get_supabase", lambda: _TestSchemaClient())


@pytest.mark.usefixtures("clean_test_tables")
def test_create_then_get_then_delete_deductible(monkeypatch, test_db):
    _override_schema_to_test(monkeypatch)
    from backend.services import tax_service

    payload = TaxEntryCreate(
        description="Notion subscription",
        amount_aud=32.50,
        date="2026-03-15",
        type="software",
        notes="March 2026",
        attachment_ids=[],
    )

    created = tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, payload)
    assert created.financial_year == "2025-26"
    assert created.amount_aud == 32.50
    assert created.description == "Notion subscription"

    fetched = tax_service.get_entry(TaxEntryKind.DEDUCTIBLE, created.id)
    assert fetched.id == created.id
    assert fetched.description == "Notion subscription"
    assert fetched.attachments == []

    tax_service.delete_entry(TaxEntryKind.DEDUCTIBLE, created.id)

    # Verify it's actually gone — get_entry should raise EntryNotFoundError
    from backend.services.tax_service import EntryNotFoundError
    with pytest.raises(EntryNotFoundError):
        tax_service.get_entry(TaxEntryKind.DEDUCTIBLE, created.id)


@pytest.mark.usefixtures("clean_test_tables")
def test_overview_aggregates_across_kinds(monkeypatch, test_db):
    _override_schema_to_test(monkeypatch)
    from backend.services import tax_service

    tax_service.create_entry(TaxEntryKind.DEDUCTIBLE, TaxEntryCreate(
        description="A", amount_aud=10.0, date="2026-03-01",
        type="software", notes=None, attachment_ids=[],
    ))
    tax_service.create_entry(TaxEntryKind.INCOME, TaxEntryCreate(
        description="B", amount_aud=6500.0, date="2026-03-01",
        type="salary_wages", notes=None, attachment_ids=[],
    ))
    tax_service.create_entry(TaxEntryKind.TAX_PAID, TaxEntryCreate(
        description="C", amount_aud=1500.0, date="2026-03-01",
        type="payg_withholding", notes=None, attachment_ids=[],
    ))

    overview = tax_service.get_overview()

    fy_2526 = next((o for o in overview if o.financial_year == "2025-26"), None)
    assert fy_2526 is not None, f"No FY 2025-26 in overview: {overview}"
    assert fy_2526.deductibles_total_aud == 10.0
    assert fy_2526.income_total_aud == 6500.0
    assert fy_2526.tax_paid_total_aud == 1500.0
