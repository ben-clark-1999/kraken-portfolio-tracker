from datetime import datetime, timedelta, timezone

from backend.services.trading.trigger_state import TriggerState, TriggerConfig


def _cfg(debounce=5, cooldown=900, rate_cap=10):
    return TriggerConfig(debounce_seconds=debounce,
                         cooldown_seconds=cooldown,
                         max_calls_per_hour=rate_cap)


def test_first_event_fires():
    state = TriggerState()
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert state.should_fire(event_ts=now, config=_cfg())
    state.record_invocation(now)


def test_second_event_within_debounce_does_not_fire():
    state = TriggerState()
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert state.should_fire(event_ts=t0, config=_cfg())
    state.record_invocation(t0)
    t1 = t0 + timedelta(seconds=3)  # within debounce window of 5s
    assert not state.should_fire(event_ts=t1, config=_cfg())


def test_event_after_debounce_but_within_cooldown_does_not_fire():
    state = TriggerState()
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    state.record_invocation(t0)
    t1 = t0 + timedelta(seconds=10)  # past debounce, still within cooldown of 900s
    assert not state.should_fire(event_ts=t1, config=_cfg())


def test_event_after_cooldown_fires():
    state = TriggerState()
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    state.record_invocation(t0)
    t1 = t0 + timedelta(seconds=901)
    assert state.should_fire(event_ts=t1, config=_cfg())


def test_rate_cap_enforced():
    state = TriggerState()
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    # 10 invocations spaced 16 minutes apart (past cooldown each time).
    for i in range(10):
        ts = base + timedelta(minutes=16 * i)
        assert state.should_fire(event_ts=ts, config=_cfg(rate_cap=10))
        state.record_invocation(ts)
    # The 11th would be cap-blocked even if past cooldown — but actually
    # 10 × 16min = 160min, all within the same hour? No — the rolling
    # 1h window is what matters. Build a tighter test:
    # Use a short cooldown so this block isolates the *rate cap* check
    # (the default 900s cooldown would dominate at t=61 and mask the rate-cap
    # behaviour we're trying to verify).
    cfg = _cfg(cooldown=60, rate_cap=10)
    state2 = TriggerState()
    for i in range(10):
        ts = base + timedelta(minutes=i * 6)  # 0,6,12,...,54 min
        # First always fires; subsequent ones are inside cooldown so won't
        # fire — irrelevant to the cap test. Force-record to populate window.
        state2.record_invocation(ts)
    next_ts = base + timedelta(minutes=58)
    assert not state2.should_fire(event_ts=next_ts, config=cfg)
    # Hour has rolled — should fire again.
    after_hour = base + timedelta(minutes=61)
    assert state2.should_fire(event_ts=after_hour, config=cfg)
