"""顺序执行需求检查、地点查询、模型规划、业务校验和结果装配。"""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

import httpx
from langchain_core.language_models import BaseChatModel

from backend.agents.planner import create_draft
from backend.config.planner import PlannerSettings
from backend.integrations.chat_model import create_chat_model
from backend.integrations.map_client import MapClient, create_map_client
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
    map_client: MapClient,
    on_progress: Callable[[str], None] = print,
) -> PlanResult:
    """
    读完本函数即可看完规划主流程；模型与地图可注入测试替身。

    总超时由真实运行入口统一约束，包括地图查询和模型调用。
    """
    try:
        end_date = request.start_date + timedelta(days=request.day_count - 1)
    except OverflowError:
        raise ValueError("旅行日期超出可表示范围") from None
    on_progress(f"解析目的地：{request.destination}")
    region = await map_client.resolve_region(request.destination)

    # 景点、美食各查一次，再补充一种兴趣，保持调用数量直观可控。
    keywords = ["景点", "当地美食"]
    if request.interests and request.interests[0] not in keywords:
        keywords.append(request.interests[0])
    places: dict[str, Place] = {}
    for keyword in keywords:
        on_progress(f"查询地点：{keyword}")
        results = await map_client.search_places(region, keyword)
        places.update({place.id: place for place in results})
    if not places:
        raise ValueError("目的地没有查询到可用地点，无法生成行程")

    on_progress(
        f"生成 {request.start_date} 至 {end_date} 的行程，候选地点 {len(places)} 个"
    )
    draft = await create_draft(request, list(places.values()), model)
    on_progress("校验日期、活动时间和地点来源")
    validate_draft(draft, request, places)
    result = build_result(request, draft, places)
    on_progress("行程草稿已生成")
    return result


def validate_draft(
    draft: TravelDraft, request: TripRequest, places: dict[str, Place]
) -> None:
    """校验模型不能保证的业务约束，失败即返回明确错误。"""
    expected = [
        request.start_date + timedelta(days=i) for i in range(request.day_count)
    ]
    if [day.date for day in draft.days] != expected:
        raise ValueError("模型返回的日期或天数与输入不一致")
    for day in draft.days:
        times = [activity.time for activity in day.activities]
        if times != sorted(set(times)):
            raise ValueError("活动开始时间必须按顺序排列且不能重复")
        if any(activity.place_id not in places for activity in day.activities):
            raise ValueError("模型行程包含未经本轮查询的地点")


def build_result(
    request: TripRequest, draft: TravelDraft, places: dict[str, Place]
) -> PlanResult:
    """将模型安排与地点事实组合为前端所需数据，不伪造费用或地图像素。"""
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
            "天气、住宿、开放时间、预约与营业情况尚未核验。",
        ],
        reply=f"已为{request.destination}生成{request.day_count}天行程草稿，引用{len(used_places)}个查询地点。",
    )


async def generate_trip(
    request: TripRequest,
    settings: PlannerSettings,
    on_progress: Callable[[str], None] = print,
) -> PlanResult:
    """装配真实依赖，用一个总超时覆盖整轮流程，结束时关闭连接。"""
    key = (
        settings.amap_api_key
        if settings.map_provider == "amap"
        else settings.baidu_api_key
    )
    async with asyncio.timeout(settings.planner_timeout_seconds):
        async with (
            httpx.AsyncClient() as map_http,
            httpx.AsyncClient(timeout=settings.model_timeout_seconds) as model_http,
        ):
            return await plan_trip(
                request,
                create_chat_model(settings, model_http),
                create_map_client(settings.map_provider, key, map_http),
                on_progress,
            )
