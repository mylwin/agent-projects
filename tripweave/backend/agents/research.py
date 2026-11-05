"""景点、天气、住宿分别使用 LangChain Agent 调用官方 MCP 工具。"""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from backend.agents.prompts import ResearchTopic, get_research_prompt
from backend.errors import PlanningError
from backend.integrations.map_mcp import MapTools
from backend.schemas.trip import ResearchReport, ToolEvidence, TripRequest

# 显式授权只读查询工具，不把分享地图、打车等操作工具交给研究 Agent。
SEARCH_TOOLS = {
    "maps_text_search",
    "maps_search_detail",
    "maps_geo",
    "map_search_places",
    "map_place_details",
    "map_geocode",
}
WEATHER_TOOLS = {"maps_weather", "map_weather"}
GEOCODE_TOOLS = {"maps_geo", "map_geocode"}
LIMIT_MESSAGE_MARKERS = ("Model call limit", "Tool call limit")


def _normalize_location(value: object) -> str | None:
    """
    把天气工具的数组或对象坐标转换为供应商要求的“经度,纬度”字符串。

    :param value: 模型传入的 location 参数。
    :return: 可用的坐标字符串；已经是字符串或无法转换时返回 None。
    """
    if isinstance(value, (list, tuple)) and len(value) == 2:
        longitude, latitude = value
    elif isinstance(value, dict):
        longitude = value.get("lng", value.get("longitude"))
        latitude = value.get("lat", value.get("latitude"))
    else:
        return None
    if longitude is None or latitude is None:
        return None
    try:
        return f"{float(longitude)},{float(latitude)}"
    except (TypeError, ValueError):
        return None


class NormalizeWeatherLocationMiddleware(AgentMiddleware[Any, None]):
    """
    在天气工具执行前把数组或对象坐标归一化为字符串。

    模型可能忽略提示词，把 location 传成 `[lng, lat]`；供应商只接受
    `"lng,lat"`。这里在调用前转换，避免同一参数错误反复消耗调用次数。
    """

    def __init__(self, tool_names: set[str]) -> None:
        """
        :param tool_names: 需要归一化 location 的天气工具名称。
        """
        super().__init__()
        self.tool_names = tool_names

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """
        归一化天气位置参数，其他工具和参数保持原样。

        :param request: 工具调用请求。
        :param handler: 执行底层工具的异步回调。
        :return: 底层工具返回的消息或命令。
        """
        if request.tool_call["name"] not in self.tool_names:
            return await handler(request)
        args = dict(request.tool_call["args"])
        location = _normalize_location(args.get("location"))
        if location is None:
            return await handler(request)
        args["location"] = location
        return await handler(
            request.override(tool_call={**request.tool_call, "args": args})
        )


async def research_topic(
    topic: ResearchTopic, request: TripRequest, model: BaseChatModel, maps: MapTools
) -> ResearchReport:
    """
    一个主题运行一个独立 Agent，共享模型连接但各自保有消息和调用上限。

    :param topic: 研究主题，景点、天气或住宿。
    :param request: 已校验的旅行需求。
    :param model: 共享的聊天模型，各主题使用独立的 Agent 状态。
    :param maps: 当前供应商在同一 MCP 会话中发现的工具。
    :return: 研究摘要、成功工具证据与缺失警告；无可用工具时返回缺失说明。
    :raises PlanningError: Agent 执行失败；达到调用上限时会结束该主题并写入警告。
    """
    # 允许的工具范围：如果主题是天气，则只允许天气工具；否则只允许搜索工具。
    allowed = WEATHER_TOOLS | GEOCODE_TOOLS if topic == "weather" else SEARCH_TOOLS

    # 筛选得到允许运行的工具
    tools = [tool for tool in maps.tools if tool.name in allowed]
    # 如果工具不存在，或者主题为天气时没有任何工具
    if not tools or (
        topic == "weather" and not any(tool.name in WEATHER_TOOLS for tool in tools)
    ):
        return ResearchReport(
            topic=topic,
            summary="未提供该主题的查询工具。",
            warnings=[f"{topic}：地图 MCP 没有提供所需的只读工具。"],
        )
    # 两种中间件各自扩展框架状态，按公共接口声明，避免被推断为第一种状态。
    # 达到上限时结束当前研究，保留已有工具证据，不让单个主题拖垮整轮规划。
    middleware: list[AgentMiddleware[Any, None]] = [
        ModelCallLimitMiddleware(run_limit=6, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=8, exit_behavior="end"),
    ]
    if topic == "weather":
        middleware.append(NormalizeWeatherLocationMiddleware(WEATHER_TOOLS))
    # 创建研究 Agent
    agent = create_agent(
        model=model,
        tools=tools,
        name=topic,
        system_prompt=get_research_prompt(topic, maps.provider),
        middleware=middleware,
    )
    try:
        # agent 执行结果
        state = await agent.ainvoke(
            {"messages": [HumanMessage(content=request.model_dump_json(indent=2))]},
            config={
                "recursion_limit": 40,
                "callbacks": model.callbacks,
                "tags": [f"agent:{topic}"],
            },
        )
    except Exception as exc:
        raise PlanningError(f"{topic} 研究", exc) from None

    # 遍历结果消息，生成结构化证据 工具调用警告 总结信息
    evidence = []
    warnings = []
    summary = ""
    for message in state["messages"]:
        if isinstance(message, ToolMessage):
            if message.status == "error":
                warnings.append(
                    f"{topic}：工具 {message.name} 查询失败，未作为事实使用。"
                )
                continue
            artifact = message.artifact or {}
            evidence.append(
                ToolEvidence(
                    tool=message.name or "unknown",
                    content=message.content
                    if isinstance(message.content, str)
                    else json.dumps(message.content, ensure_ascii=False),
                    structured_content=artifact.get("structured_content"),
                    fetched_at=datetime.now(UTC),
                )
            )
        elif isinstance(message, AIMessage) and not message.tool_calls:
            summary = message.text
    if summary.startswith(LIMIT_MESSAGE_MARKERS):
        summary = "研究 Agent 达到调用上限，未完成最终总结。"
        warnings.append(f"{topic}：达到调用上限，已保留此前的工具结果。")
    if not evidence or (
        topic == "weather" and not any(item.tool in WEATHER_TOOLS for item in evidence)
    ):
        summary = "没有成功的工具查询，资料未知。"
        warnings.append(f"{topic}：未取得工具证据，不采用模型自行给出的事实。")
    elif not summary.strip():
        summary = "已取得工具结果，但模型未给出研究摘要。"
        warnings.append(f"{topic}：模型未输出最终摘要，已保留工具结果。")
    return ResearchReport(
        topic=topic, summary=summary, evidence=evidence, warnings=warnings
    )
