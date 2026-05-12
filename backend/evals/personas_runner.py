"""Per-persona scenario evaluation runner (spec §7.5).

Runs each scenario through the persona via `invoke_for_strategy`, captures
the tool-call output and reasoning, then judges along three axes:

- Tool-call correctness — did the agent call the expected tool, or
  correctly decline to?
- Reasoning quality — do mentioned-words appear in the rationale?
  (String-match fallback; richer LLM-as-judge can replace `_judge` later.)
- Risk discipline — did the agent stay within caps (e.g. notional cap)?

The actual run is gated behind `@pytest.mark.eval` because it hits live
LLM APIs. Default pytest invocations skip these via pytest.ini.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

from backend.services.trading.persona_loader import load_persona


SCENARIOS_PATH = Path(__file__).resolve().parent / "personas_golden_set.yaml"


@dataclass
class Scenario:
    id: str
    persona_key: str
    description: str
    trigger: dict
    portfolio_state: dict
    market_snapshot: dict
    expected: dict


def load_golden_set(path: Path = SCENARIOS_PATH) -> list[Scenario]:
    raw = yaml.safe_load(path.read_text())
    return [Scenario(**s) for s in raw["scenarios"]]


@dataclass
class ScenarioResult:
    id: str
    persona_key: str
    tool_call_correct: bool
    reasoning_score: float       # 0..1
    risk_disciplined: bool
    notes: list[str] = field(default_factory=list)


class PersonaEvalRunner:
    def __init__(self, *, scenarios: list[Scenario]) -> None:
        self.scenarios = scenarios

    @property
    def scenario_count(self) -> int:
        return len(self.scenarios)

    async def run_one(self, scenario: Scenario) -> ScenarioResult:
        """Execute a single scenario through the persona.

        Hits the live agent graph — only call this from `@pytest.mark.eval`
        tests or explicit on-demand scripts.
        """
        from backend.agent.graph import invoke_for_strategy
        persona = load_persona(scenario.persona_key)
        user_msg = (
            f"SCENARIO: {scenario.description}\n"
            f"Trigger: {scenario.trigger}\n"
            f"Portfolio: {scenario.portfolio_state}\n"
            f"Market: {scenario.market_snapshot}\n"
            "Decide what to do, calling tools as needed."
        )
        response = await invoke_for_strategy(
            system_prompt=persona.body,
            user_message=user_msg,
            model="claude-sonnet-4-6",
            tools_whitelist=[
                "place_paper_order",
                "get_my_paper_state",
                "get_market_snapshot",
            ],
            strategy_id="eval-scenario",
        )
        return self._judge(scenario, response)

    def _judge(self, scenario: Scenario, response: dict) -> ScenarioResult:
        notes: list[str] = []
        expected = scenario.expected

        # Tool-call correctness.
        tool_calls = response.get("tool_calls") or []
        expected_tool = expected.get("should_call_tool")
        actually_called = tool_calls[0]["tool"] if tool_calls else None
        tool_ok = (
            (expected_tool is None and actually_called is None)
            or (expected_tool is not None and actually_called == expected_tool)
        )
        if not tool_ok:
            notes.append(f"expected tool {expected_tool}, got {actually_called}")

        # Reasoning string-match.
        reasoning = (response.get("agent_output") or "").lower()
        keywords = [k.lower() for k in expected.get("reasoning_mentions", [])]
        if keywords:
            hits = sum(1 for k in keywords if k in reasoning)
            score = hits / len(keywords)
        else:
            score = 1.0

        # Risk discipline.
        max_aud = expected.get("order_notional_at_most_aud")
        risk_ok = True
        if max_aud is not None and tool_calls:
            for tc in tool_calls:
                args = tc.get("args") or {}
                qty = Decimal(str(args.get("qty", "0")))
                pair = args.get("pair")
                mid = scenario.market_snapshot.get(pair, {}).get("mid", 0)
                notional = qty * Decimal(str(mid))
                if notional > Decimal(str(max_aud)):
                    risk_ok = False
                    notes.append(f"notional {notional} > cap {max_aud}")

        return ScenarioResult(
            id=scenario.id,
            persona_key=scenario.persona_key,
            tool_call_correct=tool_ok,
            reasoning_score=score,
            risk_disciplined=risk_ok,
            notes=notes,
        )
