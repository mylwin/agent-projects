"""通过真实 MCP 会话、LangChain 多 Agent 和模型 HTTP 替身验证主流程。"""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from backend.config.planner import PlannerSettings
from backend.integrations.chat_model import create_chat_model
from backend.integrations.map_mcp import MapTools
from backend.schemas.trip import PlanResult, TripRequest
from backend.services.planning import generate_trip, plan_trip

ROOT = Path(__file__).resolve().parents[2]


def make_request(days: int = 1) -> TripRequest:
    """直接复用 CLI 样例。"""
    data = json.loads((ROOT / "examples/trip-request.json").read_text())
    data["day_count"] = days
    return TripRequest.model_validate(data)


def make_draft(days: int = 1) -> dict:
    """构造只引用合成 MCP 地点的草稿。"""
    return {
        "days": [
            {
                "date": f"2027-03-{12 + i:02d}",
                "title": "城市慢游",
                "activities": [
                    {
                        "time": "10:00",
                        "title": "参观测试地点",
                        "description": "仅用于自动验证",
                        "place_id": "test-poi",
                    }
                ],
            }
            for i in range(days)
        ]
    }


class ModelStub:
    """模拟 OpenAI 兼容流式响应，三个研究 Agent 各调用一次 MCP 后总结。"""

    def __init__(self, provider: str = "amap", draft: dict | None = None):
        """记录实际模型请求以验证角色隔离和调用数量。"""
        self.provider = provider
        self.draft = draft or make_draft()
        self.calls: list[dict] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        """由真实模型 SDK 请求消息决定工具调用或结构化结果。"""
        body = json.loads(request.content)
        self.calls.append(body)
        assert body["stream"] is True
        available = {tool["function"]["name"] for tool in body["tools"]}
        assert "share_map" not in available
        if "TravelDraft" in available:
            function, arguments = "TravelDraft", self.draft
            assert "test-poi" in body["messages"][1]["content"]
            assert "研究资料" in body["messages"][1]["content"]
        elif any(message["role"] == "tool" for message in body["messages"]):
            function, arguments = None, {}
        else:
            weather = "查询目的地天气" in body["messages"][0]["content"]
            if weather:
                function = "maps_weather" if self.provider == "amap" else "map_weather"
                assert available == {function}
                arguments = {"city": "成都"}
            else:
                function = (
                    "maps_text_search"
                    if self.provider == "amap"
                    else "map_search_places"
                )
                arguments = {
                    "query": "酒店"
                    if "住宿候选" in body["messages"][0]["content"]
                    else "景点"
                }
        delta: dict[str, object] = {"role": "assistant"}
        if function:
            delta["tool_calls"] = [
                {
                    "index": 0,
                    "id": f"call-{len(self.calls)}",
                    "type": "function",
                    "function": {"name": function, "arguments": json.dumps(arguments)},
                }
            ]
        else:
            delta["content"] = "已查询工具，未覆盖的日期和价格保持未知。"
        chunk = {
            "id": "test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": "tool_calls" if function else "stop",
                }
            ],
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n",
        )


def make_server(
    provider: str = "amap", empty: bool = False, fail_weather: bool = False
) -> FastMCP:
    """建立内存 MCP 服务，经过 SDK 的初始化、工具发现和调用协议。"""
    server = FastMCP("合成测试地图")

    async def search(query: str) -> dict:
        """搜索合成地点或住宿。"""
        if empty:
            return {"results": []}
        is_hotel = query == "酒店"
        if provider == "amap":
            return {
                "pois": [
                    {
                        "id": "test-hotel" if is_hotel else "test-poi",
                        "name": "合成测试地点",
                        "address": "测试地址",
                        "location": "104.06,30.67",
                    }
                ]
            }
        return {
            "results": [
                {
                    "uid": "test-hotel" if is_hotel else "test-poi",
                    "name": "合成测试地点",
                    "address": "测试地址",
                    "location": {"lng": 104.06, "lat": 30.67},
                }
            ]
        }

    async def weather(city: str) -> dict:
        """查询合成天气；可以模拟供应商失败。"""
        if fail_weather:
            raise ValueError("合成天气服务不可用")
        return {"city": city, "forecast": [{"date": "2026-11-05", "weather": "晴"}]}

    async def share_map() -> str:
        """不应暴露给研究 Agent 的分享工具。"""
        raise AssertionError("禁止调用")

    server.add_tool(
        search, name="maps_text_search" if provider == "amap" else "map_search_places"
    )
    server.add_tool(
        weather, name="maps_weather" if provider == "amap" else "map_weather"
    )
    server.add_tool(share_map)
    return server


async def execute(
    stub: ModelStub, days: int = 1, *, empty: bool = False, fail_weather: bool = False
) -> PlanResult:
    """通过完整 MCP 协议及模型 SDK 调用全部 Agent。"""
    server = make_server(stub.provider, empty, fail_weather)
    async with create_connected_server_and_client_session(server) as session:
        tools = await load_mcp_tools(session)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(stub.respond)
        ) as http:
            return await plan_trip(
                make_request(days),
                create_chat_model(
                    PlannerSettings("test-model-key", "test-map-key"), http
                ),
                MapTools(stub.provider, tools),
                lambda _: None,
            )


