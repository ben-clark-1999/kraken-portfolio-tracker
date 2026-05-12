import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass(bypass_auth):
    yield


def test_health_endpoint_returns_expected_shape():
    r = client.get("/api/strategies/_health")
    assert r.status_code == 200
    body = r.json()
    assert "ws_feed" in body
    assert "strategies" in body
    assert "executor" in body
    assert "db" in body
    # ws_feed should be a dict (possibly empty when no executor attached)
    assert isinstance(body["ws_feed"], dict)
    assert "last_fill_at" in body["executor"]
    assert "open_orders" in body["executor"]
    assert "write_latency_ms_p99" in body["db"]
