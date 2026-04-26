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
