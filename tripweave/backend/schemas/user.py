from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


class UserRegisterRequest(BaseModel):
    """用户注册请求"""

    username: str = Field(min_length=2, max_length=50, description="用户名")
    password: str = Field(min_length=6, max_length=72, description="密码")
    confirm_password: str = Field(min_length=6, max_length=72, description="确认密码")

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """
        校验密码是否超过当前接口约定的 72 字节上限。
        """
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码长度不能超过 72 字节")
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> Self:
        """
        校验两次输入的密码是否一致
        """
        if self.password != self.confirm_password:
            raise ValueError("密码不一致")
        return self


class UserLoginRequest(BaseModel):
    """用户登录请求"""

    username: str = Field(min_length=2, max_length=50, description="用户名")
    password: str = Field(min_length=6, max_length=72, description="密码")

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """
        校验密码是否超过当前接口约定的 72 字节上限。
        """
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码长度不能超过 72 字节")
        return v


class UserRegisterAndLoginData(BaseModel):
    """用户注册和登陆成功返回数据"""

    id: int
    username: str
