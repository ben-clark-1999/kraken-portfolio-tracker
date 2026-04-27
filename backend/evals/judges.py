"""Eval judges. Mechanical judges live here; LLM-as-judge added in Task 4.2."""

import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.evals.prompts import (
    DIMENSION_CATALOGUE,
    JUDGE_SYSTEM_PROMPT,
    build_judge_user_prompt,
)
from backend.evals.schema import DimensionScore, GoldenQuery


def judge_classification(
    query: GoldenQuery,
    actual_classification: str | None,
    actual_confidence: float | None,
) -> tuple[bool | None, str | None]:
    """Pass if actual matches expected and confidence >= min_confidence.

    Returns (None, None) when the query has no classification expectation —
    that query simply isn't graded on this dimension.
    """
    if query.expected_classification is None:
        return None, None
    if actual_classification != query.expected_classification:
        return False, (
            f"expected={query.expected_classification} got={actual_classification} "
            f"(confidence={actual_confidence})"
        )
    if query.min_confidence is not None:
        if actual_confidence is None or actual_confidence < query.min_confidence:
            return False, (
                f"confidence too low: got={actual_confidence} min={query.min_confidence}"
            )
    return True, None


def judge_tool_use(
    query: GoldenQuery,
    actual_tools: list[str],
) -> tuple[bool, str | None]:
    """Pass when expected tools (any_of) were called and no forbidden tools fired."""
    actual_set = set(actual_tools)
    forbidden = set(query.forbidden_tools)
    forbidden_hit = actual_set & forbidden
    if forbidden_hit:
        return False, f"forbidden tool(s) called: {sorted(forbidden_hit)}"
    if query.expected_tools_any_of:
        expected = set(query.expected_tools_any_of)
        if not (actual_set & expected):
            return False, f"expected at least one of {sorted(expected)}, got {sorted(actual_set)}"
    return True, None


class _JudgeOutput(BaseModel):
    """Structured output target for the LLM judge."""
    scores: list[DimensionScore]


# Default judge model = same as the agent. Override via env var for cheap iteration.
DEFAULT_JUDGE_MODEL = "claude-sonnet-4-5-20241022"


def _judge_model_name() -> str:
    return os.environ.get("EVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)


async def judge_answer_quality(
    query: GoldenQuery,
    answer: str,
    tool_results_summary: str,
) -> list[DimensionScore]:
    """LLM-as-judge for answer quality. Returns one DimensionScore per dimension."""
    if not query.judge_dimensions:
        return []

    dimensions = [DIMENSION_CATALOGUE[name] for name in query.judge_dimensions]
    model = ChatAnthropic(model=_judge_model_name()).with_structured_output(_JudgeOutput)
    user_prompt = build_judge_user_prompt(
        query_text=query.query,
        answer=answer,
        tool_results_summary=tool_results_summary,
        dimensions=dimensions,
    )

    response: _JudgeOutput = await model.ainvoke([
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    return response.scores
