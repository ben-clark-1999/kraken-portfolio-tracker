import pytest

from backend.services.trading.persona_loader import (
    load_persona, persona_hash, PersonaNotFound,
)


def test_load_trend_follower():
    p = load_persona("trend-follower")
    assert "Trend-Follower" in p.body
    assert p.key == "trend-follower"


def test_persona_hash_stable_across_calls():
    a = persona_hash("trend-follower")
    b = persona_hash("trend-follower")
    assert a == b
    assert len(a) == 64   # sha256 hex


def test_persona_hash_differs_per_persona():
    a = persona_hash("trend-follower")
    b = persona_hash("mean-reverter")
    assert a != b


def test_unknown_persona_raises():
    with pytest.raises(PersonaNotFound):
        load_persona("doesnt-exist")
