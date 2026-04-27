"""Unit tests for the mechanical (non-LLM) judges."""
from backend.evals.judges import judge_classification, judge_tool_use
from backend.evals.schema import GoldenQuery


def test_classification_pass_when_match_and_confident():
    query = GoldenQuery(
        id="q1", query="...", expected_classification="quick", min_confidence=0.8,
    )
    passed, reason = judge_classification(
        query, actual_classification="quick", actual_confidence=0.92,
    )
    assert passed is True


def test_classification_fail_on_wrong_category():
    query = GoldenQuery(
        id="q1", query="...", expected_classification="quick", min_confidence=0.8,
    )
    passed, reason = judge_classification(
        query, actual_classification="analysis", actual_confidence=0.92,
    )
    assert passed is False
    assert "expected=quick" in reason


def test_classification_fail_on_low_confidence():
    query = GoldenQuery(
        id="q1", query="...", expected_classification="quick", min_confidence=0.8,
    )
    passed, reason = judge_classification(
        query, actual_classification="quick", actual_confidence=0.6,
    )
    assert passed is False
    assert "confidence" in reason


def test_classification_skipped_when_no_expected():
    query = GoldenQuery(id="q1", query="...")
    passed, reason = judge_classification(
        query, actual_classification="quick", actual_confidence=0.6,
    )
    assert passed is None  # Not graded


def test_tool_use_pass_when_expected_called_and_no_forbidden():
    query = GoldenQuery(
        id="q1", query="...",
        expected_tools_any_of=["get_portfolio_summary"],
        forbidden_tools=["get_buy_and_hold_comparison"],
    )
    passed, reason = judge_tool_use(query, actual_tools=["get_portfolio_summary"])
    assert passed is True


def test_tool_use_fail_when_expected_missing():
    query = GoldenQuery(
        id="q1", query="...",
        expected_tools_any_of=["get_portfolio_summary"],
    )
    passed, reason = judge_tool_use(query, actual_tools=["get_balances"])
    assert passed is False
    assert "expected" in reason.lower()


def test_tool_use_fail_when_forbidden_called():
    query = GoldenQuery(
        id="q1", query="...",
        expected_tools_any_of=["get_portfolio_summary"],
        forbidden_tools=["get_buy_and_hold_comparison"],
    )
    passed, reason = judge_tool_use(
        query, actual_tools=["get_portfolio_summary", "get_buy_and_hold_comparison"],
    )
    assert passed is False
    assert "forbidden" in reason.lower()


def test_tool_use_pass_when_no_expectations_set():
    query = GoldenQuery(id="q1", query="...")
    passed, reason = judge_tool_use(query, actual_tools=["anything"])
    assert passed is True


import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.evals.judges import judge_answer_quality


@pytest.mark.asyncio
async def test_answer_quality_judge_returns_one_score_per_dimension(monkeypatch):
    """Mock Anthropic; assert judge returns DimensionScore per requested dimension."""
    from backend.evals.schema import DimensionScore

    fake_response = MagicMock()
    fake_response.scores = [
        DimensionScore(name="cites_aud_value", passed=True, reasoning="contains $5,000"),
        DimensionScore(name="cites_timestamp", passed=False, reasoning="no date stated"),
    ]

    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(return_value=fake_response)
    fake_model.with_structured_output = MagicMock(return_value=fake_model)

    monkeypatch.setattr(
        "backend.evals.judges.ChatAnthropic",
        MagicMock(return_value=fake_model),
    )

    query = GoldenQuery(
        id="q1", query="value?",
        judge_dimensions=["cites_aud_value", "cites_timestamp"],
    )
    scores = await judge_answer_quality(
        query, answer="Your portfolio is $5,000.", tool_results_summary="",
    )
    assert len(scores) == 2
    names = [s.name for s in scores]
    assert names == ["cites_aud_value", "cites_timestamp"]
    assert scores[0].passed is True
    assert scores[1].passed is False


@pytest.mark.asyncio
async def test_answer_quality_judge_returns_empty_when_no_dimensions(monkeypatch):
    """If a query has no judge_dimensions, the LLM is not invoked."""
    fake_chat = MagicMock(side_effect=AssertionError("ChatAnthropic should not be called"))
    monkeypatch.setattr("backend.evals.judges.ChatAnthropic", fake_chat)
    query = GoldenQuery(id="q1", query="x", judge_dimensions=[])
    scores = await judge_answer_quality(query, answer="anything", tool_results_summary="")
    assert scores == []
