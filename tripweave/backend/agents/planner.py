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
    """
    candidates = [
        {"place_id": place.id, "name": place.name, "address": place.address}
        for place in places
    ]
    content = (
        request.model_dump_json()
        + "\n候选地点："
        + json.dumps(candidates, ensure_ascii=False)
    )
    if research:
        content += "\n研究资料（工具原文优先于摘要，缺失事项保持未知）："
        content += json.dumps(
            [report.model_dump(mode="json") for report in research], ensure_ascii=False
        )
    planner = model.with_structured_output(TravelDraft, method="function_calling")
    try:
        draft = await planner.ainvoke(
            [("system", PLANNER_SYSTEM_PROMPT), ("human", content)],
            config={"tags": ["agent:planner"]},
        )
        return TravelDraft.model_validate(draft)
    except Exception as exc:
        raise PlanningError("行程生成", exc) from None
