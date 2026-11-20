from typing import Annotated
from uuid import UUID

from app.infra.database import get_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.policy.schemas import (
    PolicyItemData,
    PolicyListData,
    PolicyStatusFilter,
)
from app.modules.policy.service import PolicyService
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/policies", tags=["保单接口"])


def get_policy_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyService:
    """使用请求级数据库会话创建保单服务。"""
    return PolicyService(session)


@router.get("", response_model=PolicyListData)
async def list_policies(
    user: CurrentUser,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    status: PolicyStatusFilter = "active",
) -> PolicyListData:
    """查询当前用户的保单列表，默认返回生效中的保单。"""
    return await service.list_policies(user.id, status)


@router.get("/{policy_id}", response_model=PolicyItemData)
async def get_policy(
    policy_id: UUID,
    user: CurrentUser,
    service: Annotated[PolicyService, Depends(get_policy_service)],
) -> PolicyItemData:
    """查询当前用户指定 UUID 的保单详情。"""
    return await service.get_policy(policy_id, user.id)
