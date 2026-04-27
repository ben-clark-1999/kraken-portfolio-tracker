"""Verify uncaught exceptions return sanitized 500 with request_id."""
from fastapi import APIRouter
from fastapi.testclient import TestClient

from backend.main import app


# Inject a route that always throws — registered at module import time.
_test_router = APIRouter()


@_test_router.get("/api/__test_throw__")
async def _always_throws():
    raise RuntimeError("internal secret detail that must not leak")


app.include_router(_test_router)


def test_uncaught_exception_returns_sanitized_500():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/__test_throw__")
    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "internal_error"
    assert body["message"] == "Something went wrong. Please try again."
    assert "request_id" in body
    # Must NOT leak exception text:
    assert "internal secret detail" not in response.text
    assert "RuntimeError" not in response.text


def test_response_request_id_matches_header():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/__test_throw__")
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
