from typing import Annotated
from uuid import UUID

from app.infra.database import get_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.order.schemas import OrderCreate, OrderData, OrderListData
from app.modules.order.service import OrderService
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/orders", tags=["订单接口"])


def get_order_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderService:
    """用请求级数据库会话创建订单服务。"""
    return OrderService(session)


@router.get("", response_model=OrderListData)
async def list_orders(
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderListData:
    """查询当前用户的投保订单列表。"""
    return await service.list_orders(user.id)


@router.post("", response_model=OrderData)
async def create_order(
    data: OrderCreate,
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderData:
    """按报价创建订单，重复提交时返回原订单。"""
    return await service.create_order(user.id, data)


@router.get("/{order_id}", response_model=OrderData)
async def get_order(
    order_id: UUID,
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderData:
    """按订单 UUID 查询当前用户的订单详情。"""
    return await service.get_order(order_id, user.id)


@router.post("/{order_id}/cancel", response_model=OrderData)
async def cancel_order(
    order_id: UUID,
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderData:
    """取消当前用户的待支付订单。"""
    return await service.cancel_order(order_id, user.id)
