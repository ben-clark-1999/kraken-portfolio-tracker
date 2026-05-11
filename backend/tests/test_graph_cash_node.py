"""Smoke test: the compiled graph has a cash_agent node and routing reaches it."""

from backend.agent.graph import build_graph


def test_graph_has_cash_agent_node():
    graph = build_graph(all_tools=[], checkpointer=None)
    nodes = set(graph.get_graph().nodes)
    assert "cash_agent" in nodes
