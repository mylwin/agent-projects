from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

FIELD_LABELS = {"username": "用户名", "email": "邮箱", "password": "密码"}
# 去掉 FastAPI 标记的参数来源，只保留字段路径
PARAM_SOURCES = {"body", "query", "path", "header", "cookie"}
LENGTH_RULES = {
    "string_too_short": ("至少需要", "min_length"),
    "string_too_long": ("最多允许", "max_length"),
}


def _location(error: dict) -> tuple[str, str]:
    """返回字段路径与中文字段名。"""
    parts = [
        part
        for part in error.get("loc", ())
        if isinstance(part, str) and part not in PARAM_SOURCES
    ]
    field = ".".join(parts)
    return field or "body", FIELD_LABELS.get(field, "参数")


def _message(error: dict, field: str, label: str) -> str:
    """把 pydantic 错误类型翻译成中文，且不回显用户输入。"""
    error_type = error.get("type", "")
    if error_type == "json_invalid":
        return "请求体必须是有效的 JSON"
    if error_type == "missing":
        return f"{label}不能为空"
    if error_type in LENGTH_RULES:
        rule, key = LENGTH_RULES[error_type]
        limit = (error.get("ctx") or {}).get(key)
        if not isinstance(limit, int):
            return f"{label}长度不符合要求"
        return f"{label}{rule}{limit}个字符"
    if field == "email":
        return "请输入有效的邮箱地址"
    if field == "body":
        return "请求体不符合要求"
    return f"{label}格式不正确"


def build_validation_error_response(exc: RequestValidationError) -> JSONResponse:
    """统一请求参数校验响应，保留字段定位，仅返回中文提示。"""
    errors = []
    for error in exc.errors():
        field, label = _location(error)
        errors.append({"field": field, "message": _message(error, field, label)})

    messages = list(dict.fromkeys(item["message"] for item in errors))
    return JSONResponse(
        status_code=422,
        content={
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "；".join(messages) or "请求参数错误",
            "errors": errors,
        },
    )
