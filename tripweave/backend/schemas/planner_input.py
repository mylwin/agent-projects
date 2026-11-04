"""单 Planner 的输入契约，只保留首次生成用到的字段。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from backend.schemas.common import (
    BudgetScope,
    ContractModel,
    IsoDate,
    Money,
    NonEmptyText,
    Note,
    SchemaVersion,
)


class DestinationQuery(ContractModel):
    """
    待解析的国内目的地查询。

    Attributes:
        query: 用户提供的目的地文本，如"成都"或"武侯区"，行政区由程序解析。
    """

    query: NonEmptyText


class BudgetRequirement(ContractModel):
    """
    全团预算；口径未知时保持为空，交由后续澄清。

    Attributes:
        amount: 预算金额；不填时为未知。
        currency: 预算币种，默认为人民币。
        scope: 预算范围，默认为未知。
    """

    amount: Annotated[Money, Field(gt=0, le=1000000)] | None = None
    currency: Literal["CNY"] = "CNY"
    scope: BudgetScope | None = None


class TravelPreferences(ContractModel):
    """
    用户明确提供的软偏好，不自动填充用户画像。

    Attributes:
        pace: 出游节奏，可选 ``relaxed`` 轻松、``balanced`` 均衡或
            ``packed`` 紧凑；不填时表示用户尚未指定。
        interests: 兴趣主题，如历史、园林或当地小吃；默认为空列表。
        food_preferences: 饮食口味偏好；默认为空列表，不代表商家已确认满足。
        transport_preferences: 交通方式软偏好，不等同于必须遵守的交通限制。
        notes: 其他尚未分类的偏好说明；默认为空列表。
    """

    pace: Literal["relaxed", "balanced", "packed"] | None = None
    interests: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    food_preferences: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    transport_preferences: list[NonEmptyText] = Field(
        default_factory=list, max_length=20
    )
    notes: list[Note] = Field(default_factory=list, max_length=20)


class TravelRequirements(ContractModel):
    """
    允许信息不齐的需求输入，缺失值留给后续规范化与澄清。

    Attributes:
        destination: 待解析的国内目的地区域；不填时需向用户确认。
        start_date: 出发日期；不填时保持未知，不自动使用当天日期。
        day_count: 出游天数，首版为 1–5 天；可与起止日期区间相互核对。
        end_date: 可选结束日期；与出发日期同时提供时，区间包含首尾两天。
        travelers: 全团人数，首版为 1–12 人；不填时需澄清。
        budget: 全团预算金额、币种与费用覆盖口径；不填时保持未知。
        preferences: 用户软偏好；默认创建独立的空偏好对象。
    """

    destination: DestinationQuery | None = None
    start_date: IsoDate | None = None
    day_count: Annotated[int, Field(strict=True, ge=1, le=5)] | None = None
    end_date: IsoDate | None = None
    travelers: Annotated[int, Field(strict=True, ge=1, le=12)] | None = None
    budget: BudgetRequirement | None = None
    preferences: TravelPreferences = Field(default_factory=TravelPreferences)

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        """
        拒绝倒置日期与结构化日期范围的自相矛盾。

        :param self: 已完成字段类型校验且允许缺值的旅行需求。
        :return: 已提供日期字段相互一致的当前需求。
        :raises ValueError: 日期区间超过五天或与给定天数不一致时抛出。
        """
        if self.start_date is not None and self.end_date is not None:
            duration = (self.end_date - self.start_date).days + 1
            if not 1 <= duration <= 5:
                raise ValueError("日期区间必须为连续 1–5 天")
            if self.day_count is not None and duration != self.day_count:
                raise ValueError("天数与起止日期区间不一致")
        return self


class PlannerInput(ContractModel):
    """
    国内旅行单 Planner 的首次生成输入。

    仅验证结构；国内归属、自然语言理解及实时证据在运行阶段处理。

    Attributes:
        schema_version: 输入契约版本，当前仅接受整数 1。
        operation: 操作类型，当前仅支持 ``generate`` 首次生成。
        instruction: 用户本轮原始指令，最多 500 字。
        requirements: 结构化旅行需求，允许保留未知字段供后续澄清。
    """

    schema_version: SchemaVersion = 1
    operation: Literal["generate"] = "generate"
    instruction: Annotated[str, Field(max_length=500)] = ""
    requirements: TravelRequirements
