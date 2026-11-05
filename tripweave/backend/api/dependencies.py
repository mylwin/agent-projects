"""FastAPI 共享依赖：读取配置与并发生成限制。"""

import asyncio

from fastapi import Request

from backend.config.planner import PlannerSettings
from backend.errors.api import ApiException


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
