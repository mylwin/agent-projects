import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from langchain.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.schemas import InsuranceAgentState
from app.modules.chat_thread.service import ChatThreadService


class ChatHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_sources_survive_checkpoint_and_belong_to_each_answer(self):
        builder = StateGraph(InsuranceAgentState)
        builder.add_node("reply", lambda state: {})
        builder.add_edge(START, "reply")
        builder.add_edge("reply", END)
        agent = builder.compile(checkpointer=InMemorySaver())
        thread_id = uuid4()
        config = {"configurable": {"thread_id": str(thread_id)}}
        await agent.ainvoke(
            {
                "messages": [
                    HumanMessage("问题一"),
                    AIMessage("回答一", id="answer-1"),
                    HumanMessage("问题二"),
                    AIMessage("回答二", id="answer-2"),
                    AIMessage("无引用回复", id="answer-3"),
                ]
            },
            config,
        )
        first = {"sources": {"ref-clause-6-first": {"content": "第一条条款"}}}
        second = {"sources": {"ref-clause-10-second": {"content": "第二条条款"}}}
        await agent.aupdate_state(config, {"additional_info": {"answer-1": first}})
        await agent.aupdate_state(config, {"additional_info": {"answer-2": second}})
        service = ChatThreadService.__new__(ChatThreadService)
        service.agent = agent
        service.repository = AsyncMock()
        service.repository.find_owned.return_value = object()
        history = await service.get_history(thread_id, 1)
        messages = history.model_dump(mode="json")["messages"]
        self.assertIsNone(messages[0]["additional_info"])
        self.assertEqual(messages[1]["additional_info"], first)
        self.assertIsNone(messages[2]["additional_info"])
        self.assertEqual(messages[3]["additional_info"], second)
        self.assertIsNone(messages[4]["additional_info"])

    async def test_history_without_sources_remains_readable(self):
        from types import SimpleNamespace

        service = ChatThreadService.__new__(ChatThreadService)
        service.repository = AsyncMock()
        service.repository.find_owned.return_value = object()
        service.agent = AsyncMock()
        service.agent.aget_state.return_value = SimpleNamespace(
            values={
                "messages": [HumanMessage("你好"), AIMessage("您好")],
            }
        )
        history = await service.get_history(uuid4(), 1)
        self.assertEqual(len(history.messages), 2)
        self.assertTrue(
            all(message.additional_info is None for message in history.messages)
        )
