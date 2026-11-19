from typing import Annotated

from fastapi import Depends, Request

from app.core.exceptions import TokenInvalidError
from app.core.security import decode_access_token
from app.infra.database import AsyncSessionFactory
from app.modules.auth.exceptions import UnauthorizedError, status_exception
from app.modules.auth.repository import UsersRepository
from app.modules.auth.schemas import UserAuthData


async def get_current_user(request: Request) -> UserAuthData:
    """解析 Authorization: Bearer 访问令牌，返回当前登录用户。"""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError

    user_id = int(decode_access_token(token)["sub"])
    # 认证查询使用独立短会话：请求级 Session 留给业务服务，
    # 避免这里的 SELECT 自动开启事务后与 service 中的 session.begin() 冲突。
    async with AsyncSessionFactory() as session:
        user = await UsersRepository(session).find_by_id(user_id)
        if user is None:
            raise TokenInvalidError
        if user.status != "active":
            raise status_exception(user.status)
        return UserAuthData.from_user(user)


CurrentUser = Annotated[UserAuthData, Depends(get_current_user)]


async def get_optional_current_user(request: Request) -> UserAuthData | None:
    """没有 Bearer 时返回 None；带了令牌则复用登录解析逻辑。"""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return await get_current_user(request)


OptionalCurrentUser = Annotated[
    UserAuthData | None, Depends(get_optional_current_user)
]
