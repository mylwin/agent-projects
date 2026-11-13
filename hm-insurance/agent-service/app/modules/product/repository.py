from app.modules.product.models import Product
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ProductRepository:
    """产品数据库操作类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_category(self, category: str | None) -> list[Product]:
        """
        根据分类查询产品

        :param category: 分类名称，可以为 None
        :return: 产品列表
        """
        # 1.组装查询条件
        # 默认只查询 active 状态的产品
        condition = [Product.status == "active"]

        # 如果有 category 参数，则添加查询条件
        if category:
            condition.append(Product.category == category)

        # 2.执行查询
        products = await self.session.scalars(
            select(Product).where(*condition).order_by(Product.id.asc())
        )

        return list(products.all())
