"""Skeleton tests — class shape and basic round-tripping only.

Integration tests in test_trading_executor_market.py (Task 11) and
test_trading_executor_limit.py (Task 12).
"""
from inspect import signature

from backend.services.trading.executor import (
    OrderExecutor, PaperExecutor,
)


def test_protocol_has_three_methods():
    methods = {"submit_order", "cancel_order", "get_open_orders"}
    assert methods.issubset(set(dir(OrderExecutor)))


def test_paper_executor_satisfies_protocol_shape():
    # Structural check — PaperExecutor should expose the three async methods.
    pe = PaperExecutor()
    for m in ("submit_order", "cancel_order", "get_open_orders"):
        assert callable(getattr(pe, m))


def test_submit_order_signature_matches_protocol():
    proto_sig = signature(OrderExecutor.submit_order)
    impl_sig = signature(PaperExecutor.submit_order)
    proto_params = list(proto_sig.parameters)
    impl_params = list(impl_sig.parameters)
    # Drop 'self' for both.
    assert proto_params[1:] == impl_params[1:]
