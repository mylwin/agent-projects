from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.modules.premium.adapters.base import PricingRequest
from app.modules.premium.adapters.registry import get_adapter
from app.modules.premium.exceptions import (
    PriceBindingNotFoundError,
    PriceParamsInvalidError,
    ProductIdIsNullError,
)
from app.modules.premium.models import PremiumQuote
from app.modules.premium.repository import PremiumRepository
from app.modules.premium.schemas import (
    BreakdownItem,
    PremiumCalculateRequest,
    PremiumQuoteResponse,
)
from app.modules.premium.validator import validate_answers
from sqlalchemy.ext.asyncio import AsyncSession


class PremiumService:
    """保费试算业务类"""

    # 试算结果过期时间,单位分钟
    QUOTE_TTL = timedelta(minutes=30)
    WARNINGS = (
        "本结果由教学 mock adapter 生成，不构成真实保险报价",
        "真实产品保费以保险公司试算接口和核保结果为准",
    )

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = PremiumRepository(session)

    async def calculate(
        self, request: PremiumCalculateRequest, user_id: int | None = None
    ) -> PremiumQuoteResponse:
        """按产品绑定生成报价快照，返回给前端并写入 premium_quotes。"""
        if request.product_id is None:
            raise ProductIdIsNullError
        if request.product_id <= 0:
            raise PriceParamsInvalidError("product_id must be a positive integer")

        # 读 + 写放在同一事务，避免 SELECT 自动开启事务后与 begin() 冲突
        async with self.session.begin():
            # 从数据库中获取当前生效的绑定
            context = await self.repository.find_active_binding(
                request.product_id, request.scenario
            )
            if context is None:
                raise PriceBindingNotFoundError

            # 从请求中获取嵌套的answers数据
            nested_answers = request.answers.model_dump(exclude_none=True)
            # 校验试算模板数据是否合规
            validate_answers(nested_answers, context.schema.schema_json)

            # 把试算项映射成适配器的字段
            answers = _flatten_answers(nested_answers)
            payload = _map_answers(answers, context.binding.field_mapping)
            adapter = get_adapter(context.adapter.adapter_type)
            result = await adapter.quote(
                PricingRequest(
                    adapter_code=context.adapter.insurer_code,
                    external_product_code=context.binding.external_product_code,
                    api_code=context.binding.api_code,
                    payload=payload,
                ),
                context.binding.mock_config,
            )

            quote_id: UUID = uuid4()
            expires_at = datetime.now(ZoneInfo("Asia/Shanghai")) + self.QUOTE_TTL
            response = PremiumQuoteResponse(
                quote_id=str(quote_id),
                product_id=request.product_id,
                plan_code=answers["plan_code"],
                pricing_mode=adapter.pricing_mode,
                annual_premium=f"{result.annual_premium:.2f}",
                payment_frequency=result.payment_frequency,
                breakdown=[BreakdownItem(**item) for item in result.breakdown],
                warnings=list(self.WARNINGS),
                expires_at=expires_at,
            )

            await self.repository.add_quote(
                PremiumQuote(
                    id=quote_id,
                    user_id=user_id,
                    product_id=request.product_id,
                    request_params=request.model_dump(mode="json"),
                    answers=answers,
                    result=response.model_dump(mode="json"),
                    total_premium=result.annual_premium,
                    pricing_mode=adapter.pricing_mode,
                    expires_at=expires_at,
                    pricing_schema_id=context.schema.id,
                    schema_version=context.schema.schema_version,
                    adapter_id=context.adapter.id,
                    external_request={
                        "external_product_code": context.binding.external_product_code,
                        "api_code": context.binding.api_code,
                        "payload": payload,
                    },
                    external_response=result.raw,
                )
            )

        return response


def _flatten_answers(answers: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """把分层试算项展开成模板用的点号 key（如 insured.age）。"""
    flat: dict[str, Any] = {}
    for key, value in answers.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten_answers(value, dotted))
        else:
            flat[dotted] = value
    return flat


def _map_answers(
    answers: dict[str, Any], field_mapping: dict[str, str]
) -> dict[str, Any]:
    """按绑定的字段映射，把内部点号 key 转成外部字段名。"""
    return {
        external_key: answers[internal_key]
        for internal_key, external_key in field_mapping.items()
        if internal_key in answers
    }
