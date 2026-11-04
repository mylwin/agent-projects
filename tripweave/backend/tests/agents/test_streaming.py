"""验证思考链、回复正文和工具事件的流式输出。"""

import json
import unittest
from collections.abc import Sequence
from typing import Any, Self

import httpx
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from backend.agents.runtime import run_structured_agent
from backend.integrations.chat_model import ReasoningChatOpenAI
from backend.schemas.run_event import (
    AgentEvent,
    MessageDelta,
    ReasoningDelta,
    ToolFinished,
    ToolStarted,
)


class Draft(BaseModel):
    """测试用结构化结果。"""

    title: str


class ToolCallingModel(FakeMessagesListChatModel):
    """可绑定工具的非流式消息替身。"""

    def bind_tools(self, tools: Sequence[object], **kwargs: object) -> Self:
        """
        接受框架注册的工具，由预设消息决定工具调用。

        :param self: 当前消息模型。
        :param tools: 框架注册的工具定义。
        :param kwargs: 框架传入的工具绑定选项。
        :return: 保持预设响应顺序的模型本身。
        """
        return self


def _chunk(delta: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
    """
    构造一条 OpenAI 兼容的流式分片。

    :param delta: 分片中的增量字段。
    :param finish_reason: 结束原因，普通分片为 None。
    :return: 可直接序列化为 SSE data 的字典。
    """
    return {
        "id": "chunk",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "qwen3",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _sse_response(events: list[dict[str, Any]]) -> httpx.Response:
    """
    把分片列表转换成 OpenAI SDK 可解析的 SSE 响应。

    :param events: 按顺序发送的分片。
    :return: 带 text/event-stream 头的模拟响应。
    """
    body = "".join(
        f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events
    )
    return httpx.Response(
        200,
        content=(body + "data: [DONE]\n\n").encode("utf-8"),
        headers={"content-type": "text/event-stream"},
    )


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    """验证三类模型文本和工具事件都能被观察。"""

    async def test_stream_emits_reasoning_message_and_tool_events(self) -> None:
        """
        流式分片要分别产生思考、回复和工具事件，且不重复。

        :param self: 当前异步测试实例。
        """
        events = [
            _chunk(
                {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "用户想去成都，",
                }
            ),
            _chunk({"content": "", "reasoning_content": "三天预算三千。"}),
            _chunk({"content": "我先按市区为主安排。"}),
            _chunk(
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "Draft",
                                "arguments": '{"title":',
                            },
                        }
                    ],
                }
            ),
            _chunk(
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {"arguments": '"成都三日"}'},
                        }
                    ],
                }
            ),
            _chunk({}, "tool_calls"),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            """忽略请求内容，始终返回预设流。"""
            return _sse_response(events)

        observed: list[AgentEvent] = []
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            model = ReasoningChatOpenAI(
                model="qwen3",
                api_key="test",
                base_url="http://test/v1",
                streaming=True,
                max_retries=0,
                http_async_client=http,
                http_socket_options=(),
            )
            result = await run_structured_agent(
                model=model,
                tools=[],
                system_prompt="测试",
                response_model=Draft,
                user_content="安排成都三天",
                timeout_seconds=5,
                max_model_calls=1,
                on_event=observed.append,
            )

        self.assertEqual(result.response, Draft(title="成都三日"))
        self.assertEqual(result.reasoning, "用户想去成都，三天预算三千。")
        self.assertEqual(result.message, "我先按市区为主安排。")
        self.assertEqual(result.call_index, 1)
        self.assertEqual(
            "".join(event.text for event in observed if isinstance(event, ReasoningDelta)),
            result.reasoning,
        )
        self.assertEqual(
            "".join(event.text for event in observed if isinstance(event, MessageDelta)),
            result.message,
        )
        self.assertEqual(
            [event.name for event in observed if isinstance(event, ToolStarted)],
            ["Draft"],
        )
        self.assertEqual(
            [event.name for event in observed if isinstance(event, ToolFinished)],
            ["Draft"],
        )

    async def test_non_streaming_message_is_emitted_once(self) -> None:
        """
        非流式替身通过完整消息补发一次，不能重复。

        :param self: 当前异步测试实例。
        """
        message = AIMessage(
            content="这是给用户的说明。",
            additional_kwargs={"reasoning_content": "先分析需求。"},
            tool_calls=[
                {
                    "name": "Draft",
                    "id": "call-1",
                    "args": {"title": "成都三日"},
                }
            ],
        )
        observed: list[AgentEvent] = []
        result = await run_structured_agent(
            model=ToolCallingModel(responses=[message]),
            tools=[],
            system_prompt="测试",
            response_model=Draft,
            user_content="安排成都三天",
            timeout_seconds=5,
            max_model_calls=1,
            on_event=observed.append,
        )

        self.assertEqual(result.reasoning, "先分析需求。")
        self.assertEqual(result.message, "这是给用户的说明。")
        self.assertEqual(sum(isinstance(e, ReasoningDelta) for e in observed), 1)
        self.assertEqual(sum(isinstance(e, MessageDelta) for e in observed), 1)
        self.assertEqual(
            [event.name for event in observed if isinstance(event, ToolStarted)],
            ["Draft"],
        )
        self.assertEqual(
            [event.name for event in observed if isinstance(event, ToolFinished)],
            ["Draft"],
        )
