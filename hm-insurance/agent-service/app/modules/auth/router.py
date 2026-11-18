from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_refresh_token
from app.infra.database import get_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.schemas import (
    AuthResponse,
    RefreshCookieAttrs,
    UserAuthData,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.modules.auth.service import UsersService

# 创建路由对象
router = APIRouter(prefix="/api/v1/auth", tags=["用户认证接口"])

# 刷新 cookie 名称
REFRESH_COOKIE_NAME = "refresh_token"
# 刷新 cookie 路径
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _cookie_attrs() -> RefreshCookieAttrs:
    """刷新令牌 Cookie 的公共属性，下发与清除保持一致。"""
    return {
        "path": REFRESH_COOKIE_PATH,
        "httponly": True,
        "secure": settings.jwt.refresh_cookie_secure,
        "samesite": "lax",
    }


def set_refresh_cookie(response: Response, user_id: int) -> None:
    """只通过 HttpOnly Cookie 下发刷新令牌。"""
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=create_refresh_token(str(user_id)),
        max_age=settings.jwt.refresh_token_expire_days * 86400,  # 最大生效时长
        **_cookie_attrs(),
    )


def clear_refresh_cookie(response: Response) -> None:
    """清除刷新令牌 Cookie。"""
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(key=REFRESH_COOKIE_NAME, **_cookie_attrs())


def get_user_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UsersService:
    """获取用户服务对象"""
    return UsersService(session)


@router.post("/register", response_model=AuthResponse)
async def register(
    body: UserRegisterRequest,
    response: Response,
    service: Annotated[UsersService, Depends(get_user_service)],
) -> AuthResponse:
    """注册用户并返回访问令牌及用户信息。"""
    result = await service.register(body)
    set_refresh_cookie(response, result.user.id)
    return result


@router.post("/login", response_model=AuthResponse)
async def login(
    body: UserLoginRequest,
    response: Response,
    service: Annotated[UsersService, Depends(get_user_service)],
) -> AuthResponse:
    """用户登录，返回访问令牌及用户信息。"""
    result = await service.login(body)
    set_refresh_cookie(response, result.user.id)
    return result


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    service: Annotated[UsersService, Depends(get_user_service)],
) -> AuthResponse:
    """读取 Refresh Token Cookie，刷新访问令牌并轮换 Cookie。"""
    result = await service.refresh(request.cookies.get(REFRESH_COOKIE_NAME, ""))
    set_refresh_cookie(response, result.user.id)
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """清除浏览器刷新令牌 Cookie；无需携带访问令牌。"""
    clear_refresh_cookie(response)


@router.get("/me", response_model=UserAuthData)
async def me(user: CurrentUser) -> UserAuthData:
    """返回当前登录用户信息。"""
    return user
