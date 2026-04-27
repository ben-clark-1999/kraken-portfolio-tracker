import os

import pytest
from supabase import create_client, Client
from backend.config import settings

# Propagate secrets from pydantic settings → process environment so that
# langchain_anthropic's ChatAnthropic() can resolve the API key without
# requiring callers to pass api_key= everywhere.
if settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

# UUID that will never exist — used to match all rows via neq
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="session")
def test_db() -> Client:
    return create_client(settings.supabase_url, settings.supabase_key)


@pytest.fixture
def clean_test_tables(test_db: Client):
    """Truncate test schema tables before and after the test.

    Opt-in fixture — request it explicitly from tests that hit the live
    Supabase test schema. Pure unit tests should NOT request it, so they
    remain DB-free.
    """
    def _clean():
        for table in ["lots", "portfolio_snapshots", "sync_log"]:
            test_db.schema("test").table(table).delete().neq("id", _SENTINEL_UUID).execute()
        # prices table uses asset (text) as PK
        test_db.schema("test").table("prices").delete().neq("asset", "__sentinel__").execute()
        # ohlc_cache table uses (pair, date) composite PK — no id column
        test_db.schema("test").table("ohlc_cache").delete().neq("pair", "__sentinel__").execute()

    _clean()
    yield
    _clean()
