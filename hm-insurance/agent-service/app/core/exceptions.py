class ApplicationError(Exception):
    """应用业务异常基类"""

    status_code: int = 500  # 默认状态码
    code: str = "APPLICATION_ERROR"  # 默认异常code
    message: str = "服务器内部错误"  # 默认异常提示


class TokenError(ApplicationError):
    """令牌异常基类，由 core.security 抛出，供各业务模块共用"""

    status_code = 401


class TokenExpiredError(TokenError):
    """访问令牌已过期"""

    code = "TOKEN_EXPIRED"
    message = "登录已过期，请重新登录"


class TokenInvalidError(TokenError):
    """访问令牌无效"""

    code = "TOKEN_INVALID"
    message = "登录状态无效，请重新登录"


class InvalidRefreshTokenError(TokenError):
    """刷新令牌无效或已过期"""

    code = "INVALID_REFRESH_TOKEN"
    message = "登录状态已失效，请重新登录"
