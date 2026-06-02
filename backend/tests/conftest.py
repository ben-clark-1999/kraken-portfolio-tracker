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


@pytest.fixture
def bypass_auth():
    """Override the require_auth dependency for FastAPI tests so we don't
    need a real JWT cookie. Restores the dependency on teardown."""
    from backend.auth.dependencies import require_auth
    from backend.main import app

    app.dependency_overrides[require_auth] = lambda: None
    yield
    app.dependency_overrides.pop(require_auth, None)


# ---------------------------------------------------------------------------
# Auto-tag integration tests with the `db` marker.
#
# CI runs with dummy credentials and no network access to Supabase / Up Bank,
# so any test that makes a real call must be skipped there via `-m "not db"`.
# Rather than scatter a `pytestmark` line across ~30 files, we tag them from
# this one place using pytest's post-collection hook. Two rules catch them:
#   1. Tests requesting a live-DB fixture (`clean_test_tables` / `test_db`).
#      This auto-covers the repo integration tests with no maintenance.
#   2. Tests in the modules listed below, which call repos/services that reach
#      Supabase or the Up Bank API directly — there's no fixture to key on, so
#      they're enumerated explicitly.
# ---------------------------------------------------------------------------
_DB_FIXTURES = {"clean_test_tables", "test_db"}

_INTEGRATION_MODULES = {
    "test_combined_router",
    "test_manual_cash_flow_scanner",
    "test_manual_cash_flows_repo",
    "test_manual_leaderboard",
    "test_mcp_up_tools",
    "test_notification_service",
    "test_reset_paper_experiment",
    "test_strategies_health",
    "test_strategies_leaderboard_trades",
    "test_strategies_router",
    "test_trading_benchmark_state_repo",
    "test_trading_benchmark_wiring",
    "test_trading_decision_writer",
    "test_trading_equity_snapshot",
    "test_trading_executor_limit",
    "test_trading_executor_market",
    "test_trading_llm_strategy",
    "test_trading_mcp_tools",
    "test_trading_reconcile_wiring",
    "test_trading_seed",
    "test_up_accounts_repo",
    "test_up_categories_repo",
    "test_up_recurring_service",
    "test_up_router",
    "test_up_snapshot_service",
    "test_up_sync_log_repo",
    "test_up_sync_service",
    "test_up_transactions_repo",
}


def pytest_collection_modifyitems(config, items):
    """Attach the `db` marker to every integration test after collection."""
    for item in items:
        module_name = item.module.__name__.rsplit(".", 1)[-1]
        uses_db_fixture = _DB_FIXTURES & set(getattr(item, "fixturenames", ()))
        if module_name in _INTEGRATION_MODULES or uses_db_fixture:
            item.add_marker(pytest.mark.db)
