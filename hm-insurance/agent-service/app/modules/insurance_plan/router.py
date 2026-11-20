from typing import Annotated
from uuid import UUID

from app.infra.database import get_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.insurance_plan.schemas import (
    InsurancePlanCreate,
    InsurancePlanData,
    InsurancePlanList,
)
from app.modules.insurance_plan.service import InsurancePlanService
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/insurance-plans", tags=["保险计划方案接口"])


def get_insurance_plan_service(session: Annotated[AsyncSession, Depends(get_session)]):
    """获取 insurance plan 服务对象"""
    return InsurancePlanService(session)


@router.get("", response_model=InsurancePlanList)
async def list_insurance_plans(
    user: CurrentUser,
    service: Annotated[InsurancePlanService, Depends(get_insurance_plan_service)],
) -> InsurancePlanList:
    """列出保险计划方案"""
    return InsurancePlanList(items=await service.find_by_user_id(user.id))


@router.get("/current", response_model=InsurancePlanData)
async def get_current_insurance_plan(
    user: CurrentUser,
    service: Annotated[InsurancePlanService, Depends(get_insurance_plan_service)],
) -> InsurancePlanData:
    """查询当前保险方案"""
    return await service.find_current_by_user_id(user.id)


@router.put("/current", response_model=InsurancePlanData)
async def save_current_insurance_plan(
    user: CurrentUser,
    data: InsurancePlanCreate,
    service: Annotated[InsurancePlanService, Depends(get_insurance_plan_service)],
) -> InsurancePlanData:
    """保存当前保险方案"""
    return await service.create_plan(user.id, data)


@router.get("/{plan_id}", response_model=InsurancePlanData)
async def get_insurance_plan_detail(
    plan_id: UUID,
    user: CurrentUser,
    service: Annotated[InsurancePlanService, Depends(get_insurance_plan_service)],
) -> InsurancePlanData:
    """查询保险方案"""
    return await service.find_by_id_and_user_id(plan_id, user.id)


@router.patch("/{plan_id}/items/{item_id}/insured", response_model=InsurancePlanData)
async def mark_plan_item_insured(
    plan_id: UUID,
    item_id: UUID,
    user: CurrentUser,
    service: Annotated[InsurancePlanService, Depends(get_insurance_plan_service)],
) -> InsurancePlanData:
    """标记方案项已投保并生成教学保单。"""
    return await service.mark_item_insured(
        user.id, plan_id, item_id, holder_name=user.display_name
    )
