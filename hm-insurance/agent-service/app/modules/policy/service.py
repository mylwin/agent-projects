from uuid import UUID

from app.modules.policy.exceptions import PolicyNotFoundError
from app.modules.policy.repository import PolicyRepository
from app.modules.policy.schemas import (
    PolicyItemData,
    PolicyListData,
    PolicyStatusFilter,
)
from sqlalchemy.ext.asyncio import AsyncSession


class PolicyService:
    """提供保单列表和详情查询。"""

    def __init__(self, session: AsyncSession):
        """创建当前请求使用的保单仓库。"""
        self.repository = PolicyRepository(session)

    async def list_policies(
        self, user_id: int, status: PolicyStatusFilter
    ) -> PolicyListData:
        """返回当前用户符合状态筛选的保单。"""
        policies = await self.repository.list_by_user(user_id, status)
        return PolicyListData(
            items=[PolicyItemData.model_validate(policy) for policy in policies]
        )

    async def get_policy(self, policy_id: UUID, user_id: int) -> PolicyItemData:
        """返回当前用户指定保单的详情。"""
        policy = await self.repository.find_by_id_and_user(policy_id, user_id)
        if policy is None:
            raise PolicyNotFoundError
        return PolicyItemData.model_validate(policy)
