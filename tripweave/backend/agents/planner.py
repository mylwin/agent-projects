"""Planner 汇总研究 Agent 的证据，一次结构化调用生成行程。"""

import json

from langchain_core.language_models import BaseChatModel

from backend.agents.prompts import PLANNER_SYSTEM_PROMPT
from backend.errors import PlanningError
from backend.schemas.trip import Place, ResearchReport, TravelDraft, TripRequest


async def create_draft(
    request: TripRequest,
    places: list[Place],
    model: BaseChatModel,
    research: list[ResearchReport] | None = None,
) -> TravelDraft:
    """
    将已查询事实交给模型，一次调用生成结构化草稿。

    工具查询由研究 Agent 完成，本函数只做最终汇总，不循环修复无效结果。

    :param request: 已校验的旅行需求。
    :param places: 本轮地图查询得到的候选地点，模型只能引用其中的 ID。
    :param model: 支持结构化输出的聊天模型。
    :param research: 可选的研究摘要与工具原文；为空时不附加研究资料。
    :return: 通过结构校验的模型行程草稿。
    :raises PlanningError: 模型调用或草稿结构校验失败。
    """
    # 候选地点列表
    candidates = [
        {"place_id": place.id, "name": place.name, "address": place.address}
        for place in places
    ]
    # 拼装输入上下文
    content = (
        "# 旅行需求\n\n```json\n"
        + request.model_dump_json(indent=2)
        + "\n```\n\n# 候选地点\n\n```json\n"
        + json.dumps(candidates, ensure_ascii=False, indent=2)
        + "\n```"
    )
    # 如果有研究资料，则附加到输入上下文中，供模型参考
    if research:
        content += (
            "\n\n# 研究资料\n\n工具原文优先于摘要，缺失事项保持未知。\n\n```json\n"
        )
        content += json.dumps(
            [report.model_dump(mode="json") for report in research],
            ensure_ascii=False,
            indent=2,
        )
        content += "\n```"
    # 固定模型输出结构
    planner = model.with_structured_output(TravelDraft, method="function_calling")
    try:
        # 生成旅行计划草稿
        draft = await planner.ainvoke(
            [("system", PLANNER_SYSTEM_PROMPT), ("human", content)],
            config={"tags": ["agent:planner"]},
        )
        # 校验草稿结构并返回
        return TravelDraft.model_validate(draft)
    except Exception as exc:
        raise PlanningError("行程生成", exc) from None
