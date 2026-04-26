# Login Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-user JWT-cookie auth gate in front of the existing dashboard, REST endpoints, and agent WebSocket — with a polished two-pane atmospheric login screen.

**Architecture:** Stateless server-side auth — bcrypt-hashed password and JWT signing secret in `.env`, FastAPI dependency `require_auth` on every protected route. Frontend has a top-level `<App>` that flips between `<Login>` and `<Dashboard>` based on a single `auth` state resolved on mount via `GET /api/auth/me`.

**Tech Stack:** bcrypt + PyJWT (backend), FastAPI Depends + Cookie auth, React 19 + Tailwind (frontend).

**Spec:** `docs/superpowers/specs/2026-04-26-login-component-design.md`

---

## File Structure

```
backend/
  auth/
    __init__.py              # Empty package marker
    password.py              # verify_password() — bcrypt wrapper
    jwt.py                   # encode_token / decode_token — PyJWT wrapper
    rate_limit.py            # In-memory per-IP failure counter (5-in-60s)
    dependencies.py          # require_auth FastAPI dependency
  scripts/
    __init__.py              # Empty package marker
    set_password.py          # CLI: prompts for password, prints bcrypt hash
  routers/
    auth.py                  # POST /login, POST /logout, GET /me

backend/tests/
    test_password.py
    test_jwt.py
    test_rate_limit.py
    test_require_auth.py
    test_auth_router.py

frontend/src/
  App.tsx                    # Top-level: holds auth state, renders Login or Dashboard
  api/
    client.ts                # apiFetch wrapper — global 401 → unauthenticated event
    auth.ts                  # login / logout / me
  components/
    AtmospherePane.tsx       # Right-pane visual (gradients + chart + grid)
    SignOutButton.tsx        # Top-right sign-out affordance
  pages/
    Login.tsx                # Two-pane atmospheric login screen
```

---

### Task 1: Backend dependencies and configuration

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`
- Create: `backend/auth/__init__.py`

- [ ] **Step 1: Add Python packages to requirements.txt**

Append these lines to `backend/requirements.txt` (look up latest stable versions on PyPI at implementation time and pin exact versions):

```
bcrypt==<latest>
pyjwt==<latest>
```

Latest stable as of plan-write: `bcrypt==5.0.0`, `pyjwt==2.12.1`. Re-check at implementation time.

- [ ] **Step 2: Install packages**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/pip install -r backend/requirements.txt`

- [ ] **Step 3: Add new required settings to config.py**

Replace the `Settings` class in `backend/config.py` so it reads:

```python
from pathlib import Path
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    kraken_api_key: str
    kraken_api_secret: str
    supabase_url: str
    supabase_key: str
    supabase_db_url: str = ""
    anthropic_api_key: str = ""
    app_password_hash: str
    jwt_secret: str
    kraken_live_tests: bool = False

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


settings = Settings()
```

`app_password_hash` and `jwt_secret` are required (no default). Server fails fast at startup if either is missing.

- [ ] **Step 4: Create auth package**

Create an empty `backend/auth/__init__.py`.

- [ ] **Step 5: Set temporary placeholder env vars for development**

Add to `.env` so the server can boot during development:

```
APP_PASSWORD_HASH=$2b$12$placeholder.placeholder.placeholder.placeholder.placeholder.placeholder
JWT_SECRET=dev-only-secret-replace-before-deploy-with-32-byte-random
```

The hash is intentionally invalid — Task 2 generates a real one. The JWT secret is dev-only — generate a real one with `python -c "import secrets; print(secrets.token_urlsafe(32))"` before any deploy.

- [ ] **Step 6: Verify imports**

Run: `backend/.venv/bin/python -c "import bcrypt; import jwt; from backend.config import settings; print('OK', bool(settings.jwt_secret))"`

Expected: `OK True`

- [ ] **Step 7: Verify the server still boots with the new required fields**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &`

Wait 4 seconds, then: `curl http://127.0.0.1:8000/api/health`

Expected: `{"status":"ok","agent":true}`

Then: `pkill -f "uvicorn backend.main:app"`

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/config.py backend/auth/__init__.py
git commit -m "feat(auth): add Phase 4 dependencies and config fields"
```

Don't commit `.env` — it's gitignored.

---

### Task 2: Password setup script

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/set_password.py`

- [ ] **Step 1: Create scripts package**

Create an empty `backend/scripts/__init__.py`.

- [ ] **Step 2: Create the set_password CLI**

Create `backend/scripts/set_password.py`:

