from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.common.models import Base, UpdateAtMixin
from app.modules.policy.models import Policy
from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Claim(Base, UpdateAtMixin):
    """数据库中的理赔记录。"""

    __tablename__ = "claims"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("policies.id"))
    claim_number: Mapped[str | None] = mapped_column(String(60))
    claim_type: Mapped[str] = mapped_column(String(50))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy: Mapped[Policy | None] = relationship()
