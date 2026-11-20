from decimal import Decimal
from typing import Any
from uuid import UUID

from app.common.models import Base, CreateAtMixin, UpdateAtMixin
from sqlalchemy import BigInteger, ForeignKey, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column


class Order(Base, CreateAtMixin, UpdateAtMixin):
    """以报价为依据创建的教学投保订单。"""

    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    thread_id: Mapped[UUID | None]
    order_number: Mapped[str] = mapped_column(String(40), unique=True)
    confirmation_id: Mapped[str | None] = mapped_column(String(60), unique=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    idempotency_fingerprint: Mapped[str | None] = mapped_column(String(64))
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    quote_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid))
    total_premium: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    recommendation_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), server_default="pending_payment")
