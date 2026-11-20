import json
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from app.common.dates import BUSINESS_TIME_ZONE
from app.modules.chat_thread.exceptions import ChatThreadNotFoundError
from app.modules.chat_thread.repository import ChatThreadRepository
from app.modules.order.exceptions import (
    OrderIdempotencyConflictError,
    OrderItemMismatchError,
    OrderNotCancellableError,
    OrderNotFoundError,
    QuoteExpiredError,
    QuoteNotFoundError,
)
from app.modules.order.models import Order
from app.modules.order.repository import OrderRepository
from app.modules.order.schemas import OrderCreate, OrderData, OrderListData
from sqlalchemy.ext.asyncio import AsyncSession


class OrderService:
    """提供订单查询、幂等创建和取消。"""

    def __init__(self, session: AsyncSession):
        """初始化处理订单和客服会话的仓库。"""
        self.session = session
        self.repository = OrderRepository(session)
        self.threads = ChatThreadRepository(session)

    async def list_orders(self, user_id: int) -> OrderListData:
        """返回当前用户的全部订单。"""
        orders = await self.repository.list_by_user(user_id)
        return OrderListData(
            items=[OrderData.model_validate(order) for order in orders]
        )

    async def get_order(self, order_id: UUID, user_id: int) -> OrderData:
        """返回当前用户指定订单的详情。"""
        order = await self.repository.find_owned(order_id, user_id)
        if order is None:
            raise OrderNotFoundError
        return OrderData.model_validate(order)

    async def _find_replay(
        self, user_id: int, data: OrderCreate, fingerprint: str
    ) -> Order | None:
        """找到同一次提交的原订单，拒绝复用标识提交不同内容。"""
        existing = await self.repository.find_by_submission_keys(
            user_id, data.idempotency_key, data.confirmation_id
        )
        if not existing:
            return None
        if len(existing) != 1 or existing[0].idempotency_fingerprint not in (
            None,
            fingerprint,
        ):
            raise OrderIdempotencyConflictError
        return existing[0]

    async def create_order(self, user_id: int, data: OrderCreate) -> OrderData:
        """用有效报价计算总保费，并在一次事务内创建或返回原订单。"""
        payload = data.model_dump(mode="json", exclude={"idempotency_key"})
        fingerprint = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        async with self.session.begin():
            existing = await self._find_replay(user_id, data, fingerprint)
            if existing is not None:
                return OrderData.model_validate(existing)
            if data.thread_id is not None:
                thread = await self.threads.find_owned(data.thread_id, user_id)
                if thread is None:
                    raise ChatThreadNotFoundError

            quotes = await self.repository.find_quotes(user_id, data.quote_ids)
            if len(quotes) != len(data.quote_ids):
                raise QuoteNotFoundError
            now = datetime.now(BUSINESS_TIME_ZONE)
            if any(quote.expires_at <= now for quote in quotes):
                raise QuoteExpiredError

            quotes_by_id = {quote.id: quote for quote in quotes}
            request_items = {item.quote_id: item for item in data.items}
            items = []
            for quote_id in data.quote_ids:
                product_id = quotes_by_id[quote_id].product_id
                item = request_items.get(quote_id)
                snapshot = item.model_dump(mode="json") if item else {}
                if item and item.product_id not in (None, product_id):
                    raise OrderItemMismatchError
                items.append(
                    {**snapshot, "quote_id": str(quote_id), "product_id": product_id}
                )

            order_id = uuid4()
            order = await self.repository.insert_order(
                {
                    "id": order_id,
                    "user_id": user_id,
                    "thread_id": data.thread_id,
                    "order_number": f"ORD-{now:%Y%m%d%H%M%S}-{order_id.hex[:20]}",
                    "confirmation_id": data.confirmation_id,
                    "idempotency_key": data.idempotency_key,
                    "idempotency_fingerprint": fingerprint,
                    "items": items,
                    "quote_ids": data.quote_ids,
                    "total_premium": sum(
                        (quote.total_premium for quote in quotes), Decimal("0.00")
                    ),
                    "recommendation_snapshot": data.recommendation_snapshot,
                }
            )
            if order is None:
                # 并发请求可能已插入同一订单，用新查询读取胜出的记录。
                order = await self._find_replay(user_id, data, fingerprint)
                if order is None:
                    raise OrderIdempotencyConflictError
            return OrderData.model_validate(order)

    async def cancel_order(self, order_id: UUID, user_id: int) -> OrderData:
        """取消待支付订单，重复取消时返回原结果。"""
        async with self.session.begin():
            order = await self.repository.find_owned(order_id, user_id, for_update=True)
            if order is None:
                raise OrderNotFoundError
            if order.status == "cancelled":
                return OrderData.model_validate(order)
            if order.status != "pending_payment":
                raise OrderNotCancellableError
            order.status = "cancelled"
            await self.session.flush()
            await self.session.refresh(order, attribute_names=["updated_at"])
            return OrderData.model_validate(order)
