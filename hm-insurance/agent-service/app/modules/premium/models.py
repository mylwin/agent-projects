from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, CreateAtMixin, UpdateAtMixin


class InsurerApiAdapter(Base, CreateAtMixin, UpdateAtMixin):
    """保险公司保费试算接口适配器配置"""

    __tablename__ = "insurer_api_adapters"
    __table_args__ = (
        CheckConstraint(
            "adapter_type IN ('mock', 'http')",
            name="chk_insurer_api_adapters_type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="chk_insurer_api_adapters_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    insurer_code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        unique=True,
    )
    adapter_type: Mapped[str] = mapped_column(String(40), nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    auth_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="none",
        server_default="none",
    )
    # 数据库中为 JSONB，直接映射为 dict，避免在业务层反复 json.loads
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )


class PricingBinding(Base, CreateAtMixin, UpdateAtMixin):
    """产品、试算模板与保险公司适配器的绑定表"""

    __tablename__ = "product_pricing_bindings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="chk_product_pricing_bindings_status",
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
    pricing_schema_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("product_pricing_schemas.id"),
        nullable=False,
    )
    adapter_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("insurer_api_adapters.id"),
        nullable=False,
    )
    external_product_code: Mapped[str] = mapped_column(String(120), nullable=False)
    api_code: Mapped[str] = mapped_column(String(120), nullable=False)
    # 内部字段到外部字段的映射，形如 {"insured.age": "age"}
    field_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    response_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    # 教学 mock 计价配置：基准保费、年龄/性别/社保/职业/免赔额系数
    mock_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )


class PremiumQuote(Base, CreateAtMixin):
    """单个产品的保费试算结果快照"""

    __tablename__ = "premium_quotes"
    __table_args__ = (
        CheckConstraint(
            "pricing_mode IN ('table', 'demo_formula', 'mock_adapter', "
            "'insurer_api', 'local_fallback')",
            name="chk_premium_quotes_pricing_mode",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    # 未登录也可以试算，此时发起人为空
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id"),
        nullable=False,
    )
    request_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    total_premium: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    pricing_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    pricing_schema_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("product_pricing_schemas.id"),
    )
    schema_version: Mapped[str | None] = mapped_column(String(80))
    adapter_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("insurer_api_adapters.id"),
    )
    # 用户填写的动态表单答案，key 为扁平点号字符串
    answers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # 发给适配器的请求快照与适配器原始响应快照，便于排查 mock 系数
    external_request: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    external_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
