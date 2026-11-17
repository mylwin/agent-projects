from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class UserRegisterRequest(BaseModel):
    """用户注册请求参数"""

    username: Annotated[str, StringConstraints(strip_whitespace=True)] = Field(
        description="用户名",
        min_length=3,
        max_length=20,
    )
    email: Annotated[str, StringConstraints(strip_whitespace=True)] = Field(
        description="邮箱",
        min_length=5,
        max_length=160,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(
        description="密码",
        min_length=6,
        max_length=20,
        repr=False,
    )


class UserAuthData(BaseModel):
    """用户认证(注册/登录)成功后返回的数据"""

    id: int = Field(description="用户ID")
    username: str = Field(description="用户名")
    email: str = Field(description="邮箱")
    display_name: str = Field(
        description="展示昵称",
    )


class UserRegisterResponse(BaseModel):
    """用户注册响应参数"""

    access_token: str = Field(description="访问令牌")
    token_type: str = Field(description="令牌类型", default="Bearer")
    user: UserAuthData = Field(description="用户信息")


class UserLoginRequest(BaseModel):
    """用户登录请求参数"""

    username: Annotated[str, StringConstraints(strip_whitespace=True)] = Field(
        description="用户名",
        min_length=3,
        max_length=20,
    )
    password: str = Field(
        description="密码",
        min_length=6,
        max_length=20,
        repr=False,
    )


class UserLoginResponse(BaseModel):
    """用户登录响应参数"""

    access_token: str = Field(description="访问令牌")
    user: UserAuthData = Field(description="用户信息")


class UserLogoutResponse(BaseModel):
    """退出登录响应"""

    ok: bool = True
