from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.common.dates import BusinessDateTime


class InsurancePlanItemCreate(BaseModel):
    """保存保险方案时每个保险项数据"""

    product_id: int
    product_name: str = Field(description="产品的名称")
    category: str = Field(description="产品的险种类型")
    priority: int = Field(default=1, ge=1)
    recommendation_reason: str | None = None
    annual_premium_budget: Decimal | None = Field(
        default=None, ge=0, description="该产品的最低保费"
    )


class InsurancePlanCreate(BaseModel):
    """保存保险方案时的数据"""

    plan_name: str = Field(min_length=1, max_length=120)
    summary: str | None = None
    budget_note: str | None = None
    insured_profile: dict[str, Any] = Field(default_factory=dict)
    items: list[InsurancePlanItemCreate] = Field(min_length=1)


class InsurancePlanProductData(BaseModel):
    """保险方案产品数据"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str


class InsurancePlanItemData(BaseModel):
    """查看保险方案时保险项的数据"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    product_id: int
    priority: int
    recommendation_reason: str | None
    annual_premium_budget: Decimal | None
    status: str
    product: InsurancePlanProductData

    @computed_field
    @property
    def category(self) -> str:
        return self.product.category


class InsurancePlanData(BaseModel):
    """保险方案数据"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int
    plan_name: str
    summary: str | None = None
    budget_note: str | None = None
    insured_profile: dict[str, Any] = Field(default_factory=dict)
    status: str
    annual_premium_budget: Decimal | None = None
    version: int
    created_at: BusinessDateTime
    updated_at: BusinessDateTime
    items: list[InsurancePlanItemData]


class InsurancePlanList(BaseModel):
    items: list[InsurancePlanData]
