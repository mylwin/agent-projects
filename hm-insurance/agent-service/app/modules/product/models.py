from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, CreateAtMixin, UpdateAtMixin


class Product(Base, CreateAtMixin, UpdateAtMixin):
    """保险产品"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    clause_name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(50))
    insurer: Mapped[str] = mapped_column(String(120))
    image_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    min_premium: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    max_premium: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    target_group: Mapped[str | None] = mapped_column(String(300))
    highlights: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        server_default="active",
    )


class ProductPrice(Base, CreateAtMixin):
    """保险产品价格试算模板表"""

    __tablename__ = "product_pricing_schemas"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "scenario",
            "schema_version",
            name="uk_product_pricing_schema_version",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive')",
            name="chk_product_pricing_schemas_status",
        ),
        Index(
            "idx_product_pricing_schemas_product",
            "product_id",
            "scenario",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id"),
        nullable=False,
    )
    scenario: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="premium_by_coverage",
        server_default="premium_by_coverage",
    )
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    # 数据库中为 JSONB，直接映射为 dict，避免在业务层反复 json.loads
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
