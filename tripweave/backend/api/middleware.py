"""从签名 Cookie 查询当前登录用户。"""

from fastapi import FastAPI, Request

from backend.api.exception_handlers import failure_response
from backend.crud.user import find_user_by_id
from backend.errors.api import ApiException
from backend.models.user import User
from backend.util.session import COOKIE, session_user_id, signing_key


async def resolve_current_user(request: Request) -> User | None:
    """
    校验 Cookie 并查询用户；无效登录态返回 None。

    :param request: 当前请求。
    :return: 已验证的用户；无效登录态返回 None。

    """
    cookie = request.cookies.get(COOKIE)
    factory = getattr(request.app.state, "database_session_factory", None)
    if not cookie or factory is None:
        return None
    user_id = session_user_id(cookie, signing_key())
    if user_id is None:
        return None
    async with factory() as session:
        return await find_user_by_id(session, user_id)


def register_auth_middleware(app: FastAPI) -> None:
    """
    为每次请求保存已验证的当前用户，供接口读取。

    :param app: FastAPI 应用。
    """

    @app.middleware("http")
    async def current_user(request: Request, call_next):
        """在路由执行前将当前用户放入请求状态。"""
        try:
            request.state.current_user = await resolve_current_user(request)
        except ApiException as exc:
            return failure_response(exc.status_code, exc.error)
        return await call_next(request)