```python
"""CLI to bcrypt-hash a password.

Usage:
    backend/.venv/bin/python -m backend.scripts.set_password

Prompts twice for a password, then prints an env line you paste into .env:
    APP_PASSWORD_HASH=$2b$12$...

To change the password later, run again and replace the line in .env.
"""

import getpass
import sys

import bcrypt


def main() -> None:
    pw = getpass.getpass("Password: ")
    if not pw:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)
    confirm = getpass.getpass("Confirm: ")
    if pw != confirm:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    hashed = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    print()
    print("Add this line to your .env (replacing any existing APP_PASSWORD_HASH):")
    print()
    print(f"APP_PASSWORD_HASH={hashed}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the script and update .env**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m backend.scripts.set_password`

Type your password twice. Copy the printed `APP_PASSWORD_HASH=...` line. Replace the placeholder line in `.env`.

Verify: `grep -c '^APP_PASSWORD_HASH=' .env` should print `1`.

- [ ] **Step 4: Generate a real JWT secret and update .env**

Run: `backend/.venv/bin/python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(32))"`

Replace the dev placeholder line in `.env` with the output.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/__init__.py backend/scripts/set_password.py
git commit -m "feat(auth): add password setup CLI"
```

---

### Task 3: Password verification module

**Files:**
- Create: `backend/auth/password.py`
- Create: `backend/tests/test_password.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_password.py`:

```python
import bcrypt
import pytest

from backend.auth.password import verify_password


@pytest.fixture
def known_hash() -> str:
    return bcrypt.hashpw(b"correct horse battery staple", bcrypt.gensalt()).decode("utf-8")


def test_verify_password_returns_true_for_correct(known_hash: str):
    assert verify_password("correct horse battery staple", known_hash) is True


def test_verify_password_returns_false_for_wrong(known_hash: str):
    assert verify_password("wrong password", known_hash) is False


def test_verify_password_returns_false_for_empty(known_hash: str):
    assert verify_password("", known_hash) is False


def test_verify_password_returns_false_for_malformed_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_verify_password_returns_false_for_empty_hash():
    assert verify_password("anything", "") is False
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/python -m pytest backend/tests/test_password.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: Implement password.py**

Create `backend/auth/password.py`:

```python
"""bcrypt password verification."""

import bcrypt


def verify_password(plain: str, hashed: str) -> bool:
    """Check whether plain-text password matches a bcrypt hash.

    Returns False on any failure — empty inputs, malformed hash, mismatch.
    Never raises.
    """
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_password.py -v`

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/auth/password.py backend/tests/test_password.py
git commit -m "feat(auth): add bcrypt password verification"
```

---

### Task 4: JWT encode/decode module

**Files:**
- Create: `backend/auth/jwt.py`
- Create: `backend/tests/test_jwt.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_jwt.py`:

```python
import time

import jwt as pyjwt
import pytest

from backend.auth.jwt import TOKEN_TTL_SECONDS, decode_token, encode_token


def test_encode_decode_roundtrip():
    token = encode_token()
    payload = decode_token(token)
    assert payload["sub"] == "user"
    assert "iat" in payload
    assert "exp" in payload


def test_encoded_token_expires_in_30_days():
    token = encode_token()
    payload = decode_token(token)
    expected_exp = payload["iat"] + TOKEN_TTL_SECONDS
    assert payload["exp"] == expected_exp


def test_expired_token_raises():
    # Encode a token with iat 31 days ago
    from backend.config import settings
    long_ago = int(time.time()) - (TOKEN_TTL_SECONDS + 86_400)
    expired = pyjwt.encode(
        {"sub": "user", "iat": long_ago, "exp": long_ago + TOKEN_TTL_SECONDS},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.PyJWTError):
        decode_token(expired)


def test_tampered_signature_raises():
    token = encode_token()
    # Flip the last char — invalidates the signature
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(pyjwt.PyJWTError):
        decode_token(tampered)


def test_garbage_token_raises():
    with pytest.raises(pyjwt.PyJWTError):
        decode_token("not.a.token")


def test_empty_token_raises():
    with pytest.raises(pyjwt.PyJWTError):
        decode_token("")
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_jwt.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: Implement jwt.py**

Create `backend/auth/jwt.py`:

```python
"""JWT encode / decode for the single-user auth gate."""

import time

import jwt as pyjwt

from backend.config import settings

TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
ALGORITHM = "HS256"


def encode_token() -> str:
    """Issue a signed JWT for the (only) user.

    Payload: sub="user", iat=now, exp=now + 30 days.
    """
    now = int(time.time())
    payload = {
        "sub": "user",
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises pyjwt.PyJWTError on any failure.

    Verifies signature and expiration. Caller should treat any raise as 401.
    """
    return pyjwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_jwt.py -v`

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/auth/jwt.py backend/tests/test_jwt.py
git commit -m "feat(auth): add JWT encode/decode with 30-day expiry"
```

---

### Task 5: Rate limit module

**Files:**
- Create: `backend/auth/rate_limit.py`
- Create: `backend/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_rate_limit.py`:

```python
import pytest

