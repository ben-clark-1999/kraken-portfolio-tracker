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
