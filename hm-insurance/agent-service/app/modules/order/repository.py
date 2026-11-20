from typing import Any
from uuid import UUID

from app.modules.order.models import Order
from app.modules.premium.models import PremiumQuote
from sqlalchemy import Select, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class OrderRepository:
    """查询和写入当前用户的订单。"""

    def __init__(self, session: AsyncSession):
        """绑定本次请求的数据库会话。"""
        self.session = session

    @staticmethod
    def _query_for_user(user_id: int) -> Select[Order]:
        """构建按用户归属筛选的订单查询。"""
        return select(Order).where(Order.user_id == user_id)

    async def list_by_user(self, user_id: int) -> list[Order]:
        """按创建时间倒序列出用户的订单。"""
        orders = await self.session.scalars(
            self._query_for_user(user_id).order_by(
                Order.created_at.desc(), Order.id.desc()
            )
        )
        return list(orders)

    async def find_owned(
        self, order_id: UUID, user_id: int, *, for_update: bool = False
    ) -> Order | None:
        """查询当前用户的订单，取消操作可锁定该行。"""
        query = self._query_for_user(user_id).where(Order.id == order_id)
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def find_by_submission_keys(
        self, user_id: int, idempotency_key: str | None, confirmation_id: str | None
    ) -> list[Order]:
        """查找当前用户已使用指定幂等键或确认 ID 创建的订单。"""
        conditions = []
        if idempotency_key is not None:
            conditions.append(Order.idempotency_key == idempotency_key)
        if confirmation_id is not None:
            conditions.append(Order.confirmation_id == confirmation_id)
        if not conditions:
            return []
        orders = await self.session.scalars(
            self._query_for_user(user_id).where(or_(*conditions))
        )
        return list(orders)

    async def find_quotes(
        self, user_id: int, quote_ids: list[UUID]
    ) -> list[PremiumQuote]:
        """查询当前用户的报价和匿名试算报价。"""
        quotes = await self.session.scalars(
            select(PremiumQuote).where(
                PremiumQuote.id.in_(quote_ids),
                or_(PremiumQuote.user_id == user_id, PremiumQuote.user_id.is_(None)),
            )
        )
        return list(quotes)

    async def insert_order(self, values: dict[str, Any]) -> Order | None:
        """利用数据库唯一约束处理并发创建，冲突时返回空。"""
        result = await self.session.scalars(
            insert(Order).values(**values).on_conflict_do_nothing().returning(Order)
        )
        return result.one_or_none()
