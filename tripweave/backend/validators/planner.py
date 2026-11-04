"""首次行程生成的纯业务校验。"""

from datetime import timedelta

from backend.schemas.planner_input import TravelRequirements
from backend.schemas.planner_result import QueriedPlace, TravelDraft


def validate_draft(
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
