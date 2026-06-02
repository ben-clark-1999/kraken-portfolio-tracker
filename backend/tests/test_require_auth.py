import time

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.auth.dependencies import require_auth
from backend.auth.jwt import TOKEN_TTL_SECONDS, encode_token
from backend.config import settings


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/protected")
    async def protected(_: None = Depends(require_auth)):
        return {"ok": True}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_missing_cookie_returns_401(client):
    response = client.get("/protected")
    assert response.status_code == 401


def test_invalid_cookie_returns_401(client):
    client.cookies.set("auth_token", "garbage")
    response = client.get("/protected")
    assert response.status_code == 401


def test_valid_cookie_returns_200(client):
    client.cookies.set("auth_token", encode_token())
    response = client.get("/protected")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_expired_cookie_returns_401(client):
    long_ago = int(time.time()) - (TOKEN_TTL_SECONDS + 86_400)
    expired = pyjwt.encode(
        {"sub": "user", "iat": long_ago, "exp": long_ago + TOKEN_TTL_SECONDS},
        settings.jwt_secret,
        algorithm="HS256",
    )
    client.cookies.set("auth_token", expired)
    response = client.get("/protected")
    assert response.status_code == 401


def test_tampered_cookie_returns_401(client):
    token = encode_token()
    # Corrupt the FIRST char of the signature segment. Flipping the last
    # char of the token was flaky: base64's final char has spare bits that
    # can decode to the same signature bytes, leaving the token valid.
    head, payload, sig = token.split(".")
    sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    tampered = f"{head}.{payload}.{sig}"
    client.cookies.set("auth_token", tampered)
    response = client.get("/protected")
    assert response.status_code == 401
