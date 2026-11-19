from typing import Any

from app.modules.premium.exceptions import (
    PriceParamsInvalidError,
    PriceParamsMissingError,
)


def validate_answers(answers: dict[str, Any], schema_json: dict[str, Any]) -> None:
    """
    按产品试算模板校验用户填写的试算项

    Field 只能约束所有产品通用的规则（类型、枚举、非负）；
    模板里的必填项与每个产品不同的年龄区间只能在这里动态校验。
    """
    fields = schema_json["fields"]

    missing = [
        field["key"]
        for field in fields
        if field["required"] and _get_answer(answers, field["key"]) in (None, "")
    ]
    if missing:
        raise PriceParamsMissingError(missing)

    errors = [error for field in fields if (error := _range_error(answers, field))]
    if errors:
        raise PriceParamsInvalidError("；".join(errors))


def _get_answer(answers: dict[str, Any], key: str) -> Any:
    """
    按模板的点号 key（如 insured.age）从分层试算项中取值
    """
    value: Any = answers
    for part in key.split("."):
        value = value.get(part)
    return value


def _range_error(answers: dict[str, Any], field: dict[str, Any]) -> str | None:
    """返回字段超出模板区间时的提示"""
    value = _get_answer(answers, field["key"])
    if value in (None, ""):
        return None

    minimum = field.get("min")
    if minimum is not None and value < minimum:
        return f"{field['key']} 不能小于 {minimum}"

    maximum = field.get("max")
    if maximum is not None and value > maximum:
        return f"{field['key']} 不能大于 {maximum}"
    return None
