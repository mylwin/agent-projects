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
