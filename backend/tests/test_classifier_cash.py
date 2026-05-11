import pytest
from langchain_core.messages import HumanMessage
from backend.agent.classifier import classify, route_query


@pytest.mark.asyncio
@pytest.mark.eval
@pytest.mark.parametrize("question", [
    "How much cash do I have?",
    "How much did I spend on takeaway last month?",
    "What's my income vs expense for May?",
])
async def test_classifies_as_cash(question):
    out = await classify([HumanMessage(content=question)])
    assert out.primary_category == "cash"
    assert route_query(out) == "cash_agent"
