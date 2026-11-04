"""通用结构化 Agent 执行器，不包含旅行或其他业务规则。"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel


class AgentBudgetError(RuntimeError):
    """模型循环用尽步数或调用次数，仍没有提交结构化结果。"""


class _ChunkWatcher(AsyncCallbackHandler):
    """模型流式生成期间逐片通知调用方，用于显示仍在生成。"""

    def __init__(self, on_chunk: Callable[[], None]) -> None:
        """
        记录片段回调。

        :param on_chunk: 每收到一个流式片段时调用一次。
        """
        self._on_chunk = on_chunk

    async def on_llm_new_token(self, *args: Any, **kwargs: Any) -> None:
        """
        忽略片段内容，只统计到达次数。

        结构化输出时片段文本为空字符串，无法展示真实文字，只能用于确认仍在生成。

        :param args: 框架传入的片段文本及位置参数，此处不使用。
        :param kwargs: 框架附加的 chunk、run_id 等信息，此处不使用。
        """
        self._on_chunk()


@dataclass(frozen=True)
class AgentStep:
    """
    Agent 循环中的一次可观察步骤，供调用方转换成用户可见的进度。

    Attributes:
        kind: 步骤类型，``model`` 为模型返回，``tool`` 为工具返回。
        call_index: 第几次模型调用；工具步骤沿用触发它的调用序号。
        tool_names: 相关工具名；模型步骤是它请求的工具，工具步骤是执行完的工具。
    """

    kind: Literal["model", "tool"]
    call_index: int
    tool_names: tuple[str, ...] = ()


async def run_structured_agent(
    *,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
    response_model: type[BaseModel],
    user_content: str,
    timeout_seconds: float,
    max_model_calls: int = 6,
    recursion_limit: int | None = None,
    on_step: Callable[[AgentStep], None] | None = None,
    on_chunk: Callable[[], None] | None = None,
) -> BaseModel:
    """
    执行一次"模型—工具—结构化结果"循环。

    只负责循环本身：建 Agent、流式取状态、按上限结束、写出结构化结果。
    目的地区域、地点真实性等业务约束由调用方在进入和离开本函数时处理。

    :param model: 支持工具调用的聊天模型。
    :param tools: 本轮允许模型调用的工具。
    :param system_prompt: 本轮系统提示词，由业务层提供。
    :param response_model: 最终结构化结果类型。
    :param user_content: 本轮唯一的用户消息内容。
    :param timeout_seconds: 整轮执行的总超时秒数。
    :param max_model_calls: 模型调用次数上限。
    :param recursion_limit: 框架步数上限。
    :param on_step: 步骤回调，为 None 时不输出进度。
    :param on_chunk: 流式片段回调，用于在长生成期间显示活动。
    :return: 已校验的结构化结果实例。
    :raises TimeoutError: 整轮超过 ``timeout_seconds`` 时抛出。
    :raises AgentBudgetError: 达到步数或调用次数上限仍没有结构化结果时抛出。
    :raises RuntimeError: 循环没有返回状态时抛出。
    """
    agent = create_agent(
        model=model,
        tools=list(tools),
        system_prompt=system_prompt,
        response_format=ToolStrategy(response_model, handle_errors=False),
        middleware=[
            ModelCallLimitMiddleware(run_limit=max_model_calls, exit_behavior="error")
        ],
    )
    # 每次模型调用最多占 4 个图步（前置中间件、模型、后置中间件、工具），
    # 步数上限必须大于调用上限，否则会先撞图步数而不是给出可解释的调用超限。
    step_budget = recursion_limit or max_model_calls * 4 + 8
    state: dict[str, Any] | None = None
    seen_messages = 0
    model_calls = 0
    async with asyncio.timeout(timeout_seconds):
        config: RunnableConfig = {"recursion_limit": step_budget}
        if on_chunk is not None:
            config["callbacks"] = [_ChunkWatcher(on_chunk)]
        try:
            async for snapshot in agent.astream(
                {"messages": [{"role": "user", "content": user_content}]},
                config=config,
                stream_mode="values",
            ):
                state = snapshot
                messages = snapshot["messages"]
                for message in messages[seen_messages:]:
                    if isinstance(message, AIMessage):
                        model_calls += 1
                        names = tuple(call["name"] for call in message.tool_calls)
                        _emit(on_step, AgentStep("model", model_calls, names))
                    elif isinstance(message, ToolMessage):
                        _emit(
                            on_step,
                            AgentStep("tool", model_calls, (message.name or "",)),
                        )
                seen_messages = len(messages)
        except GraphRecursionError:
            raise AgentBudgetError(
                f"模型在 {step_budget} 个图步内没有提交结构化结果，"
                "可能一直在重复调用工具"
            ) from None
        except ModelCallLimitExceededError:
            raise AgentBudgetError(
                f"模型调用达到 {max_model_calls} 次上限仍未提交结构化结果"
            ) from None
    if state is None or "structured_response" not in state:
        raise RuntimeError("模型循环没有返回结构化结果")
    return state["structured_response"]


def _emit(on_step: Callable[[AgentStep], None] | None, step: AgentStep) -> None:
    """
    把步骤交给回调，调用方未提供回调时什么都不做。

    :param on_step: 步骤回调。
    :param step: 当前步骤。
    """
    if on_step is not None:
        on_step(step)
