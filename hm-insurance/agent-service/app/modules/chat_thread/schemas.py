from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.common.dates import BusinessDateTime


class ChatThreadCreate(BaseModel):
    """创建会话请求"""

    title: str = Field(default="新会话", min_length=1, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """规范化标题"""
        return value.strip()


class ChatThreadResponse(BaseModel):
    """会话响应"""

    id: UUID
    title: str
    created_at: BusinessDateTime
    updated_at: BusinessDateTime


class ChatMessageResponse(BaseModel):
    """历史消息"""

    role: Literal["user", "assistant"]
    content: str
    additional_info: dict[str, Any] | None = None


class ChatHistoryResponse(BaseModel):
    """会话历史响应"""

    thread_id: UUID
    messages: list[ChatMessageResponse]
    interrupt: Any | None = None
