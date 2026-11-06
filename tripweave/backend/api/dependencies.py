"""FastAPI 共享依赖：读取配置与并发生成限制。"""

import asyncio

from fastapi import Request

from backend.config.planner import PlannerSettings
from backend.errors.api import ApiException
from backend.models.user import User
from backend.schemas.api import ApiError


def get_settings() -> PlannerSettings:
    """
    读取运行配置，缺失时转为统一配置错误。

    :return: 模型与地图配置。
    :raises ApiException: 必需环境变量缺失或配置值非法。
    """
    try:
        return PlannerSettings.from_env()
    except ValueError as exc:
        raise ApiException.configuration(str(exc)) from exc


def get_generation_limit(request: Request) -> asyncio.Semaphore:
    """
    返回应用生命周期内创建的并发生成限制。

    :param request: 当前 HTTP 请求，用于读取应用状态。
    :return: 应用级信号量。
    """
    return request.app.state.generation_limit


def get_current_user(request: Request) -> User:
    """
    读取中间件验证的用户，供需登录接口复用。

    :param request: 当前 HTTP 请求。
    :return: 已验证的用户。
    :raises ApiException: 未登录或登录态失效时抛出。
    """
    user: User | None = request.state.current_user
    if user is None:
        raise ApiException(401, ApiError(code="unauthorized", message="请先登录"))
    return user
