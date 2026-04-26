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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Try again in {locked_for} seconds.",
            headers={"Retry-After": str(locked_for)},
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
