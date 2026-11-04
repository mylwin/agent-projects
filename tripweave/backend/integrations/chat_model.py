"""OpenAI 兼容聊天模型适配：流式请求与思考链保留。"""

from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.config.planner import PlannerSettings


class ReasoningChatOpenAI(ChatOpenAI):
    """
    保留第三方兼容接口扩展字段的聊天模型。

    ``ChatOpenAI`` 在流式请求中只转换标准 OpenAI 字段，会丢掉 Qwen、DeepSeek
    等供应商返回的 ``reasoning_content``。这里在本地子类中补回该字段，
    不修改依赖包。
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None,
    ) -> ChatGenerationChunk | None:
        """
        在标准分片转换之后补回思考链文本。

        :param chunk: 供应商返回的原始 SSE 分片字典。
        :param default_chunk_class: 未指定角色时使用的消息分片类型。
        :param base_generation_info: 框架附加的生成信息。
        :return: 带 reasoning_content 的消息分片，无法转换时为 None。
        """
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation is None:
            return None
        choices = chunk.get("choices") or []
        for choice in choices:
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
            # 与父类一致，只处理首个 choice。
            break
        return generation


def create_chat_model(
    settings: PlannerSettings, http: httpx.AsyncClient
) -> BaseChatModel:
    """
    按配置创建支持工具调用与流式输出的聊天模型。

    默认开启流式：思考型模型在非流式请求下要等整段生成完才返回响应头，
    很容易被单次读超时打断；流式改按分片计时，长生成不再误判超时。

    :param settings: 从环境变量读取的服务配置。
    :param http: 调用方管理的异步 HTTP 客户端。
    :return: 指向 OpenAI 兼容接口的聊天模型。
    """
    # 只在显式配置时发送思考链参数：部分供应商与模型不支持，默认不传。
    extra_body: dict[str, object] = {}
    if settings.model_enable_thinking is not None:
        extra_body["enable_thinking"] = settings.model_enable_thinking
    if settings.model_thinking_budget is not None:
        extra_body["thinking_budget"] = settings.model_thinking_budget
    return ReasoningChatOpenAI(
        model=settings.model_name,
        base_url=settings.model_base_url,
        api_key=SecretStr(settings.model_api_key),
        timeout=settings.model_timeout_seconds,
        max_retries=0,
        streaming=True,
        extra_body=extra_body or None,
        http_async_client=http,
    )
