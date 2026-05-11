import pytest
import respx
from httpx import Response
from backend.services.up_client import UpClient, UpRateLimitError, UpServerError


@pytest.mark.asyncio
@respx.mock
async def test_429_then_200_recovers(monkeypatch):
    sleeps: list[float] = []
    async def fake_sleep(s): sleeps.append(s)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    route = respx.get("https://api.up.com.au/api/v1/accounts")
    route.side_effect = [
        Response(429, headers={"Retry-After": "2"}, json={"errors": []}),
        Response(200, json={"data": [], "links": {"prev": None, "next": None}}),
    ]
    accounts = await UpClient("up:test:tok").list_accounts()
    assert accounts == []
    assert 2 in sleeps   # honoured Retry-After


@pytest.mark.asyncio
@respx.mock
async def test_persistent_429_raises(monkeypatch):
    async def fake_sleep(_): return None
    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    respx.get("https://api.up.com.au/api/v1/accounts").mock(return_value=Response(
        429, headers={"Retry-After": "1"}, json={"errors": []},
    ))
    with pytest.raises(UpRateLimitError):
        await UpClient("up:test:tok").list_accounts()


@pytest.mark.asyncio
@respx.mock
async def test_persistent_5xx_raises(monkeypatch):
    async def fake_sleep(_): return None
    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    respx.get("https://api.up.com.au/api/v1/accounts").mock(return_value=Response(503, json={"errors": []}))
    with pytest.raises(UpServerError):
        await UpClient("up:test:tok").list_accounts()
