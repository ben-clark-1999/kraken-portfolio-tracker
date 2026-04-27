"""Pydantic schema for golden-set entries and eval results."""

from pydantic import BaseModel, Field


class JudgeDimension(BaseModel):
    """A single graded dimension for the answer-quality judge.

    Used by the LLM-as-judge in Task 4.2; defined here so the schema is
    stable from Task 4.1 onward.
    """
    name: str
    criterion: str = Field(
        description="Human-readable pass criterion. Embedded in the judge prompt."
    )


class GoldenQuery(BaseModel):
    id: str
    query: str
    expected_classification: str | None = None
    min_confidence: float | None = None
    expected_tools_any_of: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    judge_dimensions: list[str] = Field(
        default_factory=list,
        description="Names of dimensions to apply (looked up in DIMENSION_CATALOGUE in Task 4.2).",
    )
    previous: str | None = Field(
        default=None,
        description="ID of a prior query in the same session, for multi-turn tests.",
    )


class DimensionScore(BaseModel):
    name: str
    passed: bool
    reasoning: str


class QueryResult(BaseModel):
    id: str
    query: str
    actual_classification: str | None
    actual_confidence: float | None
    actual_tools: list[str]
    actual_answer: str
    classification_pass: bool | None  # None when the query has no expected_classification
    classification_reason: str | None = None
    tool_use_pass: bool
    tool_use_reason: str | None = None
    answer_quality_scores: list[DimensionScore] = Field(default_factory=list)
    error: str | None = None


class EvalRun(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    results: list[QueryResult]

    @property
    def classification_pass_rate(self) -> float:
        rated = [r for r in self.results if r.classification_pass is not None]
        if not rated:
            return 0.0
        return sum(1 for r in rated if r.classification_pass) / len(rated)

    @property
    def tool_use_pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.tool_use_pass) / len(self.results)

    @property
    def answer_quality_pass_rate(self) -> float:
        all_dim_scores = [s for r in self.results for s in r.answer_quality_scores]
        if not all_dim_scores:
            return 0.0
        return sum(1 for s in all_dim_scores if s.passed) / len(all_dim_scores)
