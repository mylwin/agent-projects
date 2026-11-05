"""验证 MCP 工厂、证据边界与 Agent 调用上限，不连接真实供应商。"""

import asyncio
import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.tools import load_mcp_tools

from backend.agents.research import research_topic
from backend.config.planner import PlannerSettings
from backend.integrations.map_mcp import MapTools, create_map_mcp
from backend.integrations.place_evidence import collect_places
from backend.schemas.trip import ResearchReport, ToolEvidence
from backend.tests.test_planning import make_request, make_server


@pytest.mark.parametrize(
    "provider,host,key_name",
    [
        ("amap", "mcp.amap.com", "key"),
        ("baidu", "mcp.map.baidu.com", "ak"),
    ],
)
def test_factory(provider: str, host: str, key_name: str) -> None:
    """工厂选择官方 HTTP 地址并正确编码凭据，不混用供应商密钥。"""
    key = "test key&value"
    settings = PlannerSettings(
        "model-test", key, map_provider=provider, baidu_api_key=key
    )
    client = create_map_mcp(settings)
    connection = client.connections[provider]
    assert connection["transport"] == "streamable_http"
    parsed = urlsplit(connection["url"])
    assert parsed.scheme == "https" and parsed.netloc == host and parsed.path == "/mcp"
    assert parse_qs(parsed.query) == {key_name: [key]}


@pytest.mark.parametrize("provider", ["unsupported", "amap", "baidu"])
def test_factory_rejects_invalid_configuration(provider: str) -> None:
    """缺密钥和未知供应商在连接前失败。"""
    with pytest.raises(ValueError):
        create_map_mcp(PlannerSettings("test", "", map_provider=provider))


@pytest.mark.parametrize("provider", ["amap", "baidu"])
def test_streamable_http_session(provider: str) -> None:
    """经过真实 Streamable HTTP 握手、工具发现和调用，网络由 ASGI 替身接管。"""

    async def run() -> None:
        server = make_server(provider)
        server.settings.json_response = True
        server.settings.stateless_http = True
        app = server.streamable_http_app()
        client = create_map_mcp(
            PlannerSettings("test", "test", map_provider=provider, baidu_api_key="test")
        )

        def http_factory(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
            """仅测试中替换传输层，不访问真实服务。"""
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                headers=headers,
                timeout=timeout,
                auth=auth,
            )

        connection = client.connections[provider]
        assert connection["transport"] == "streamable_http"
        connection["url"] = "http://localhost:8000/mcp"
        connection["httpx_client_factory"] = http_factory
        async with server.session_manager.run():
            async with client.session(provider) as session:
                tools = await load_mcp_tools(session)
                name = "maps_text_search" if provider == "amap" else "map_search_places"
                result = await next(
                    tool for tool in tools if tool.name == name
                ).ainvoke(
                    {
                        "type": "tool_call",
                        "id": "test-call",
                        "name": name,
                        "args": {"query": "景点"},
                    }
                )
                assert result.status == "success"
                assert "test-poi" in json.dumps(result.content)

    asyncio.run(run())


def test_collect_places_rejects_summary_and_missing_coordinates() -> None:
    """模型摘要、缺坐标地点和非 JSON 文本都不能变成地点事实。"""
    report = ResearchReport(
        topic="attractions",
        summary="伪造地点，位置 104,30",
        evidence=[
            ToolEvidence(
                tool="map_search_places",
                content=json.dumps(
                    {
                        "results": [
                            {"uid": "missing", "name": "无坐标地点"},
                            {
                                "uid": "bad",
                                "name": "越界地点",
                                "location": {"lng": 999, "lat": 30},
                            },
                        ]
                    }
                ),
                fetched_at=datetime.now(UTC),
            ),
            ToolEvidence(
                tool="map_search_places",
                content="普通文字，没有地点 JSON",
                fetched_at=datetime.now(UTC),
            ),
        ],
    )
    assert collect_places([report], "baidu") == {}


def test_research_without_tools_returns_unknown() -> None:
    """缺少 MCP 天气工具时明确降级，不调用模型编造资料。"""
    report = asyncio.run(
        research_topic(
            "weather",
            make_request(),
            FakeMessagesListChatModel(responses=[]),
            MapTools("amap", []),
        )
    )
    assert not report.evidence and report.warnings


