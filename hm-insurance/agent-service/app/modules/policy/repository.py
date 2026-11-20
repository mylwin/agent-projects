from uuid import UUID

from app.modules.policy.models import Policy
from app.modules.policy.schemas import PolicyStatusFilter
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload


class PolicyRepository:
    """查询保单和关联的保险产品。"""

    def __init__(self, session: AsyncSession):
        """绑定当前请求的数据库会话。"""
        self.session = session

    @staticmethod
    def _query_for_user(user_id: int) -> Select[Policy]:
        """构建仅查询当前用户保单的语句，并加载关联产品。"""
        return (
            select(Policy)
            .where(Policy.user_id == user_id)
            .options(joinedload(Policy.product, innerjoin=True))
        )

    async def list_by_user(
        self, user_id: int, status: PolicyStatusFilter
    ) -> list[Policy]:
        """按状态筛选用户保单，并按生效时间倒序返回。"""
        query = self._query_for_user(user_id)
        if status != "all":
            database_status = "terminated" if status == "cancelled" else status
            query = query.where(Policy.status == database_status)
        policies = await self.session.scalars(
            query.order_by(Policy.effective_at.desc(), Policy.id.desc())
        )
        return list(policies)

    async def find_by_id_and_user(self, policy_id: UUID, user_id: int) -> Policy | None:
        """按保单 ID 查询当前用户的保单。"""
        policies = await self.session.scalars(
            self._query_for_user(user_id).where(Policy.id == policy_id)
        )
        return policies.first()
