from app.core.exceptions import ApplicationError


class UnauthorizedError(ApplicationError):
    """未携带访问令牌"""

    code = "UNAUTHORIZED"
    message = "请先登录"
    status_code = 401


class UserAlreadyExistsError(ApplicationError):
    """用户名或邮箱已被注册"""

    code = "USER_EXISTS"
    message = "用户名或邮箱已被注册"
    status_code = 409


class InvalidCredentialsError(ApplicationError):
    """用户名或密码错误"""

    code = "INVALID_CREDENTIALS"
    message = "用户名或密码错误"
    status_code = 401


class UserInactiveError(ApplicationError):
    """用户尚未激活"""

    code = "USER_INACTIVE"
    message = "用户尚未激活"
    status_code = 403


class UserSuspendedError(ApplicationError):
    """用户已被封禁"""

    code = "USER_SUSPENDED"
    message = "用户已被封禁"
    status_code = 403


def status_exception(status: str) -> ApplicationError:
    """非 active 状态对应的业务异常。"""
    return UserSuspendedError() if status == "suspended" else UserInactiveError()
