from uuid import UUID

from app.modules.claim.models import Claim
from app.modules.claim.schemas import ClaimStatus
from app.modules.policy.models import Policy
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload


class ClaimRepository:
    """查询当前用户的理赔记录和关联保单。"""

    def __init__(self, session: AsyncSession):
        """绑定请求级数据库会话。"""
        self.session = session

    @staticmethod
    def _query_for_user(user_id: int) -> Select[Claim]:
        """限定记录和关联保单的用户归属。"""
        return (
            select(Claim)
            .where(Claim.user_id == user_id)
            .options(joinedload(Claim.policy.and_(Policy.user_id == user_id)))
        )

    async def list_by_user(
        self, user_id: int, policy_id: UUID | None, status: ClaimStatus | None
    ) -> list[Claim]:
        """按保单和状态筛选，并按提交时间倒序返回。"""
        query = self._query_for_user(user_id)
        if policy_id is not None:
            query = query.where(Claim.policy_id == policy_id)
        if status is not None:
            query = query.where(Claim.status == status)
        claims = await self.session.scalars(
            query.order_by(Claim.submitted_at.desc(), Claim.id.desc())
        )
        return list(claims)

    async def find_by_id_and_user(self, claim_id: UUID, user_id: int) -> Claim | None:
        """按 UUID 查询当前用户的理赔记录。"""
        return await self.session.scalar(
            self._query_for_user(user_id).where(Claim.id == claim_id)
        )
