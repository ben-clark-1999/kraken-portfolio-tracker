"""Data access for `up_categories`."""

from backend.db.supabase_client import get_supabase
from backend.models.up import UpCategory


def upsert_many(categories: list[UpCategory], schema: str = "public") -> None:
    if not categories:
        return
    db = get_supabase()
    rows = [
        {"id": c.id, "name": c.name, "parent_id": c.parent_id}
        for c in categories
    ]
    db.schema(schema).table("up_categories").upsert(rows).execute()


def get_all(schema: str = "public") -> list[UpCategory]:
    db = get_supabase()
    result = db.schema(schema).table("up_categories").select("*").execute()
    return [UpCategory(**row) for row in result.data]
