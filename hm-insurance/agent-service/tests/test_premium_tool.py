import json
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

from langchain.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agents import tools
from app.modules.premium.schemas import PremiumCalculateRequest


class PremiumToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_accepts_validated_answers_and_returns_quote(self):
        session = object()

        @asynccontextmanager
        async def session_factory():
            yield session

        expected_quote = {"quote_id": "test-quote", "annual_premium": "330.00"}
        builder = StateGraph(MessagesState)
        builder.add_node("tools", ToolNode([tools.calculate_premium]))
        builder.add_edge(START, "tools")
        builder.add_edge("tools", END)
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "calculate_premium",
                    "id": "quote-call",
                    "args": {
                        "product_id": 2,
                        "answers": {"insured": {"age": 30}},
                    },
                }
            ],
        )

        with (
            patch.object(tools, "AsyncSessionFactory", session_factory),
            patch.object(tools, "PremiumService") as service,
        ):
            quote = Mock()
            quote.model_dump.return_value = expected_quote
            calculate = AsyncMock(return_value=quote)
            service.return_value.calculate = calculate

            result = await builder.compile().ainvoke({"messages": [message]})

        request = calculate.await_args.args[0]
        self.assertEqual(request.product_id, 2)
        self.assertEqual(request.answers.insured.age, 30)
        reply = result["messages"][-1]
        self.assertEqual(reply.tool_call_id, "quote-call")
        self.assertEqual(json.loads(reply.content), expected_quote)

    def test_request_accepts_flat_and_nested_answers(self):
        flat = PremiumCalculateRequest.model_validate(
            {"answers": {"insured.age": 30, "coverage.deductible": 0}}
        )
        nested = PremiumCalculateRequest.model_validate(
            {"answers": {"insured": {"age": 30}, "coverage": {"deductible": 0}}}
        )

        self.assertEqual(flat.answers, nested.answers)
        self.assertEqual(flat.answers.insured.age, 30)
        self.assertEqual(flat.answers.coverage.deductible, 0)
