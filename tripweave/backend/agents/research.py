"""景点、天气、住宿分别使用 LangChain Agent 调用官方 MCP 工具。"""

import json
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
    :raises PlanningError: Agent 执行失败或超过模型、工具调用上限。
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
    middleware: list[AgentMiddleware[Any, None]] = [
        ModelCallLimitMiddleware(run_limit=6, exit_behavior="error"),
        ToolCallLimitMiddleware(run_limit=8, exit_behavior="error"),
    ]
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
    if not evidence or (
        topic == "weather" and not any(item.tool in WEATHER_TOOLS for item in evidence)
    ):
        summary = "没有成功的工具查询，资料未知。"
        warnings.append(f"{topic}：未取得工具证据，不采用模型自行给出的事实。")
    return ResearchReport(
        topic=topic, summary=summary, evidence=evidence, warnings=warnings
    )
