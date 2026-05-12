from datetime import datetime, timezone

import pytest
import respx
from httpx import Response
from backend.services.up_client import UpClient


def _tx_row(tx_id: str, status: str = "SETTLED", category_id: str | None = "restaurants-and-cafes"):
    rels = {
        "account": {"data": {"type": "accounts", "id": "acct-1"}},
        "category": {"data": {"type": "categories", "id": category_id}} if category_id else {"data": None},
        "parentCategory": {"data": {"type": "categories", "id": "good-life"}} if category_id else {"data": None},
    }
    return {
        "type": "transactions", "id": tx_id,
        "attributes": {
            "status": status, "rawText": "RAW", "description": "Coffee", "message": None,
            "isCategorizable": True, "holdInfo": None, "roundUp": None, "cashback": None,
            "amount": {"currencyCode": "AUD", "value": "-5.50", "valueInBaseUnits": -550},
            "foreignAmount": None, "cardPurchaseMethod": None,
            "settledAt": None if status == "HELD" else "2026-04-01T10:00:00+10:00",
            "createdAt": "2026-04-01T09:55:00+10:00",
        },
        "relationships": rels,
    }


@pytest.mark.asyncio
@respx.mock
async def test_list_transactions_paginates_and_parses():
    respx.get("https://api.up.com.au/api/v1/transactions", params={"page[after]": "cursor1"}).mock(return_value=Response(
        200,
        json={"data": [_tx_row("t3", status="HELD", category_id=None)],
              "links": {"prev": None, "next": None}},
    ))
    respx.get("https://api.up.com.au/api/v1/transactions").mock(return_value=Response(
        200,
        json={"data": [_tx_row("t1"), _tx_row("t2")],
              "links": {"prev": None, "next": "https://api.up.com.au/api/v1/transactions?page%5Bafter%5D=cursor1"}},
    ))

    client = UpClient("up:test:tok")
    collected = [tx async for tx in client.list_transactions()]
    assert [tx.id for tx in collected] == ["t1", "t2", "t3"]
    assert collected[0].account_id == "acct-1"
    assert collected[0].amount_value == -5.50
    assert collected[0].parent_category_id == "good-life"
    assert collected[2].status == "HELD"
    assert collected[2].settled_at is None
    assert collected[2].category_id is None


@pytest.mark.asyncio
@respx.mock
async def test_list_transactions_passes_since_filter():
    route = respx.get("https://api.up.com.au/api/v1/transactions").mock(return_value=Response(
        200, json={"data": [], "links": {"prev": None, "next": None}},
    ))
    client = UpClient("up:test:tok")
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _ = [tx async for tx in client.list_transactions(since=since)]
    assert "filter[since]" in route.calls.last.request.url.params