from backend.auth.rate_limit import (
    THRESHOLD,
    WINDOW_SECONDS,
    is_locked,
    record_failure,
    reset,
)


@pytest.fixture(autouse=True)
def clean_state():
    """Reset module state before each test."""
    from backend.auth import rate_limit
    rate_limit._failures.clear()
    yield
    rate_limit._failures.clear()


def test_fresh_ip_is_not_locked():
    assert is_locked("1.2.3.4", now=1000.0) == 0


def test_under_threshold_is_not_locked():
    for _ in range(THRESHOLD - 1):
        record_failure("1.2.3.4", now=1000.0)
    assert is_locked("1.2.3.4", now=1000.0) == 0


def test_at_threshold_is_locked():
    for _ in range(THRESHOLD):
        record_failure("1.2.3.4", now=1000.0)
    remaining = is_locked("1.2.3.4", now=1000.0)
    assert remaining == WINDOW_SECONDS


def test_lock_expires_after_window():
    for _ in range(THRESHOLD):
        record_failure("1.2.3.4", now=1000.0)
    # Window has passed
    assert is_locked("1.2.3.4", now=1000.0 + WINDOW_SECONDS + 1) == 0


def test_lock_remaining_decreases_with_time():
    for _ in range(THRESHOLD):
        record_failure("1.2.3.4", now=1000.0)
    # Halfway through the window
    half = WINDOW_SECONDS // 2
    assert is_locked("1.2.3.4", now=1000.0 + half) == WINDOW_SECONDS - half


def test_different_ips_are_independent():
    for _ in range(THRESHOLD):
        record_failure("1.2.3.4", now=1000.0)
    assert is_locked("5.6.7.8", now=1000.0) == 0


def test_reset_clears_an_ip():
    for _ in range(THRESHOLD):
        record_failure("1.2.3.4", now=1000.0)
    reset("1.2.3.4")
    assert is_locked("1.2.3.4", now=1000.0) == 0
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_rate_limit.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: Implement rate_limit.py**

Create `backend/auth/rate_limit.py`:

```python
"""In-memory per-IP login rate limit.

5 failures within 60 seconds → IP is locked for 60s from the oldest failure.
State is in-memory and resets on server restart — acceptable for a personal
single-user gate.
"""

import time

THRESHOLD = 5
WINDOW_SECONDS = 60

_failures: dict[str, list[float]] = {}


def _prune(ip: str, now: float) -> list[float]:
    """Remove timestamps outside the rolling window."""
    timestamps = _failures.get(ip, [])
    pruned = [t for t in timestamps if now - t < WINDOW_SECONDS]
    if pruned:
        _failures[ip] = pruned
    else:
        _failures.pop(ip, None)
    return pruned


def is_locked(ip: str, *, now: float | None = None) -> int:
    """Return seconds remaining if locked, 0 if free.

    `now` parameter is for test injection; production callers omit it.
    """
    if now is None:
        now = time.time()
    pruned = _prune(ip, now)
    if len(pruned) < THRESHOLD:
        return 0
    oldest = pruned[0]
    return int(WINDOW_SECONDS - (now - oldest))


def record_failure(ip: str, *, now: float | None = None) -> None:
    """Record a failed login attempt for an IP."""
    if now is None:
        now = time.time()
    _failures.setdefault(ip, []).append(now)


def reset(ip: str) -> None:
    """Clear all recorded failures for an IP (e.g., on successful login)."""
    _failures.pop(ip, None)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_rate_limit.py -v`

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/auth/rate_limit.py backend/tests/test_rate_limit.py
git commit -m "feat(auth): add in-memory per-IP login rate limit"
```

---

### Task 6: require_auth dependency

**Files:**
- Create: `backend/auth/dependencies.py`
- Create: `backend/tests/test_require_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_require_auth.py`:

```python
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
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    client.cookies.set("auth_token", tampered)
    response = client.get("/protected")
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_require_auth.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: Implement dependencies.py**

Create `backend/auth/dependencies.py`:

