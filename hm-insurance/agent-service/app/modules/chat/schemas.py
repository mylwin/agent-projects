from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """基础对话请求"""

    thread_id: UUID
    message: str | None = Field(
        description="用户输入的消息", default=None, min_length=1
    )
    decision: dict[str, Any] | None = Field(description="决策结果", default=None)
