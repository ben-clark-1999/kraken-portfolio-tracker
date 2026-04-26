import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import rate_limit
from backend.auth.dependencies import COOKIE_NAME
from backend.config import settings
from backend.routers.auth import router


KNOWN_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def setup_password(monkeypatch):
    """Replace the configured password hash with a known one for tests."""
    real_hash = bcrypt.hashpw(KNOWN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    monkeypatch.setattr(settings, "app_password_hash", real_hash)
    rate_limit._failures.clear()
    yield
    rate_limit._failures.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_login_with_correct_password_sets_cookie(client):
    response = client.post("/api/auth/login", json={"password": KNOWN_PASSWORD})
    assert response.status_code == 200
    assert COOKIE_NAME in response.cookies
    assert len(response.cookies[COOKIE_NAME]) > 20


def test_login_with_wrong_password_returns_401(client):
    response = client.post("/api/auth/login", json={"password": "wrong"})
    assert response.status_code == 401
    assert COOKIE_NAME not in response.cookies


def test_login_with_empty_body_returns_422(client):
    response = client.post("/api/auth/login", json={})
    assert response.status_code == 422


def test_login_with_no_body_returns_422(client):
    response = client.post("/api/auth/login")
    assert response.status_code == 422


def test_login_after_5_failures_returns_429(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"password": "wrong"})
    response = client.post("/api/auth/login", json={"password": KNOWN_PASSWORD})
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_logout_clears_cookie(client):
    # First log in
    login = client.post("/api/auth/login", json={"password": KNOWN_PASSWORD})
    assert login.status_code == 200

    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    # FastAPI/TestClient: deleted cookie shows as empty value
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()


def test_me_without_cookie_returns_401(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_valid_cookie_returns_200(client):
    login = client.post("/api/auth/login", json={"password": KNOWN_PASSWORD})
    assert login.status_code == 200
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
