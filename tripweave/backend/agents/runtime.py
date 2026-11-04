"""通用结构化 Agent 执行器，不包含旅行或其他业务规则。"""

import asyncio
from collections.abc import Sequence
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel

from backend.agents.errors import AgentBudgetError
from backend.agents.result import AgentRunResult
from backend.agents.streaming import StreamObserver
from backend.schemas.run_event import EventSink


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
    on_event: EventSink | None = None,
) -> AgentRunResult:
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
    :param on_event: 运行事件回调，为 None 时只累计文本。
    :return: 结构化结果及累计的思考链与回复正文。
    :raises TimeoutError: 整轮超过 ``timeout_seconds`` 时抛出。
    :raises AgentBudgetError: 达到步数或调用次数上限仍没有结构化结果时抛出。
    :raises RuntimeError: 循环没有返回状态时抛出。
    """
    observer = StreamObserver(on_event)
    # 创建agent
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
    async with asyncio.timeout(timeout_seconds):
        config: RunnableConfig = {
            "recursion_limit": step_budget,
            "callbacks": [observer],
        }
        try:
            async for snapshot in agent.astream(
                {"messages": [{"role": "user", "content": user_content}]},
                config=config,
                stream_mode="values",
            ):
                state = snapshot
                observer.absorb_snapshot(snapshot["messages"])
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
    return AgentRunResult(
        response=state["structured_response"],
        reasoning=observer.reasoning,
        message=observer.message,
        call_index=observer.call_index,
    )
