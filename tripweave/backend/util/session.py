"""签名登录 Cookie 的生成和校验。"""

import base64
import hashlib
import hmac
import os
import time

from fastapi import Response

from backend.errors.api import ApiException

COOKIE = "tripweave_session"
SESSION_SECONDS = 7 * 24 * 60 * 60


def signing_key() -> bytes:
    """读取签名密钥，拒绝缺失或过短的配置。"""
    key = os.environ.get("AUTH_SECRET_KEY", "").encode()
    if len(key) < 32:
        raise ApiException.configuration("AUTH_SECRET_KEY 至少需要 32 字节")
    return key


def set_session(response: Response, user_id: int, key: bytes) -> None:
    """设置带签名和有效期的 HttpOnly Cookie。"""
    payload = f"{user_id}.{int(time.time()) + SESSION_SECONDS}"
    signature = hmac.new(key, payload.encode(), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    response.set_cookie(
        COOKIE,
        f"{payload}.{token}",
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )


def session_user_id(cookie: str, key: bytes) -> int | None:
    """验证 Cookie 签名和有效期，失败时返回 None。"""
    try:
        user_id, expires, signature = cookie.split(".")
        payload = f"{user_id}.{expires}"
        expected = (
            base64.urlsafe_b64encode(
                hmac.new(key, payload.encode(), hashlib.sha256).digest()
            )
            .decode()
            .rstrip("=")
        )
        if (
            not hmac.compare_digest(signature, expected)
            or int(expires) <= int(time.time())
            or int(user_id) <= 0
        ):
            return None
        return int(user_id)
    except (ValueError, TypeError):
        return None
