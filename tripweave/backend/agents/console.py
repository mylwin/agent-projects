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
    """
    显示正文、服务公开返回的推理与工具生命周期，最终 JSON 不经过此回调。

    Attributes:
        stream: 终端输出流，默认 stderr。
        debug_tools: 是否显示工具参数。
        secrets: 输出前隐藏的已知凭据。
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        debug_tools: bool = False,
        secrets: Sequence[str] = (),
    ) -> None:
        """
        注入终端输出，默认 stderr；仅调试模式显示工具参数分片。

        :param stream: 输出流；None 时使用 stderr。
        :param debug_tools: 是否显示工具调用参数分片和执行参数。
        :param secrets: 输出前需要隐藏的已知凭据。
        """
        self.stream = stream if stream is not None else sys.stderr
        self.debug_tools = debug_tools
        self.secrets = secrets
        self._channel: tuple[str, str] | None = None
        self._tools: dict[UUID, tuple[str, str]] = {}
        self._wrote_reply = False

    def progress(self, message: str) -> None:
        """
        与已有阶段回调共用同一输出，先结束未换行的模型分片。

        :param message: 需要脱敏并独占一行显示的阶段进度。
        """
        self.finish()
        print(redact(message, self.secrets), file=self.stream, flush=True)

    def finish(self) -> None:
        """模型完成、报错或运行结束时补齐换行。"""
        if self._channel is not None:
            print(file=self.stream, flush=True)
            self._channel = None

    def _write(self, role: str, channel: str, text: str) -> None:
        """
        同一通道连续输出，切换 Agent 或内容类型时换行。

        :param role: 当前 Agent 的中文展示名。
        :param channel: 输出内容类型，如回复、推理或参数生成。
        :param text: 供应商返回的增量文本；空字符串不输出。
        """
        if not text:
            return
        # 如果通道不同，则先结束当前通道
        if self._channel != (role, channel):
            self.finish()
            print(f"[{role}·{channel}] ", end="", file=self.stream)
            self._channel = (role, channel)
        if channel == "回复" and text.strip():
            self._wrote_reply = True
        print(redact(text, self.secrets), end="", file=self.stream, flush=True)

    @staticmethod
    def _response_text(response: LLMResult) -> str:
        """
        读取最终响应中的正文，供未收到流式分片时兜底显示。

        :param response: 模型完整响应。
        :return: 第一条非空正文；没有正文时返回空字符串。
        """
        for batch in response.generations:
            for generation in batch:
                message = getattr(generation, "message", None)
                text = (
                    message.text
                    if isinstance(message, BaseMessage)
                    else generation.text
                )
                if text:
                    return text
        return ""

    @staticmethod
    def _role(tags: list[str] | None) -> str:
        """
        使用调用配置中的标签定位 Agent，不依赖全局当前角色。

        :param tags: 框架调用标签；通过 agent: 前缀识别角色。
        :return: 角色的中文名称；无法识别时返回“模型”。
        """
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
        """
        展示每次模型请求的起点，包括只生成结构化工具参数的 Planner。

        :param serialized: 框架传入的模型序列化信息，本回调不读取。
        :param messages: 本次请求的消息批次，本回调不读取。
        :param tags: 用于识别 Agent 的调用标签。
        :param kwargs: 框架提供的其他回调元数据，本回调不读取。
        """
        self._wrote_reply = False
        self.progress(f"[{self._role(tags)}] 模型开始生成")

    async def on_llm_new_token(
        self,
        token: str | list[str | dict[str, Any]],
        *,
        chunk: GenerationChunk | ChatGenerationChunk | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        实时显示模型返回的增量，不拼接后重播，不增加模型调用。

        :param token: 原始增量；缺少聊天消息分片时仅显示字符串内容。
        :param chunk: 框架提供的分片，用于读取公开推理、正文及工具参数。
        :param tags: 用于识别 Agent 的调用标签。
        :param kwargs: 框架提供的其他回调元数据，本回调不读取。
        """
        role = self._role(tags)
        # 如果模型返回的分片不是聊天产生的分片，或者分片不是 AIMessageChunk
        if not isinstance(chunk, ChatGenerationChunk) or not isinstance(
            chunk.message, AIMessageChunk
        ):
            # 如果是字符串，则直接显示
            if isinstance(token, str):
                self._write(role, "回复", token)
            return
        message = chunk.message
        # 获取模型推理思考的内容
        reasoning = [
            block.get("reasoning")
            for block in message.content_blocks
            if block["type"] == "reasoning"
        ]
        # 如果没有推理内容，则尝试从额外参数中获取
        if not reasoning:
            reasoning = [message.additional_kwargs.get("reasoning_content")]
        # 如果有推理内容，则显示
        for text in reasoning:
            if isinstance(text, str):
                self._write(role, "推理", text)
        self._write(role, "回复", message.text)
        # 如果显示工具参数，则显示
        if self.debug_tools:
            for call in message.tool_call_chunks:
                self._write(role, "参数生成", call.get("args") or "")

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        完成一轮模型输出后换行；没有流式正文时补打最终响应。

        :param response: 本轮模型的完整结果。
        :param tags: 用于识别 Agent 的调用标签。
        :param kwargs: 框架提供的其他回调元数据，本回调不读取。
        """
        if not self._wrote_reply:
            text = self._response_text(response)
            if text:
                self._write(self._role(tags), "回复", text)
        self.finish()

    async def on_llm_error(
        self, error: BaseException, *, tags: list[str] | None = None, **kwargs: Any
    ) -> None:
        """
        记录模型错误类型；最终业务异常负责给出脱敏原因。

        :param error: 模型抛出的底层异常，仅展示类型名。
        :param tags: 用于识别 Agent 的调用标签。
        :param kwargs: 框架提供的其他回调元数据，本回调不读取。
        """
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
        """
        显示工具开始，只在调试模式打印参数。

        :param serialized: 工具序列化信息，从 name 字段读取工具名称。
        :param input_str: 工具入参文本，仅在调试模式下脱敏显示。
        :param run_id: 本次工具调用的唯一标识，用于匹配结束或错误事件。
        :param tags: 用于识别 Agent 的调用标签。
        :param kwargs: 框架提供的其他回调元数据，本回调不读取。
        """
        role, name = self._role(tags), str(serialized.get("name", "未知工具"))
        self._tools[run_id] = (role, name)
        self.progress(f"[{role}] 工具开始：{name}")
        if self.debug_tools:
            self.progress(f"[{role}·执行参数] {input_str}")

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """
        区分成功结果和被框架转为 ToolMessage 的错误结果。

        :param output: 工具结果，包含错误状态的 ToolMessage 按失败展示。
        :param run_id: 用于取回工具所属角色与名称的调用标识。
        :param kwargs: 框架提供的其他回调元数据，本回调不读取。
        """
        role, name = self._tools.pop(run_id, ("模型", "未知工具"))
        if isinstance(output, ToolMessage) and output.status == "error":
            self.progress(f"[{role}] 工具失败：{name}；{output.text}")
        else:
            self.progress(f"[{role}] 工具完成：{name}")

    async def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        """
        工具异常也显示脱敏原因，不输出原始堆栈。

        :param error: 工具抛出的异常，输出前由进度方法统一脱敏。
        :param run_id: 用于取回工具所属角色与名称的调用标识。
        :param kwargs: 框架提供的其他回调元数据，本回调不读取。
        """
        role, name = self._tools.pop(run_id, ("模型", "未知工具"))
        self.progress(f"[{role}] 工具失败：{name} [{type(error).__name__}]；{error}")
