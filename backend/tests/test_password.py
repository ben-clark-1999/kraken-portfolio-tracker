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
