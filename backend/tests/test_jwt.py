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
