"""Verify MCP subprocess params are derived from runtime, not hardcoded paths."""
import sys
from pathlib import Path

from backend.agent.tools import MCP_SERVER_PARAMS


def test_mcp_command_uses_current_python():
    assert MCP_SERVER_PARAMS.command == sys.executable


def test_mcp_cwd_is_project_root():
    expected = Path(__file__).resolve().parents[2]
    assert Path(MCP_SERVER_PARAMS.cwd) == expected


def test_mcp_cwd_is_absolute():
    """Stdio subprocess requires an absolute cwd."""
    assert Path(MCP_SERVER_PARAMS.cwd).is_absolute()
