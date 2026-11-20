from datetime import datetime, timedelta
from uuid import UUID

from app.common.dates import BUSINESS_TIME_ZONE
from app.modules.insurance_plan.exceptions import (
    InsurancePlanNotFoundError,
    PlanItemNotFoundError,
)
from app.modules.insurance_plan.repository import InsurancePlanRepository
from app.modules.insurance_plan.schemas import InsurancePlanCreate, InsurancePlanData
from app.modules.policy.models import Policy
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
    ) -> InsurancePlanData:
        """创建保险方案"""
        try:
            plan = await self.repository.create(
                user_id=user_id,
                data=data,
            )
            saved_plan = InsurancePlanData.model_validate(plan)
            await self.session.commit()
            return saved_plan
        except Exception:
            await self.session.rollback()
            raise

    async def find_by_user_id(self, user_id: int) -> list[InsurancePlanData]:
        """查询用户全部保险方案"""
        plans = await self.repository.find_by_user_id(user_id)
        return [InsurancePlanData.model_validate(plan) for plan in plans]

    async def find_current_by_user_id(self, user_id: int) -> InsurancePlanData:
        """查询当前用户最近使用且尚未全部投保的保险方案"""
        plan = await self.repository.find_current_by_user_id(user_id)
        if plan is None:
            raise InsurancePlanNotFoundError
        return InsurancePlanData.model_validate(plan)

    async def find_by_id_and_user_id(
        self, plan_id: UUID, user_id: int
    ) -> InsurancePlanData:
        """根据方案ID查询当前用户的保险方案详情"""
        plan = await self.repository.find_by_id_and_user_id(plan_id, user_id)
        if plan is None:
            raise InsurancePlanNotFoundError
        return InsurancePlanData.model_validate(plan)

    async def mark_item_insured(
        self, user_id: int, plan_id: UUID, item_id: UUID, holder_name: str
    ) -> InsurancePlanData:
        """标记方案项并在同一事务中生成教学保单。"""
        async with self.session.begin():
            # 锁定整份方案，同一方案下的标记请求串行更新状态。
            plan = await self.repository.find_by_id_and_user_id(
                plan_id, user_id, for_update=True
            )
            if plan is None:
                raise PlanItemNotFoundError
            item = next((item for item in plan.items if item.id == item_id), None)
            if item is None:
                raise PlanItemNotFoundError
            if item.status == "insured":
                return InsurancePlanData.model_validate(plan)

            now = datetime.now(BUSINESS_TIME_ZONE)
            insured_name = plan.insured_profile.get("name")
            if not isinstance(insured_name, str) or not insured_name.strip():
                insured_name = holder_name

            self.session.add(
                Policy(
                    user_id=plan.user_id,
                    product_id=item.product_id,
                    policy_number=f"POL-DEMO-{item.id.hex}",
                    application_no=f"APP-DEMO-{item.id.hex}",
                    effective_at=now,
                    expires_at=now + timedelta(days=365),
                    issued_at=now,
                    holder_name=holder_name[:80],
                    insured_name=insured_name.strip()[:80],
                    premium_amount=item.annual_premium_budget,
                    payment_frequency="annual",
                    policy_snapshot={
                        "plan_id": str(plan.id),
                        "plan_item_id": str(item.id),
                        "plan_name": plan.plan_name,
                        "product_name": item.product.name,
                        "category": item.product.category,
                        "recommendation_reason": item.recommendation_reason,
                    },
                    coverage_snapshot={"category": item.product.category},
                )
            )
            item.status = "insured"
            plan.status = (
                "insured"
                if all(plan_item.status == "insured" for plan_item in plan.items)
                else "applying"
            )
            plan.version += 1
            await self.session.flush()
            await self.session.refresh(plan, attribute_names=["updated_at"])
            return InsurancePlanData.model_validate(plan)
