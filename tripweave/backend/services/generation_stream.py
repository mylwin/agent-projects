"""将真实规划回调作为 SSE 发送，不向页面公开工具参数或原始结果。"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import UUID

from anyio import CancelScope
from langchain_core.messages import ToolMessage
from langchain_core.outputs import LLMResult

from backend.errors import ApiException, redact
from backend.schemas.api import ApiSuccess
from backend.schemas.projects import GeneratePlanData
from backend.schemas.trip import PlanResult
from backend.services.model_trace import ModelTrace

logger = logging.getLogger("tripweave.api.stream")

AGENT_LABELS = {
    "attractions": "景点研究",
    "weather": "天气研究",
    "hotels": "住宿研究",
    "planner": "行程规划",
}


class GenerationStream(ModelTrace):
    """保留原有模型轨迹，同时收集有限数量的阶段和工具生命周期事件。"""

    def __init__(self, model_name: str, secrets: tuple[str, ...]) -> None:
        """注入模型名称与需要隐藏的凭据。"""
        super().__init__(model_name, secrets)
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.tools: dict[UUID, tuple[str, str]] = {}

    def progress(self, message: str) -> None:
        """把真实阶段说明放入本轮事件队列。"""
        self.emit("progress", message)

    def emit(self, event: str, message: str, **data: Any) -> None:
        """发送脱敏后的有限元数据，不发送模型输入和工具原文。"""
        self.events.put_nowait(
            {"event": event, "message": redact(message, self.secrets), **data}
        )

    @staticmethod
    def agent_label(tags: list[str] | None) -> str:
        """从框架标签读取当前研究角色。"""
        return next(
            (
                AGENT_LABELS[tag[6:]]
                for tag in tags or []
                if tag.startswith("agent:") and tag[6:] in AGENT_LABELS
            ),
            "模型",
        )

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """记录调用并立即通知页面模型已经开始工作。"""
        await super().on_chat_model_start(serialized, messages, run_id=run_id, **kwargs)
        self.emit("model_start", f"{self.agent_label(tags)}：模型开始生成")

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """沿用公开轨迹保存，并标记本次模型调用完成。"""
        await super().on_llm_end(response, run_id=run_id, tags=tags, **kwargs)
        self.emit("model_end", f"{self.agent_label(tags)}：模型生成完成")

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """仅公开工具名称和调用标识，不公开请求参数。"""
        role = self.agent_label(tags)
        name = redact(str(serialized.get("name", "未知工具")), self.secrets)
        self.tools[run_id] = (role, name)
        self.emit("tool_start", f"{role}：正在调用 {name}", call_id=str(run_id))

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """区分工具返回的错误与成功；工具失败可能由研究 Agent 恢复。"""
        role, name = self.tools.pop(run_id, ("模型", "未知工具"))
        failed = isinstance(output, ToolMessage) and output.status == "error"
        self.emit(
            "tool_error" if failed else "tool_end",
            f"{role}：{name} {'调用失败' if failed else '调用完成'}",
            call_id=str(run_id),
        )

    async def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        """工具异常只公开失败状态，详细原因由最终业务错误处理。"""
        role, name = self.tools.pop(run_id, ("模型", "未知工具"))
        self.emit("tool_error", f"{role}：{name} 调用失败", call_id=str(run_id))

    async def iterate(
        self,
        generate: Callable[[], Awaitable[ApiSuccess[PlanResult | GeneratePlanData]]],
    ) -> AsyncGenerator[str]:
        """并发执行规划和事件发送；断开连接时取消规划并等待清理。"""

        async def produce() -> None:
            """把最终结果或稳定的业务错误作为唯一终态事件发送。"""
            try:
                result = await generate()
                self.events.put_nowait(
                    {"event": "complete", "data": result.data.model_dump(mode="json")}
                )
            except ApiException as exc:
                self.events.put_nowait(
                    {"event": "error", "error": exc.error.model_dump()}
                )
            except Exception as exc:
                logger.error(
                    "流式生成失败 [%s]：%s",
                    type(exc).__name__,
                    redact(str(exc), self.secrets),
                )
                self.events.put_nowait(
                    {
                        "event": "error",
                        "error": ApiException.internal().error.model_dump(),
                    }
                )

        task = asyncio.create_task(produce())
        try:
            yield self.encode({"event": "started", "message": "已开始生成行程"})
            while True:
                try:
                    event = await asyncio.wait_for(self.events.get(), timeout=15)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield self.encode(event)
                if event["event"] in {"complete", "error"}:
                    break
        finally:
            task.cancel()
            # Starlette 使用取消作用域处理中断；清理期间允许运行记录落盘。
            with CancelScope(shield=True), suppress(asyncio.CancelledError):
                await task

    @staticmethod
    def encode(event: dict[str, Any]) -> str:
        """每个事件编码成独立 SSE 帧，JSON 内换行不会破坏帧边界。"""
        return f"event: {event['event']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
