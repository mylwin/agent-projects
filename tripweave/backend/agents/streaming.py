"""把 LangChain 流式分片和消息快照转换成运行事件。"""

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from backend.schemas.run_event import (
    AgentEvent,
    EventSink,
    MessageDelta,
    ReasoningDelta,
    ToolFinished,
    ToolStarted,
)


class StreamObserver(AsyncCallbackHandler):
    """观察模型分片和消息快照，累计文本并发出运行事件。"""

    def __init__(self, emit: EventSink | None) -> None:
        """
        记录事件回调并初始化累计文本。

        :param emit: 收到事件时调用；为 None 时只累计文本。
        """
        self._emit = emit
        self._call_index = 0
        self._seen_messages = 0
        self._reasoning: list[str] = []
        self._message: list[str] = []
        self._saw_reasoning = False
        self._saw_message = False
        self._started_tools: set[str] = set()

    @property
    def call_index(self) -> int:
        """当前模型调用序号，至少为一。"""
        return max(self._call_index, 1)

    @property
    def reasoning(self) -> str:
        """本轮累计的思考链文本。"""
        return "".join(self._reasoning)

    @property
    def message(self) -> str:
        """本轮累计的面向用户回复文本。"""
        return "".join(self._message)

    async def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        """
        每次模型调用开始时重置单次标记。

        :param args: 框架传入的位置参数，此处不使用。
        :param kwargs: 框架传入的关键字参数，此处不使用。
        """
        self._call_index += 1
        self._saw_reasoning = False
        self._saw_message = False
        self._started_tools.clear()

    async def on_llm_new_token(
        self, token: str, *, chunk: Any = None, **kwargs: Any
    ) -> None:
        """
        把思考链、回复正文和工具调用的分片转成事件。

        ``chunk`` 是 ``ChatGenerationChunk``，文本和扩展字段都在
        ``chunk.message`` 上；工具参数在 ``tool_call_chunks`` 中。

        :param token: 框架给出的回复正文分片，思考型模型通常为空字符串。
        :param chunk: 带附加字段和工具调用的完整生成分片。
        :param kwargs: 框架附加的 run_id 等信息，此处不使用。
        """
        message = getattr(chunk, "message", None)
        if message is not None:
            reasoning = _reasoning_text(message)
            if reasoning:
                self._saw_reasoning = True
                self._reasoning.append(reasoning)
                self._emit_event(ReasoningDelta(reasoning, self.call_index))
            for tool_chunk in getattr(message, "tool_call_chunks", ()) or ():
                name = tool_chunk.get("name")
                if name:
                    self._start_tool(name)
        if token:
            self._saw_message = True
            self._message.append(token)
            self._emit_event(MessageDelta(token, self.call_index))

    def absorb_snapshot(self, messages: Sequence[BaseMessage]) -> None:
        """
        处理一次 values 快照中的新消息。

        流式路径已经逐片发过，单次标记为真时不会重复输出；非流式路径
        在这里补发完整文本。消息 diff 留在观察器内，运行时只负责循环。

        :param messages: LangGraph 当前状态中的完整消息列表。
        """
        for message in messages[self._seen_messages :]:
            if isinstance(message, AIMessage):
                self._absorb_message(message)
            elif isinstance(message, ToolMessage):
                self._finish_tool(message.name or "")
        self._seen_messages = len(messages)

    def _absorb_message(self, message: AIMessage) -> None:
        """从完整模型消息补发思考链、回复正文和工具开始事件。"""
        if not self._saw_reasoning:
            reasoning = _reasoning_text(message)
            if reasoning:
                self._reasoning.append(reasoning)
                self._emit_event(ReasoningDelta(reasoning, self.call_index))
        if not self._saw_message:
            text = _message_text(message)
            if text:
                self._message.append(text)
                self._emit_event(MessageDelta(text, self.call_index))
        for call in message.tool_calls:
            name = call.get("name")
            if name:
                self._start_tool(name)

    def _finish_tool(self, name: str) -> None:
        """发出工具完成事件。"""
        if name:
            self._emit_event(ToolFinished(name, self.call_index))

    def _start_tool(self, name: str) -> None:
        """同一模型调用内同名工具只发一次开始事件。"""
        if name in self._started_tools:
            return
        self._started_tools.add(name)
        self._emit_event(ToolStarted(name, self.call_index))

    def _emit_event(self, event: AgentEvent) -> None:
        """调用方没有提供回调时只累计文本。"""
        if self._emit is not None:
            self._emit(event)


def _reasoning_text(message: BaseMessage) -> str:
    """
    从消息附加字段中取出思考链文本。

    兼容 ``reasoning_content`` 与 ``reasoning`` 两种常见供应商字段。

    :param message: 模型消息或消息分片。
    :return: 本次分片包含的思考文本，没有时为空字符串。
    """
    for key in ("reasoning_content", "reasoning"):
        text = _text_value(message.additional_kwargs.get(key))
        if text:
            return text
    return ""


def _message_text(message: BaseMessage) -> str:
    """
    取出消息正文，兼容字符串和文本内容块两种形式。

    :param message: 模型完整消息。
    :return: 面向用户的正文，没有时为空字符串。
    """
    content = message.content
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _text_value(value: object) -> str:
    """
    把字符串或结构化文本列表统一成字符串。

    :param value: 附加字段的原始值。
    :return: 拼接后的文本，没有可读内容时为空字符串。
    """
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("reasoning")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)
