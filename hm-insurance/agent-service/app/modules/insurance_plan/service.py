from uuid import UUID

from app.modules.insurance_plan.repository import InsurancePlanRepository
from app.modules.insurance_plan.schemas import InsurancePlanCreate, InsurancePlanData
from sqlalchemy.ext.asyncio import AsyncSession


class InsurancePlanService:
    """保险方案业务类"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = InsurancePlanRepository(session)

    async def create_plan(
        self,
        user_id: int,
        data: InsurancePlanCreate,
    ) -> UUID:
        """创建保险方案"""
        try:
            plan = await self.repository.create(
                user_id=user_id,
                data=data,
            )
            await self.session.commit()
            return plan.id
        except Exception:
            await self.session.rollback()
            raise

    async def find_by_user_id(self, user_id: int) -> list[InsurancePlanData] | None:
        """查询用户全部保险方案"""
        plans = await self.repository.find_by_user_id(user_id)
        return (
            [InsurancePlanData.model_validate(plan) for plan in plans]
            if plans
            else None
        )
