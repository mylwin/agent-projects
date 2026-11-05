"""FastAPI 全局异常处理器：把异常转换为统一失败响应。"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.errors.api import ApiException
from backend.schemas.api import ApiError, ApiFailure


def failure_response(status_code: int, error: ApiError) -> JSONResponse:
    """
    将统一失败体转换为 JSON 响应。

    :param status_code: HTTP 状态码。
    :param error: 错误码、说明和可选失败阶段。
    :return: 失败响应。
    """
    return JSONResponse(
        status_code=status_code,
        content=ApiFailure(error=error).model_dump(mode="json"),
    )


async def handle_api_exception(_request: Request, exc: ApiException) -> JSONResponse:
    """
    输出业务异常对应的统一失败体。

    :param _request: 当前 HTTP 请求，未使用。
    :param exc: 携带状态码和错误体的业务异常。
    :return: 统一失败响应。
    """
    return failure_response(exc.status_code, exc.error)


async def handle_http_exception(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    让 404、405 等框架错误也使用统一失败体。

    :param _request: 当前 HTTP 请求，未使用。
    :param exc: Starlette 抛出的 HTTP 异常。
    :return: 统一失败响应。
    """
    messages = {404: "接口不存在", 405: "请求方法不允许"}
    message = messages.get(exc.status_code, str(exc.detail))
    code = "not_found" if exc.status_code == 404 else "http_error"
    return failure_response(exc.status_code, ApiError(code=code, message=message))


async def handle_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    只暴露错误字段位置，不回传原始输入值。

    :param _request: 当前 HTTP 请求，未使用。
    :param exc: FastAPI 请求模型校验错误。
    :return: 统一失败响应。
    """
    fields = [
        ".".join(str(part) for part in error["loc"][1:]) for error in exc.errors()
    ]
    message = "请求参数不合法"
    if fields:
        message += "：" + "、".join(dict.fromkeys(fields))
    return failure_response(422, ApiError(code="invalid_request", message=message))


def register_exception_handlers(app: FastAPI) -> None:
    """
    注册全局异常处理器。

    :param app: 当前 FastAPI 应用。
    """
    app.exception_handler(ApiException)(handle_api_exception)
    app.exception_handler(StarletteHTTPException)(handle_http_exception)
    app.exception_handler(RequestValidationError)(handle_validation_error)
