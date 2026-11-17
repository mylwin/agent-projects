from app.core.exceptions import ApplicationError


class UserAlreadyExistError(ApplicationError):
    code = "USER_EXISTS"
    message = "用户已存在"
    status_code = 409


class UserRegisterParameterError(ApplicationError):
    code = "INVALID_REGISTER_REQUEST"
    message = "注册参数错误"
    status_code = 400


class UserNotFoundError(ApplicationError):
    code = "USER_NOT_FOUND"
    message = "用户不存在"
    status_code = 401


class UserInactiveError(ApplicationError):
    code = "USER_INACTIVE"
    message = "用户尚未激活"
    status_code = 403


class UserSuspendedError(ApplicationError):
    code = "USER_SUSPENDED"
    message = "用户已被封禁"
    status_code = 403


class InvalidCredentialsError(ApplicationError):
    code = "INVALID_CREDENTIALS"
    message = "用户名或密码错误"
    status_code = 401


class TokenExpiredError(ApplicationError):
    """访问令牌已过期"""

    code = "TOKEN_EXPIRED"
    message = "登录已过期，请重新登录"
    status_code = 401


class TokenInvalidError(ApplicationError):
    """访问令牌无效"""

    code = "TOKEN_INVALID"
    message = "登录令牌无效，请重新登录"
    status_code = 401


class InvalidRefreshTokenError(ApplicationError):
    code = "INVALID_REFRESH_TOKEN"
    message = "Refresh token is invalid or expired"
    status_code = 401


class RefreshUserNotFoundError(ApplicationError):
    code = "USER_NOT_FOUND"
    message = "用户不存在"
    status_code = 404


class InactiveRefreshUserError(ApplicationError):
    code = "INACTIVE_USER"
    message = "用户已被停用"
    status_code = 400
