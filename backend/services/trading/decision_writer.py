"""Thin wrapper around agent_decisions_repo for the strategy loop."""
from __future__ import annotations

from backend.repositories.agent_decisions_repo import insert as _insert


def write_agent_decision(**kwargs) -> str:
    return _insert(**kwargs)
