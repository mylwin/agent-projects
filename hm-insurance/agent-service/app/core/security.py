from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import settings
from app.core.exceptions import (
    InvalidRefreshTokenError,
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
)

password_hash = PasswordHash.recommended()

# 刷新令牌的 sub 是 BIGINT 用户 ID
MAX_USER_ID = 2**63 - 1


def hash_password(password: str) -> str:
    """生成带随机盐的 Argon2 密码哈希，供数据库保存。"""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """校验明文密码；密码不匹配或哈希损坏时返回 False。"""
    try:
        return password_hash.verify(password, hashed_password)
    except UnknownHashError:
        return False


def _secret() -> str:
    return settings.jwt.secret_key.get_secret_value()


def _encode(subject: str, lifetime: timedelta, token_type: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,  # 签名
            "iat": now,  # 签发时间
            "exp": now + lifetime,  # 过期时间
            "type": token_type,  # 令牌类型
            "jti": str(uuid4()),  # 令牌 ID
        },
        _secret(),
        algorithm=settings.jwt.algorithm,
    )


def create_access_token(subject: str) -> str:
    """为用户签发访问令牌，sub 保存用户 ID。"""
    return _encode(
        subject, timedelta(minutes=settings.jwt.access_token_expire_minutes), "access"
    )


def create_refresh_token(subject: str) -> str:
    """签发仅用于刷新登录态的令牌。"""
    return _encode(
        subject, timedelta(days=settings.jwt.refresh_token_expire_days), "refresh"
    )


def _decode(
    token: str, token_type: str, required: tuple[str, ...] = ()
) -> dict[str, Any]:
    """校验签名、有效期、令牌类型与必需声明。"""
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[settings.jwt.algorithm],
            options={"require": [*required, "sub", "iat", "exp", "type"]},
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError from exc
    except InvalidTokenError as exc:
        raise TokenInvalidError from exc

    subject = payload["sub"]
    if (
        payload["type"] != token_type
        or not isinstance(subject, str)
        or not subject.strip()
    ):
        raise TokenInvalidError
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    """解析访问令牌；无效或过期时抛出认证异常。"""
    payload = _decode(token, "access")
    if not payload["sub"].isdigit():
        raise TokenInvalidError
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """解析刷新令牌，并校验 sub 是可用的用户 ID。"""
    try:
        payload = _decode(token, "refresh", ("jti",))
    except TokenError as exc:
        raise InvalidRefreshTokenError from exc

    subject = payload["sub"]
    if not subject.isdigit() or not 0 < int(subject) <= MAX_USER_ID:
        raise InvalidRefreshTokenError
    return payload
