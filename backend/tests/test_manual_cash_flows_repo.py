"""Repo tests for manual_cash_flows. Round-trips through the test schema."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.db.supabase_client import get_supabase
from backend.repositories import manual_cash_flows_repo

SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("manual_cash_flows").delete().neq("id", _SENTINEL_UUID).execute()
    yield


def test_upsert_by_refid_inserts_new_row():
    occurred = datetime.now(timezone.utc) - timedelta(days=1)
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="REF-1", kind="deposit",
        amount_aud=Decimal("500.00"), occurred_at=occurred,
        schema=SCHEMA,
    )
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=2), schema=SCHEMA,
    )
    assert len(rows) == 1
    assert rows[0]["kraken_refid"] == "REF-1"
    assert rows[0]["kind"] == "deposit"
    assert Decimal(str(rows[0]["amount_aud"])) == Decimal("500.00")


def test_upsert_by_refid_is_idempotent():
    occurred = datetime.now(timezone.utc) - timedelta(hours=1)
    for _ in range(3):
        manual_cash_flows_repo.upsert_by_refid(
            kraken_refid="REF-DUP", kind="deposit",
            amount_aud=Decimal("100.00"), occurred_at=occurred,
            schema=SCHEMA,
        )
    rows = manual_cash_flows_repo.list_since(
        since=datetime.now(timezone.utc) - timedelta(days=1), schema=SCHEMA,
    )
    assert len(rows) == 1


def test_list_since_filters_by_occurred_at():
    old = datetime.now(timezone.utc) - timedelta(days=10)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="OLD", kind="deposit",
        amount_aud=Decimal("100"), occurred_at=old, schema=SCHEMA,
    )
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="NEW", kind="deposit",
        amount_aud=Decimal("200"), occurred_at=recent, schema=SCHEMA,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    rows = manual_cash_flows_repo.list_since(since=cutoff, schema=SCHEMA)
    refids = [r["kraken_refid"] for r in rows]
    assert refids == ["NEW"]


def test_last_created_at_returns_max():
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="A", kind="deposit",
        amount_aud=Decimal("1"),
        occurred_at=datetime.now(timezone.utc) - timedelta(hours=2),
        schema=SCHEMA,
    )
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="B", kind="withdrawal",
        amount_aud=Decimal("2"),
        occurred_at=datetime.now(timezone.utc) - timedelta(hours=1),
        schema=SCHEMA,
    )
    last = manual_cash_flows_repo.last_created_at(schema=SCHEMA)
    assert last is not None
    assert (datetime.now(timezone.utc) - last).total_seconds() < 60


def test_last_created_at_returns_none_when_empty():
    assert manual_cash_flows_repo.last_created_at(schema=SCHEMA) is None


def test_latest_occurred_at_returns_max_kraken_event_time():
    earlier = datetime.now(timezone.utc) - timedelta(hours=5)
    later = datetime.now(timezone.utc) - timedelta(hours=1)
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="A", kind="deposit", amount_aud=Decimal("1"),
        occurred_at=earlier, schema=SCHEMA,
    )
    manual_cash_flows_repo.upsert_by_refid(
        kraken_refid="B", kind="deposit", amount_aud=Decimal("2"),
        occurred_at=later, schema=SCHEMA,
    )
    latest = manual_cash_flows_repo.latest_occurred_at(schema=SCHEMA)
    assert latest is not None
    # ~1 hour ago, give or take parsing precision
    assert abs((datetime.now(timezone.utc) - latest).total_seconds() - 3600) < 60
