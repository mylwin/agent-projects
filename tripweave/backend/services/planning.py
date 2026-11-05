"""顺序执行景点、天气、住宿研究，再由 Planner 汇总、校验和装配结果。"""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_mcp_adapters.tools import load_mcp_tools

from backend.agents.planner import create_draft
from backend.agents.research import research_topic
from backend.config.planner import PlannerSettings
from backend.errors import PlanningError
from backend.integrations.chat_model import create_chat_model
from backend.integrations.map_mcp import MapTools, create_map_mcp
from backend.integrations.place_evidence import collect_places
from backend.schemas.trip import (
    Place,
    PlanResult,
    TravelDraft,
    Trip,
    TripActivity,
    TripDay,
    TripRequest,
)


async def plan_trip(
    request: TripRequest,
    model: BaseChatModel,
    maps: MapTools,
    on_progress: Callable[[str], None] = print,
) -> PlanResult:
    """
    读完本函数即可看完规划主流程；模型与地图可注入测试替身。

    总超时由真实运行入口统一约束，包括地图查询和模型调用。

    :param request: 已通过输入模型校验的旅行需求。
    :param model: 可注入替身的聊天模型。
    :param maps: 已发现的地图工具及供应商信息。
    :param on_progress: 同步阶段回调；默认 print，CLI 注入写入 stderr 的回调。
    :return: 包含行程、引用地点、研究证据和警告的完整结果。
    :raises ValueError: 日期溢出、没有有效地点或草稿违反业务约束。
    :raises PlanningError: 研究 Agent 或 Planner 调用失败。
    """
    try:
        # 根据旅行起始日期和天数，计算旅行结束日期。
        end_date = request.start_date + timedelta(days=request.day_count - 1)
    except OverflowError:
        raise ValueError("旅行日期超出可表示范围") from None
    # 调研报告
    reports = []
    # 顺序运行三个独立研究 Agent，便于从终端逐步定位问题。
    for topic in ("attractions", "weather", "hotels"):
        on_progress(f"研究 {topic}：{request.destination}")
        reports.append(await research_topic(topic, request, model, maps))
    # 根据调研报告，从地图供应商中收集地点信息。
    places = collect_places(reports, maps.provider)
    if not places:
        raise ValueError("目的地没有查询到可用地点，无法生成行程")

    on_progress(
        f"生成 {request.start_date} 至 {end_date} 的行程，候选地点 {len(places)} 个"
    )

    # 创建行程草稿
    draft = await create_draft(request, list(places.values()), model, reports)
    on_progress("校验日期、活动时间和地点来源")
    validate_draft(draft, request, places)

    result = build_result(request, draft, places)
    result.research = reports
    result.warnings.extend(warning for report in reports for warning in report.warnings)
    on_progress("行程草稿已生成")
    return result


def validate_draft(
    draft: TravelDraft, request: TripRequest, places: dict[str, Place]
) -> None:
    """
    校验模型不能保证的业务约束，失败即返回明确错误。

    :param draft: 模型返回的结构化行程草稿。
    :param request: 用于确定完整日期范围的原始需求。
    :param places: 本轮有效候选地点，以地点 ID 索引。
    :raises ValueError: 日期不完整、活动时间无序或重复、引用未知地点。
    """
    # 预期旅行计划的日期列表
    expected = [
        request.start_date + timedelta(days=i) for i in range(request.day_count)
    ]
    # 如果模型返回的日期与输入不一致，则返回错误
    if [day.date for day in draft.days] != expected:
        raise ValueError("模型返回的日期或天数与输入不一致")
    # 活动时间必须按顺序排列且不能重复
    for day in draft.days:
        times = [activity.time for activity in day.activities]
        if times != sorted(set(times)):
            raise ValueError("活动开始时间必须按顺序排列且不能重复")
        if any(activity.place_id not in places for activity in day.activities):
            raise ValueError("模型行程包含未经本轮查询的地点")


def build_result(
    request: TripRequest, draft: TravelDraft, places: dict[str, Place]
) -> PlanResult:
    """
    将模型安排与地点事实组合为前端所需数据，不伪造费用或地图像素。

    :param request: 提供目的地、人数和全团预算的原始需求。
    :param draft: 已通过 validate_draft 的行程草稿。
    :param places: 覆盖草稿全部地点引用的事实索引。
    :return: 供前端展示的行程与引用地点；附带尚未核验事项的警告。
    :raises KeyError: 草稿引用的地点不在事实索引中。
    """
    days: list[TripDay] = []
    used_places: dict[str, Place] = {}
    for index, day in enumerate(draft.days, 1):
        activities: list[TripActivity] = []
        for number, activity in enumerate(day.activities, 1):
            place = places[activity.place_id]
            used_places[place.id] = place
            activities.append(
                TripActivity(
                    id=f"day-{index}-activity-{number}",
                    time=activity.time,
                    title=activity.title,
                    description=activity.description,
                    location=f"{place.name} {place.address}".strip(),
                    kind=activity.kind,
                    placeId=place.id,
                )
            )
        days.append(
            TripDay(
                id=index,
                date=day.date,
                label=f"第 {index} 天",
                title=day.title,
                description=day.description,
                activities=activities,
            )
        )
    return PlanResult(
        trip=Trip(
            id=str(uuid4()),
            destination=request.destination,
            travelers=request.travelers,
            budget=float(request.budget),
            days=days,
        ),
        places=list(used_places.values()),
        warnings=[
            "活动费用尚未查询，cost 为 null；全团预算不含往返大交通。",
            "地点坐标来自地图查询；point 尚未投影，路线与交通耗时待核实。",
            "天气预报是否覆盖出行日期、酒店价格与可订状态、开放时间和预约仍需确认。",
        ],
        reply=f"已为{request.destination}生成{request.day_count}天行程草稿，引用{len(used_places)}个查询地点。",
    )


async def generate_trip(
    request: TripRequest,
    settings: PlannerSettings,
    on_progress: Callable[[str], None] = print,
    callback: AsyncCallbackHandler | None = None,
) -> PlanResult:
    """
    装配真实依赖，总超时覆盖整轮；异常保留阶段、类型与脱敏原因。

    :param request: 已校验的旅行需求。
    :param settings: 模型、地图凭据及单次请求和整轮规划超时配置。
    :param on_progress: 同步阶段进度回调，CLI 使用 stderr 输出。
    :param callback: 可选的模型流式回调。
    :return: 由真实地图证据和模型草稿装配的规划结果。
    :raises TimeoutError: 整轮规划或底层请求超时。
    :raises PlanningError: 其他连接、模型或业务校验失败，保留阶段并脱敏。
    """
    stage = "MCP 连接与工具发现"
    # 所需要的密钥
    secrets = (settings.model_api_key, settings.amap_api_key, settings.baidu_api_key)
    try:
        # 异步创建 MCP 客户端并加载工具
        async with asyncio.timeout(settings.planner_timeout_seconds):
            client = create_map_mcp(settings)
            async with client.session(settings.map_provider) as session:
                tools = await load_mcp_tools(session)
                stage = "行程规划"
                async with httpx.AsyncClient(
                    timeout=settings.model_timeout_seconds,
                    trust_env=False,
                ) as model_http:
                    return await plan_trip(
                        request,
                        create_chat_model(settings, model_http, callback),
                        MapTools(settings.map_provider, tools),
                        on_progress,
                    )
    except TimeoutError:
        raise
    except Exception as exc:
        raise PlanningError(stage, exc, secrets) from None
