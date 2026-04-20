import asyncio
import json

from mcp.server.fastmcp import FastMCP

from backend.services import portfolio_service

mcp = FastMCP("kraken-portfolio")


@mcp.tool()
async def get_portfolio_summary() -> str:
    """Get current portfolio value, per-asset breakdown with quantities, AUD prices, values, cost basis, unrealised P&L, and allocation percentages."""
    summary = await asyncio.to_thread(portfolio_service.build_summary)
    return json.dumps(summary.model_dump(), default=str)


if __name__ == "__main__":
    mcp.run()
