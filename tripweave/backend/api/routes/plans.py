"""行程生成路由。"""

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_generation_limit, get_settings
from backend.config.planner import PlannerSettings
from backend.errors import ApiException, PlanningError, redact
from backend.schemas.api import ApiFailure, ApiSuccess
from backend.schemas.trip import PlanResult, TripRequest
from backend.services.planning import generate_trip

logger = logging.getLogger("tripweave.api.plans")
router = APIRouter(tags=["plans"])

# 仅用于 OpenAPI 文档，实际失败响应由全局异常处理器生成。
PLAN_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"model": ApiFailure, "description": "请求不合法或无法生成"},
    429: {"model": ApiFailure, "description": "并发生成任务已满"},
    500: {"model": ApiFailure, "description": "未处理异常"},
    502: {"model": ApiFailure, "description": "模型或地图服务失败"},
    503: {"model": ApiFailure, "description": "运行配置缺失"},
    504: {"model": ApiFailure, "description": "规划超时"},
}


def log_progress(message: str) -> None:
    """
    将同步规划进度写入服务端日志。

    :param message: 规划阶段说明。
    """
    logger.info("规划进度：%s", message)


@router.post(
    "/plans/generate",
    response_model=ApiSuccess[PlanResult],
    responses=PLAN_ERROR_RESPONSES,
)
async def generate(
    request: TripRequest,
    settings: Annotated[PlannerSettings, Depends(get_settings)],
    limit: Annotated[asyncio.Semaphore, Depends(get_generation_limit)],
) -> ApiSuccess[PlanResult]:
    """
    运行一次完整规划，返回统一成功体；失败由统一异常处理器转换。

    :param request: 已校验的旅行需求。
    :param settings: 模型与地图配置。
    :param limit: 应用级并发生成限制。
    :return: 包含 PlanResult 的统一成功响应。
    """
    # 如果并发生成已满，则返回错误。
    if limit.locked():
        raise ApiException.busy()
    async with limit:
        try:
            result = await generate_trip(
                request,
                settings,
                on_progress=log_progress,
            )
        except TimeoutError:
            raise ApiException.timeout() from None
        except PlanningError as exc:
            raise ApiException.from_planning(exc) from None
        except Exception as exc:
            secrets = (
                settings.model_api_key,
                settings.amap_api_key,
                settings.baidu_api_key,
            )
            logger.error(
                "生成行程时发生未处理异常 [%s]：%s",
                type(exc).__name__,
                redact(str(exc), secrets),
            )
            raise ApiException.internal() from None
    return ApiSuccess(data=result)
