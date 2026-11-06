"""行程生成路由。"""

import asyncio
import logging
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import get_generation_limit, get_settings
from backend.config.planner import PlannerSettings
from backend.errors import ApiException, PlanningError, redact
from backend.schemas.api import ApiError, ApiFailure, ApiSuccess
from backend.schemas.projects import GeneratePlanData, GeneratePlanRequest
from backend.schemas.trip import PlanResult
from backend.services import saved_generation
from backend.services.model_trace import ModelTrace
from backend.services.planning import generate_trip

logger = logging.getLogger("tripweave.api.plans")
router = APIRouter(tags=["plans"])

# 仅用于 OpenAPI 文档，实际失败响应由全局异常处理器生成。
PLAN_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiFailure, "description": "保存时未登录"},
    404: {"model": ApiFailure, "description": "要追加版本的计划不存在"},
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
    response_model=ApiSuccess[PlanResult | GeneratePlanData],
    responses=PLAN_ERROR_RESPONSES,
)
async def generate(
    request: GeneratePlanRequest,
    http_request: Request,
    settings: Annotated[PlannerSettings, Depends(get_settings)],
    limit: Annotated[asyncio.Semaphore, Depends(get_generation_limit)],
) -> ApiSuccess[PlanResult | GeneratePlanData]:
    """
    运行一次完整规划，返回统一成功体；失败由统一异常处理器转换。

    :param request: 已校验的旅行需求。
    :param settings: 模型与地图配置。
    :param limit: 应用级并发生成限制。
    :return: 包含 PlanResult 的统一成功响应。
    """
    # 如果请求中计划名称不为 None，或者项目 ID 不为 None，则保存计划。
    save = request.name is not None or request.project_id is not None
    # 如果计划名称和项目 ID 都不为 None，则返回错误。
    if request.name is not None and request.project_id is not None:
        raise ApiException(
            422, ApiError(code="invalid_request", message="已有计划不需要 name")
        )
    # 获取当前用户。
    user = http_request.state.current_user
    if save and user is None:
        raise ApiException(401, ApiError(code="unauthorized", message="请先登录"))
    factory = getattr(http_request.app.state, "database_session_factory", None)
    if save and factory is None:
        raise ApiException.configuration("未配置数据库连接")
    factory = cast(async_sessionmaker[AsyncSession], factory)
    if (
        save
        and request.project_id is not None
        and not await saved_generation.existing_project(
            factory, user.id, request.project_id
        )
    ):
        raise ApiException(
            404, ApiError(code="project_not_found", message="计划不存在")
        )
    # 如果并发生成已满，则返回错误。
    if limit.locked():
        raise ApiException.busy()
    async with limit:
        # 单独提交运行记录并返回运行的ID。
        run_id = (
            await saved_generation.start_run(
                factory,
                user.id,
                request.project_id,
                request,
                settings.model_name,
                settings.map_provider,
            )
            if save
            else None
        )
        # 创建模型调用追踪器
        trace = (
            ModelTrace(
                settings.model_name,
                (settings.model_api_key, settings.amap_api_key, settings.baidu_api_key),
            )
            if save
            else None
        )
        try:
            # 生成旅途规划
            result = await generate_trip(
                request,
                settings,
                on_progress=log_progress,
                callback=trace,
            )
        except TimeoutError:
            # 如果是规划超时，则保存失败记录并返回超时错误。
            if run_id is not None:
                await saved_generation.mark_failed(
                    factory, run_id, "planning_timeout", None
                )
            raise ApiException.timeout() from None
        except PlanningError as exc:
            # 如果是规划错误，则保存失败记录并返回错误。
            error = ApiException.from_planning(exc)
            if run_id is not None:
                await saved_generation.mark_failed(
                    factory, run_id, error.error.code, exc.stage
                )
            raise error from None
        except Exception as exc:
            # 如果是系统内部错误，则保存失败记录并返回错误。
            if run_id is not None:
                await saved_generation.mark_failed(
                    factory, run_id, "internal_error", None
                )
            # 系统密钥
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

    # 如果运行记录不为 None，则保存结果并返回结果。
    if run_id is not None:
        try:
            saved = await saved_generation.save_result(
                factory,
                user.id,
                request.project_id,
                request.name,
                request,
                run_id,
                result,
                trace.calls if trace is not None else [],
            )
        except Exception:
            await saved_generation.mark_failed(factory, run_id, "save_failed", "持久化")
            logger.exception("保存生成结果失败")
            raise ApiException.internal() from None
        return ApiSuccess(data=saved)
    return ApiSuccess(data=result)
