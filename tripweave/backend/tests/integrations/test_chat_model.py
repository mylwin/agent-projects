"""验证聊天模型适配层保留供应商扩展字段。"""

import unittest
from typing import Any

from langchain_core.messages import AIMessageChunk

from backend.integrations.chat_model import ReasoningChatOpenAI


def _chunk(delta: dict[str, Any]) -> dict[str, Any]:
    """
    构造一条 OpenAI 兼容的流式分片。

    :param delta: 分片中的增量字段。
    :return: 可直接交给适配层转换的字典。
    """
    return {
        "id": "chunk",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "qwen3",
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
    }


class ChatModelTests(unittest.TestCase):
    """覆盖思考链字段的兼容处理。"""

    def test_reasoning_chunk_is_preserved(self) -> None:
        """
        本地子类要保留供应商的 reasoning_content。

        :param self: 当前测试实例。
        """
        model = ReasoningChatOpenAI(
            model="qwen3",
            api_key="test",
            base_url="http://test/v1",
            max_retries=0,
        )
        for key in ("reasoning_content", "reasoning"):
            generation = model._convert_chunk_to_generation_chunk(
                _chunk(
                    {
                        "role": "assistant",
                        "content": "",
                        key: "先分析需求",
                    }
                ),
                AIMessageChunk,
                None,
            )
            assert generation is not None
            self.assertEqual(
                generation.message.additional_kwargs["reasoning_content"],
                "先分析需求",
            )
