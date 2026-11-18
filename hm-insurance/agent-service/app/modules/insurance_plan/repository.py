from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.insurance_plan.models import InsurancePlan, InsurancePlanItem
from app.modules.insurance_plan.schemas import (
    InsurancePlanCreate,
)


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

        # TODO(citation-flow): 接收服务端验证后的确认快照，与方案及方案项在同一事务保存；
        # 快照中的产品/保费必须与确认版本一致，保存回执返回该版本的产品及来源。
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
