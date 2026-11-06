"""认证接口测试，使用数据库替身，不连接真实服务。"""

import asyncio
from collections.abc import Generator
from typing import Any

import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend.api import middleware
from backend.api.app import app
from backend.config.database import get_db
from backend.models.user import User
from backend.util.password import hash_password
from backend.util.session import COOKIE, session_user_id, set_session, signing_key


class FakeSession:
    """模拟用户读写与用户名唯一约束。"""

    def __init__(self) -> None:
        """初始化内存用户集合。"""
        self.users: list[User] = []
        self.pending: User | None = None

    def add(self, user: User) -> None:
        """暂存待创建用户。"""
        self.pending = user

    async def flush(self) -> None:
        """模拟数据库插入与唯一约束及主键分配。"""
        if self.pending is None:
            return
        if any(u.username.lower() == self.pending.username.lower() for u in self.users):
            self.pending = None
            raise IntegrityError("insert", {}, Exception(1062, "duplicate"))
        self.pending.id = len(self.users) + 1
        self.users.append(self.pending)
        self.pending = None

    async def rollback(self) -> None:
        """清除失败的插入。"""
        self.pending = None

    async def scalar(self, statement: Any) -> User | None:
        """按查询参数查找用户。"""
        name = next(iter(statement.compile().params.values()))
        return next((u for u in self.users if u.username.lower() == name.lower()), None)

    async def get(self, model: Any, user_id: int) -> User | None:
        """按主键查找用户。"""
        return next((u for u in self.users if u.id == user_id), None)


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, FakeSession]]:
    """提供隔离的认证客户端和内存会话。"""
    session = FakeSession()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[signing_key] = lambda: b"a" * 32

    async def fake_current_user(request):
        """从测试用户集合解析签名 Cookie。"""
        cookie = request.cookies.get(COOKIE)
        user_id = session_user_id(cookie, b"a" * 32) if cookie else None
        return await session.get(User, user_id) if user_id is not None else None

    monkeypatch.setattr(middleware, "resolve_current_user", fake_current_user)
    with TestClient(app) as test_client:
        yield test_client, session
    app.dependency_overrides.clear()


def test_register_login_me_logout(client: tuple[TestClient, FakeSession]) -> None:
    """注册、恢复登录态、退出和重新登录。"""
    http, db = client
    body = {"username": "alice", "password": "secret12", "confirm_password": "secret12"}
    response = http.post("/api/auth/register", json=body)
    assert response.status_code == 201
    assert response.json()["data"] == {"id": 1, "username": "alice"}
    assert "HttpOnly" in response.headers["set-cookie"]
    assert db.users[0].password_hash != body["password"]
    registered_at = db.users[0].last_login_at
    assert registered_at is not None
    assert http.get("/api/auth/me").json()["data"]["id"] == 1
    assert http.post("/api/auth/register", json=body).status_code == 409
    assert http.post("/api/auth/logout").status_code == 200
    assert http.get("/api/auth/me").status_code == 401
    assert (
        http.post(
            "/api/auth/login", json={"username": "alice", "password": "wrong12"}
        ).status_code
        == 401
    )
    assert db.users[0].last_login_at == registered_at
    assert (
        http.post(
            "/api/auth/login", json={"username": "alice", "password": "secret12"}
        ).status_code
        == 200
    )
    assert http.get("/api/auth/me").status_code == 200
    assert db.users[0].last_login_at is not None
    assert db.users[0].last_login_at >= registered_at


def test_invalid_registration_and_cookie(
    client: tuple[TestClient, FakeSession],
) -> None:
    """拒绝不一致密码、超长密码和伪造或过期 Cookie。"""
    http, _ = client
    assert (
        http.post(
            "/api/auth/register",
            json={
                "username": "alice",
                "password": "secret12",
                "confirm_password": "different",
            },
        ).status_code
        == 422
    )
    assert (
        http.post(
            "/api/auth/register",
            json={
                "username": "alice",
                "password": "中" * 25,
                "confirm_password": "中" * 25,
            },
        ).status_code
        == 422
    )
    http.cookies.set("tripweave_session", "1.9999999999.invalid")
    assert http.get("/api/auth/me").status_code == 401
    assert hash_password("secret12") != hash_password("secret12")


def test_middleware_queries_user_from_verified_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实中间件流程使用签名 Cookie 中的 ID 查询用户。"""
    user = User(id=7, username="alice", password_hash="stored")
    queried_ids: list[int] = []

    class SessionContext:
        """模拟中间件使用的异步会话。"""

        async def __aenter__(self):
            """进入会话。"""
            return self

        async def __aexit__(self, *args):
            """退出会话。"""
            return None

        async def get(self, model, user_id):
            """记录数据库查询的用户 ID。"""
            queried_ids.append(user_id)
            return user if user_id == 7 else None

    monkeypatch.setattr(middleware, "signing_key", lambda: b"a" * 32)
    response = Response()
    set_session(response, 7, b"a" * 32)
    cookie = response.headers["set-cookie"].split(";", 1)[0]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/me",
            "headers": [(b"cookie", cookie.encode())],
            "app": app,
        }
    )
    app.state.database_session_factory = lambda: SessionContext()
    assert asyncio.run(middleware.resolve_current_user(request)) is user
    assert queried_ids == [7]
