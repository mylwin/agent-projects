from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

FIELD_LABELS = {
    "username": "用户名",
    "email": "邮箱",
    "password": "密码",
}

VALIDATION_MESSAGES = {
    "missing": "不能为空",
    "string_type": "必须是字符串",
    "int_type": "必须是整数",
    "int_parsing": "必须是整数",
    "float_type": "必须是数字",
    "float_parsing": "必须是数字",
    "bool_type": "必须是布尔值",
    "bool_parsing": "必须是布尔值",
    "list_type": "必须是列表",
    "dict_type": "必须是对象",
    "uuid_parsing": "必须是有效的 UUID",
    "uuid_type": "必须是有效的 UUID",
}


async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """统一请求参数校验响应，仅返回错误码与中文提示。"""
    messages: list[str] = []
    for error in exc.errors():
        location = error.get("loc", ())
        # 去掉 FastAPI 标记的参数来源，提取字段名称。
        parts = (
            location[1:]
            if location and location[0] in {"body", "query", "path", "header", "cookie"}
            else location
        )
        label = FIELD_LABELS.get(str(parts[-1]), "参数") if parts else "请求体"
        error_type = error.get("type", "")
        context = error.get("ctx") or {}

        if error_type == "json_invalid":
            message = "请求体必须是有效的 JSON"
        elif error_type == "string_pattern_mismatch":
            message = (
                "请输入有效的邮箱地址"
                if parts and parts[-1] == "email"
                else f"{label}格式不正确"
            )
        elif error_type in {"string_too_short", "string_too_long"}:
            is_short = error_type == "string_too_short"
            limit = context.get("min_length" if is_short else "max_length")
            if isinstance(limit, int):
                rule = "至少需要" if is_short else "最多允许"
                message = f"{label}{rule}{limit}个字符"
            else:
                message = f"{label}长度不符合要求"
        else:
            message = f"{label}{VALIDATION_MESSAGES.get(error_type, '不符合要求')}"

        # 不透传 input、ctx、原始 msg 或异常字符串，避免回显密码等输入。
        messages.append(message)

    return JSONResponse(
        status_code=422,
        content={
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "；".join(dict.fromkeys(messages)) or "请求参数错误",
        },
    )
