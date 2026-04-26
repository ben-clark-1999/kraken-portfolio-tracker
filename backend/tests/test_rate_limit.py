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
