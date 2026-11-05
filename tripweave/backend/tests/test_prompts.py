"""通过 MCP 参数校验和行程模型验证 few-shot，不依赖真实模型是否遵循提示。"""

import asyncio
import json
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from backend.agents.prompts import (
    PLANNER_SYSTEM_PROMPT,
    ResearchTopic,
    get_research_prompt,
)
from backend.schemas.trip import Place, TravelDraft, TripRequest
from backend.services.planning import validate_draft


def schema_server(provider: str) -> FastMCP:
    """按已使用的地图参数定义测试工具，重点保留日志中出错的字符串类型。"""
    server = FastMCP("提示词参数验证")
    if provider == "baidu":

        async def search(query: str, region: str) -> str:
            """按百度关键词与区域检索合成数据。"""
            return "合成搜索结果"

        async def geocode(
            address: str, city: str, is_chinese_mainland: str = "true"
        ) -> str:
            """字符串标志不能被布尔值替代。"""
            return '{"location":{"lng":104.06,"lat":30.67}}'

        async def weather(location: str) -> str:
            """天气位置是一个坐标字符串，不能使用数组。"""
            assert location == "104.06,30.67"
            return "合成天气结果"

        server.add_tool(search, name="map_search_places")
        server.add_tool(geocode, name="map_geocode")
        server.add_tool(weather, name="map_weather")
    else:

        async def amap_search(keywords: str, city: str) -> str:
            """高德使用 keywords/city，与百度参数分开。"""
            return "合成搜索结果"

        async def amap_weather(city: str) -> str:
            """高德天气示例直接使用工具接受的城市字段。"""
            return "合成天气结果"

        server.add_tool(amap_search, name="maps_text_search")
        server.add_tool(amap_weather, name="maps_weather")
    return server


@pytest.mark.parametrize("provider", ["amap", "baidu"])
@pytest.mark.parametrize("topic", ["attractions", "weather", "hotels"])
def test_few_shot_calls_pass_mcp_validation(
    provider: str, topic: ResearchTopic
) -> None:
    """提取模型实际收到的调用示例，送入真实 MCP 校验，防止示例本身类型错误。"""
    prompt = get_research_prompt(topic, provider)
    calls = re.findall(
        r"^### 调用 ([a-z_]+)\n\n```json\n(.*?)\n```", prompt, re.MULTILINE | re.DOTALL
    )
    assert calls

    async def run() -> None:
        async with create_connected_server_and_client_session(
            schema_server(provider)
        ) as session:
            for tool_name, arguments in calls:
                response = await session.call_tool(tool_name, json.loads(arguments))
                assert not response.isError, response.content

    asyncio.run(run())


@pytest.mark.parametrize(
    "tool_name,arguments",
    [
        (
            "map_geocode",
            {"address": "示例市", "city": "示例市", "is_chinese_mainland": True},
        ),
        ("map_weather", {"location": [104.06, 30.67]}),
    ],
)
def test_logged_invalid_types_are_rejected(tool_name: str, arguments: dict) -> None:
    """确认测试工具确实能复现用户日志中的两类错误，避免宽松替身让错误示例通过。"""

    async def run() -> None:
        async with create_connected_server_and_client_session(
            schema_server("baidu")
        ) as session:
            response = await session.call_tool(tool_name, arguments)
            assert response.isError
            assert "string" in str(response.content)

    asyncio.run(run())


def test_planner_few_shot_passes_business_validation() -> None:
    """Planner 的示例也必须满足真实草稿模型、日期、时间和候选引用约束。"""
    match = re.search(r"```json\n(.*?)\n```", PLANNER_SYSTEM_PROMPT, re.DOTALL)
    assert match is not None
    example = match.group(1)
    draft = TravelDraft.model_validate_json(example)
    request = TripRequest(
        destination="示例市",
        start_date=draft.days[0].date,
        day_count=1,
        travelers=2,
        budget=Decimal("3000"),
    )
    places = {
        place_id: Place(
            id=place_id,
            name="示例地点",
            address="示例地址",
            longitude=104,
            latitude=30,
            fetched_at=datetime.now(UTC),
        )
        for place_id in ["example-park", "example-food"]
    }
    validate_draft(draft, request, places)
