"""通过 python -m backend.agents.planner 从 JSON 文件生成行程。"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from backend.agents.errors import AgentBudgetError
from backend.config.planner import PlannerSettings
from backend.schemas.planner_input import PlannerInput
from backend.schemas.planner_result import PlannerResult
from backend.schemas.run_event import (
    AgentEvent,
    MessageDelta,
    ReasoningDelta,
    StageChanged,
    ToolFinished,
    ToolStarted,
)
from backend.services.planning import generate_draft


def _thinking_label(settings: PlannerSettings) -> str:
    """
    把思考链配置转换成配置行里的短标签。

    :param settings: 从环境变量读取的服务配置。
    :return: 例如"默认""关闭""开启（预算 512）"。
    """
    if settings.model_enable_thinking is None:
        return "默认"
    state = "开启" if settings.model_enable_thinking else "关闭"
    if settings.model_thinking_budget is None:
        return state
    return f"{state}（预算 {settings.model_thinking_budget}）"


class _EventPrinter:
    """把运行事件写到标准错误，保持标准输出只有最终 JSON。"""

    def __init__(self, *, show_reasoning: bool) -> None:
        """
        记录展示选项并开始计时。

        :param show_reasoning: 是否把思考链写到终端。
        """
        self._show_reasoning = show_reasoning
        self._started = time.monotonic()
        self._channel = ""
        self._message: list[str] = []
        self._saw_reasoning = False
        self._reached_model = False

    @property
    def message_text(self) -> str:
        """已经流式展示过的回复正文。"""
        return "".join(self._message)

    def __call__(self, event: AgentEvent) -> None:
        """按事件类型选择对应的终端前缀。"""
        if isinstance(event, StageChanged):
            self._end_line()
            if event.stage == "generating":
                self._reached_model = True
            elapsed = time.monotonic() - self._started
            print(f"[规划] {event.message}（{elapsed:.1f}s）", file=sys.stderr, flush=True)
        elif isinstance(event, ReasoningDelta):
            self._saw_reasoning = True
            if self._show_reasoning:
                self._write_channel("思考", event.text)
        elif isinstance(event, MessageDelta):
            self._message.append(event.text)
            self._write_channel("回复", event.text)
        elif isinstance(event, ToolStarted):
            self._end_line()
            print(f"[工具] {event.name} 开始", file=sys.stderr, flush=True)
        elif isinstance(event, ToolFinished):
            self._end_line()
            print(f"[工具] {event.name} 完成", file=sys.stderr, flush=True)

    def finalize(self, result: PlannerResult) -> None:
        """
        补打模型没有流式输出的兜底回复，并提示思考链缺失。

        :param result: 已完成的规划结果。
        """
        reply = result.reply.strip()
        if reply and self.message_text.strip() != reply:
            self._write_channel("回复", reply)
        self._end_line()
        if self._show_reasoning and self._reached_model and not self._saw_reasoning:
            print(
                "[提示] 本轮未收到思考链；请确认模型支持思考并设置 "
                "MODEL_ENABLE_THINKING=true。",
                file=sys.stderr,
                flush=True,
            )

    def close(self) -> None:
        """结束尚未换行的流式输出。"""
        self._end_line()

    def _write_channel(self, name: str, text: str) -> None:
        """在同一通道内连续输出，切换通道时先换行。"""
        if self._channel != name:
            self._end_line()
            print(f"[{name}] ", end="", file=sys.stderr, flush=True)
            self._channel = name
        print(text, end="", file=sys.stderr, flush=True)

    def _end_line(self) -> None:
        """结束当前流式通道。"""
        if self._channel:
            print(file=sys.stderr, flush=True)
            self._channel = ""


def main() -> int:
    """
    读取输入文件并将结果 JSON 输出到标准输出，错误写入标准错误。

    需求检查与日期推导由 Planner 内部统一完成，此处只负责读取文件、装配配置
    和映射退出码，避免同一份校验在两处各执行一次。

    :return: 成功为 0，输入、配置或执行失败为 1。
    """
    parser = argparse.ArgumentParser(description="生成一份国内旅行行程草稿")
    parser.add_argument("input", type=Path, help="PlannerInput JSON 文件路径")
    parser.add_argument(
        "--no-reasoning",
        action="store_true",
        help="不显示模型思考链，仅显示阶段、回复与工具事件",
    )
    args = parser.parse_args()
    try:
        request = PlannerInput.model_validate_json(
            args.input.read_text(encoding="utf-8")
        )
        settings = PlannerSettings.from_env()
    except (OSError, ValueError, ValidationError) as exc:
        print(f"输入或配置错误：{exc}", file=sys.stderr)
        return 1
    # 先打印实际生效的配置，便于区分"模型慢"与"配错了地址或模型"。
    print(
        f"[配置] 模型={settings.model_name} 地址={settings.model_base_url} "
        f"单次超时={settings.model_timeout_seconds:g}s "
        f"整轮超时={settings.planner_timeout_seconds:g}s "
        f"地图={settings.map_provider} 思考={_thinking_label(settings)}",
        file=sys.stderr,
        flush=True,
    )
    printer = _EventPrinter(show_reasoning=not args.no_reasoning)
    try:
        result = asyncio.run(
            generate_draft(request, settings, on_event=printer)
        )
    except TimeoutError:
        # 整轮超时是预期内的结果，单独说明并给出可调项。
        print(
            f"规划超时：超过 {settings.planner_timeout_seconds:g} 秒未完成，"
            "可调大 PLANNER_TIMEOUT_SECONDS 或更换更快的模型。",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        # 需求不完整、日期或地点引用不合法时直接给出原因。
        print(f"未能生成有效行程：{exc}", file=sys.stderr)
        return 1
    except AgentBudgetError as exc:
        # 模型循环用尽预算，属于模型行为问题而不是网络故障。
        print(f"未能在预算内生成行程：{exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        # 供应商客户端已转换异常，且不会携带密钥。
        print(f"外部服务调用失败（{type(exc).__name__}）：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        # SDK 异常可能携带原始请求与 URL，仅展示异常类别。
        print(
            f"未预期的失败（{type(exc).__name__}），请检查配置与网络。",
            file=sys.stderr,
        )
        return 1
    finally:
        printer.close()
    printer.finalize(result)
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
