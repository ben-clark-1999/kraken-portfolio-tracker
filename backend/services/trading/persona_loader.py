"""Loads persona prompt markdown from disk and computes a stable hash.

Spec §7.3.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PERSONAS_DIR = Path(__file__).resolve().parents[2] / "agent" / "personas"


class PersonaNotFound(Exception):
    pass


@dataclass(frozen=True)
class Persona:
    key: str
    body: str


@lru_cache(maxsize=32)
def load_persona(key: str) -> Persona:
    path = PERSONAS_DIR / f"{key}.md"
    if not path.exists():
        raise PersonaNotFound(f"No persona at {path}")
    return Persona(key=key, body=path.read_text(encoding="utf-8"))


def persona_hash(key: str) -> str:
    p = load_persona(key)
    return hashlib.sha256(p.body.encode("utf-8")).hexdigest()


def clear_cache() -> None:
    """For tests that mutate persona files on disk."""
    load_persona.cache_clear()