@pytest.mark.parametrize("provider", ["amap", "baidu"])
@pytest.mark.parametrize("days", [1, 3, 5])
def test_complete_flow(provider: str, days: int) -> None:
    """两家地图和不同天数均通过三个研究 Agent 加 Planner。"""
    stub = ModelStub(provider, make_draft(days))
    result = asyncio.run(execute(stub, days))
    assert len(stub.calls) == 7
    assert len(result.trip.days) == days
    assert [report.topic for report in result.research] == [
        "attractions",
        "weather",
        "hotels",
    ]
    assert all(len(report.evidence) == 1 for report in result.research)
    assert result.places[0].source == provider
    assert result.places[0].coordinate_system == (
        "GCJ-02" if provider == "amap" else "BD-09"
    )
    activity = result.trip.days[0].activities[0]
    assert activity.placeId == result.places[0].id
    assert activity.cost is None and activity.point is None
    encoded = result.model_dump_json()
    assert "test-model-key" not in encoded and "test-map-key" not in encoded
    assert PlanResult.model_validate_json(encoded) == result
    fixture = json.loads((ROOT / "frontend/src/data/trip.json").read_text())
    assert set(fixture) - {"messages"} == set(result.trip.model_dump())
    assert set(fixture["days"][0]) == set(result.trip.days[0].model_dump())
    assert set(fixture["days"][0]["activities"][0]) <= set(activity.model_dump())


@pytest.mark.parametrize("invalid", ["date", "place", "time"])
def test_rejects_invalid_draft(invalid: str) -> None:
    """拒绝错位日期、虚构地点、重复时间。"""
    draft = make_draft()
    day = draft["days"][0]
    if invalid == "date":
        day["date"] = "2027-03-13"
    elif invalid == "place":
        day["activities"][0]["place_id"] = "invented"
    else:
        day["activities"].append(day["activities"][0].copy())
    with pytest.RaisesGroup(ValueError, flatten_subgroups=True):
        asyncio.run(execute(ModelStub(draft=draft)))


def test_empty_pool_skips_planner() -> None:
    """没有工具地点证据时不调用最终 Planner。"""
    stub = ModelStub()
    with pytest.RaisesGroup(
        pytest.RaisesExc(ValueError, match="没有查询到"), flatten_subgroups=True
    ):
        asyncio.run(execute(stub, empty=True))
    assert len(stub.calls) == 6


def test_weather_error_keeps_unknown() -> None:
    """天气工具错误不会作为成功查询，仍可生成有缺失说明的行程。"""
    result = asyncio.run(execute(ModelStub(), fail_weather=True))
    report = result.research[1]
    assert not report.evidence
    assert "未知" in report.summary
    assert any("查询失败" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    "field,value",
    [
        ("destination", ""),
        ("day_count", 6),
        ("day_count", True),
        ("travelers", 0),
        ("budget", "-1"),
        ("budget", "NaN"),
    ],
)
def test_input_constraints(field: str, value: object) -> None:
    """先校验需求，再调用供应商。"""
    data = make_request().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        TripRequest.model_validate(data)


def test_cli_stdout_contains_only_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """结果可直接重定向保存，阶段输出与 JSON 分离。"""
    from backend.__main__ import main

    result = asyncio.run(execute(ModelStub()))

    async def generate(
        request: TripRequest,
        settings: PlannerSettings,
        on_progress: Callable[[str], None],
        callback: AsyncCallbackHandler | None = None,
    ) -> PlanResult:
        """按真实入口的签名验证进度回调。"""
        on_progress("测试进度")
        return result

    monkeypatch.setattr(
        "sys.argv", ["backend", str(ROOT / "examples/trip-request.json")]
    )
    monkeypatch.setattr("backend.__main__.generate_trip", generate)
    monkeypatch.setattr(
        PlannerSettings, "from_env", lambda: PlannerSettings("test", "test")
    )
    assert main() == 0
    output = capsys.readouterr()
    assert PlanResult.model_validate_json(output.out) == result
    assert "测试进度" in output.err


def test_total_timeout_covers_mcp() -> None:
    """整轮超时覆盖 MCP 连接，超时后结束会话。"""
    from contextlib import asynccontextmanager

    class SlowClient:
        """模拟无法在预算内连接的 MCP 服务。"""

        @asynccontextmanager
        async def session(self, *args: object):
            """会话创建也受整轮超时约束。"""
            await asyncio.sleep(1)
            yield None

    with patch("backend.services.planning.create_map_mcp", return_value=SlowClient()):
        with pytest.raises(TimeoutError):
            asyncio.run(
                generate_trip(
                    make_request(),
                    PlannerSettings("test", "test", planner_timeout_seconds=0.01),
                )
            )
