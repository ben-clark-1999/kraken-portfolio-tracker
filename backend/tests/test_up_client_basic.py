import pytest
import respx
from httpx import Response
from backend.services.up_client import UpClient, UpAuthError


@pytest.mark.asyncio
@respx.mock
async def test_list_accounts_parses_response():
    respx.get("https://api.up.com.au/api/v1/accounts").mock(return_value=Response(
        200,
        json={
            "data": [{
                "type": "accounts",
                "id": "acct-1",
                "attributes": {
                    "displayName": "Spending",
                    "accountType": "TRANSACTIONAL",
                    "ownershipType": "INDIVIDUAL",
                    "balance": {"currencyCode": "AUD", "value": "100.00", "valueInBaseUnits": 10000},
                    "createdAt": "2026-01-01T00:00:00+10:00",
                },
            }],
            "links": {"prev": None, "next": None},
        },
    ))
    client = UpClient("up:test:token")
    accounts = await client.list_accounts()
    assert len(accounts) == 1
    assert accounts[0].id == "acct-1"
    assert accounts[0].display_name == "Spending"
    assert accounts[0].balance_value == 100.00


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_auth_error():
    respx.get("https://api.up.com.au/api/v1/accounts").mock(return_value=Response(401, json={"errors": []}))
    client = UpClient("up:test:bad")
    with pytest.raises(UpAuthError):
        await client.list_accounts()
