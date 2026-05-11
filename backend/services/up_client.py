"""Async HTTP client for the UP Bank API.

Handles authentication, pagination, retries (429 with Retry-After,
5xx with exponential backoff). Generators auto-walk `next` links.
"""

import asyncio
import logging
from datetime import datetime
from typing import AsyncIterator, Literal

import httpx

from backend.models.up import UpAccount, UpCategory, UpTransaction

logger = logging.getLogger(__name__)


class UpClientError(Exception):
    """Base exception for UP client failures."""


class UpAuthError(UpClientError):
    """401 — token revoked or invalid."""


class UpRateLimitError(UpClientError):
    """429 — exceeded rate limit even after retry."""


class UpServerError(UpClientError):
    """5xx — UP API down or returning errors."""


class UpClient:
    BASE = "https://api.up.com.au/api/v1"
    BACKOFFS = (1.0, 4.0, 16.0)

    def __init__(self, token: str, *, timeout: float = 30.0):
        self._headers = {"Authorization": f"Bearer {token}"}
        self._timeout = timeout

    async def _request(self, url: str, params: dict | None = None) -> dict:
        """Single request with retry on 429/5xx."""
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            for attempt, backoff in enumerate([0.0, *self.BACKOFFS]):
                if backoff > 0:
                    await asyncio.sleep(backoff)
                resp = await http.get(url, headers=self._headers, params=params)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 401:
                    raise UpAuthError("UP API returned 401 — token invalid or revoked")
                if resp.status_code == 429:
                    if attempt == len(self.BACKOFFS):
                        raise UpRateLimitError("UP API 429 — exhausted retries")
                    retry_after = float(resp.headers.get("Retry-After", backoff or 1))
                    await asyncio.sleep(retry_after)
                    continue
                if 500 <= resp.status_code < 600:
                    if attempt == len(self.BACKOFFS):
                        raise UpServerError(f"UP API {resp.status_code} — exhausted retries")
                    continue
                raise UpClientError(f"Unexpected UP API status {resp.status_code}: {resp.text[:200]}")
            raise UpClientError("UP request loop exited unexpectedly")

    async def list_accounts(self) -> list[UpAccount]:
        url = f"{self.BASE}/accounts"
        out: list[UpAccount] = []
        while url:
            payload = await self._request(url)
            for row in payload["data"]:
                attrs = row["attributes"]
                out.append(UpAccount(
                    id=row["id"],
                    display_name=attrs["displayName"],
                    account_type=attrs["accountType"],
                    ownership_type=attrs["ownershipType"],
                    balance_value=float(attrs["balance"]["value"]),
                    balance_currency=attrs["balance"]["currencyCode"],
                    created_at=datetime.fromisoformat(attrs["createdAt"]),
                ))
            url = payload.get("links", {}).get("next")
        return out
