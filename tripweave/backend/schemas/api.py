"""HTTP 接口统一的成功与失败响应结构。"""

from typing import Literal

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    """
    失败响应的错误说明，不包含底层异常对象或密钥。

    Attributes:
        code: 稳定的机器可读错误码。
        message: 面向调用方的中文说明。
        stage: 规划失败阶段，非规划错误时为 None。
    """

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    stage: str | None = None


class ApiSuccess[T](BaseModel):
    """
    成功响应，data 为具体业务结果。

    Attributes:
        success: 成功标记，固定为 True。
        data: 业务结果，例如 PlanResult。
    """

    success: Literal[True] = True
    data: T


class ApiFailure(BaseModel):
    """
    失败响应，error 说明失败原因。

    Attributes:
        success: 失败标记，固定为 False。
        error: 错误码、说明和可选失败阶段。
    """

    success: Literal[False] = False
    error: ApiError


class HealthData(BaseModel):
    """
    健康检查返回的公开配置，不含密钥。

    Attributes:
        status: 服务状态，当前固定为 ok。
        map_provider: 当前地图供应商。
        model: 当前模型名称。
    """

    status: Literal["ok"] = "ok"
    map_provider: str
    model: str
