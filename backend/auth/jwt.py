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
