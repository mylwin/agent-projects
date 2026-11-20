from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from app.common.dates import BusinessDateTime
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class OrderItemCreate(BaseModel):
    """创建订单时提供的报价和产品信息。"""

    model_config = ConfigDict(extra="allow")

    quote_id: UUID
    product_id: int | None = None


class OrderCreate(BaseModel):
    """创建订单的请求。"""

    quote_ids: list[UUID] = Field(
        default_factory=list, validation_alias=AliasChoices("quote_ids", "quoteIds")
    )
    thread_id: UUID | None = Field(
        default=None, validation_alias=AliasChoices("thread_id", "threadId")
    )
    confirmation_id: str | None = Field(default=None, min_length=1, max_length=60)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)
    items: list[OrderItemCreate] = Field(default_factory=list)
    recommendation_snapshot: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_quote_ids(self) -> Self:
        """从订单项补全报价 ID，并保证每份报价只计算一次。"""
        item_quote_ids = [item.quote_id for item in self.items]
        if not self.quote_ids:
            self.quote_ids = item_quote_ids
        if not self.quote_ids or len(self.quote_ids) != len(set(self.quote_ids)):
            raise ValueError("订单必须引用至少一份报价，且报价 ID 不能重复")
        if item_quote_ids and (
            len(item_quote_ids) != len(self.quote_ids)
            or set(item_quote_ids) != set(self.quote_ids)
        ):
            raise ValueError("订单项引用的报价须与 quote_ids 一致")
        return self


class OrderData(BaseModel):
    """订单列表、详情、创建和取消共用的响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int
    thread_id: UUID | None
    order_number: str
    confirmation_id: str | None
    idempotency_key: str | None
    items: list[dict[str, Any]]
    quote_ids: list[UUID]
    total_premium: Decimal
    recommendation_snapshot: dict[str, Any] | None
    status: str
    created_at: BusinessDateTime
    updated_at: BusinessDateTime


class OrderListData(BaseModel):
    """当前用户的订单列表。"""

    items: list[OrderData]
