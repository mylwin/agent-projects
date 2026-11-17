from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from app.core.config import settings
from app.modules.auth.exceptions import (
    InvalidRefreshTokenError,
    TokenExpiredError,
    TokenInvalidError,
)
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """注册时生成带随机盐的 Argon2 密码哈希，供数据库保存。"""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """校验明文密码；密码不匹配或哈希损坏时返回 False。"""
    try:
        return password_hash.verify(password, hashed_password)
    except UnknownHashError:
        return False


def create_access_token(
    subject: str | UUID, expires_delta: timedelta | None = None
) -> str:
    """为用户签发访问令牌，sub 保存用户 ID。"""
    subject = str(subject)
    if not subject.strip():
        raise ValueError("令牌用户标识不能为空")

    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt.access_token_expire_minutes)
    )
    if lifetime <= timedelta(0):
        raise ValueError("令牌有效期必须大于零")

    now = datetime.now(UTC)
    payload = {
        "sub": subject, "iat": now, "exp": now + lifetime,
        "type": "access", "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        settings.jwt.secret_key.get_secret_value(),
        algorithm=settings.jwt.algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """校验签名及声明并返回载荷；无效或过期时抛出认证异常。"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt.secret_key.get_secret_value(),
            algorithms=[settings.jwt.algorithm],
            options={"require": ["sub", "iat", "exp"]},
        )
        subject = payload["sub"]
        if not isinstance(subject, str) or not subject.strip():
            raise InvalidTokenError("令牌用户标识无效")
        if payload.get("type", "access") != "access":
            raise InvalidTokenError("令牌类型无效")
        return payload
    except ExpiredSignatureError as exc:
        raise TokenExpiredError from exc
    except InvalidTokenError as exc:
        raise TokenInvalidError from exc


def create_refresh_token(subject: str | int) -> str:
    """签发仅用于刷新登录态的令牌，独立于访问令牌有效期。"""
    subject = str(subject)
    if not subject.strip():
        raise ValueError("令牌用户标识不能为空")
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "iat": now,
            "exp": now + timedelta(days=settings.jwt.refresh_token_expire_days),
            "type": "refresh",
            "jti": str(uuid4()),
        },
        settings.jwt.secret_key.get_secret_value(),
        algorithm=settings.jwt.algorithm,
    )


def decode_refresh_token(token: str) -> dict[str, Any]:
    """验证刷新令牌，拒绝访问令牌、无效签名和过期令牌。"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt.secret_key.get_secret_value(),
            algorithms=[settings.jwt.algorithm],
            options={"require": ["sub", "iat", "exp", "type", "jti"]},
        )
        if payload["type"] != "refresh":
            raise InvalidTokenError("令牌类型无效")
        if not isinstance(payload["sub"], str) or not payload["sub"].strip():
            raise InvalidTokenError("令牌用户标识无效")
        return payload
    except (InvalidTokenError, ValueError, TypeError, OverflowError) as exc:
        raise InvalidRefreshTokenError from exc
