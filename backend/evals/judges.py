"""Eval judges. Mechanical judges live here; LLM-as-judge added in Task 4.2."""

from backend.evals.schema import GoldenQuery


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
