from dataclasses import dataclass

from app.modules.premium.models import InsurerApiAdapter, PremiumQuote, PricingBinding
from app.modules.product.models import ProductPrice
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class PricingContext:
    """试算所需的完整绑定上下文：模板 + 绑定 + 适配器"""

    binding: PricingBinding
    schema: ProductPrice
    adapter: InsurerApiAdapter


class PremiumRepository:
    """保费试算数据库操作类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_active_binding(
        self, product_id: int, scenario: str
    ) -> PricingContext | None:
        """
        一次 JOIN 查出生效的试算绑定、模板与适配器。

        同一产品可能有多个模板版本，取 activated_at 最新且 active 的一条。
        """
        row = (
            await self.session.execute(
                select(PricingBinding, ProductPrice, InsurerApiAdapter)
                .join(
                    ProductPrice,
                    PricingBinding.pricing_schema_id == ProductPrice.id,
                )
                .join(
                    InsurerApiAdapter,
                    PricingBinding.adapter_id == InsurerApiAdapter.id,
                )
                .where(
                    PricingBinding.product_id == product_id,
                    PricingBinding.status == "active",
                    ProductPrice.scenario == scenario,
                    ProductPrice.status == "active",
                    InsurerApiAdapter.status == "active",
                )
                .order_by(
                    ProductPrice.activated_at.desc().nullslast(),
                    ProductPrice.created_at.desc(),
                )
                .limit(1)
            )
        ).first()
        if row is None:
            return None

        binding, schema, adapter = row
        return PricingContext(binding=binding, schema=schema, adapter=adapter)

    async def add_quote(self, quote: PremiumQuote) -> None:
        """新增一条报价快照"""
        self.session.add(quote)
