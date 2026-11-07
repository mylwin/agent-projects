"""项目对话的输入、持久化回复与上下文标识。"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    """普通交流默认不允许生成版本；整趟规划须由界面显式授权。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2000)
    base_revision_id: int = Field(ge=1)
    day_id: int = Field(ge=1, le=5)
    generate: bool = False


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
