"""FastAPI dependency that gates protected routes on a valid auth_token cookie.

Accepts HTTPConnection (the common base of Request and WebSocket) so the same
dependency works on both REST and WebSocket routes.
"""

import jwt as pyjwt
from fastapi import HTTPException, status
from starlette.requests import HTTPConnection

from backend.auth.jwt import decode_token

COOKIE_NAME = "auth_token"


async def require_auth(conn: HTTPConnection) -> None:
    """Raise HTTPException(401) unless a valid JWT is present in the cookie."""
    token = conn.cookies.get(COOKIE_NAME)
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
