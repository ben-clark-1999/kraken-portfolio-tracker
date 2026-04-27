"""Dimension catalogue + LLM-as-judge prompt template.

Adding a new dimension = one entry in DIMENSION_CATALOGUE. The judge prompt
embeds whichever dimensions a given query requires.
"""

from backend.evals.schema import JudgeDimension


DIMENSION_CATALOGUE: dict[str, JudgeDimension] = {
    "cites_aud_value": JudgeDimension(
        name="cites_aud_value",
        criterion=(
            "The answer must contain at least one AUD value with $ prefix and "
            "comma separators (e.g. $5,777.83)."
        ),
    ),
    "cites_timestamp": JudgeDimension(
        name="cites_timestamp",
        criterion=(
            "The answer must explicitly state when the data is from — either a "
            "date (DD/MM/YYYY) or a relative phrase like 'as of'."
        ),
    ),
    "no_filler_preamble": JudgeDimension(
        name="no_filler_preamble",
        criterion=(
            "The answer must start with substantive content. Phrases like "
            "'Let me check', 'I'll look that up', 'Here's what I found' as the "
            "opening are FAIL."
        ),
    ),
    "formatting_correct": JudgeDimension(
        name="formatting_correct",
        criterion=(
            "AUD values use comma separators, percentages have 2 decimal places, "
            "crypto quantities have 4 decimal places."
        ),
    ),
    "cites_actual_dates_from_tools": JudgeDimension(
        name="cites_actual_dates_from_tools",
        criterion=(
            "When the answer references a date or period, that date or period "
            "must appear in the tool results provided. No invented dates."
        ),
    ),
    "cites_ato_rule": JudgeDimension(
        name="cites_ato_rule",
        criterion=(
            "For any tax claim, the specific ATO rule must be named (e.g. "
            "'CGT discount: asset held >12 months')."
        ),
    ),
    "shows_math": JudgeDimension(
        name="shows_math",
        criterion=(
            "For tax / math-heavy answers, the calculation must be shown — "
            "not just a final number."
        ),
    ),
    "states_assumptions": JudgeDimension(
        name="states_assumptions",
        criterion=(
            "For comparison answers, the assumptions are stated (e.g. 'this "
            "assumes you'd bought ETH at the daily close price on each DCA date')."
        ),
    ),
    "no_recommendation": JudgeDimension(
        name="no_recommendation",
        criterion=(
            "The answer presents data, not buy/sell recommendations. No phrases "
            "like 'you should buy', 'consider selling', etc."
        ),
    ),
    "carries_timeframe_from_previous": JudgeDimension(
        name="carries_timeframe_from_previous",
        criterion=(
            "For follow-up queries, the answer carries forward the timeframe "
            "from the previous turn without asking the user to restate it."
        ),
    ),
    "carries_assets_from_previous": JudgeDimension(
        name="carries_assets_from_previous",
        criterion=(
            "For follow-up queries, the answer carries forward the asset(s) "
            "discussed in the previous turn."
        ),
    ),
    "addresses_question": JudgeDimension(
        name="addresses_question",
        criterion=(
            "The answer directly addresses what the user asked. Tangents or "
            "evasive non-answers are FAIL."
        ),
    ),
    "honest_about_missing_data": JudgeDimension(
        name="honest_about_missing_data",
        criterion=(
            "When tool results are incomplete, the answer surfaces that. No "
            "silently substituting a shorter window for the requested one."
        ),
    ),
}


JUDGE_SYSTEM_PROMPT = """\
You are evaluating a portfolio analyst's answer against specific quality
dimensions. For each dimension, decide PASS or FAIL based ONLY on the criteria
stated. Provide a one-sentence reason for each decision that references
specific text in the answer.

Be strict: if the answer "sort of" satisfies a dimension, that is FAIL.
"""


def build_judge_user_prompt(
    query_text: str,
    answer: str,
    tool_results_summary: str,
    dimensions: list[JudgeDimension],
) -> str:
    """Build the per-query user prompt for the answer-quality judge."""
    dimension_block = "\n".join(
        f"- {d.name}: {d.criterion}" for d in dimensions
    )
    return (
        f"QUERY:\n{query_text}\n\n"
        f"TOOL RESULTS AVAILABLE TO THE ANSWER:\n{tool_results_summary or '<none>'}\n\n"
        f"ANSWER:\n{answer}\n\n"
        f"DIMENSIONS TO SCORE:\n{dimension_block}\n\n"
        f"Return one DimensionScore per dimension above."
    )
