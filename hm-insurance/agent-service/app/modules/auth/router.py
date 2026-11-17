from typing import Annotated

from app.core.config import settings
from app.core.security import create_refresh_token
from app.infra.database import get_session
from app.modules.auth.schemas import (
    UserLoginRequest,
    UserLoginResponse,
    UserLogoutResponse,
    UserRegisterRequest,
    UserRegisterResponse,
)
from app.modules.auth.service import UsersService
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

# 创建路由对象
router = APIRouter(prefix="/api/v1/auth", tags=["用户认证接口"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, user_id: int) -> None:
    """只通过 HttpOnly Cookie 传递刷新令牌。"""
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=create_refresh_token(user_id),
        max_age=settings.jwt.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.jwt.refresh_cookie_secure,
        samesite="lax",
    )


def get_user_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UsersService:
    """获取用户服务对象"""
    return UsersService(session)


@router.post(
    "/register",
    response_model=UserRegisterResponse,
)
async def register(
    request: UserRegisterRequest,
    response: Response,
    service: Annotated[UsersService, Depends(get_user_service)],
) -> UserRegisterResponse:
    """注册用户并返回访问令牌及用户信息。"""
    result = await service.register(request)
    set_refresh_cookie(response, result.user.id)
    return result


@router.post("/login", response_model=UserLoginResponse)
async def login(
    request: UserLoginRequest,
    response: Response,
    service: Annotated[UsersService, Depends(get_user_service)],
) -> UserLoginResponse:
    """用户登录，返回访问令牌及用户信息。"""
    result = await service.login(request)
    set_refresh_cookie(response, result.user.id)
    return result


@router.post("/refresh", response_model=UserRegisterResponse)
async def refresh(
    request: Request,
    response: Response,
    service: Annotated[UsersService, Depends(get_user_service)],
) -> UserRegisterResponse:
    """读取 Refresh Token Cookie，刷新访问令牌并延长浏览器登录态。"""
    result = await service.refresh(request.cookies.get(REFRESH_COOKIE_NAME))
    set_refresh_cookie(response, result.user.id)
    return result


@router.post("/logout", response_model=UserLogoutResponse)
async def logout(response: Response) -> UserLogoutResponse:
    """清除浏览器刷新令牌 Cookie；无需携带访问令牌。"""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.jwt.refresh_cookie_secure,
        samesite="lax",
    )
    return UserLogoutResponse()
