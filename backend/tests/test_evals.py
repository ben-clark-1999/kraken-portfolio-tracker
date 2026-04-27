"""Eval suite entrypoint. Opt-in via `pytest -m eval`.

Hits live LLM APIs — runs only when the marker is selected.
"""

import pytest

from backend.evals.runner import (
    load_baseline, load_golden_set, render_summary, run_evals, save_run,
)


@pytest.mark.eval
@pytest.mark.asyncio
async def test_full_eval_suite():
    """Run the complete golden set against the real agent graph."""
    # Build the graph the same way main.py does, sharing tools/checkpointer.
    from backend.agent.checkpointer import create_checkpointer
    from backend.agent.graph import build_graph
    from backend.agent.tools import MCPToolManager

    tool_manager = MCPToolManager()
    tools = await tool_manager.start()
    try:
        checkpointer = await create_checkpointer()
        graph = build_graph(tools, checkpointer)

        queries = load_golden_set()
        run = await run_evals(graph, queries)
    finally:
        await tool_manager.stop()

    baseline = load_baseline()
    summary = render_summary(run, baseline)
    print("\n" + summary)
    save_run(run)

    # Soft pass: don't fail the test on quality scores. The point of running
    # this is the printed report and the JSON record. Hard failures
    # (exceptions per query) DO fail the suite via the assertion below.
    errors = [r for r in run.results if r.error]
    assert not errors, f"{len(errors)} queries errored — see report above"
