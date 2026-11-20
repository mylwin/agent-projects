from app.core.exceptions import ApplicationError


class OrderNotFoundError(ApplicationError):
    """订单不存在或不属于当前用户。"""

    status_code = 404
    code = "ORDER_NOT_FOUND"
    message = "订单不存在"


class QuoteNotFoundError(ApplicationError):
    """报价不存在或不允许当前用户使用。"""

    status_code = 404
    code = "QUOTE_NOT_FOUND"
    message = "报价不存在"


class QuoteExpiredError(ApplicationError):
    """创建订单时引用的报价已过期。"""

    status_code = 409
    code = "QUOTE_EXPIRED"
    message = "报价已过期，请重新试算"


class OrderItemMismatchError(ApplicationError):
    """订单项的产品与报价对应的产品不一致。"""

    status_code = 422
    code = "ORDER_ITEM_MISMATCH"
    message = "订单项的产品与报价不一致"


class OrderIdempotencyConflictError(ApplicationError):
    """提交使用了已被其他订单占用的幂等键或确认 ID。"""

    status_code = 409
    code = "ORDER_IDEMPOTENCY_CONFLICT"
    message = "幂等键或确认 ID 已被其他订单使用"


class OrderNotCancellableError(ApplicationError):
    """仅待支付订单可取消。"""

    status_code = 409
    code = "ORDER_NOT_CANCELLABLE"
    message = "当前订单状态不允许取消"
