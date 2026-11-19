from decimal import Decimal

from app.modules.insurance_plan.models import InsurancePlan, InsurancePlanItem
from app.modules.insurance_plan.schemas import (
    InsurancePlanCreate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class InsurancePlanRepository:
    """保险方案数据库操作"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, data: InsurancePlanCreate):
        """创建保险方案"""
        # 1.计算保险年缴费金额
        item_budgets = [
            item.annual_premium_budget
            for item in data.items
            if item.annual_premium_budget is not None
        ]

        annual_premium_budget = (
            sum(item_budgets, Decimal("0.0")) if item_budgets else None
        )

        # 2.保存保险方案
        insurance_plan = InsurancePlan(
            user_id=user_id,
            plan_name=data.plan_name,
            summary=data.summary,
            insured_profile=data.insured_profile,
            annual_premium_budget=annual_premium_budget,
        )
        self.session.add(insurance_plan)
        await self.session.flush()

        # 3.保存保险方案项
        plan_items = [
            InsurancePlanItem(
                plan_id=insurance_plan.id,
                product_id=item.product_id,
                priority=item.priority,
                recommendation_reason=item.recommendation_reason,
                annual_premium_budget=item.annual_premium_budget,
            )
            for item in data.items
        ]
        self.session.add_all(plan_items)

        return insurance_plan

    async def find_by_user_id(self, user_id: int):
        """根据用户ID查询全部保险方案"""
        return await self.session.scalars(
            select(InsurancePlan)
            .where(InsurancePlan.user_id == user_id)
            .order_by(InsurancePlan.created_at.desc())
        )
