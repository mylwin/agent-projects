"""用真实 LangChain 和 HTTP 协议替身验证主流程，不调用付费服务。"""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from backend.config.planner import PlannerSettings
from backend.integrations.chat_model import create_chat_model
from backend.integrations.map_client import create_map_client
from backend.schemas.trip import PlanResult, TripRequest
from backend.services.planning import generate_trip, plan_trip

ROOT = Path(__file__).resolve().parents[2]


def make_request(days: int = 1) -> TripRequest:
    """直接复用 CLI 样例。"""
    data = json.loads((ROOT / "examples/trip-request.json").read_text())
    data["day_count"] = days
    return TripRequest.model_validate(data)


def make_draft(days: int = 1) -> dict:
    """构造只引用合成测试地点的草稿。"""
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


class SupplierStub:
    """模拟两家地图和模型的 HTTP 响应，记录调用次数。"""

    def __init__(self, draft: dict | None = None, empty: bool = False):
        """指定模型响应及候选池边界。"""
        self.draft = draft or make_draft()
        self.empty = empty
        self.model_calls = 0
        self.map_calls = 0

    def respond(self, request: httpx.Request) -> httpx.Response:
        """接收真实 SDK 构造的 HTTP 请求。"""
        if request.url.path.endswith("/chat/completions"):
            self.model_calls += 1
            body = json.loads(request.content)
            assert body["stream"] is True
            assert body["tools"][0]["function"]["name"] == "TravelDraft"
            assert "test-poi" in body["messages"][1]["content"]
            chunk = {
                "id": "test",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "TravelDraft",
                                        "arguments": json.dumps(self.draft),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n",
            )
        self.map_calls += 1
        if request.url.host == "restapi.amap.com":
            if request.url.path.endswith("/district"):
                return httpx.Response(
                    200,
                    json={
                        "status": "1",
                        "districts": [
                            {"name": "成都市", "level": "city", "adcode": "510100"}
                        ],
                    },
                )
            assert request.url.params["city"] == "510100"
            assert request.url.params["citylimit"] == "true"
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "pois": []
                    if self.empty
                    else [
                        {
                            "id": "test-poi",
                            "name": "合成测试地点",
                            "address": "测试地址",
                            "adcode": "510105",
                            "location": "104.06,30.67",
                        }
                    ],
                },
            )
        if request.url.path == "/api_region_search/v1/":
            return httpx.Response(
                200, json={"status": 0, "districts": [{"name": "成都市", "level": 2}]}
            )
        assert request.url.params["region"] == "成都市"
        assert request.url.params["ret_coordtype"] == "gcj02ll"
        return httpx.Response(
            200,
            json={
                "status": 0,
                "results": []
                if self.empty
                else [
                    {
                        "uid": "test-poi",
                        "name": "合成测试地点",
                        "address": "测试地址",
                        "location": {"lng": 104.06, "lat": 30.67},
                    }
                ],
            },
        )


async def execute(
    stub: SupplierStub, provider: str = "amap", days: int = 1
) -> PlanResult:
    """经过模型 SDK、地图适配器、规划和装配的完整链路。"""
    async with httpx.AsyncClient(transport=httpx.MockTransport(stub.respond)) as http:
        return await plan_trip(
            make_request(days),
            create_chat_model(PlannerSettings("test-model-key", "test-map-key"), http),
            create_map_client(provider, "test-map-key", http),
            lambda _: None,
        )


@pytest.mark.parametrize("provider", ["amap", "baidu"])
@pytest.mark.parametrize("days", [1, 3, 5])
def test_complete_flow(provider: str, days: int) -> None:
    """两家地图、1/3/5 天均只调用一次模型，结果字段对应前端。"""
    stub = SupplierStub(make_draft(days))
    result = asyncio.run(execute(stub, provider, days))
    assert stub.model_calls == 1 and stub.map_calls == 4
    assert len(result.trip.days) == days
    assert result.places[0].source == provider
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
    with pytest.raises(ValueError):
        asyncio.run(execute(SupplierStub(draft)))


def test_empty_pool_skips_model() -> None:
    """没有地点时停止，不消费模型调用。"""
    stub = SupplierStub(empty=True)
    with pytest.raises(ValueError, match="没有查询到"):
        asyncio.run(execute(stub))
    assert stub.model_calls == 0


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


def test_configuration_and_error_privacy() -> None:
    """配置和 HTTP 错误均不暴露密钥。"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="MODEL_API_KEY"):
            PlannerSettings.from_env()
    assert "private-key" not in repr(PlannerSettings("private-key", "private-key"))

    async def fail() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(403))
        ) as http:
            await create_map_client("amap", "private-key", http).resolve_region("成都")

    with pytest.raises(RuntimeError) as caught:
        asyncio.run(fail())
    assert "private-key" not in str(caught.value)


def test_total_timeout_covers_maps() -> None:
    """整轮超时包括地图阶段。"""

    async def slow(*args: object) -> None:
        await asyncio.sleep(1)

    with patch("backend.services.planning.plan_trip", side_effect=slow):
        with pytest.raises(TimeoutError):
            asyncio.run(
                generate_trip(
                    make_request(),
                    PlannerSettings("test", "test", planner_timeout_seconds=0.01),
                )
            )


def test_cli_stdout_contains_only_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI 的结果可直接重定向保存，阶段输出与 JSON 分离。"""
    from backend.__main__ import main

    result = asyncio.run(execute(SupplierStub()))

    async def generate(*args: object) -> PlanResult:
        args[2]("测试进度")
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


def test_cli_invalid_input_skips_services(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """无法读取请求时以非零退出，不进入外部服务。"""
    from backend.__main__ import main

    monkeypatch.setattr("sys.argv", ["backend", str(ROOT / "examples/missing.json")])
    assert main() == 1
    output = capsys.readouterr()
    assert output.out == "" and "输入或配置错误" in output.err
