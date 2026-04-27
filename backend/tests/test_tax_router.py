"""Router tests for /api/tax/*. Services are mocked.

Auth is bypassed via dependency_overrides (Phase 4 pattern from
test_auth_router.py).
"""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.auth.dependencies import require_auth


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_auth] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_overview_returns_summary(client):
    fake_overview_obj = MagicMock()
    fake_overview_obj.model_dump.return_value = {
        "financial_year": "2025-26",
        "income_total_aud": 6500.0,
        "tax_paid_total_aud": 1840.0,
        "deductibles_total_aud": 60.0,
        "kraken_activity": {
            "total_aud_invested": 1220.0,
            "total_buys": 3,
            "per_asset": {"ETH": {"aud_spent": 1020.0, "buy_count": 2, "current_value_aud": 1000.0}},
        },
    }
    # FastAPI uses .model_dump() during response_model serialization
    fake_overview_obj.financial_year = "2025-26"
    fake_overview_obj.income_total_aud = 6500.0
    fake_overview_obj.tax_paid_total_aud = 1840.0
    fake_overview_obj.deductibles_total_aud = 60.0

    # Easier: return a real Pydantic instance from the service mock
    from backend.models.tax import FYOverview, KrakenFYActivity, KrakenAssetActivity
    real_overview = FYOverview(
        financial_year="2025-26",
        income_total_aud=6500.0,
        tax_paid_total_aud=1840.0,
        deductibles_total_aud=60.0,
        kraken_activity=KrakenFYActivity(
            total_aud_invested=1220.0,
            total_buys=3,
            per_asset={"ETH": KrakenAssetActivity(aud_spent=1020.0, buy_count=2, current_value_aud=1000.0)},
        ),
    )

    with patch("backend.routers.tax.tax_service.get_overview") as m:
        m.return_value = [real_overview]
        response = client.get("/api/tax/overview")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["financial_year"] == "2025-26"
    assert body[0]["income_total_aud"] == 6500.0


def test_create_deductible_returns_entry(client):
    from backend.models.tax import TaxEntry
    real_entry = TaxEntry(
        id="abc", description="Notion", amount_aud=32.0, date="2026-03-15",
        type="software", notes=None, financial_year="2025-26",
        attachments=[],
        created_at="2026-03-15T00:00:00+11:00",
        updated_at="2026-03-15T00:00:00+11:00",
    )
    with patch("backend.routers.tax.tax_service.create_entry") as m:
        m.return_value = real_entry
        response = client.post("/api/tax/deductibles", json={
            "description": "Notion",
            "amount_aud": 32.0,
            "date": "2026-03-15",
            "type": "software",
            "notes": None,
            "attachment_ids": [],
        })

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "abc"
    assert body["financial_year"] == "2025-26"


def test_unknown_path_kind_returns_404(client):
    response = client.get("/api/tax/wrongthing?fy=2025-26")
    # FastAPI may surface unknown path as 404 either via the path validator
    # or the explicit _kind_or_404 helper raising HTTPException(404).
    assert response.status_code == 404


def test_update_missing_entry_returns_404(client):
    from backend.services.tax_service import EntryNotFoundError
    with patch("backend.routers.tax.tax_service.update_entry") as m:
        m.side_effect = EntryNotFoundError("not found")
        response = client.patch("/api/tax/deductibles/missing", json={"description": "x"})

    assert response.status_code == 404


def test_attachment_upload_too_large_returns_413(client):
    from backend.services.storage_service import AttachmentValidationError
    with patch("backend.routers.tax.storage_service.upload_attachment") as m:
        m.side_effect = AttachmentValidationError("file size 11000000 bytes exceeds 10485760")
        response = client.post(
            "/api/tax/attachments",
            data={"parent_kind": "deductible"},
            files={"file": ("big.pdf", b"x" * 100, "application/pdf")},
        )

    assert response.status_code == 413


def test_attachment_upload_wrong_type_returns_415(client):
    from backend.services.storage_service import AttachmentValidationError
    with patch("backend.routers.tax.storage_service.upload_attachment") as m:
        m.side_effect = AttachmentValidationError("content-type 'application/x-msdownload' not allowed")
        response = client.post(
            "/api/tax/attachments",
            data={"parent_kind": "deductible"},
            files={"file": ("evil.exe", b"x", "application/x-msdownload")},
        )

    assert response.status_code == 415


def test_signed_url_returns_url_and_expiry(client):
    from datetime import datetime, timedelta, timezone
    expires = datetime.now(timezone.utc) + timedelta(seconds=300)
    with patch("backend.routers.tax.storage_service.create_signed_url") as m:
        m.return_value = ("https://signed.example/abc", expires)
        response = client.get("/api/tax/attachments/att-1/url")

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "https://signed.example/abc"
    assert "expires_at" in body
