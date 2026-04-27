"""Verify every response gets an X-Request-ID header."""
import re

from fastapi.testclient import TestClient

from backend.main import app

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def test_health_response_has_request_id_header():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert UUID_PATTERN.match(response.headers["X-Request-ID"])


def test_each_request_gets_unique_id():
    client = TestClient(app)
    r1 = client.get("/api/health")
    r2 = client.get("/api/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]
