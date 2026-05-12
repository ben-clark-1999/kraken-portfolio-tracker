"""Detect recurring outflow subscriptions from the UP transaction log.

Pure-Python heuristic. See docs/superpowers/specs/2026-05-12-recurring-charges-design.md
for the algorithm and thresholds.
"""

import re

# Card-network prefixes that should be stripped before grouping.
_PREFIX_RE = re.compile(r"^(sq|py|tpg|paypal)\s*\*\s*", re.IGNORECASE)
# Whitespace-bounded 3-12 digit numeric token (store ID, terminal ID).
# Replaces a trailing-only regex because UP embeds store numbers mid-string
# (e.g. "COLES 0382 BONDI" → "coles bondi").
_INTERIOR_DIGITS_RE = re.compile(r"(?:^|\s)\d{3,12}(?=\s|$)")
# Pure-digit merchant string after other strips → empty.
_ALL_DIGITS_RE = re.compile(r"^\d+$")
# Collapse whitespace.
_WS_RE = re.compile(r"\s+")


def normalise(description: str) -> str:
    """Normalise a UP merchant string to group similar transactions.

    Lowercases, strips card-network prefixes, takes the part after any
    asterisk separator, removes whitespace-bounded 3-12 digit numeric
    tokens (store/terminal IDs), and collapses whitespace.
    """
    s = description.strip().lower()
    if not s:
        return ""
    s = _PREFIX_RE.sub("", s)
    if "*" in s:
        s = s.split("*", 1)[1].strip()
    s = _INTERIOR_DIGITS_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    if _ALL_DIGITS_RE.match(s):
        return ""
    return s
