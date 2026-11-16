import unittest
from unittest.mock import AsyncMock, patch

from langchain.messages import AIMessage, HumanMessage

from app.agents.chitchat import ChitchatAgent, MAX_CHITCHAT_COUNT
from app.agents.orchestrator import route_node
from app.agents.schemas import RouteResult


class IntentRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_uses_model_intent_and_preserves_previous_workflow(self):
        for intent in ("recommendation_plan", "claim", "human_handoff", "chitchat", "fallback"):
            with self.subTest(intent=intent):
                result = RouteResult(intent=intent, reason="测试")
                with patch("app.agents.orchestrator.intent_router.route", new=AsyncMock(return_value=result)):
                    command = await route_node({
                        "messages": [AIMessage("你好"), HumanMessage("有什么保险产品值得推荐吗")],
                        "active_workflow": "chitchat",
                    })
                self.assertEqual(command.goto, intent)
                self.assertEqual(command.update["active_workflow"], intent)
                self.assertEqual(command.update["previous_workflow"], "chitchat")

    async def test_social_reply_ends_without_entering_a_workflow(self):
        with patch("app.agents.orchestrator.intent_router.route", new=AsyncMock(return_value="您好")):
            command = await route_node({"messages": [HumanMessage("你好")]})
        self.assertEqual(command.goto, "__end__")
        self.assertEqual(command.update["messages"][0].content, "您好")

    async def test_chitchat_returns_messages_for_both_paths(self):
        agent = ChitchatAgent.__new__(ChitchatAgent)
        agent.model = AsyncMock()
        agent.model.ainvoke.return_value = AIMessage("回复")
        result = await agent.handle_chitchat({"messages": [HumanMessage("聊天")], "previous_workflow": "chitchat"})
        self.assertEqual(result["messages"][0].content, "回复")
        result = await agent.handle_chitchat({"messages": [HumanMessage("聊天")], "previous_workflow": "chitchat", "chitchat_count": MAX_CHITCHAT_COUNT})
        self.assertIn("保险", result["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
