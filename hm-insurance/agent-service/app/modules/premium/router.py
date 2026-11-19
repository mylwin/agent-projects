from typing import Annotated

from app.infra.database import get_session
from app.modules.premium.schemas import PremiumCalculateRequest, PremiumQuoteResponse
from app.modules.premium.service import PremiumService
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# 创建路由对象
router = APIRouter(prefix="/api/v1/premium", tags=["保费试算接口"])


async def get_premium_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PremiumService:
    """获取保费试算服务对象"""
    return PremiumService(session)


@router.post("/calculate", response_model=PremiumQuoteResponse)
async def calculate_premium(
    body: PremiumCalculateRequest,
    service: Annotated[PremiumService, Depends(get_premium_service)],
) -> PremiumQuoteResponse:
    """生成教学用模拟保费试算结果"""
    return await service.calculate(body)
