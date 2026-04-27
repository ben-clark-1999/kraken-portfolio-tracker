"""Unit tests for the eval runner — uses a stub graph, no real LLM."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from backend.evals.runner import load_golden_set, run_evals
from backend.evals.schema import GoldenQuery


class _StubGraph:
    """Minimal graph stub matching the .astream interface our runner uses."""

    def __init__(self, classification: str, confidence: float, tools: list[str], answer: str):
        self.classification = classification
        self.confidence = confidence
        self.tools = tools
        self.answer = answer

    async def astream(self, input_data, config, stream_mode):
        # Yield classify_query update first
        yield ("updates", {
            "classify_query": {
                "classification": {
                    "primary_category": self.classification,
                    "confidence": self.confidence,
                    "secondary_categories": [],
                },
            },
        })
        # Yield AIMessage chunks with tool_calls
        msg = MagicMock(spec=AIMessage)
        msg.content = self.answer
        msg.tool_calls = [{"name": t, "args": {}, "id": f"c{i}"} for i, t in enumerate(self.tools)]
        yield ("messages", (msg, {}))


@pytest.mark.asyncio
async def test_runner_captures_classification_and_tools():
    graph = _StubGraph("quick", 0.91, ["get_portfolio_summary"], "Your value is $5,000.")
    queries = [GoldenQuery(
        id="q1", query="value?",
        expected_classification="quick", min_confidence=0.8,
        expected_tools_any_of=["get_portfolio_summary"],
    )]
    run = await run_evals(graph, queries)
    assert len(run.results) == 1
    r = run.results[0]
    assert r.actual_classification == "quick"
    assert r.actual_confidence == 0.91
    assert r.actual_tools == ["get_portfolio_summary"]
    assert r.classification_pass is True
    assert r.tool_use_pass is True


@pytest.mark.asyncio
async def test_runner_marks_classification_failure():
    graph = _StubGraph("analysis", 0.91, [], "ok")
    queries = [GoldenQuery(
        id="q1", query="value?",
        expected_classification="quick", min_confidence=0.8,
    )]
    run = await run_evals(graph, queries)
    assert run.results[0].classification_pass is False


def test_load_golden_set_parses_yaml(tmp_path):
    yaml_content = """
- id: q001
  query: How much is my portfolio worth?
  expected_classification: quick
  min_confidence: 0.85
  expected_tools_any_of: [get_portfolio_summary]
"""
    path = tmp_path / "golden.yaml"
    path.write_text(yaml_content)
    queries = load_golden_set(path)
    assert len(queries) == 1
    assert queries[0].id == "q001"
    assert queries[0].expected_classification == "quick"
