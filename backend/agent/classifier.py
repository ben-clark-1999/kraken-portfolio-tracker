"""Query classifier — routes user questions to specialised agent paths."""

from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from backend.agent.agent_config import (
    CATEGORY_TO_NODE,
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    CLASSIFIER_MODEL,
)
from backend.agent.prompts import CLASSIFIER_PROMPT


class ClassifierOutput(BaseModel):
    """Structured output from the query classifier."""

    primary_category: str = Field(description="One of: quick, analysis, tax, comparison, open")
    confidence: float = Field(description="Confidence in primary classification, 0-1")
    secondary_categories: list[str] = Field(
        default_factory=list,
        description="Other relevant categories (only if confidence >= 0.5)",
    )


def route_query(classification: ClassifierOutput) -> str:
    """Determine which agent node to route to based on classifier output.

    Returns the node name string for LangGraph conditional routing.
    """
    if classification.confidence < CLASSIFIER_CONFIDENCE_THRESHOLD:
        return "general_agent"

    if classification.secondary_categories:
        return "general_agent"

    return CATEGORY_TO_NODE.get(classification.primary_category, "general_agent")


async def classify(messages: list) -> ClassifierOutput:
    """Classify a user query using Haiku.

    Extracts the last human message and classifies it.
    """
    model = ChatAnthropic(model=CLASSIFIER_MODEL).with_structured_output(ClassifierOutput)

    last_human = None
    for msg in reversed(messages):
        if hasattr(msg, "content") and hasattr(msg, "type") and msg.type == "human":
            last_human = msg.content
            break

    if last_human is None:
        last_human = str(messages[-1]) if messages else ""

    return await model.ainvoke([
        SystemMessage(content=CLASSIFIER_PROMPT),
        HumanMessage(content=last_human),
    ])
