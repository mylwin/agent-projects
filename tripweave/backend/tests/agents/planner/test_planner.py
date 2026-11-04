"""使用真实 LangChain 循环与替身服务验证首次规划。"""

import json
import unittest
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Self
from unittest.mock import patch

import httpx
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from backend.config.planner import PlannerSettings
from backend.integrations.amap import AmapClient
from backend.schemas.planner_input import PlannerInput
from backend.schemas.run_event import AgentEvent, MessageDelta
from backend.services.planning import plan_trip, prepare_requirements


class ToolCallingModel(FakeMessagesListChatModel):
    """
    可绑定工具的消息替身，实际执行框架的模型与工具循环。
    """

    def bind_tools(self, tools: Sequence[object], **kwargs: object) -> Self:
        """
        接受框架注册的工具，由预设消息决定工具调用。

        :param self: 当前消息模型。
        :param tools: 框架注册的工具定义。
        :param kwargs: 框架传入的工具绑定选项。
        :return: 保持预设响应顺序的模型本身。
        """
        return self


def make_request() -> PlannerInput:
    """
    读取可直接用于 CLI 的请求示例，避免两套输入样本漂移。

    :return: 将运行天数缩为一天的完整请求。
    """
    path = (
        Path(__file__).resolve().parents[3]
        / "agents/planner/examples/generate.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    data["requirements"]["day_count"] = 1
    return PlannerInput.model_validate(data)


def draft_message(place_id: str = "test-poi", day: str = "2027-03-12") -> AIMessage:
    """
    构造模型通过结构化工具提交的结果。

    :param place_id: 活动引用的地点 ID，可传入错误 ID 验证拒绝逻辑。
    :param day: 活动日期，可传入错误日期验证区间保护。
    :return: LangChain 结构化输出工具调用消息。
    """
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "TravelDraft",
                "id": "draft-call",
                "args": {
                    "days": [
                        {
                            "date": day,
                            "title": "城市慢游",
                            "activities": [
                                {
                                    "time": "10:00",
                                    "title": "游览测试地点",
                                    "description": "仅用于测试的安排",
                                    "place_id": place_id,
                                }
                            ],
                        }
                    ],
                },
            }
        ],
    )


def amap_response(request: httpx.Request) -> httpx.Response:
    """
    替代真实高德请求，仅使用显式测试地点。

    :param request: HTTPX 构造的供应商请求。
    :return: 行政区或地点的合成测试响应。
    """
    if request.url.path.endswith("district"):
        return httpx.Response(
            200,
            json={
                "status": "1",
                "districts": [
                    {"name": "成都市", "level": "city", "adcode": "510100"},
                ],
            },
        )
    assert request.url.params["city"] == "510100"
    assert request.url.params["citylimit"] == "true"
    return httpx.Response(
        200,
        json={
            "status": "1",
            "pois": [
                {
                    "id": "test-poi",
                    "name": "合成测试地点",
                    "address": [],
                    "location": "104.06,30.67",
                    "adcode": "510105",
                }
            ],
        },
    )


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    """
    验证工具执行、输出核对与无需付费调用的失败边界。
    """

    async def test_program_queries_places_and_model_returns_draft(self) -> None:
        """
        程序完成地点查询后，模型单次调用返回结构化行程。

        :param self: 当前异步测试实例。
        """
        model = ToolCallingModel(responses=[draft_message()])
        events: list[AgentEvent] = []
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(amap_response)
        ) as http:
            result = await plan_trip(
                make_request(),
                model,
                AmapClient("test-key", http),
                on_event=events.append,
            )
        self.assertEqual(result.places[0].id, "test-poi")
        self.assertEqual(result.places[0].name, "合成测试地点")
        self.assertEqual(result.requirements.end_date, date(2027, 3, 12))
        self.assertTrue(result.warnings)
        self.assertIn("成都", result.reply)
        self.assertTrue(any(isinstance(event, MessageDelta) for event in events))
        self.assertNotIn("test-key", result.model_dump_json())

    async def test_rejects_unqueried_place_and_wrong_date(self) -> None:
        """
        模型即使输出格式正确，也不能引用假地点或改动旅行日期。

        :param self: 当前异步测试实例。
        """
        for message in (draft_message("invented"), draft_message(day="2027-03-13")):
            model = ToolCallingModel(responses=[message])
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(amap_response)
            ) as http:
                with self.assertRaises(ValueError):
                    await plan_trip(make_request(), model, AmapClient("test-key", http))

    async def test_empty_candidate_pool_is_rejected(self) -> None:
        """
        供应商没有返回任何候选地点时直接报错，不调用模型。

        :param self: 当前异步测试实例。
        """

        def empty_response(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("district"):
                return amap_response(request)
            return httpx.Response(200, json={"status": "1", "pois": []})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(empty_response)
        ) as http:
            with self.assertRaisesRegex(ValueError, "没有查询到可用地点"):
                await plan_trip(
                    make_request(),
                    ToolCallingModel(responses=[draft_message()]),
                    AmapClient("test-key", http),
                )

    async def test_supplier_error_does_not_expose_key(self) -> None:
        """
        HTTP 错误不得向调用方泄露带密钥的 URL。

        :param self: 当前异步测试实例。
        """
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(403))
        ) as http:
            with self.assertRaises(RuntimeError) as caught:
                await AmapClient("private-test-key", http).resolve_region("成都")
        self.assertNotIn("private-test-key", str(caught.exception))

    async def test_wrong_region_and_ambiguous_destination(self) -> None:
        """
        拒绝其他城市的地点，以及无法唯一确定的行政区域。

        :param self: 当前异步测试实例。
        """
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(amap_response)
        ) as http:
            client = AmapClient("test-key", http)
            with self.assertRaisesRegex(ValueError, "唯一解析"):
                await client.resolve_region("朝阳")
            # 替身仍返回成都地点，不应纳入北京的候选集合。
            with patch.object(
                client,
                "_get",
                return_value={
                    "pois": [
                        {
                            "id": "wrong-city",
                            "name": "合成地点",
                            "location": "104.06,30.67",
                            "adcode": "510105",
                        }
                    ],
                },
            ):
                self.assertEqual(await client.search_places("110000", "景点"), [])

    def test_missing_input_and_date_derivation(self) -> None:
        """
        信息不足时先报错，有明确日期区间时可推导天数。

        :param self: 当前测试实例。
        """
        with self.assertRaisesRegex(ValueError, "请补齐"):
            prepare_requirements(PlannerInput(operation="generate", requirements={}))
        data = make_request().model_dump(mode="json")
        data["requirements"].update(day_count=None, end_date="2027-03-14")
        request = PlannerInput.model_validate(data)
        self.assertEqual(prepare_requirements(request).day_count, 3)
        self.assertIsNone(request.requirements.day_count)

    def test_credentials_are_required_and_hidden(self) -> None:
        """
        凭证缺失明确提示变量名，配置展示不包含密钥。

        :param self: 当前测试实例。
        """
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "MODEL_API_KEY"):
                PlannerSettings.from_env()
        settings = PlannerSettings("private-model-key", "private-map-key")
        self.assertNotIn("private-model-key", repr(settings))
        self.assertNotIn("private-map-key", repr(settings))
