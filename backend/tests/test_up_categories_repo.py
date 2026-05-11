import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpCategory
from backend.repositories import up_categories_repo

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_categories").delete().neq("id", "").execute()
    yield
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_categories").delete().neq("id", "").execute()


def test_upsert_and_get_all():
    parents = [UpCategory(id="good-life", name="Good Life")]
    children = [UpCategory(id="restaurants-and-cafes", name="Restaurants & Cafes", parent_id="good-life")]
    up_categories_repo.upsert_many(parents + children, schema=SCHEMA)
    rows = up_categories_repo.get_all(schema=SCHEMA)
    assert {r.id for r in rows} == {"good-life", "restaurants-and-cafes"}


def test_upsert_is_idempotent():
    cat = UpCategory(id="good-life", name="Good Life")
    up_categories_repo.upsert_many([cat], schema=SCHEMA)
    up_categories_repo.upsert_many([cat], schema=SCHEMA)
    rows = up_categories_repo.get_all(schema=SCHEMA)
    assert len(rows) == 1
