import pytest
from unittest.mock import MagicMock
from backend.agent.tools import filter_tools


def _mock_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    return tool


def test_filter_tools_quick_subset():
    all_tools = [_mock_tool(n) for n in [
        "get_portfolio_summary", "get_balances", "get_prices",
        "get_dca_history", "get_dca_analysis", "get_snapshots",
        "get_unrealised_cgt",
    ]]
    result = filter_tools(all_tools, "quick")
    names = [t.name for t in result]
    assert "get_portfolio_summary" in names
    assert "get_balances" in names
    assert "get_snapshots" not in names
    assert "get_unrealised_cgt" not in names


def test_filter_tools_general_returns_all():
    all_tools = [_mock_tool(n) for n in ["a", "b", "c"]]
    result = filter_tools(all_tools, "general")
    assert len(result) == 3


def test_filter_tools_unknown_category_returns_all():
    all_tools = [_mock_tool(n) for n in ["a", "b"]]
    result = filter_tools(all_tools, "unknown")
    assert len(result) == 2
