"""用户名密码认证接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.config.database import get_db
from backend.crud.user import create_user, find_user_by_username, record_login
from backend.errors.api import ApiException
from backend.models.user import User
from backend.schemas.api import ApiError, ApiFailure, ApiSuccess
from backend.schemas.user import (
    UserLoginRequest,
    UserRegisterAndLoginData,
    UserRegisterRequest,
)
from backend.util.password import hash_password, verify_password
from backend.util.session import COOKIE, set_session, signing_key

router = APIRouter(prefix="/auth", tags=["auth"])


def auth_error(status: int, code: str, message: str) -> ApiException:
    """
    构造不暴露内部细节的认证错误。

    :param status: HTTP 状态码。
    :param code: 错误码。
    :param message: 错误信息。
    :return: 认证错误。
    """
    return ApiException(status, ApiError(code=code, message=message))


Session = Annotated[AsyncSession, Depends(get_db, scope="function")]
Key = Annotated[bytes, Depends(signing_key)]


@router.post(
    "/register",
    response_model=ApiSuccess[UserRegisterAndLoginData],
    status_code=201,
    responses={409: {"model": ApiFailure}, 503: {"model": ApiFailure}},
)
async def register(
    body: UserRegisterRequest, response: Response, session: Session, key: Key
) -> ApiSuccess[UserRegisterAndLoginData]:
    """创建用户并建立登录态，用户名重复时返回 409。"""
    password_hash = await run_in_threadpool(hash_password, body.password)
    try:
        # 创建用户
        user = await create_user(session, body.username, password_hash)
    except IntegrityError as exc:
        if exc.orig is not None and exc.orig.args and exc.orig.args[0] == 1062:
            raise auth_error(409, "username_taken", "用户名已存在") from None
        raise
    # 设置登录 session
    set_session(response, user.id, key)
    return ApiSuccess(data=UserRegisterAndLoginData(id=user.id, username=user.username))


@router.post(
    "/login",
    response_model=ApiSuccess[UserRegisterAndLoginData],
    responses={401: {"model": ApiFailure}, 503: {"model": ApiFailure}},
)
async def login(
    body: UserLoginRequest, response: Response, session: Session, key: Key
) -> ApiSuccess[UserRegisterAndLoginData]:
    """验证用户名密码，成功后建立登录态。"""
    user = await find_user_by_username(session, body.username)
    if user is None or not await run_in_threadpool(
        verify_password, body.password, user.password_hash
    ):
        raise auth_error(401, "invalid_credentials", "用户名或密码错误")
    await record_login(session, user)
    set_session(response, user.id, key)
    return ApiSuccess(data=UserRegisterAndLoginData(id=user.id, username=user.username))


@router.get(
    "/me",
    response_model=ApiSuccess[UserRegisterAndLoginData],
    responses={401: {"model": ApiFailure}},
)
async def me(request: Request) -> ApiSuccess[UserRegisterAndLoginData]:
    """返回中间件验证过的当前用户。"""
    user: User | None = request.state.current_user
    if user is None:
        raise auth_error(401, "unauthorized", "请先登录")
    return ApiSuccess(data=UserRegisterAndLoginData(id=user.id, username=user.username))


@router.post("/logout", response_model=ApiSuccess[None])
async def logout(response: Response) -> ApiSuccess[None]:
    """清除当前浏览器中的登录 Cookie。"""
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax")
    return ApiSuccess(data=None)
