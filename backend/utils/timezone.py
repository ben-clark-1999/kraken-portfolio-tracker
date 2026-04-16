from datetime import datetime, timezone
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Sydney")


def now_aest() -> datetime:
    """Current time in AEST/AEDT (handles DST automatically)."""
    return datetime.now(tz=AEST)


def utc_to_aest(dt: datetime) -> datetime:
    """Convert a UTC datetime to AEST/AEDT."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(AEST)


def unix_to_aest(timestamp: float) -> datetime:
    """Convert a Unix timestamp (float) to AEST/AEDT datetime."""
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.astimezone(AEST)


def to_iso(dt: datetime) -> str:
    """Serialize a datetime to ISO 8601 string."""
    return dt.isoformat()
