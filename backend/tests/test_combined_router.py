from datetime import datetime, timezone

from fastapi.testclient import TestClient
from backend.db.supabase_client import get_supabase
from backend.main import app
from backend.repositories import snapshots_repo

SCHEMA = "test"
client = TestClient(app)


def _truncate():
    get_supabase().schema(SCHEMA).table("portfolio_snapshots").delete().neq(
        "id", "00000000-0000-0000-0000-000000000001"
    ).execute()


def test_combined_snapshots_pivots_sources(monkeypatch, bypass_auth):
    _truncate()
    monkeypatch.setattr("backend.routers.combined.SCHEMA", SCHEMA)

    ts = "2026-05-01T00:00:00+00:00"
    snapshots_repo.insert_source_snapshot(
        captured_at=ts, total_value_aud=10000.0, source="crypto", schema=SCHEMA,
    )
    snapshots_repo.insert_source_snapshot(
        captured_at=ts, total_value_aud=2000.0, source="up", schema=SCHEMA,
    )
    resp = client.get("/api/combined/snapshots")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["crypto"] == 10000.0
    assert body[0]["up"] == 2000.0
    assert body[0]["total"] == 12000.0


def test_combined_summary_uses_latest_each_source(monkeypatch, bypass_auth):
    _truncate()
    monkeypatch.setattr("backend.routers.combined.SCHEMA", SCHEMA)
    snapshots_repo.insert_source_snapshot(
        captured_at="2026-04-01T00:00:00+00:00", total_value_aud=8000.0, source="crypto", schema=SCHEMA,
    )
    snapshots_repo.insert_source_snapshot(
        captured_at="2026-05-01T00:00:00+00:00", total_value_aud=10000.0, source="crypto", schema=SCHEMA,
    )
    snapshots_repo.insert_source_snapshot(
        captured_at="2026-05-01T00:00:00+00:00", total_value_aud=2000.0, source="up", schema=SCHEMA,
    )
    resp = client.get("/api/combined/summary")
    body = resp.json()
    assert body == {"crypto": 10000.0, "up": 2000.0, "total": 12000.0}
