"""输入契约共用的基础类型与标量校验。"""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
)


class ContractModel(BaseModel):
    """
    拒绝额外字段并重新校验嵌套模型，避免静默丢失输入。
    """

    model_config = ConfigDict(
        extra="forbid",  # 额外字段状态：拒绝
        validate_default=True,  # 模型校验默认值：重新校验嵌套模型
        revalidate_instances="always",  # 重新校验嵌套模型实例：总是
    )


def _parse_date(value: object) -> date:
    """
    将明确的 ISO 日期转换为 date，拒绝时间戳和 datetime 隐式截断。

    :param value: 调用方提供的 YYYY-MM-DD 字符串或 date 对象。
    :return: 不带时间部分的日历日期。
    :raises ValueError: 输入类型、日期格式或日历日期无效时抛出。
    """
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("日期必须为 YYYY-MM-DD 字符串或 date 对象")
    return date.fromisoformat(value)


def _parse_money(value: object) -> Decimal:
    """
    转换精确金额，避免浮点数在进入契约时产生精度歧义。

    :param value: 至多两位小数的十进制字符串或 Decimal 对象。
    :return: 交由后续金额范围约束校验的 Decimal。
    :raises ValueError: 输入不是允许的金额类型或格式时抛出。
    """
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
        raise ValueError("金额必须为至多两位小数的十进制字符串或 Decimal")
    return Decimal(value)


# 通用短文本：去除首尾空白后必须为 1–200 字，避免空白内容进入业务字段。
NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

# 资源或关联标识：去除首尾空白后长度为 1–128，不限定为 UUID。
Identifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]

# 说明与备注：去除首尾空白后长度为 1–500，用于约束说明和澄清文本。
Note = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]

# 契约结构版本：当前仅接受整数 1，拒绝其他版本及布尔值。
SchemaVersion = Annotated[int, Field(strict=True, ge=1, le=1)]

# 日历日期：先校验 YYYY-MM-DD 字符串或 date，拒绝时间戳及 datetime 截断。
IsoDate = Annotated[date, BeforeValidator(_parse_date)]

# 精确非负金额：最多 12 位有效数字、两位小数，禁止 NaN 和无穷值。
# 输入仅接受十进制字符串或 Decimal；输出 JSON 时统一为两位小数字符串。
Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False),
    BeforeValidator(_parse_money),
    PlainSerializer(
        lambda value: format(value, ".2f"), return_type=str, when_used="json"
    ),
]

# 本地活动时间：采用 24 小时制 HH:mm，只接受 00:00 至 23:59。
LocalClock = Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]

# 经度：有限数值且位于 [-180, 180]，拒绝字符串和布尔值转换。
Longitude = Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]

# 纬度：有限数值且位于 [-90, 90]，拒绝字符串和布尔值转换。
Latitude = Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]

# 全团预算口径：明确费用覆盖范围，避免将活动小计当作整趟旅行总费用。
BudgetScope = Literal[
    "group_excluding_intercity",  # 全团预算，不含往返大交通。
    "group_activities_only",  # 仅覆盖行程中列出的活动费用。
    "group_total",  # 覆盖全程费用，未估算部分仍需明确标注。
]
