from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InsurancePlanItemCreate(BaseModel):
    """保险方案项"""

    product_id: int
    product_name: str = Field(description="产品的名称")
    category: str = Field(description="产品的险种类型")
    priority: int = Field(default=1, ge=1)
    recommendation_reason: str | None = None
    annual_premium_budget: Decimal | None = Field(
        default=None, ge=0, description="该产品的最低保费"
    )


class InsurancePlanCreate(BaseModel):
    """保险方案"""

    plan_name: str = Field(min_length=1, max_length=120)
    summary: str | None = None
    insured_profile: dict[str, Any] = Field(default_factory=dict)
    items: list[InsurancePlanItemCreate] = Field(min_length=1)


class InsurancePlanData(BaseModel):
    """保险方案数据"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int
    plan_name: str
    summary: str | None = None
    insured_profile: dict[str, Any] = Field(default_factory=dict)
    status: str
    annual_premium_budget: Decimal | None = None
