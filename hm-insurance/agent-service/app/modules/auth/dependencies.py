from typing import Annotated

from app.core.exceptions import TokenInvalidError
from app.core.security import decode_access_token
from app.infra.database import get_session
from app.modules.auth.exceptions import UnauthorizedError, status_exception
from app.modules.auth.repository import UsersRepository
from app.modules.auth.schemas import UserAuthData
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserAuthData:
    """解析 Authorization: Bearer 访问令牌，返回当前登录用户。"""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError

    user_id = int(decode_access_token(token)["sub"])
    user = await UsersRepository(session).find_by_id(user_id)
    if user is None:
        raise TokenInvalidError
    if user.status != "active":
        raise status_exception(user.status)
    return UserAuthData.from_user(user)


CurrentUser = Annotated[UserAuthData, Depends(get_current_user)]
