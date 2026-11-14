from uuid import UUID

from app.modules.insurance_plan.repository import InsurancePlanRepository
from app.modules.insurance_plan.schemas import InsurancePlanCreate
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
