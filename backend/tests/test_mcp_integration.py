import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PARAMS = StdioServerParameters(
    command="backend/.venv/bin/python",
    args=["-m", "backend.mcp_server"],
    cwd="/Users/benclark/Desktop/kraken-portfolio-tracker",
)


@pytest.mark.asyncio
async def test_mcp_server_lists_tools():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            tool_names = {t.name for t in result.tools}

    assert tool_names == {
        "get_portfolio_summary",
        "get_balances",
        "get_prices",
        "get_dca_history",
        "get_snapshots",
        "sync_trades",
        "get_balance_change",
        "get_dca_analysis",
        "get_unrealised_cgt",
        "get_buy_and_hold_comparison",
    }


@pytest.mark.asyncio
async def test_mcp_server_lists_resources():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_resources()
            resource_uris = {str(r.uri) for r in result.resources}

    assert resource_uris == {
        "portfolio://summary",
        "portfolio://snapshots/7d",
    }
