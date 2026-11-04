"""通过 python -m backend.agents 从 JSON 文件生成行程。"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from backend.agents.runtime import AgentBudgetError
from backend.config.planner import PlannerSettings
from backend.schemas.planner_input import PlannerInput
from backend.services.planning import generate_draft

# 模型生成期间的心跳间隔：既能看到还在动，又不刷屏。
BEAT_INTERVAL_SECONDS = 3.0


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


def main() -> int:
    """
    读取输入文件并将结果 JSON 输出到标准输出，错误写入标准错误。

    需求检查与日期推导由 Planner 内部统一完成，此处只负责读取文件、装配配置
    和映射退出码，避免同一份校验在两处各执行一次。

    :return: 成功为 0，输入、配置或执行失败为 1。
    """
    parser = argparse.ArgumentParser(description="生成一份国内旅行行程草稿")
    parser.add_argument("input", type=Path, help="PlannerInput JSON 文件路径")
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
    chunks = 0
    last_beat = 0.0

    def write_progress(message: str) -> None:
        """输出一条业务进度。"""
        print(f"[规划] {message}", file=sys.stderr, flush=True)

    def write_chunk() -> None:
        """模型生成期间按固定间隔报告已收到的流式片段数。"""
        nonlocal chunks, last_beat
        chunks += 1
        now = time.monotonic()
        if now - last_beat >= BEAT_INTERVAL_SECONDS:
            last_beat = now
            write_progress(f"模型生成中… 已收到 {chunks} 个片段")

    try:
        result = asyncio.run(
            generate_draft(
                request,
                settings,
                on_progress=write_progress,
                on_chunk=write_chunk,
            )
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
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
