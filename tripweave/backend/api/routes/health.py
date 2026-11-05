"""健康检查路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_settings
from backend.config.planner import PlannerSettings
from backend.schemas.api import ApiFailure, ApiSuccess, HealthData

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=ApiSuccess[HealthData],
    responses={503: {"model": ApiFailure, "description": "运行配置缺失"}},
)
async def health(
    settings: Annotated[PlannerSettings, Depends(get_settings)],
) -> ApiSuccess[HealthData]:
    """
    返回不含密钥的服务状态。

    :param settings: 模型与地图配置。
    :return: 统一成功响应。
    """
    return ApiSuccess(
        data=HealthData(
            map_provider=settings.map_provider,
            model=settings.model_name,
        )
    )
