from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.common.models import Base, CreateAtMixin, UpdateAtMixin
from app.modules.product.models import Product
from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Policy(Base, CreateAtMixin, UpdateAtMixin):
    """教学保单。"""

    __tablename__ = "policies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"))
    policy_number: Mapped[str] = mapped_column(String(60), unique=True)
    application_no: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), server_default="active")
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    holder_name: Mapped[str | None] = mapped_column(String(80))
    insured_name: Mapped[str | None] = mapped_column(String(80))
    insured_id_no_masked: Mapped[str | None] = mapped_column(String(40))
    insured_phone: Mapped[str | None] = mapped_column(String(40))
    coverage_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    premium_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    payment_frequency: Mapped[str | None] = mapped_column(String(30))
    beneficiary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    policy_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    coverage_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    product: Mapped[Product] = relationship()
