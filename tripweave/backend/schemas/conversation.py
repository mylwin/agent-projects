"""项目对话的输入、模型工具契约与持久化回复。"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from backend.schemas.trip import TripRequest


class ChatRequest(BaseModel):
    """普通交流默认不允许生成版本；整趟规划须由界面显式授权。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2000)
    base_revision_id: int = Field(ge=1)
    day_id: int = Field(ge=1, le=5)
    generate: bool = False


class GenerateFullPlan(TripRequest):
    """重新规划整趟行程的工具参数；仅在用户显式授权时绑定给模型。"""


class ActivityAdjustment(BaseModel):
    """
    局部调整中的单个活动，只允许改时间、标题和说明。

    未提供的字段保留当前版本的值；地点、费用和日期等事实字段不在契约内，
    因此模型无法通过局部调整伪造或改写外部事实。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=100)
    time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class AdjustTrip(BaseModel):
    """
    模型对当前版本某一天行程的局部调整。

    活动列表是调整后的完整当日安排：未列出的活动会被移除，但只能引用当前
    版本已有的活动 ID，不能新增地点或活动。
    """

    model_config = ConfigDict(extra="forbid")
    day_id: int = Field(ge=1, le=5)
    activities: list[ActivityAdjustment] = Field(min_length=1, max_length=10)


class ConversationTurnData(BaseModel):
    """可回读的公开对话，包括中断状态与关联版本。"""

    model_config = ConfigDict(from_attributes=True)
    id: int
    base_revision_id: int
    result_revision_id: int | None
    day_id: int
    generate: bool
    user_text: str
    assistant_text: str
    status: Literal["running", "succeeded", "failed", "cancelled"]
    error_code: str | None
    created_at: AwareDatetime

    @field_validator("created_at", mode="before")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        """数据库无时区时间统一按 UTC 解释。"""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
