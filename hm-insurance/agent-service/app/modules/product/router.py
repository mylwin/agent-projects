from decimal import Decimal
from typing import Annotated

from app.infra.database import get_session
from app.modules.product.schemas import ProductResponse
from app.modules.product.service import ProductService
from fastapi import APIRouter, Depends
from fastapi.params import Query
from sqlalchemy.ext.asyncio import AsyncSession

# 创建路由对象
router = APIRouter(prefix="/api/v1/products", tags=["products"])


async def get_product_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProductService:
    """
    获取产品服务对象

    :param session: 数据库会话
    :return: 产品服务对象
    """
    return ProductService(session)


@router.get("", response_model=list[ProductResponse])
async def list_products(
    service: Annotated[ProductService, Depends(get_product_service)],
    category: str | None = None,
) -> list[ProductResponse]:
    """
    查询产品列表

    :param category: 产品类别，可以为空
    :param session: 数据库会话
    :return: 产品列表
    """
    # 调用服务方法
    products = await service.list_products(category)
    return [
        ProductResponse.model_validate(product, from_attributes=True)
        for product in products
    ]


@router.get("/candidates", response_model=list[ProductResponse])
async def list_candidates(
    service: Annotated[ProductService, Depends(get_product_service)],
    categories: Annotated[list[str], Query(min_length=1)],
    premium_min: Decimal | None = None,
    limit: int = 5,
) -> list[ProductResponse]:
    """
    查询候选产品列表
    :param service: 产品服务对象
    :param categories: 产品类别列表
    :param premium_min: 最小保费
    :param limit: 返回数量限制
    """
    candidates_products = await service.list_limited_products(
        categories, premium_min, limit
    )
    return [
        ProductResponse.model_validate(product, from_attributes=True)
        for product in candidates_products
    ]
