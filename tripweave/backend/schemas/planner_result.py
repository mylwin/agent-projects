"""首次生成原型使用的轻量草稿及地点来源结构。"""

from typing import Literal

from pydantic import AwareDatetime, Field

from backend.schemas.common import (
    ContractModel,
    Identifier,
    IsoDate,
    Latitude,
    LocalClock,
    Longitude,
    NonEmptyText,
)
from backend.schemas.planner_input import TravelRequirements


class QueriedPlace(ContractModel):
    """
    从地图供应商查询得到的地点，不由模型填写权威坐标。

    Attributes:
        id: 供应商地点标识，供行程活动引用。
        name: 供应商返回的地点名称。
        address: 供应商返回的地址，可为空字符串。
        longitude: 经度。
        latitude: 纬度。
        coordinate_system: 返回坐标系，固定为 GCJ-02。
        source: 查询来源，支持 amap 和 baidu。
        fetched_at: 实际查询时间，包含时区。
    """

    id: Identifier
    name: NonEmptyText
    address: str
    longitude: Longitude
    latitude: Latitude
    coordinate_system: Literal["GCJ-02"] = "GCJ-02"
    source: Literal["amap", "baidu"] = "amap"
    fetched_at: AwareDatetime


class ActivityPlan(ContractModel):
    """
    模型安排的一项活动，仅引用本轮查询得到的地点。

    Attributes:
        time: 建议开始时间，采用 HH:mm 格式。
        title: 活动标题。
        description: 活动安排说明，不代表预约或营业状态保证。
        place_id: 本轮地点查询结果中的 ID。
    """

    time: LocalClock
    title: NonEmptyText
    description: str = Field(max_length=500)
    place_id: Identifier


class DayPlan(ContractModel):
    """
    一天的建议行程。

    Attributes:
        date: 实际旅行日期，必须与输入日期区间一致。
        title: 当天主题。
        activities: 按开始时间排列的活动，至少一项。
    """

    date: IsoDate
    title: NonEmptyText
    activities: list[ActivityPlan] = Field(min_length=1, max_length=10)


class TravelDraft(ContractModel):
    """
    单 Agent 通过结构化输出提交的首次行程草稿。

    Attributes:
        days: 完整旅行日列表，首版最多五天。
    """

    days: list[DayPlan] = Field(min_length=1, max_length=5)


class PlannerResult(ContractModel):
    """
    终端返回的规划草稿，不等同于已核验正式业务版本。

    Attributes:
        requirements: 本轮采用的完整需求，已补齐明确可推导的日期。
        itinerary: 经日期和地点引用检查的行程草稿。
        places: 行程实际引用的供应商地点及来源。
        warnings: 尚未核验的路线、费用及开放预约等事项。
        reply: 可直接展示给用户的说明，来自模型正文或程序兜底摘要。
    """

    requirements: TravelRequirements
    itinerary: TravelDraft
    places: list[QueriedPlace]
    warnings: list[str]
    reply: str
