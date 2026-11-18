from decimal import Decimal

from app.modules.product.exceptions import (
    PriceTemplateNotFoundError,
    ProductNotFoundError,
)
from app.modules.product.models import Product
from app.modules.product.repository import ProductRepository
from app.modules.product.schemas import (
    PriceResponse,
    PriceSchema,
    ProductResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession


class ProductService:
    """产品业务类"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = ProductRepository(session)

    async def list_products(self, category: str | None) -> list[Product]:
        """
        查询产品列表

        :param category: 产品类别，可以为空
        :return: 产品列表
        """
        return await self.repository.find_by_category(category)

    async def list_limited_products(
        self, categories: list[str], premium_min: Decimal | None, limit: int
    ) -> list[Product]:
        """
        根据筛选条件查询候选产品列表

        :param category: 产品类别，可以为空
        :param premium_min: 最小保费
        :param limit: 查询数量
        :return: 产品列表
        """
        candidate_products: list[Product] = []

        for category in dict.fromkeys(categories):
            products = await self.repository.find_limited_by_category(
                category, premium_min, limit
            )
            candidate_products.extend(products)

        return candidate_products

    async def find_by_id(self, product_id: int) -> ProductResponse:
        """
        根据 ID 查询产品

        :param product_id: 产品 ID
        :return: 产品
        """
        result = await self.repository.find_by_id(product_id)
        if result is None:
            raise ProductNotFoundError
        return ProductResponse.model_validate(result, from_attributes=True)

    async def find_pricing_schema_by_id(self, product_id: int) -> PriceResponse:
        """
        根据 ID 查询产品价格模板
        """
        result = await self.repository.find_pricing_schema_by_id(product_id)
        if result is None:
            raise PriceTemplateNotFoundError

        return PriceResponse(
            product_id=result.product_id,
            scenario=result.scenario,
            schema_version=result.schema_version,
            schema=PriceSchema.model_validate(result.schema_json),
        )
