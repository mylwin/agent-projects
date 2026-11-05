"""HTTP 接口业务异常与规划失败映射。"""

from backend.errors.planning import PlanningError
from backend.schemas.api import ApiError


class ApiException(Exception):
    """
    携带 HTTP 状态码和统一错误体的业务异常。

    Attributes:
        status_code: 返回给调用方的 HTTP 状态码。
        error: 统一失败响应中的错误说明。
    """

    def __init__(self, status_code: int, error: ApiError) -> None:
        """
        :param status_code: 返回给调用方的 HTTP 状态码。
        :param error: 统一失败响应中的错误说明。
        """
        super().__init__(error.message)
        self.status_code = status_code
        self.error = error

    @classmethod
    def configuration(cls, message: str) -> "ApiException":
        """
        构造配置缺失或非法错误。

        :param message: 不含密钥的配置错误说明。
        :return: 503 业务异常。
        """
        return cls(503, ApiError(code="configuration_error", message=message))

    @classmethod
    def busy(cls) -> "ApiException":
        """
        构造并发生成任务已满错误。

        :return: 429 业务异常。
        """
        return cls(429, ApiError(code="busy", message="当前生成任务已满，请稍后重试"))

    @classmethod
    def timeout(cls) -> "ApiException":
        """
        构造整轮规划超时错误。

        :return: 504 业务异常。
        """
        return cls(504, ApiError(code="planning_timeout", message="规划超时，请重试"))

    @classmethod
    def internal(cls) -> "ApiException":
        """
        构造未处理异常错误；原始细节只写服务端日志。

        :return: 500 业务异常。
        """
        return cls(
            500, ApiError(code="internal_error", message="服务内部错误，请稍后重试")
        )

    @classmethod
    def from_planning(cls, exc: PlanningError) -> "ApiException":
        """
        把规划失败映射为稳定的 HTTP 状态码和错误码。

        业务校验失败说明请求本身无法生成行程；底层超时返回 504；
        其他情况视为上游模型或地图服务失败。

        :param exc: 保留阶段和底层异常的规划错误。
        :return: 可供接口层抛出的业务异常。
        """
        if isinstance(exc.original, ValueError):
            return cls(
                422,
                ApiError(
                    code="planning_rejected",
                    message=str(exc),
                    stage=exc.stage,
                ),
            )
        if isinstance(exc.original, TimeoutError):
            return cls(
                504,
                ApiError(
                    code="planning_timeout",
                    message=str(exc),
                    stage=exc.stage,
                ),
            )
        return cls(
            502,
            ApiError(
                code="upstream_failed",
                message=str(exc),
                stage=exc.stage,
            ),
        )
