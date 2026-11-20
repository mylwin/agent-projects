from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.common.models import Base, CreateAtMixin, UpdateAtMixin
from app.modules.product.models import Product
from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class InsurancePlan(Base, CreateAtMixin, UpdateAtMixin):
    """用户保险方案"""

    __tablename__ = "insurance_plans"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
    )
    plan_name: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str | None] = mapped_column(Text)
    budget_note: Mapped[str | None] = mapped_column(Text)
    insured_profile: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    annual_premium_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        String(30),
        default="uninsured",
        server_default="uninsured",
    )
    items: Mapped[list["InsurancePlanItem"]] = relationship(
        order_by=lambda: (
            InsurancePlanItem.priority,
            InsurancePlanItem.created_at,
            InsurancePlanItem.id,
        ),
        lazy="raise",
        viewonly=True,
    )


class InsurancePlanItem(Base, CreateAtMixin, UpdateAtMixin):
    """保险方案项"""

    __tablename__ = "insurance_plan_items"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("insurance_plans.id", ondelete="CASCADE"),
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id"),
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
    )
    recommendation_reason: Mapped[str | None] = mapped_column(Text)
    annual_premium_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(
        String(30),
        default="uninsured",
        server_default="uninsured",
    )
    product: Mapped[Product] = relationship(lazy="raise")
