import pytest
from backend.agent.graph import route_after_classify, AgentState


def _state(primary: str, confidence: float, secondary: list[str] | None = None) -> AgentState:
    return {
        "messages": [],
        "classification": {
            "primary_category": primary,
            "confidence": confidence,
            "secondary_categories": secondary or [],
        },
    }


def test_route_quick():
    assert route_after_classify(_state("quick", 0.9)) == "quick_agent"


def test_route_analysis():
    assert route_after_classify(_state("analysis", 0.85)) == "analysis_agent"


def test_route_tax():
    assert route_after_classify(_state("tax", 0.82)) == "tax_agent"


def test_route_comparison():
    assert route_after_classify(_state("comparison", 0.9)) == "comparison_agent"


def test_route_open_goes_to_general():
    assert route_after_classify(_state("open", 0.95)) == "general_agent"


def test_route_low_confidence_goes_to_general():
    assert route_after_classify(_state("quick", 0.5)) == "general_agent"


def test_route_secondary_goes_to_general():
    assert route_after_classify(_state("tax", 0.9, ["analysis"])) == "general_agent"


def test_route_no_classification_goes_to_general():
    state: AgentState = {"messages": [], "classification": None}
    assert route_after_classify(state) == "general_agent"


def test_route_delegates_to_route_query():
    """Verify route_after_classify delegates to classifier.route_query."""
    from backend.agent.classifier import route_query, ClassifierOutput

    cls = ClassifierOutput(primary_category="tax", confidence=0.9)
    state = _state("tax", 0.9)
    assert route_after_classify(state) == route_query(cls)
