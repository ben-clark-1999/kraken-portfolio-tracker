import pytest
import respx
from httpx import Response
from backend.services.up_client import UpClient


@pytest.mark.asyncio
@respx.mock
async def test_list_categories_with_parents():
    respx.get("https://api.up.com.au/api/v1/categories").mock(return_value=Response(
        200,
        json={
            "data": [
                {
                    "type": "categories",
                    "id": "good-life",
                    "attributes": {"name": "Good Life"},
                    "relationships": {"parent": {"data": None}},
                },
                {
                    "type": "categories",
                    "id": "restaurants-and-cafes",
                    "attributes": {"name": "Restaurants and Cafes"},
                    "relationships": {"parent": {"data": {"type": "categories", "id": "good-life"}}},
                },
            ],
        },
    ))
    client = UpClient("up:test:tok")
    cats = await client.list_categories()
    assert len(cats) == 2
    parent = next(c for c in cats if c.id == "good-life")
    child = next(c for c in cats if c.id == "restaurants-and-cafes")
    assert parent.parent_id is None
    assert child.parent_id == "good-life"
