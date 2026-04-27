"""MCP tool lifecycle — persistent subprocess, tool loading, timeout wrapper."""

import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.agent.agent_config import (
    MCP_RESPONSIVENESS_TIMEOUT,
    TOOL_SUBSETS,
    TOOL_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# Project root: backend/agent/tools.py → backend/agent → backend → project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

MCP_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "backend.mcp_server"],
    cwd=str(_PROJECT_ROOT),
)


def filter_tools(tools: list[BaseTool], category: str) -> list[BaseTool]:
    """Return the tool subset for a given agent category.

    If category is "general" or not in TOOL_SUBSETS, returns all tools.
    """
    allowed = TOOL_SUBSETS.get(category)
    if allowed is None:
        return list(tools)
    return [t for t in tools if t.name in allowed]


class MCPToolManager:
    """Manages the MCP subprocess lifecycle and provides tools.

    Spawned once at FastAPI startup via an AsyncExitStack. The subprocess
    stays alive for the application lifetime. Restart-on-crash is the
    operator's responsibility.
    """

    def __init__(self) -> None:
        self._tools: list[BaseTool] = []
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    @property
    def tools(self) -> list[BaseTool]:
        return list(self._tools)

    async def start(self) -> list[BaseTool]:
        """Start the MCP subprocess and load tools. Called once at startup."""
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        read, write = await self._stack.enter_async_context(
            stdio_client(MCP_SERVER_PARAMS)
        )
        self._session = await self._stack.enter_async_context(
            ClientSession(read, write)
        )
        await asyncio.wait_for(
            self._session.initialize(),
            timeout=MCP_RESPONSIVENESS_TIMEOUT,
        )
        self._tools = await load_mcp_tools(self._session)
        logger.info("[MCP] Started — %d tools loaded", len(self._tools))
        return self._tools

    async def stop(self) -> None:
        """Shut down the MCP subprocess."""
        if self._stack:
            await self._stack.aclose()
            self._stack = None
            self._session = None
            self._tools = []
            logger.info("[MCP] Stopped")


async def invoke_tool_with_timeout(tool: BaseTool, args: dict) -> str:
    """Invoke a tool with a timeout. Returns error string on failure."""
    try:
        result = await asyncio.wait_for(
            tool.ainvoke(args),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        return str(result)
    except asyncio.TimeoutError:
        return f"Error: Tool {tool.name} timed out after {TOOL_TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"Error: Tool {tool.name} failed — {e}"
