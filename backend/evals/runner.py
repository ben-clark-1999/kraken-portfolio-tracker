"""Eval runner — invoke the agent graph against each golden-set entry, capture
classification + tools + answer, hand off to judges.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage

from backend.evals.judges import judge_classification, judge_tool_use
from backend.evals.schema import EvalRun, GoldenQuery, QueryResult

logger = logging.getLogger(__name__)


def load_golden_set(path: Path | None = None) -> list[GoldenQuery]:
    """Load and validate the golden_set.yaml file."""
    if path is None:
        path = Path(__file__).parent / "golden_set.yaml"
    with open(path) as f:
        raw = yaml.safe_load(f)
    return [GoldenQuery(**entry) for entry in raw]


async def _run_single(graph, query: GoldenQuery, prior_thread_id: str | None) -> QueryResult:
    """Invoke the graph on one query, capture the four observable outputs."""
    if query.previous and prior_thread_id is None:
        raise ValueError(f"Query {query.id} requires previous={query.previous} but no thread provided")

    thread_id = prior_thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    actual_classification = None
    actual_confidence = None
    actual_tools: list[str] = []
    actual_answer_parts: list[str] = []
    error_str: str | None = None

    try:
        async for mode, data in graph.astream(
            {"messages": [HumanMessage(content=query.query)]},
            config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                for node_name, update in data.items():
                    if node_name == "classify_query" and update.get("classification"):
                        cls = update["classification"]
                        actual_classification = cls.get("primary_category")
                        actual_confidence = cls.get("confidence")
            elif mode == "messages":
                chunk, _meta = data
                if isinstance(chunk, AIMessage) and chunk.content:
                    actual_answer_parts.append(str(chunk.content))
                if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        actual_tools.append(tc["name"])
    except Exception as e:
        error_str = str(e)
        logger.exception("[Eval] query %s failed", query.id)

    actual_answer = "".join(actual_answer_parts).strip()

    cls_pass, cls_reason = judge_classification(
        query, actual_classification, actual_confidence,
    )
    tool_pass, tool_reason = judge_tool_use(query, actual_tools)

    return QueryResult(
        id=query.id,
        query=query.query,
        actual_classification=actual_classification,
        actual_confidence=actual_confidence,
        actual_tools=actual_tools,
        actual_answer=actual_answer,
        classification_pass=cls_pass,
        classification_reason=cls_reason,
        tool_use_pass=tool_pass,
        tool_use_reason=tool_reason,
        error=error_str,
    )


async def run_evals(graph, queries: list[GoldenQuery]) -> EvalRun:
    """Run every query, return an EvalRun. Handles multi-turn linkage."""
    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    results: list[QueryResult] = []
    # Map query_id → thread_id so multi-turn continuations re-use the session.
    thread_for: dict[str, str] = {}

    for query in queries:
        prior_thread = thread_for.get(query.previous) if query.previous else None
        thread_id = prior_thread or str(uuid.uuid4())
        thread_for[query.id] = thread_id

        # Always pass the registered thread_id so multi-turn chains share state.
        # The previous version passed None when query.previous was unset, which
        # caused _run_single to mint a SECOND UUID — meaning the first turn of
        # a chain ran on a different thread than what got registered for
        # downstream turns. Latent bug; only matters once multi-turn queries
        # land in golden_set.yaml (Task 4.2).
        result = await _run_single(graph, query, thread_id)
        results.append(result)

    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return EvalRun(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        results=results,
    )


def render_summary(run: EvalRun, baseline: EvalRun | None = None) -> str:
    """Pretty summary table for stdout."""
    lines = [
        f"EVAL RESULTS (run-id {run.run_id}, {run.finished_at})",
        "─" * 53,
    ]

    def _delta(current: float, base: float | None) -> str:
        if base is None:
            return ""
        diff = current - base
        if abs(diff) < 0.005:
            return f"  = baseline {base*100:.0f}%"
        arrow = "▲" if diff > 0 else "▼"
        return f"  {arrow} baseline {base*100:.0f}%"

    lines.append(
        f"Classification:    {sum(1 for r in run.results if r.classification_pass)}"
        f"/{sum(1 for r in run.results if r.classification_pass is not None)}"
        f"  ({run.classification_pass_rate*100:.0f}%)"
        f"{_delta(run.classification_pass_rate, baseline.classification_pass_rate if baseline else None)}"
    )
    lines.append(
        f"Tool-use:          {sum(1 for r in run.results if r.tool_use_pass)}"
        f"/{len(run.results)}"
        f"  ({run.tool_use_pass_rate*100:.0f}%)"
        f"{_delta(run.tool_use_pass_rate, baseline.tool_use_pass_rate if baseline else None)}"
    )
    lines.append(
        f"Answer quality:    {sum(1 for r in run.results for s in r.answer_quality_scores if s.passed)}"
        f"/{sum(len(r.answer_quality_scores) for r in run.results)} dimensions"
        f"  ({run.answer_quality_pass_rate*100:.0f}%)"
        f"{_delta(run.answer_quality_pass_rate, baseline.answer_quality_pass_rate if baseline else None)}"
    )
    lines.append("")

    failures = [r for r in run.results if (
        r.classification_pass is False or not r.tool_use_pass or r.error
        or any(not s.passed for s in r.answer_quality_scores)
    )]
    if failures:
        lines.append("FAILURES:")
        for r in failures:
            tag = r.actual_classification or "?"
            if r.error:
                lines.append(f"  {r.id} [{tag}]  error: {r.error[:80]}")
                continue
            if r.classification_pass is False:
                lines.append(f"  {r.id} [{tag}]  classification: {r.classification_reason}")
            if not r.tool_use_pass:
                lines.append(f"  {r.id} [{tag}]  tool-use: {r.tool_use_reason}")
            for s in r.answer_quality_scores:
                if not s.passed:
                    lines.append(f"  {r.id} [{tag}]  answer-quality {s.name}: FAIL — {s.reasoning}")
    return "\n".join(lines)


def load_baseline() -> EvalRun | None:
    """Load the most recent results JSON, if any."""
    results_dir = Path(__file__).parent / "results"
    if not results_dir.exists():
        return None
    files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    with open(files[-1]) as f:
        return EvalRun(**json.load(f))


def save_run(run: EvalRun) -> Path:
    """Persist a run record. Returns the file path."""
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    path = results_dir / f"{run.run_id}.json"
    with open(path, "w") as f:
        json.dump(run.model_dump(), f, indent=2, default=str)
    return path
