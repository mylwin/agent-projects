import json
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from langchain.messages import AIMessage, HumanMessage

from app.agents.schemas import InsuranceAgentContext
from app.agents.tools import (
    list_user_policies,
    query_candidate_products,
    query_product_clause,
)
from app.modules.chat.schemas import ChatRequest
from app.modules.chat.service import ChatService
from app.modules.policy.schemas import PolicyItemData, PolicyListData, PolicyProductData


class EventStream:
    def __init__(self, events):
        self.events = events

    async def __aiter__(self):
        for event in self.events:
            yield event

    async def interrupts(self):
        return []


def custom(info):
    return {
        "method": "custom",
        "params": {
            "data": {
                "type": "additional_info",
                "data": info,
            }
        },
    }


class CitationStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_policy_tool_streams_summaries_and_saves_them_with_answer(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.runtime import Runtime

        from app.agents.schemas import InsuranceAgentState
        from app.modules.chat_thread.service import ChatThreadService

        policy = PolicyItemData.model_construct(
            id=uuid4(),
            product_id=6,
            policy_number="POL-DEMO-0001",
            status="active",
            effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            coverage_amount=Decimal("1000000"),
            insured_phone="13800000000",
            insured_id_no_masked="TEST-ID",
            product=PolicyProductData(id=6, name="医疗险", category="medical"),
        )
        policy_service = AsyncMock()
        policy_service.list_policies.return_value = PolicyListData(items=[policy])
        session = MagicMock()
        session.return_value.__aenter__ = AsyncMock()
        session.return_value.__aexit__ = AsyncMock(return_value=False)

        async def reply(state, runtime: Runtime[InsuranceAgentContext]):
            await list_user_policies.coroutine(runtime=runtime)
            return {"messages": [AIMessage("请选择保单", id="policy-answer")]}

        builder = StateGraph(InsuranceAgentState, context_schema=InsuranceAgentContext)
        builder.add_node("reply", reply)
        builder.add_edge(START, "reply")
        builder.add_edge("reply", END)
        agent = builder.compile(checkpointer=InMemorySaver())
        service = ChatService.__new__(ChatService)
        service.repository = AsyncMock()
        service.repository.find_owned.return_value = object()
        service.agent = agent
        request = ChatRequest(thread_id=uuid4(), message="我该准备哪些理赔材料？")
        with (
            patch("app.agents.tools.AsyncSessionFactory", session),
            patch("app.agents.tools.PolicyService", return_value=policy_service),
        ):
            events = [event async for event in service.chat_stream(42, request)]

        policy_service.list_policies.assert_awaited_once_with(user_id=42, status="all")
        summaries = next(
            event.data["policies"] for event in events if event.event == "additional_info"
        )
        self.assertEqual(summaries[0]["id"], str(policy.id))
        self.assertEqual(summaries[0]["product"]["name"], "医疗险")
        self.assertEqual(summaries[0]["effective_at"], "2026-01-01T08:00:00+08:00")
        self.assertEqual(summaries[0]["coverage_amount"], "1000000")
        self.assertNotIn("insured_phone", summaries[0])
        self.assertNotIn("insured_id_no_masked", summaries[0])

        history_service = ChatThreadService.__new__(ChatThreadService)
        history_service.agent = agent
        history_service.repository = service.repository
        history = await history_service.get_history(request.thread_id, 42)
        self.assertEqual(history.messages[-1].additional_info["policies"], summaries)

    async def test_multiple_queries_and_cross_turn_save_keep_sources(self):
        source_id = "ref-clause-6-medical"
        old_source = {"product_id": 6, "content": "不保证续保"}
        source_a = {"ref-clause-10-accident": {"product_id": 10, "content": "意外责任"}}
        source_b = {
            "ref-clause-10-exclusion": {"product_id": 10, "content": "免责条款"}
        }
        scenarios = [
            (
                [
                    custom({"sources": source_a}),
                    custom({"sources": source_b}),
                    custom(
                        {
                            "candidate_products": [{"id": 10, "name": "意外险"}],
                        }
                    ),
                ],
                "推荐[ref-clause-10-accident][ref-clause-10-exclusion]",
                {
                    **source_a,
                    **source_b,
                },
                "candidate_products",
            ),
            (
                [custom({"plan_items": [{"product_id": 6, "plan_id": "saved"}]})],
                f"保存成功，不保证续保。[{source_id}]",
                {source_id: old_source},
                "plan_items",
            ),
        ]
        for events, content, expected, product_key in scenarios:
            with self.subTest(product_key=product_key):
                before = {
                    "messages": [HumanMessage("历史", id="user-old")],
                    "additional_info": {
                        "answer-old": {"sources": {source_id: old_source}}
                    },
                }
                after = {
                    "messages": [
                        *before["messages"],
                        AIMessage(content, id="answer-new"),
                    ]
                }
                service = ChatService.__new__(ChatService)
                service.repository = AsyncMock()
                service.repository.find_owned.return_value = object()
                service.agent = AsyncMock()
                service.agent.aget_state.side_effect = [
                    SimpleNamespace(values=before),
                    SimpleNamespace(values=after),
                ]
                service.agent.astream_events.return_value = EventStream(events)
                request = ChatRequest(thread_id=uuid4(), message="继续")
                output = [event async for event in service.chat_stream(1, request)]
                update = service.agent.aupdate_state.call_args.args[1]
                info = update["additional_info"]["answer-new"]
                self.assertEqual(info["sources"], expected)
                self.assertIn(product_key, info)
                self.assertEqual(output[-1].event, "done")

    async def test_collect_sources_from_each_message(self):
        from app.agents.evidence import collect_sources

        first = {"ref-clause-6-medical": {"content": "医疗条款"}}
        second = {"ref-clause-10-accident": {"content": "意外条款"}}
        self.assertEqual(
            collect_sources(
                {
                    "answer-1": {"sources": first},
                    "answer-2": {"sources": second, "candidate_products": [{"id": 10}]},
                    "answer-3": {"plan_items": [{"product_id": 6}]},
                }
            ),
            {**first, **second},
        )

    async def test_candidate_tool_emits_products_and_clause_ids_do_not_collide(self):
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=object())
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        product_service = MagicMock()
        product_service.list_limited_products = AsyncMock(return_value=[{"id": 6}])
        writer = MagicMock()
        with (
            patch("app.agents.tools.AsyncSessionFactory", factory),
            patch("app.agents.tools.ProductService", return_value=product_service),
            patch("app.agents.tools.get_stream_writer", return_value=writer),
        ):
            result = await query_candidate_products.coroutine(categories=["medical"])
        self.assertEqual(result, [{"id": 6}])
        self.assertEqual(writer.call_args.args[0]["data"]["candidate_products"], result)

        retrieval = SimpleNamespace(retrieve=AsyncMock())
        with (
            patch.dict(sys.modules, {"app.rag": SimpleNamespace(retrieval=retrieval)}),
            patch("app.agents.tools.get_stream_writer", return_value=writer),
        ):
            ids = []
            for product_id, content in [
                (6, "原文"),
                (10, "原文"),
                (6, "变更原文"),
                (6, "原文"),
            ]:
                retrieval.retrieve.return_value = [
                    SimpleNamespace(
                        id="same-chunk",
                        product_id=product_id,
                        clause_name="条款",
                        section_path=[],
                        content=content,
                    )
                ]
                result = await query_product_clause.coroutine("续保", 1, product_id)
                sources = json.loads(result)
                self.assertEqual(writer.call_args.args[0]["data"], {"sources": sources})
                ids.append(next(iter(sources)))
        self.assertEqual(len(set(ids[:3])), 3)
        self.assertEqual(ids[0], ids[3])

    async def test_real_checkpoint_keeps_sources_through_interrupt_and_resume(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.config import get_stream_writer
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import interrupt

        from app.agents.schemas import InsuranceAgentState
        from app.modules.chat_thread.service import ChatThreadService

        source_id = "ref-clause-6-renewal"
        source = {"product_id": 6, "content": "不保证续保"}

        def query(state):
            get_stream_writer()(
                {"type": "additional_info", "data": {"sources": {source_id: source}}}
            )
            return {
                "messages": [AIMessage(f"不保证续保。[{source_id}]", id="recommend")]
            }

        def save(state):
            decision = interrupt({"action": ["approve", "reject"]})
            if decision["action"] == "approve":
                get_stream_writer()(
                    {
                        "type": "additional_info",
                        "data": {
                            "plan_items": [{"product_id": 6, "plan_id": "saved"}],
                        },
                    }
                )
                return {
                    "messages": [
                        AIMessage(f"已保存。不保证续保。[{source_id}]", id="saved")
                    ]
                }
            return {"messages": [AIMessage("未保存", id="rejected")]}

        child = StateGraph(InsuranceAgentState)
        child.add_node("query", query)
        child.add_node("save", save)
        child.add_edge(START, "query")
        child.add_edge("query", "save")
        child.add_edge("save", END)
        parent = StateGraph(InsuranceAgentState)
        parent.add_node("recommendation", child.compile(checkpointer=True))
        parent.add_edge(START, "recommendation")
        parent.add_edge("recommendation", END)
        agent = parent.compile(checkpointer=InMemorySaver())
        service = ChatService.__new__(ChatService)
        service.repository = AsyncMock()
        service.repository.find_owned.return_value = object()
        service.agent = agent
        thread_id = uuid4()
        paused = [
            event
            async for event in service.chat_stream(
                1, ChatRequest(thread_id=thread_id, message="推荐并保存")
            )
        ]
        self.assertTrue(any(event.event == "interrupt" for event in paused))
        resumed = [
            event
            async for event in service.chat_stream(
                1, ChatRequest(thread_id=thread_id, decision={"action": "approve"})
            )
        ]
        self.assertEqual(resumed[-1].event, "done")
        history_service = ChatThreadService.__new__(ChatThreadService)
        history_service.agent = agent
        history_service.repository = service.repository
        history = await history_service.get_history(thread_id, 1)
        self.assertIsNone(history.interrupt)
        answer = history.messages[-1]
        self.assertEqual(answer.additional_info["sources"][source_id], source)
        self.assertEqual(answer.additional_info["plan_items"][0]["plan_id"], "saved")
