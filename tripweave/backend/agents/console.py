"""一个原生 LangChain 回调处理器，直接把流式内容写到终端。"""

import sys
from collections.abc import Sequence
from typing import Any, TextIO
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, GenerationChunk, LLMResult

from backend.errors import redact

AGENT_LABELS = {
    "attractions": "景点研究",
    "weather": "天气研究",
    "hotels": "住宿研究",
    "planner": "行程规划",
}


class ConsoleCallback(AsyncCallbackHandler):
    """显示正文、服务公开返回的推理与工具生命周期，最终 JSON 不经过此回调。"""

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        debug_tools: bool = False,
        secrets: Sequence[str] = (),
    ) -> None:
        """注入终端输出，默认 stderr；仅调试模式显示工具参数分片。"""
        self.stream = stream if stream is not None else sys.stderr
        self.debug_tools = debug_tools
        self.secrets = secrets
        self._channel: tuple[str, str] | None = None
        self._tools: dict[UUID, tuple[str, str]] = {}

    def progress(self, message: str) -> None:
        """与已有阶段回调共用同一输出，先结束未换行的模型分片。"""
        self.finish()
        print(redact(message, self.secrets), file=self.stream, flush=True)

    def finish(self) -> None:
        """模型完成、报错或运行结束时补齐换行。"""
        if self._channel is not None:
            print(file=self.stream, flush=True)
            self._channel = None

    def _write(self, role: str, channel: str, text: str) -> None:
        """同一通道连续输出，切换 Agent 或内容类型时换行。"""
        if not text:
            return
        if self._channel != (role, channel):
            self.finish()
            print(f"[{role}·{channel}] ", end="", file=self.stream)
            self._channel = (role, channel)
        print(redact(text, self.secrets), end="", file=self.stream, flush=True)

    @staticmethod
    def _role(tags: list[str] | None) -> str:
        """使用调用配置中的标签定位 Agent，不依赖全局当前角色。"""
        for tag in tags or []:
            if tag.startswith("agent:"):
                return AGENT_LABELS.get(tag.removeprefix("agent:"), "模型")
        return "模型"

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """展示每次模型请求的起点，包括只生成结构化工具参数的 Planner。"""
        self.progress(f"[{self._role(tags)}] 模型开始生成")

    async def on_llm_new_token(
        self,
        token: str | list[str | dict[str, Any]],
        *,
        chunk: GenerationChunk | ChatGenerationChunk | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """实时显示模型返回的增量，不拼接后重播，不增加模型调用。"""
        role = self._role(tags)
        if not isinstance(chunk, ChatGenerationChunk) or not isinstance(
            chunk.message, AIMessageChunk
        ):
            if isinstance(token, str):
                self._write(role, "回复", token)
            return
        message = chunk.message
        reasoning = [
            block.get("reasoning")
            for block in message.content_blocks
            if block["type"] == "reasoning"
        ]
        if not reasoning:
            reasoning = [message.additional_kwargs.get("reasoning_content")]
        for text in reasoning:
            if isinstance(text, str):
                self._write(role, "推理", text)
        self._write(role, "回复", message.text)
        if self.debug_tools:
            for call in message.tool_call_chunks:
                self._write(role, "工具参数", call.get("args") or "")

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """完成一轮模型输出后换行，避免下一条进度挤到同一行。"""
        self.finish()

    async def on_llm_error(
        self, error: BaseException, *, tags: list[str] | None = None, **kwargs: Any
    ) -> None:
        """记录模型错误类型；最终业务异常负责给出脱敏原因。"""
        self.progress(f"[{self._role(tags)}] 模型失败 [{type(error).__name__}]")

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """显示工具开始，只在调试模式打印参数。"""
        role, name = self._role(tags), str(serialized.get("name", "未知工具"))
        self._tools[run_id] = (role, name)
        self.progress(f"[{role}] 工具开始：{name}")
        if self.debug_tools:
            self.progress(f"[{role}·工具参数] {input_str}")

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """区分成功结果和被框架转为 ToolMessage 的错误结果。"""
        role, name = self._tools.pop(run_id, ("模型", "未知工具"))
        if isinstance(output, ToolMessage) and output.status == "error":
            self.progress(f"[{role}] 工具失败：{name}；{output.text}")
        else:
            self.progress(f"[{role}] 工具完成：{name}")

    async def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        """工具异常也显示脱敏原因，不输出原始堆栈。"""
        role, name = self._tools.pop(run_id, ("模型", "未知工具"))
        self.progress(f"[{role}] 工具失败：{name} [{type(error).__name__}]；{error}")
