"""创建标准 OpenAI 兼容模型，不依赖 SDK 私有方法。"""

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.config.planner import PlannerSettings


def create_chat_model(
    settings: PlannerSettings, http: httpx.AsyncClient
) -> BaseChatModel:
    """复用调用方的 HTTP 连接；兼容思考模型的配置只在明确设置时发送。"""
    extra_body: dict[str, object] = {}
    if settings.model_enable_thinking is not None:
        extra_body["enable_thinking"] = settings.model_enable_thinking
    if settings.model_thinking_budget is not None:
        extra_body["thinking_budget"] = settings.model_thinking_budget
    return ChatOpenAI(
        model=settings.model_name,
        base_url=settings.model_base_url,
        api_key=SecretStr(settings.model_api_key),
        timeout=settings.model_timeout_seconds,
        max_retries=0,
        streaming=True,
        extra_body=extra_body or None,
        http_async_client=http,
    )
