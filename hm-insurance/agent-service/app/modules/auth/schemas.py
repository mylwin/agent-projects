from typing import Annotated, Literal, TypedDict

from app.modules.auth.models import Users
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """用户注册请求参数"""

    model_config = ConfigDict(str_strip_whitespace=True)

    username: Annotated[str, Field(description="用户名", min_length=3, max_length=20)]
    email: Annotated[EmailStr, Field(description="邮箱")]
    password: Annotated[
        str, Field(description="密码", min_length=6, max_length=128, repr=False)
    ]


class UserLoginRequest(BaseModel):
    """用户登录请求参数"""

    model_config = ConfigDict(str_strip_whitespace=True)

    username: Annotated[
        str, Field(description="用户名或邮箱", min_length=1, max_length=160)
    ]
    password: Annotated[
        str, Field(description="密码", min_length=6, max_length=128, repr=False)
    ]


class UserAuthData(BaseModel):
    """用户信息"""

    id: int = Field(description="用户ID")
    username: str = Field(description="用户名")
    email: str = Field(description="邮箱")
    display_name: str = Field(description="展示昵称")

    @classmethod
    def from_user(cls, user: Users):
        """库中 display_name 可为空，对外统一回落到用户名。"""
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name or user.username,
        )


class AuthResponse(BaseModel):
    """认证响应：访问令牌与用户信息"""

    access_token: str = Field(description="访问令牌")
    token_type: str = Field(description="令牌类型", default="Bearer")
    user: UserAuthData = Field(description="用户信息")


class RefreshCookieAttrs(TypedDict):
    """刷新令牌 Cookie 属性"""

    path: str
    httponly: bool
    secure: bool
    samesite: Literal["lax"]
