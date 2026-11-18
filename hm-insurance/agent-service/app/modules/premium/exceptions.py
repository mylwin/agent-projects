from app.core.exceptions import ApplicationError


class ProductIdIsNullError(ApplicationError):
    """产品ID为空异常"""

    status_code = 400
    code = "INVALID_PRICING_PARAMS"
    message = "产品ID为空"


class PriceBindingNotFoundError(ApplicationError):
    """产品没有对应的生效试算绑定"""

    status_code = 404
    code = "PRICING_BINDING_NOT_FOUND"
    message = "未找到该产品生效的试算绑定"


class PriceParamsMissingError(ApplicationError):
    """缺少试算模板对应的参数"""

    status_code = 400
    code = "MISSING_PRICING_PARAMS"

    def __init__(self, fields: list[str]) -> None:
        super().__init__(fields)
        self.message = f"试算参数缺失：{', '.join(fields)}"


class PriceParamsInvalidError(ApplicationError):
    """试算参数不合法"""

    status_code = 400
    code = "INVALID_PRICING_PARAMS"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

