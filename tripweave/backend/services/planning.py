"""首次行程生成的业务流程：需求准备、地点查询、结果校验与装配。"""

import json
import time
from collections.abc import Callable
from datetime import timedelta

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.agents.prompts import PLANNER_SYSTEM_PROMPT
from backend.agents.runtime import AgentStep, run_structured_agent
from backend.clients.map_client import MapClient, create_map_client
from backend.config.planner import DEFAULT_PLANNER_TIMEOUT_SECONDS, PlannerSettings
from backend.schemas.planner_input import PlannerInput, TravelRequirements
from backend.schemas.planner_result import PlannerResult, QueriedPlace, TravelDraft

# 本轮固定查询关键词
DEFAULT_QUERY_KEYWORDS: tuple[str, ...] = ("景点", "当地美食")


def build_query_keywords(requirements: TravelRequirements) -> list[str]:
    """
    确定本轮地点查询关键词，最多三类。

    关键词只决定候选池的覆盖面，具体取舍由模型结合偏好完成。

    :param requirements: 已补齐日期的旅行需求。
    :return: 依次执行的三类查询关键词。
    """
    # 与用户兴趣文本（str）赋值不兼容，返回类型也对不上。
    keywords: list[str] = list(DEFAULT_QUERY_KEYWORDS)
    if requirements.preferences.interests:
        keywords[-1] = requirements.preferences.interests[0]
    if requirements.preferences.food_preferences:
        keywords[1] = requirements.preferences.food_preferences[0]
    return keywords


def _build_model_input(
    requirements: TravelRequirements,
    places: dict[str, QueriedPlace],
    instruction: str,
) -> str:
    """
    组装模型输入：完整需求、候选地点清单与用户补充。

    候选清单只保留挑选地点必需的字段，不传坐标、来源和查询时间。

    :param requirements: 已补齐日期的旅行需求。
    :param places: 本轮查询到的候选地点台账。
    :param instruction: 用户补充指令。
    :return: 单条用户消息内容。
    """
    candidates = [
        {"place_id": place.id, "name": place.name, "address": place.address}
        for place in places.values()
    ]
    return (
        requirements.model_dump_json()
        + "\n候选地点（只能引用其中的 place_id）：\n"
        + json.dumps(candidates, ensure_ascii=False)
        + "\n用户补充："
        + instruction
    )


def create_chat_model(
    settings: PlannerSettings, http: httpx.AsyncClient
) -> BaseChatModel:
    """
    按配置创建支持工具调用的聊天模型。

    默认开启流式：思考型模型在非流式请求下要等整段生成完才返回响应头，
    很容易被单次读超时打断；流式改按分片计时，长生成不再误判超时。

    :param settings: 从环境变量读取的服务配置。
    :param http: 调用方管理的异步 HTTP 客户端。
    :return: 指向 OpenAI 兼容接口的聊天模型。
    """
    # 只在显式配置时发送思考链参数：部分供应商与模型不支持，默认不传。
    extra_body: dict[str, object] = {}
    if settings.model_enable_thinking is not None:
        extra_body["enable_thinking"] = settings.model_enable_thinking
    if settings.model_thinking_budget is not None:
        extra_body["thinking_budget"] = settings.model_thinking_budget
    return ChatOpenAI(
        model=settings.model_name,
        base_url=settings.model_base_url,
        api_key=SecretStr(settings.model_api_key),
        timeout=settings.model_timeout_seconds,
        max_retries=0,
        streaming=True,
        extra_body=extra_body or None,
        http_async_client=http,
    )


def current_map_api_key(settings: PlannerSettings) -> str:
    """
    取出当前地图供应商对应的 Web 服务密钥。

    :param settings: 从环境变量读取的服务配置。
    :return: 与 ``MAP_PROVIDER`` 匹配的供应商密钥。
    """
    if settings.map_provider == "amap":
        return settings.amap_api_key
    return settings.baidu_api_key


def prepare_requirements(request: PlannerInput) -> TravelRequirements:
    """
    检查首次生成所需字段，补齐确定可推导的日期。

    :param request: 已通过输入模型校验的规划请求。
    :return: 可直接传入模型的完整需求副本，不修改原输入。
    :raises ValueError: 缺少必要字段或日期区间不可表示时抛出。
    """
    requirements = request.requirements
    required = {
        "destination": requirements.destination,
        "start_date": requirements.start_date,
        "travelers": requirements.travelers,
        "budget.amount": requirements.budget.amount if requirements.budget else None,
        "budget.scope": requirements.budget.scope if requirements.budget else None,
    }
    # 检查缺失字段，day_count 与 end_date 至少提供一项。
    missing = [name for name, value in required.items() if value is None]
    if requirements.day_count is None and requirements.end_date is None:
        missing.append("day_count 或 end_date")
    if missing:
        raise ValueError("请补齐出行需求：" + "、".join(missing))

    start = requirements.start_date
    assert start is not None
    count = requirements.day_count
    # 未提供天数时按起止日期推导，允许 end_date 与 start_date 相同。
    if count is None:
        assert requirements.end_date is not None
        count = (requirements.end_date - start).days + 1
    data = requirements.model_dump()
    try:
        data.update(day_count=count, end_date=start + timedelta(days=count - 1))
    except OverflowError:
        raise ValueError("旅行日期区间超出可表示范围") from None
    return TravelRequirements.model_validate(data)


