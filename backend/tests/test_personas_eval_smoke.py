"""Smoke test for the per-persona eval harness (spec §7.5).

Confirms the golden-set file parses and the runner can be instantiated.
Actual scenario runs hit live LLM APIs and are marked `@pytest.mark.eval`,
which the default pytest invocation excludes (see backend/pytest.ini).
"""
from pathlib import Path

import yaml

from backend.evals.personas_runner import PersonaEvalRunner, load_golden_set


def test_golden_set_loads():
    path = Path(__file__).resolve().parents[1] / "evals" / "personas_golden_set.yaml"
    data = yaml.safe_load(path.read_text())
    assert "scenarios" in data
    assert isinstance(data["scenarios"], list)
    assert len(data["scenarios"]) >= 6   # at least 2 scenarios × 3 personas


def test_runner_instantiates():
    scenarios = load_golden_set()
    runner = PersonaEvalRunner(scenarios=scenarios)
    assert runner.scenario_count >= 6
