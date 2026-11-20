from decimal import Decimal

from app.modules.insurance_plan.models import InsurancePlan, InsurancePlanItem
from app.modules.insurance_plan.schemas import (
    InsurancePlanCreate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class InsurancePlanRepository:
    """保险方案数据库操作"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _query_for_user(user_id: int):
        """构建用户保险方案查询，并预加载关联的保险项目及其产品信息。"""
        return (
            select(InsurancePlan)
            .where(InsurancePlan.user_id == user_id)
            .options(
                selectinload(InsurancePlan.items).joinedload(InsurancePlanItem.product)
            )
        )

    async def create(self, user_id: int, data: InsurancePlanCreate) -> InsurancePlan:
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
            budget_note=data.budget_note,
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
        await self.session.flush()

        result = await self.session.execute(
            self._query_for_user(user_id).where(InsurancePlan.id == insurance_plan.id)
        )
        return result.scalar_one()

    async def find_by_user_id(self, user_id: int) -> list[InsurancePlan]:
        """根据用户ID查询全部保险方案"""
        plans = await self.session.scalars(
            self._query_for_user(user_id).order_by(
                InsurancePlan.created_at.desc(), InsurancePlan.id.desc()
            )
        )
        return list(plans)

    async def find_current_by_user_id(self, user_id: int) -> InsurancePlan | None:
        """查询当前用户最近更新且尚未全部投保的方案"""
        return await self.session.scalar(
            self._query_for_user(user_id)
            .where(InsurancePlan.status.in_(("uninsured", "applying")))
            .order_by(
                InsurancePlan.updated_at.desc(),
                InsurancePlan.created_at.desc(),
                InsurancePlan.id.desc(),
            )
            .limit(1)
        )