```python
"""FastAPI dependency that gates protected routes on a valid auth_token cookie."""

import jwt as pyjwt
from fastapi import HTTPException, Request, status

from backend.auth.jwt import decode_token

COOKIE_NAME = "auth_token"


async def require_auth(request: Request) -> None:
    """Raise HTTPException(401) unless a valid JWT is present in the cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    try:
        decode_token(token)
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_require_auth.py -v`

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/auth/dependencies.py backend/tests/test_require_auth.py
git commit -m "feat(auth): add require_auth FastAPI dependency"
```

---

### Task 7: Auth router

**Files:**
- Create: `backend/routers/auth.py`
- Create: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth_router.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_auth_router.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: Implement auth router**

Create `backend/routers/auth.py`:

```python
"""REST endpoints for the auth gate — login, logout, me."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from backend.auth import rate_limit
from backend.auth.dependencies import COOKIE_NAME, require_auth
from backend.auth.jwt import TOKEN_TTL_SECONDS, encode_token
from backend.auth.password import verify_password
from backend.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


def _client_ip(request: Request) -> str:
    """Best-effort client IP — handles X-Forwarded-For if behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_production() -> bool:
    """True when running behind HTTPS — affects Secure cookie flag."""
    return os.getenv("ENVIRONMENT", "development") == "production"


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    """Verify password, issue JWT cookie on success."""
    ip = _client_ip(request)

    locked_for = rate_limit.is_locked(ip)
    if locked_for > 0:
        response.headers["Retry-After"] = str(locked_for)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Try again in {locked_for} seconds.",
        )

    if not verify_password(payload.password, settings.app_password_hash):
        rate_limit.record_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    rate_limit.reset(ip)
    token = encode_token()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_is_production(),
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    """Clear the auth cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_is_production(),
    )
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_auth)])
async def me():
    """Return 200 if the auth cookie is valid, else 401 (via require_auth)."""
    return {"ok": True}
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_auth_router.py -v`

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/routers/auth.py backend/tests/test_auth_router.py
git commit -m "feat(auth): add login / logout / me REST endpoints with rate limiting"
```

---

### Task 8: Wire auth into FastAPI

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/routers/agent.py`

- [ ] **Step 1: Add auth router and protect existing routers in main.py**

Replace `backend/main.py` with:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.auth.dependencies import require_auth
from backend.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── MCP tools ───────────────────────────────────────────────────
    from backend.agent.tools import MCPToolManager

    tool_manager = MCPToolManager()
    try:
        tools = await tool_manager.start()
        app.state.mcp_tool_manager = tool_manager
        logger.info("[Startup] MCP tools loaded: %d", len(tools))
    except Exception:
        logger.exception("[Startup] MCP tool loading failed — agent unavailable")
        tools = []
        app.state.mcp_tool_manager = None

    # ── Checkpointer ────────────────────────────────────────────────
    from backend.agent.checkpointer import create_checkpointer

    try:
        checkpointer = create_checkpointer()
        logger.info("[Startup] Checkpointer ready")
    except Exception:
        logger.exception("[Startup] Checkpointer setup failed — agent unavailable")
        checkpointer = None

    # ── Agent graph ─────────────────────────────────────────────────
    if tools and checkpointer:
        from backend.agent.graph import build_graph

        app.state.agent_graph = build_graph(tools, checkpointer)
        logger.info("[Startup] Agent graph compiled")
    else:
        app.state.agent_graph = None
        logger.warning("[Startup] Agent graph NOT available")

    # ── Scheduler ───────────────────────────────────────────────────
    start_scheduler()

    yield

    # ── Shutdown ────────────────────────────────────────────────────
    stop_scheduler()
    if app.state.mcp_tool_manager:
        await app.state.mcp_tool_manager.stop()


app = FastAPI(title="Kraken Portfolio Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

from backend.routers import agent, auth, history, portfolio, sync

# Auth router is unprotected (login itself can't require auth)
app.include_router(auth.router)

# All other routers require a valid auth cookie
app.include_router(portfolio.router, dependencies=[Depends(require_auth)])
app.include_router(history.router, dependencies=[Depends(require_auth)])
app.include_router(sync.router, dependencies=[Depends(require_auth)])
app.include_router(agent.router, dependencies=[Depends(require_auth)])


@app.get("/api/health")
async def health() -> dict:
    """Public — used to confirm the server is up before login."""
    agent_ok = app.state.agent_graph is not None
    return {"status": "ok", "agent": agent_ok}
```

Two things to notice:
- `allow_credentials=True` added to CORS — required for cookies to flow on cross-origin requests
- `/api/health` stays unauthenticated — checked before/during login flow

- [ ] **Step 2: Add WebSocket cookie auth to agent router**

Replace `backend/routers/agent.py` with:

```python
"""REST endpoints for the agent — session message rehydration."""

import jwt as pyjwt
from fastapi import APIRouter, Query, WebSocket

from backend.agent.checkpointer import extract_messages
from backend.auth.dependencies import COOKIE_NAME
from backend.auth.jwt import decode_token

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Rehydrate conversation history from checkpoint.

    Called by the frontend on page reload or reconnect.
    """
    from backend.main import app

    graph = app.state.agent_graph
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state.values:
        return {"session_id": session_id, "messages": []}

    messages = extract_messages(state.values.get("messages", []))
    return {"session_id": session_id, "messages": messages}


