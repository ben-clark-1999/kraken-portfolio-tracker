"""Scanner tests. Mocked Kraken via monkeypatch; real test-schema DB."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.db.supabase_client import get_supabase
from backend.repositories import manual_cash_flows_repo
from backend.services import kraken_service, manual_cash_flow_scanner


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("manual_cash_flows").delete().neq("id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("system_alerts").delete().neq("id", _SENTINEL_UUID).execute()
    kraken_service._user = None
    kraken_service._market = None
    yield
    kraken_service._user = None
    kraken_service._market = None


def _fake_kraken_entries(entries):
    """Return a fake get_cash_flow_entries callable that ignores `since`."""
    return lambda since=None: list(entries)


def test_fresh_scan_persists_new_aud_deposits(monkeypatch):
    occurred = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(
        kraken_service, "get_cash_flow_entries",
        _fake_kraken_entries([
            {"kraken_refid": "R1", "kind": "deposit",
             "amount_aud": Decimal("500"), "asset": "AUD",
             "occurred_at": occurred},
        ]),
    )
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=1), schema=SCHEMA,
    )
    assert len(rows) == 1
    assert rows[0]["kraken_refid"] == "R1"


def test_non_aud_deposit_inserts_system_alert_and_skips(monkeypatch):
    db = get_supabase()
    monkeypatch.setattr(
        kraken_service, "get_cash_flow_entries",
        _fake_kraken_entries([
            {"kraken_refid": "U1", "kind": "deposit",
             "amount_aud": Decimal("100"), "asset": "USDT",
             "occurred_at": datetime.now(timezone.utc) - timedelta(hours=1)},
        ]),
    )
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)

    # No row in manual_cash_flows
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=1), schema=SCHEMA,
    )
    assert rows == []

    # One row in system_alerts with the expected code
    alerts = (db.schema(SCHEMA).table("system_alerts")
                .select("*").eq("code", "MANUAL_CASHFLOW_NON_AUD").execute().data)
    assert len(alerts) == 1
    assert alerts[0]["payload"]["asset"] == "USDT"


def test_debounce_skips_call_within_5_minutes(monkeypatch):
    counter = {"n": 0}
    def _counting_entries(since=None):
        counter["n"] += 1
        return []
    monkeypatch.setattr(kraken_service, "get_cash_flow_entries", _counting_entries)

    # First call — runs the scan
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)
    # Insert a row to update last_created_at to "now"
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="RJUST", kind="deposit",
        amount_aud=Decimal("1"),
        occurred_at=datetime.now(timezone.utc),
        schema=SCHEMA,
    )
    # Second call within debounce window — should skip
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)
    assert counter["n"] == 1   # only the first call hit Kraken


def test_kraken_failure_is_swallowed(monkeypatch):
    def _raising_entries(since=None):
        raise kraken_service.KrakenServiceError("simulated outage")
    monkeypatch.setattr(kraken_service, "get_cash_flow_entries", _raising_entries)

    # Should NOT raise
    manual_cash_flow_scanner.ensure_cash_flows_fresh(schema=SCHEMA)

    # And there should be no rows
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=1), schema=SCHEMA,
    )
    assert rows == []
