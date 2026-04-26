"""bcrypt password verification."""

import bcrypt


def verify_password(plain: str, hashed: str) -> bool:
    """Check whether plain-text password matches a bcrypt hash.

    Returns False on any failure — empty inputs, malformed hash, mismatch.
    Never raises.
    """
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
