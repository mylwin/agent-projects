"""创建标准 OpenAI 兼容模型，不依赖 SDK 私有方法。"""

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.config.planner import PlannerSettings


def create_chat_model(
    settings: PlannerSettings,
    http: httpx.AsyncClient,
    callback: AsyncCallbackHandler | None = None,
) -> BaseChatModel:
    """
    复用调用方的 HTTP 连接；兼容思考模型的配置只在明确设置时发送。

    :param settings: 模型名称、凭据、服务地址、超时和可选思考配置。
    :param http: 由调用方创建和关闭的异步 HTTP 客户端。
    :param callback: 可选的框架异步回调，用于显示流式进度。
    :return: 已配置流式输出、关闭自动重试的聊天模型，不在此发起请求。
    """
    # 额外的参数
    extra_body: dict[str, object] = {}
    # 如果配置了思考，则发送
    if settings.model_enable_thinking is not None:
        extra_body["enable_thinking"] = settings.model_enable_thinking
    # 如果配置了思考预算，则发送
    if settings.model_thinking_budget is not None:
        extra_body["thinking_budget"] = settings.model_thinking_budget
    # 创建模型
    return ChatOpenAI.model_validate(
        {
            "model": settings.model_name,
            "base_url": settings.model_base_url,
            "api_key": SecretStr(settings.model_api_key),
            "timeout": settings.model_timeout_seconds,
            "max_retries": 0,
            "streaming": True,
            "extra_body": extra_body or None,
            # 禁用 langchain-openai 的 socket-option transport，保留 httpx 的代理自动检测。
            "http_socket_options": (),
            "http_async_client": http,
            "callbacks": [callback] if callback is not None else None,
        }
    )
