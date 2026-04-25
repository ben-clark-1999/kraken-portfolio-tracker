import pytest
from backend.agent.classifier import ClassifierOutput, route_query


def _cls(primary: str, confidence: float, secondary: list[str] | None = None) -> ClassifierOutput:
    return ClassifierOutput(
        primary_category=primary,
        confidence=confidence,
        secondary_categories=secondary or [],
    )


def test_high_confidence_no_secondary_routes_to_specialised():
    result = route_query(_cls("quick", 0.95))
    assert result == "quick_agent"


def test_high_confidence_with_secondary_routes_to_general():
    result = route_query(_cls("tax", 0.90, ["analysis"]))
    assert result == "general_agent"


def test_low_confidence_routes_to_general():
    result = route_query(_cls("analysis", 0.6))
    assert result == "general_agent"


def test_open_category_routes_to_general():
    result = route_query(_cls("open", 0.95))
    assert result == "general_agent"


def test_comparison_routes_to_comparison_agent():
    result = route_query(_cls("comparison", 0.88))
    assert result == "comparison_agent"


def test_unknown_category_routes_to_general():
    result = route_query(_cls("nonsense", 0.99))
    assert result == "general_agent"


def test_exact_threshold_routes_to_specialised():
    result = route_query(_cls("tax", 0.8))
    assert result == "tax_agent"


def test_just_below_threshold_routes_to_general():
    result = route_query(_cls("tax", 0.79))
    assert result == "general_agent"
