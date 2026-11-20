from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from app.common.dates import BusinessDateTime
from pydantic import BaseModel, ConfigDict, field_validator

type PolicyStatus = Literal["active", "expired", "cancelled", "pending"]
type PolicyStatusFilter = PolicyStatus | Literal["all"]


class PolicyProductData(BaseModel):
    """保单包含的保险产品摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str


class PolicyItemData(BaseModel):
    """保单列表和详情共用的保单数据。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int
    product_id: int
    policy_number: str
    application_no: str | None
    status: PolicyStatus
    effective_at: BusinessDateTime
    expires_at: BusinessDateTime | None
    holder_name: str | None
    insured_name: str | None
    insured_id_no_masked: str | None
    insured_phone: str | None
    coverage_amount: Decimal | None
    premium_amount: Decimal | None
    payment_frequency: str | None
    beneficiary: dict[str, Any] | None
    policy_snapshot: dict[str, Any] | None
    coverage_snapshot: dict[str, Any] | None
    product: PolicyProductData

    @field_validator("status", mode="before")
    @classmethod
    def to_public_status(cls, status: str) -> str:
        """将数据库的终止状态映射为接口中的取消状态。"""
        return "cancelled" if status == "terminated" else status


class PolicyListData(BaseModel):
    """当前用户的保单列表响应。"""

    items: list[PolicyItemData]
