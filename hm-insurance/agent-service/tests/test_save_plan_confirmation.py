import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import TypedDict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agents.tools import save_insurance_plan
from app.modules.insurance_plan.schemas import InsurancePlanCreate, InsurancePlanData


class ConfirmationState(TypedDict, total=False):
    result: dict[str, str]


class SavePlanConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupt_resume_approves_or_rejects_before_database_write(self):
        plan = InsurancePlanCreate(
            plan_name="测试方案",
            items=[
                {"product_id": 1, "product_name": "测试产品", "category": "medical"}
            ],
        )
        plan_id = uuid4()
        item_id = uuid4()
        now = datetime.now(timezone.utc)
        saved_plan = InsurancePlanData(
            id=plan_id,
            user_id=7,
            plan_name=plan.plan_name,
            status="uninsured",
            version=1,
            created_at=now,
            updated_at=now,
            items=[
                {
                    "id": item_id,
                    "plan_id": plan_id,
                    "product_id": 1,
                    "priority": 1,
                    "recommendation_reason": None,
                    "annual_premium_budget": None,
                    "status": "uninsured",
                    "product": {"id": 1, "name": "目录产品", "category": "medical"},
                }
            ],
        )
        for decision, status in [
            ({"action": "reject", "reject_reason": "  预算太高  "}, "rejected"),
            ({"action": "reject"}, "rejected"),
            ({"action": "invalid"}, "not_saved"),
            ({"action": "approve"}, "saved"),
        ]:
            with self.subTest(decision=decision):

                async def save(state):
                    result = await save_insurance_plan.coroutine(
                        plan=plan,
                        runtime=SimpleNamespace(context=SimpleNamespace(user_id=7)),
                    )
                    return {"result": result}

                builder = StateGraph(ConfirmationState)
                builder.add_node("save", save)
                builder.add_edge(START, "save")
                builder.add_edge("save", END)
                agent = builder.compile(checkpointer=InMemorySaver())
                config = {"configurable": {"thread_id": str(uuid4())}}
                factory = MagicMock()
                factory.return_value.__aenter__ = AsyncMock(return_value=object())
                factory.return_value.__aexit__ = AsyncMock(return_value=False)
                service = MagicMock()
                service.create_plan = AsyncMock(return_value=saved_plan)
                with (
                    patch("app.agents.tools.AsyncSessionFactory", factory),
                    patch(
                        "app.agents.tools.InsurancePlanService", return_value=service
                    ),
                    patch("app.agents.tools.get_stream_writer") as get_writer,
                ):
                    paused = await agent.ainvoke({}, config)
                    payload = paused["__interrupt__"][0].value
                    json.dumps(payload)
                    self.assertEqual(payload["action"], ["approve", "reject"])
                    factory.assert_not_called()
                    completed = await agent.ainvoke(Command(resume=decision), config)
                    result = completed["result"]
                    self.assertEqual(result["status"], status)
                    if status == "saved":
                        service.create_plan.assert_awaited_once_with(
                            user_id=7, data=plan
                        )
                        self.assertEqual(result["plan_id"], str(plan_id))
                        get_writer.return_value.assert_called_once_with(
                            {
                                "type": "additional_info",
                                "data": {
                                    "plan_items": [
                                        {
                                            **saved_plan.items[0].model_dump(mode="json"),
                                            "product_name": "目录产品",
                                        }
                                    ]
                                },
                            }
                        )
                    else:
                        factory.assert_not_called()
                        get_writer.assert_not_called()
                    if decision.get("reject_reason"):
                        self.assertEqual(result["reject_reason"], "预算太高")
