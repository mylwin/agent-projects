"""命令行运行独立 Agent：python -m backend examples/trip-request.json。"""

import argparse
import asyncio
import sys
from pathlib import Path

from backend.agents.console import ConsoleCallback
from backend.config.env import load_env
from backend.config.planner import PlannerSettings
from backend.schemas.trip import TripRequest
from backend.services.planning import generate_trip


def main() -> int:
    """
    读取需求、运行一次规划，进度写 stderr，结果 JSON 写 stdout。

    :return: 成功时返回 0；输入、配置、超时或服务错误时返回 1。
    """
    load_env()
    parser = argparse.ArgumentParser(description="生成国内旅行行程草稿")
    parser.add_argument("input", type=Path, help="旅行需求 JSON 文件")
    parser.add_argument(
        "--debug-tools",
        action="store_true",
        help="显示流式工具参数（含 Planner JSON 参数）",
    )
    args = parser.parse_args()
    try:
        request = TripRequest.model_validate_json(
            args.input.read_text(encoding="utf-8")
        )
        settings = PlannerSettings.from_env()
    except (OSError, ValueError) as exc:
        print(f"输入或配置错误：{exc}", file=sys.stderr)
        return 1
    console = ConsoleCallback(
        debug_tools=args.debug_tools,
        secrets=(settings.model_api_key, settings.amap_api_key, settings.baidu_api_key),
    )
    try:
        result = asyncio.run(
            generate_trip(
                request,
                settings,
                console.progress,
                console,
            )
        )
    except TimeoutError:
        print("规划超时，请检查网络或调整 PLANNER_TIMEOUT_SECONDS。", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as exc:
        print(f"规划失败：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # SDK 异常可能包含带凭证的 URL，不直接展示原始异常内容。
        print(
            f"模型或外部服务失败（{type(exc).__name__}），请检查配置与网络。",
            file=sys.stderr,
        )
        return 1
    finally:
        console.finish()
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