@router.websocket("/chat")
async def agent_chat(ws: WebSocket, session_id: str | None = Query(default=None)):
    """WebSocket endpoint for agent chat.

    Manually verifies the auth cookie before accepting the connection,
    since FastAPI dependency-based auth doesn't apply to WebSocket routes
    in the same way.
    """
    token = ws.cookies.get(COOKIE_NAME)
    if not token:
        await ws.close(code=4401)
        return
    try:
        decode_token(token)
    except pyjwt.PyJWTError:
        await ws.close(code=4401)
        return

    from backend.agent.websocket_handler import agent_chat_endpoint
    from backend.main import app

    graph = app.state.agent_graph
    await agent_chat_endpoint(ws, graph, session_id)
```

The auth check happens before `ws.accept()` — connection is rejected at upgrade time with code `4401` (custom application code for "auth required").

- [ ] **Step 3: Verify the server boots and protected endpoints 401 without a cookie**

Run in one terminal: `cd /Users/benclark/Desktop/kraken-portfolio-tracker && backend/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &`

Wait 4 seconds, then:

```bash
echo "--- /api/health (should be 200) ---"
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/health

echo "--- /api/portfolio/summary (should be 401) ---"
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/portfolio/summary

echo "--- /api/auth/me without cookie (should be 401) ---"
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/auth/me

pkill -f "uvicorn backend.main:app"
```

Expected output:
```
--- /api/health (should be 200) ---
200
--- /api/portfolio/summary (should be 401) ---
401
--- /api/auth/me without cookie (should be 401) ---
401
```

- [ ] **Step 4: Run all backend tests to confirm nothing else broke**

Run: `backend/.venv/bin/python -m pytest backend/tests/ -v --ignore=backend/tests/test_kraken_service.py 2>&1 | tail -10`

Expected: All tests pass except the pre-existing `test_get_prices_tool_default_assets` (unrelated to Phase 4).

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/routers/agent.py
git commit -m "feat(auth): protect routers and WebSocket with require_auth"
```

---

### Task 9: Frontend apiFetch wrapper and auth API client

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`

- [ ] **Step 1: Create the apiFetch wrapper**

Create `frontend/src/api/client.ts`:

```ts
/**
 * Shared fetch wrapper. Always sends cookies, dispatches a global event on 401
 * so the App component can flip auth state regardless of which call triggered it.
 */

export const UNAUTHORIZED_EVENT = 'auth:unauthorized'

export async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  }

  return response
}
```

- [ ] **Step 2: Create the auth API client**

Create `frontend/src/api/auth.ts`:

```ts
import { apiFetch } from './client'

export class LoginError extends Error {
  constructor(message: string, public retryAfterSeconds?: number) {
    super(message)
    this.name = 'LoginError'
  }
}

export async function login(password: string): Promise<void> {
  const response = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })

  if (response.status === 200) return

  if (response.status === 401) {
    throw new LoginError('Incorrect password')
  }

  if (response.status === 429) {
    const retry = parseInt(response.headers.get('Retry-After') ?? '60', 10)
    throw new LoginError(`Too many attempts. Try again in ${retry} seconds.`, retry)
  }

  throw new LoginError("Couldn't reach server. Try again.")
}

export async function logout(): Promise<void> {
  await apiFetch('/api/auth/logout', { method: 'POST' })
}

export async function me(): Promise<boolean> {
  const response = await apiFetch('/api/auth/me')
  return response.status === 200
}
```

- [ ] **Step 3: Verify build**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && ./node_modules/.bin/tsc -b`

Expected: exit 0, no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/auth.ts
git commit -m "feat(auth): add apiFetch wrapper and auth API client"
```

---

### Task 10: AtmospherePane component and globals.css animations

**Files:**
- Create: `frontend/src/components/AtmospherePane.tsx`
- Modify: `frontend/src/globals.css`

- [ ] **Step 1: Add the new animations to globals.css**

In `frontend/src/globals.css`, find the existing `@layer utilities { ... }` block (it currently contains `.animate-pulse-subtle` and `.animate-progress`) and add two more utilities inside it:

```css
@layer utilities {
  .animate-pulse-subtle {
    animation: pulse-subtle 2s ease-in-out infinite;
  }
  .animate-progress {
    animation: progress 1.5s ease-in-out infinite;
  }
  .animate-fade-in {
    animation: fade-in 200ms ease-out;
  }
  .animate-glow-pulse {
    animation: glow-pulse 8s ease-in-out infinite;
  }
}
```

Then add the matching keyframes after the existing `@keyframes progress` block:

```css
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes glow-pulse {
  0%, 100% { opacity: 0.8; }
  50% { opacity: 1; }
}
```

The existing `prefers-reduced-motion` media query already short-circuits all animations.

- [ ] **Step 2: Create the AtmospherePane component**

Create `frontend/src/components/AtmospherePane.tsx`:

```tsx
/**
 * Right-pane visual for the login screen — six layered fills:
 * base gradient, three radial glows, chart silhouette, grid texture.
 * Hidden below 768px viewport width.
 */
