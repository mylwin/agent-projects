from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InsuredAnswers(BaseModel):
    """被保人维度试算项"""

    age: int | None = Field(default=None, ge=0, description="被保人年龄")
    gender: Literal["male", "female"] | None = Field(
        default=None,
        description="被保人性别",
    )
    social_security: Literal["yes", "no"] | None = Field(
        default=None,
        description="是否有社保",
    )
    occupation_class: str | None = Field(default=None, description="职业类别")


class CoverageAnswers(BaseModel):
    """保障维度试算项"""

    coverage_amount: int | None = Field(default=None, gt=0, description="保额")
    payment_period: str | None = Field(default=None, description="缴费年限")
    coverage_period: str | None = Field(default=None, description="保障期限")
    deductible: int | None = Field(default=None, ge=0, description="免赔额")


class PremiumCalculateAnswers(BaseModel):
    """保费试算项，按计划、被保人、保障三层组织"""

    plan_code: str = Field(default="basic", min_length=1, description="计划编码")
    insured: InsuredAnswers = Field(
        default_factory=InsuredAnswers,
        description="被保人信息",
    )
    coverage: CoverageAnswers = Field(
        default_factory=CoverageAnswers,
        description="保障信息",
    )


class PremiumCalculateRequest(BaseModel):
    """保费试算请求参数"""

    product_id: int = Field(description="产品ID")
    scenario: str = Field(
        default="premium_by_coverage",
        description="试算场景",
    )
    answers: PremiumCalculateAnswers = Field(
        default_factory=PremiumCalculateAnswers,
        description="试算项",
    )


class BreakdownItem(BaseModel):
    """保费明细项"""

    item: str = Field(description="明细项编码")
    name: str = Field(description="明细项名称")
    premium: str = Field(description="明细保费，两位小数字符串")
    source: dict[str, Any] = Field(description="来源说明，如适配器编码与计价模式")


class PremiumQuoteResponse(BaseModel):
    """保费试算结果"""

    quote_id: str = Field(description="报价ID，可用于创建订单")
    product_id: int = Field(description="产品ID")
    plan_code: str = Field(description="计划编码")
    pricing_mode: str = Field(description="计价模式，当前为 mock_adapter")
    # 保费统一用字符串输出，避免 Decimal 被编码成 float 丢精度
    annual_premium: str = Field(description="年缴保费，两位小数字符串")
    payment_frequency: str = Field(description="缴费频率")
    breakdown: list[BreakdownItem] = Field(description="保费明细")
    warnings: list[str] = Field(description="风险提示")
    expires_at: datetime = Field(description="报价过期时间")
