"""Push-notification fan-out from the trading-decision write path."""
from backend.services.notifications.service import maybe_notify

__all__ = ["maybe_notify"]
