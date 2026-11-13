from decimal import Decimal

from app.modules.product.models import Product
from app.modules.product.repository import ProductRepository
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