export default function AtmospherePane() {
  return (
    <div
      className="hidden md:block relative overflow-hidden border-l border-surface-border"
      aria-hidden="true"
    >
      {/* Layer 1: base gradient corner-to-corner */}
      <div
        className="absolute inset-0"
        style={{ background: 'linear-gradient(135deg, #1a1823 0%, #0f0e14 100%)' }}
      />

      {/* Layer 2: central kraken glow with breathe pulse */}
      <div
        className="absolute inset-0 animate-glow-pulse"
        style={{
          background:
            'radial-gradient(circle at 60% 50%, rgba(123, 97, 255, 0.35) 0%, rgba(123, 97, 255, 0.15) 40%, transparent 80%)',
        }}
      />

      {/* Layer 3: bottom-left accent glow */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at 30% 90%, rgba(98, 72, 229, 0.4) 0%, transparent 60%)',
        }}
      />

      {/* Layer 4: top-right accent glow */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at 100% 0%, rgba(155, 133, 255, 0.25) 0%, transparent 50%)',
        }}
      />

      {/* Layer 5: chart silhouette */}
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="atmosphereChartFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#7B61FF" stopOpacity="0.45" />
            <stop offset="1" stopColor="#7B61FF" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path
          d="M0,75 C15,72 28,58 42,52 S68,38 82,22 L100,12 L100,100 L0,100 Z"
          fill="url(#atmosphereChartFill)"
        />
        <path
          d="M0,75 C15,72 28,58 42,52 S68,38 82,22 L100,12"
          stroke="#7B61FF"
          strokeWidth="0.9"
          fill="none"
          opacity="0.85"
          strokeLinecap="round"
        />
      </svg>

      {/* Layer 6: subtle grid texture */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'linear-gradient(rgba(240, 238, 245, 0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(240, 238, 245, 0.025) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      />
    </div>
  )
}
```

- [ ] **Step 3: Verify build**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && ./node_modules/.bin/tsc -b && npm run build 2>&1 | tail -5`

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AtmospherePane.tsx frontend/src/globals.css
git commit -m "feat(auth): add AtmospherePane component and login animations"
```

---

### Task 11: Login page

**Files:**
- Create: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: Create the Login page**

Create `frontend/src/pages/Login.tsx`:

```tsx
import { useState, type FormEvent } from 'react'

import { LoginError, login } from '../api/auth'
import AtmospherePane from '../components/AtmospherePane'

interface Props {
  onAuthenticated: () => void
}

