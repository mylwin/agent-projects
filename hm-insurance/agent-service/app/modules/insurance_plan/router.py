from typing import Annotated

from app.infra.database import get_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.insurance_plan.schemas import InsurancePlanData
from app.modules.insurance_plan.service import InsurancePlanService
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/insurance-plans", tags=["保险计划方案接口"])


def get_insurance_plan_service(session: Annotated[AsyncSession, Depends(get_session)]):
    """获取 insurance plan 服务对象"""
    return InsurancePlanService(session)


@router.get("", response_model=list[InsurancePlanData])
async def list_insurance_plans(
    user: CurrentUser,
    service: Annotated[InsurancePlanService, Depends(get_insurance_plan_service)],
) -> list[InsurancePlanData] | None:
    """列出保险计划方案"""
    return await service.find_by_user_id(user.id)