async def plan_trip(
    request: PlannerInput,
    model: BaseChatModel,
    map_client: MapClient,
    *,
    timeout_seconds: float = DEFAULT_PLANNER_TIMEOUT_SECONDS,
    on_progress: Callable[[str], None] | None = None,
    on_chunk: Callable[[], None] | None = None,
) -> PlannerResult:
    """
    执行一次行程生成：程序定区域、查询范围与事实，模型只调用一次完成组合。

    :param request: 用户的首次生成请求。
    :param model: 支持结构化输出的聊天模型，测试时可注入替身。
    :param map_client: 地图查询客户端，支持高德与百度。
    :param timeout_seconds: 整轮规划的总超时秒数。
    :param on_progress: 进度回调，为 None 时不输出。
    :param on_chunk: 模型流式片段回调，用于长生成期间显示活动。
    :return: 带来源地点及未核验事项的行程草稿。
    :raises ValueError: 日期、地点引用、时间顺序或输入不合法时抛出。
    :raises TimeoutError: 整轮规划超过 ``timeout_seconds`` 时抛出。
    """
    requirements = prepare_requirements(request)
    destination = requirements.destination
    assert destination is not None

    started = time.monotonic()
    previous = started

    def report(message: str) -> None:
        """输出一条带本步骤耗时的进度。"""
        nonlocal previous
        if on_progress is None:
            return
        now = time.monotonic()
        on_progress(f"{message}（{now - previous:.1f}s）")
        previous = now

    report(f"解析目的地：{destination.query}")
    region = await map_client.resolve_region(destination.query)
    report(f"目的地区域已确定：{region}，开始规划 {requirements.day_count} 天行程")

    # 程序决定查什么、查几次：三类关键词各查一次，模型不再驱动查询循环。
    places: dict[str, QueriedPlace] = {}
    for keyword in build_query_keywords(requirements):
        report(f"查询地点：{keyword}")
        results = await map_client.search_places(region, keyword)
        places.update({place.id: place for place in results})
        report(f"{keyword} 返回 {len(results)} 个结果，累计 {len(places)} 个候选地点")
    if not places:
        raise ValueError("目的地没有查询到可用地点，无法生成行程")

    def on_step(step: AgentStep) -> None:
        """单次调用只关心是否拿回结构化行程。"""
        if step.kind == "model" and step.tool_names == (TravelDraft.__name__,):
            report("模型已返回结构化行程")

    report(f"已提交模型，等待生成行程（{len(places)} 个候选地点）")
    response = await run_structured_agent(
        model=model,
        tools=[],
        system_prompt=PLANNER_SYSTEM_PROMPT,
        response_model=TravelDraft,
        user_content=_build_model_input(requirements, places, request.instruction),
        timeout_seconds=timeout_seconds,
        max_model_calls=1,
        on_step=on_step,
        on_chunk=on_chunk,
    )
    draft = TravelDraft.model_validate(response)
    used_ids = _validate_draft(draft, requirements, places)
    report(f"行程草稿已就绪，引用 {len(used_ids)} 个地点")
    return PlannerResult(
        requirements=requirements,
        itinerary=draft,
        places=[places[place_id] for place_id in sorted(used_ids)],
        warnings=[
            "当前结果为规划草稿，尚未核验实际路线与交通耗时。",
            "活动费用、住宿和全程预算尚未核验。",
            "天气、开放时间、预约与营业情况需另行确认。",
        ],
    )


def _validate_draft(
    draft: TravelDraft,
    requirements: TravelRequirements,
    places: dict[str, QueriedPlace],
) -> set[str]:
    """
    校验模型返回的行程：日期完整、地点来自本轮查询、时间有序。

    :param draft: 模型提交的行程草稿。
    :param requirements: 已补齐日期的旅行需求。
    :param places: 本轮查询到的候选地点台账。
    :return: 行程实际引用的地点 ID 集合。
    :raises ValueError: 日期、地点引用或时间顺序不合法时抛出。
    """
    start = requirements.start_date
    count = requirements.day_count
    assert start is not None and count is not None
    expected_dates = [start + timedelta(days=index) for index in range(count)]
    if [day.date for day in draft.days] != expected_dates:
        raise ValueError("模型返回的日期或天数与输入不一致")
    used_ids = {activity.place_id for day in draft.days for activity in day.activities}
    if not places or not used_ids <= places.keys():
        raise ValueError("模型行程包含未经本轮查询的地点")
    for day in draft.days:
        times = [activity.time for activity in day.activities]
        if times != sorted(set(times)):
            raise ValueError("活动开始时间必须按顺序排列且不能重复")
    return used_ids


async def generate_draft(
    request: PlannerInput,
    settings: PlannerSettings,
    *,
    on_progress: Callable[[str], None] | None = None,
    on_chunk: Callable[[], None] | None = None,
) -> PlannerResult:
    """
    装配真实服务依赖并执行一次行程生成，结束后关闭 HTTP 连接。

    :param request: 已通过结构校验的首次生成请求。
    :param settings: 从环境变量读取的服务配置。
    :param on_progress: 进度回调，由调用方决定写到哪里，为 None 时不输出。
    :param on_chunk: 模型流式片段回调，用于长生成期间显示活动。
    :return: 单 Agent 返回的行程草稿。
    :raises ValueError: 需求不完整或模型结果未通过程序校验时抛出。
    :raises RuntimeError: 模型或地图供应商调用失败时抛出。
    :raises TimeoutError: 整轮规划超过配置的总超时秒数时抛出。
    """
    async with (
        httpx.AsyncClient() as map_http,
        httpx.AsyncClient(timeout=settings.model_timeout_seconds) as model_http,
    ):
        return await plan_trip(
            request,
            create_chat_model(settings, model_http),
            create_map_client(
                settings.map_provider, current_map_api_key(settings), map_http
            ),
            timeout_seconds=settings.planner_timeout_seconds,
            on_progress=on_progress,
            on_chunk=on_chunk,
        )
