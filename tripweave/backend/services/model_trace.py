"""收集供应商公开返回的模型调用内容，不读取隐藏推理。"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult

from backend.errors import redact


class ModelTrace(AsyncCallbackHandler):
    """在一次生成期间按 Agent 收集公开模型结果。"""

    def __init__(self, model_name: str, secrets: tuple[str, ...]) -> None:
        """保存模型名称与需要从公开文本中脱敏的凭据。"""
        self.model_name = model_name
        self.secrets = secrets
        self.started: dict[UUID, datetime] = {}
        self.indexes: defaultdict[str, int] = defaultdict(int)
        self.calls: list[dict[str, Any]] = []

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """记录模型调用开始时间；输入消息不持久化。"""
        self.started[run_id] = datetime.now(UTC)

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """只提取供应商公开返回的正文、推理及工具名。"""
        agent = next(
            (
                tag.removeprefix("agent:")
                for tag in tags or []
                if tag.startswith("agent:")
            ),
            None,
        )
        if agent not in {"attractions", "weather", "hotels", "planner"}:
            return
        self.indexes[agent] += 1
        message: AIMessage | None = None
        for batch in response.generations:
            for generation in batch:
                candidate = getattr(generation, "message", None)
                if isinstance(candidate, AIMessage):
                    message = candidate
                    break
            if message is not None:
                break
        started = self.started.pop(run_id, datetime.now(UTC))
        finished = datetime.now(UTC)
        reasoning: str | None = None
        content: str | None = None
        tools: list[dict[str, str]] = []
        if message is not None:
            public = [
                block.get("reasoning")
                for block in message.content_blocks
                if block["type"] == "reasoning"
            ]
            if not public:
                public = [message.additional_kwargs.get("reasoning_content")]
            reasoning = (
                "\n".join(part for part in public if isinstance(part, str)) or None
            )
            content = message.text or None
            tools = [
                {"name": call.get("name") or "", "id": call.get("id") or ""}
                for call in message.tool_calls
            ]
        self.calls.append(
            {
                "agent": agent,
                "call_index": self.indexes[agent],
                "model_name": self.model_name,
                "reasoning": redact(reasoning, self.secrets) if reasoning else None,
                "content": redact(content, self.secrets) if content else None,
                "tool_calls": tools or None,
                "started_at": started.astimezone(UTC).replace(tzinfo=None),
                "finished_at": finished.astimezone(UTC).replace(tzinfo=None),
                "duration_ms": int((finished - started).total_seconds() * 1000),
            }
        )
