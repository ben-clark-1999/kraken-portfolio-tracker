import pytest
from supabase import create_client, Client
from backend.config import settings

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

    _clean()
    yield
    _clean()
