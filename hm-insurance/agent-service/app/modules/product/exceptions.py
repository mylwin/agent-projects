from app.core.exceptions import ApplicationError


class ProductNotFoundError(ApplicationError):
    """产品不存在或已下架"""

    status_code = 404
    code = "PRODUCT_NOT_FOUND"
    message = "产品不存在或已下架"


class PriceTemplateNotFoundError(ApplicationError):
    """价格试算模板不存在"""

    status_code = 404
    code = "PRICING_SCHEMA_NOT_FOUND"
    message = "Pricing schema not found"