export default function Login({ onAuthenticated }: Props) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [errorFlashing, setErrorFlashing] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!password || submitting) return

    setSubmitting(true)
    setError(null)
    try {
      await login(password)
      onAuthenticated()
    } catch (err) {
      const message = err instanceof LoginError ? err.message : "Couldn't reach server. Try again."
      setError(message)
      setErrorFlashing(true)
      setTimeout(() => setErrorFlashing(false), 1500)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid md:grid-cols-2 min-h-screen animate-fade-in">
      {/* Form pane */}
      <div
        className="flex items-center justify-center px-6 py-10"
        style={{ background: 'linear-gradient(135deg, #0f0e14 0%, #131220 100%)' }}
      >
        <form onSubmit={handleSubmit} className="w-full max-w-[320px] flex flex-col gap-6">
          <h1 className="text-lg font-semibold text-txt-primary tracking-tight">Sign in</h1>

          <div className="flex flex-col gap-1">
            <input
              type="password"
              autoFocus
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              placeholder="Password"
              className={`bg-surface-raised border rounded-md px-3 py-2.5 text-sm text-txt-primary placeholder:text-txt-muted focus:border-kraken focus:outline-none transition-colors ${
                errorFlashing ? 'border-loss' : 'border-surface-border'
              }`}
            />
            {error && <p className="text-xs text-loss mt-1">{error}</p>}
          </div>

          <button
            type="submit"
            disabled={!password || submitting}
            className="bg-kraken hover:bg-kraken-light active:scale-[0.98] text-txt-primary px-3 py-2.5 rounded-md text-sm font-medium transition disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {submitting ? 'Signing in…' : 'Continue'}
          </button>
        </form>
      </div>

      {/* Atmosphere pane (hidden < 768px) */}
      <AtmospherePane />
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && ./node_modules/.bin/tsc -b`

Expected: exit 0, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Login.tsx
git commit -m "feat(auth): add Login page with two-pane layout"
```

---

### Task 12: App component (auth state machine)

**Files:**
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create the App component**

Create `frontend/src/App.tsx`:

```tsx
import { useEffect, useState, useCallback } from 'react'

import { UNAUTHORIZED_EVENT } from './api/client'
import { me } from './api/auth'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'

type AuthState = 'checking' | 'authenticated' | 'unauthenticated'

export default function App() {
  const [auth, setAuth] = useState<AuthState>('checking')

  const refreshAuth = useCallback(async () => {
    try {
      const ok = await me()
      setAuth(ok ? 'authenticated' : 'unauthenticated')
    } catch {
      setAuth('unauthenticated')
    }
  }, [])

  // Initial check on mount
  useEffect(() => {
    refreshAuth()
  }, [refreshAuth])

  // Listen for global 401 events (any API call returning 401 fires this)
  useEffect(() => {
    function handleUnauthorized() {
      setAuth('unauthenticated')
    }
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
  }, [])

  if (auth === 'checking') {
    return <div className="min-h-screen bg-surface" />
  }

  if (auth === 'unauthenticated') {
    return <Login onAuthenticated={() => setAuth('authenticated')} />
  }

  return <Dashboard onSignedOut={() => setAuth('unauthenticated')} />
}
```

Note: `<Dashboard>` will receive a new `onSignedOut` prop in Task 14. The TypeScript compiler will flag this until Task 14 is complete — known intermediate breakage.

- [ ] **Step 2: Verify the type error is the expected one**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && ./node_modules/.bin/tsc -b 2>&1 | tail -5`

Expected: Error pointing to `App.tsx` line passing `onSignedOut` prop to `Dashboard`. Resolves at end of Task 14.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(auth): add App component with auth state machine"
```

(Build is intentionally broken at this commit; resolves in Task 14.)

---

### Task 13: SignOutButton component

**Files:**
- Create: `frontend/src/components/SignOutButton.tsx`

- [ ] **Step 1: Create the SignOutButton**

Create `frontend/src/components/SignOutButton.tsx`:

```tsx
import { useState } from 'react'

import { logout } from '../api/auth'

interface Props {
  onSignedOut: () => void
}

export default function SignOutButton({ onSignedOut }: Props) {
  const [loggingOut, setLoggingOut] = useState(false)

  async function handleClick() {
    setLoggingOut(true)
    try {
      await logout()
    } finally {
      onSignedOut()
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loggingOut}
      className="text-xs text-txt-muted hover:text-txt-secondary transition-colors disabled:opacity-60"
    >
      {loggingOut ? 'Signing out…' : 'Sign out'}
    </button>
  )
}
```

- [ ] **Step 2: Verify TypeScript still compiles this file in isolation**

The build will still fail because of the App.tsx → Dashboard prop mismatch from Task 12. That's expected.

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && ./node_modules/.bin/tsc -b 2>&1 | grep -E "SignOutButton|error" | head -10`

Expected: No errors mentioning `SignOutButton.tsx`. The Dashboard error from Task 12 may still appear; that's fine.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SignOutButton.tsx
git commit -m "feat(auth): add SignOutButton component"
```

---

### Task 14: Wire App into main.tsx, integrate SignOutButton, fix useAgentChat reconnect

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/hooks/useAgentChat.ts`

This task closes the loop — replaces the direct Dashboard render, adds SignOutButton to Dashboard, and prevents `useAgentChat` from reconnecting after an auth-related close.

- [ ] **Step 1: Replace `<Dashboard />` with `<App />` in main.tsx**

Replace the contents of `frontend/src/main.tsx` with:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './globals.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 2: Add `onSignedOut` prop and `<SignOutButton>` to Dashboard**

In `frontend/src/pages/Dashboard.tsx`, two surgical edits:

**Edit A — add the import:**

Find the existing import block. Add:

```tsx
import SignOutButton from '../components/SignOutButton'
```

**Edit B — add the `onSignedOut` prop to the component signature:**

Find:

```tsx
export default function Dashboard() {
```

Replace with:

```tsx
interface DashboardProps {
  onSignedOut: () => void
}

export default function Dashboard({ onSignedOut }: DashboardProps) {
```

**Edit C — render `<SignOutButton>` in the agent input pill row:**

Find the agent input pill block (added in Phase 3 Task 14):

```tsx
        <div className="px-6 pt-6">
          <div className="max-w-7xl mx-auto flex justify-end">
            <div className="border border-surface-border rounded-md px-3 py-1.5 hover:border-kraken/50 transition-colors">
              <AgentInput
                onSubmit={handleAgentSubmit}
                onFocus={() => setPanelOpen(true)}
                panelOpen={panelOpen}
              />
            </div>
          </div>
        </div>
```

Replace with:

```tsx
        <div className="px-6 pt-6">
          <div className="max-w-7xl mx-auto flex items-center justify-end gap-4">
            <div className="border border-surface-border rounded-md px-3 py-1.5 hover:border-kraken/50 transition-colors">
              <AgentInput
                onSubmit={handleAgentSubmit}
                onFocus={() => setPanelOpen(true)}
                panelOpen={panelOpen}
              />
            </div>
            <SignOutButton onSignedOut={onSignedOut} />
          </div>
        </div>
```

- [ ] **Step 3: Skip reconnect on close code 4401 in useAgentChat**

In `frontend/src/hooks/useAgentChat.ts`, find the `ws.onclose` handler:

```tsx
    ws.onclose = () => {
      setConnected(false)
      // Reconnect after 2s
      setTimeout(() => {
        const storedSid = localStorage.getItem(SESSION_KEY)
        if (storedSid) connect(storedSid)
      }, 2000)
    }
```

Replace with:

```tsx
    ws.onclose = (event) => {
      setConnected(false)
      // Skip reconnect on auth-required close (server told us we're not authenticated)
      if (event.code === 4401) return
      // Reconnect after 2s
      setTimeout(() => {
        const storedSid = localStorage.getItem(SESSION_KEY)
        if (storedSid) connect(storedSid)
      }, 2000)
    }
```

- [ ] **Step 4: Verify build is clean**

Run: `cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend && ./node_modules/.bin/tsc -b && npm run build 2>&1 | tail -5`

Expected: tsc exit 0; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main.tsx frontend/src/pages/Dashboard.tsx frontend/src/hooks/useAgentChat.ts
git commit -m "feat(auth): wire App component, add sign-out, skip WS reconnect on auth close"
```

---

### Task 15: End-to-end smoke test

**Files:** none — this is manual verification only.

This task isn't a code change. It's the manual checklist you walk through in a browser to confirm the whole feature works. Document any issues found, fix in follow-up commits.

- [ ] **Step 1: Boot the backend**

In one terminal:

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker
backend/.venv/bin/uvicorn backend.main:app --reload --port 8000
```

Look for `[Startup] Agent graph compiled` in the logs.

- [ ] **Step 2: Boot the frontend**

In a second terminal:

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker/frontend
npm run dev
```

- [ ] **Step 3: Visual check — Login screen**

Open `http://localhost:5173`.

Confirm:
- Two-pane layout. Left pane: "Sign in", password input, Continue button. Right pane: rich purple atmosphere with chart silhouette.
- The central glow on the right pane breathes (slow opacity pulse).
- The grid texture is barely visible across the right pane.
- At narrow viewport (< 768px), the right pane is hidden — form fills the full width.

- [ ] **Step 4: Wrong password → inline error**

Type a wrong password. Click Continue.

Confirm:
- Brief disabled state on the button ("Signing in…")
- "Incorrect password" appears below the input in red
- The input border briefly turns red (~1.5s) then fades back

- [ ] **Step 5: Correct password → Dashboard**

Type your real password. Click Continue.

Confirm:
- Page transitions to the Dashboard
- Portfolio data loads, agent panel works (press Cmd+K, ask a question)

- [ ] **Step 6: Reload persists session**

Reload the browser tab.

Confirm:
- Briefly blank, then Dashboard reappears (no Login screen flash)

- [ ] **Step 7: Sign out**

Click the "Sign out" button in the top-right of the dashboard header.

Confirm:
- Page transitions back to Login

- [ ] **Step 8: Rate limiting**

From the Login screen, submit 6 wrong passwords in rapid succession.

Confirm:
- The 6th attempt shows "Too many attempts. Try again in N seconds." (with a real number)

- [ ] **Step 9: Direct API access blocked**

In a separate terminal:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/portfolio/summary
```

Confirm:
- Output is `401`

- [ ] **Step 10: Server fails fast on missing env vars**

In your `.env`, comment out `JWT_SECRET=...`. Try to boot the server:

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker
backend/.venv/bin/uvicorn backend.main:app
```

Confirm:
- Server fails to start with a Pydantic `ValidationError` mentioning `jwt_secret`

Restore the line. Reboot. Confirm normal startup.

- [ ] **Step 11: Final commit (only if you found and fixed issues)**

If steps 3–10 all pass without code changes, no commit needed. If you fixed any issues, commit them with descriptive messages.

---

## Post-Implementation Verification

After all 15 tasks are complete, you should have:

1. **All backend tests pass:** `backend/.venv/bin/python -m pytest backend/tests/ -v --ignore=backend/tests/test_kraken_service.py`
2. **Frontend builds clean:** `cd frontend && npm run build`
3. **Server boots and protects routes:** all `/api/*` except `/api/auth/*` and `/api/health` return 401 without a cookie
4. **Login → Dashboard → Sign out → Login round-trip works in the browser**
5. **`.env` requires both `APP_PASSWORD_HASH` and `JWT_SECRET`** — server refuses to boot without them
