from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.product.models import Product, ProductPrice


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

    async def find_limited_by_category(
        self, category: str, premium_min: Decimal | None, limit: int
    ) -> list[Product]:
        """
        根据分类和保费范围查询产品，并限制数量

        :param category: 分类名称，可以为 None
        :param premium_min: 最小保费
        :param limit: 查询数量
        :return: 产品列表
        """
        # 1.组装查询条件
        condition = [Product.status == "active", Product.category == category]
        if premium_min:
            condition.append(Product.min_premium < premium_min)

        # 2.执行查询
        products = await self.session.scalars(
            select(Product)
            .where(*condition)
            .order_by(Product.min_premium.asc().nullslast(), Product.id.asc())
            .limit(limit)
        )

        return list(products.all())

    async def find_by_id(self, product_id: int) -> Product | None:
        """
        根据 ID 查询在售产品
        """
        return await self.session.scalar(
            select(Product).where(Product.id == product_id, Product.status == "active")
        )

    async def find_pricing_schema_by_id(self, product_id: int) -> ProductPrice | None:
        """
        根据 ID 查询价格试算模板

        同一产品可能保留多个历史版本，取当前生效的默认场景模板。
        """
        return await self.session.scalar(
            select(ProductPrice)
            .where(
                ProductPrice.product_id == product_id,
                ProductPrice.scenario == "premium_by_coverage",
                ProductPrice.status == "active",
            )
            .order_by(
                ProductPrice.activated_at.desc().nullslast(),
                ProductPrice.created_at.desc(),
            )
            .limit(1)
        )