def test_model_call_limit() -> None:
    """反复调用工具的 Agent 在框架的六次模型调用上限停止。"""

    class LoopModel(FakeMessagesListChatModel):
        """始终返回同一个搜索请求。"""

        def bind_tools(self, *args: object, **kwargs: object):
            """保留假消息，让真实 Agent 执行工具循环。"""
            return self

    calls = []

    @tool
    async def maps_text_search(query: str) -> str:
        """仅返回合成搜索结果。"""
        calls.append(query)
        return "{}"

    model = LoopModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "maps_text_search",
                        "id": f"loop-{index}",
                        "args": {"query": "合成搜索"},
                    }
                ],
            )
            for index in range(7)
        ]
    )
    with pytest.raises(ModelCallLimitExceededError):
        asyncio.run(
            research_topic(
                "attractions",
                make_request(),
                model,
                MapTools("amap", [maps_text_search]),
            )
        )
    assert len(calls) == 6


def test_mcp_failure_does_not_expose_credentials() -> None:
    """SDK 的原始连接异常可能带 query 密钥，业务边界必须隐藏。"""
    from contextlib import asynccontextmanager
    from unittest.mock import patch

    from backend.services.planning import generate_trip

    class BrokenClient:
        """模拟含凭据 URL 的底层连接失败。"""

        @asynccontextmanager
        async def session(self, *args: object):
            """连接直接失败，不产生真实请求。"""
            raise RuntimeError("https://mcp.amap.com/mcp?key=private-test-key")
            yield None

    with patch("backend.services.planning.create_map_mcp", return_value=BrokenClient()):
        with pytest.raises(RuntimeError) as caught:
            asyncio.run(generate_trip(make_request(), PlannerSettings("test", "test")))
    assert "private-test-key" not in str(caught.value)
    assert "MCP" in str(caught.value)


def test_weather_can_resolve_coordinates_without_search_tools() -> None:
    """百度天气可先地理编码再按坐标查询，不依赖模型猜测城市代码。"""

    class WeatherModel(FakeMessagesListChatModel):
        """按地理编码、天气、摘要三步返回。"""

        def bind_tools(self, tools, **kwargs):
            """验证天气 Agent 仅拿到定位和天气工具。"""
            assert {item.name for item in tools} == {"map_geocode", "map_weather"}
            return self

    @tool
    async def map_geocode(address: str) -> str:
        """将合成城市转为合成坐标。"""
        return '{"location": {"lng": 104.06, "lat": 30.67}}'

    @tool
    async def map_weather(location: str) -> str:
        """通过先前查到的坐标查询合成天气。"""
        assert location == "104.06,30.67"
        return '{"forecast": [{"date": "2026-11-05", "weather": "晴"}]}'

    model = WeatherModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "map_geocode", "id": "geo", "args": {"address": "成都"}}
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "map_weather",
                        "id": "weather",
                        "args": {"location": "104.06,30.67"},
                    }
                ],
            ),
            AIMessage(content="预报日期未覆盖出行日期，未来天气未知。"),
        ]
    )
    report = asyncio.run(
        research_topic(
            "weather",
            make_request(),
            model,
            MapTools("baidu", [map_geocode, map_weather]),
        )
    )
    assert [item.tool for item in report.evidence] == ["map_geocode", "map_weather"]
    assert "未知" in report.summary


@pytest.mark.parametrize(
    "field,value",
    [
        ("uid", None),
        ("name", None),
        ("location", {"lng": None, "lat": 30.67}),
        ("location", {"lng": "不是数字", "lat": 30.67}),
        ("coord_type", "未知坐标系"),
    ],
)
def test_invalid_external_place_is_rejected(field: str, value: object) -> None:
    """外部字段为空或无效时拒绝候选，不构造字段不完整的地点。"""
    item: dict[str, object] = {
        "uid": "test-poi",
        "name": "合成地点",
        "address": "测试地址",
        "location": {"lng": 104.06, "lat": 30.67},
    }
    item[field] = value
    report = ResearchReport(
        topic="attractions",
        summary="测试",
        evidence=[
            ToolEvidence(
                tool="map_search_places",
                content=json.dumps(item),
                fetched_at=datetime.now(UTC),
            ),
        ],
    )
    assert collect_places([report], "baidu") == {}
