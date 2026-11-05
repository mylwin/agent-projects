"""命令行运行独立 Agent：python -m backend examples/trip-request.json。"""

import argparse
import asyncio
import sys
from pathlib import Path

from backend.config.planner import PlannerSettings
from backend.schemas.trip import TripRequest
from backend.services.planning import generate_trip


def main() -> int:
    """读取需求、运行一次规划，进度写 stderr，结果 JSON 写 stdout。"""
    parser = argparse.ArgumentParser(description="生成国内旅行行程草稿")
    parser.add_argument("input", type=Path, help="旅行需求 JSON 文件")
    args = parser.parse_args()
    try:
        request = TripRequest.model_validate_json(
            args.input.read_text(encoding="utf-8")
        )
        settings = PlannerSettings.from_env()
    except (OSError, ValueError) as exc:
        print(f"输入或配置错误：{exc}", file=sys.stderr)
        return 1
    try:
        result = asyncio.run(
            generate_trip(
                request,
                settings,
                lambda message: print(message, file=sys.stderr, flush=True),
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
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
