"""数据库连接配置测试，不连接真实数据库。"""

import asyncio

import pytest
from fastapi import Request

from backend.config.database import create_database_engine, get_db


def test_database_disabled_without_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """未填写数据库名称时不创建引擎。"""
    monkeypatch.delenv("DB_NAME", raising=False)
    assert create_database_engine() is None


def test_database_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """连接地址正确保留密码中的特殊字符。"""
    monkeypatch.setenv("DB_NAME", "tripweave")
    monkeypatch.setenv("DB_USER", "user")
    monkeypatch.setenv("DB_PASSWORD", "p@ss:/word")
    monkeypatch.setenv("DB_PORT", "3307")
    engine = create_database_engine()
    assert engine is not None
    assert engine.url.password == "p@ss:/word"
    assert engine.url.port == 3307
    assert engine.url.database == "tripweave"


def test_database_rejects_incomplete_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """启用数据库时拒绝缺少凭证或无效端口。"""
    monkeypatch.setenv("DB_NAME", "tripweave")
    monkeypatch.delenv("DB_USER", raising=False)
    with pytest.raises(ValueError, match="DB_USER"):
        create_database_engine()
    monkeypatch.setenv("DB_USER", "user")
    monkeypatch.setenv("DB_PASSWORD", "password")
    monkeypatch.setenv("DB_PORT", "0")
    with pytest.raises(ValueError, match="DB_PORT"):
        create_database_engine()


def test_get_db_commits_and_rolls_back() -> None:
    """统一会话依赖在成功和失败时分别提交与回滚。"""
    actions: list[str] = []

    class Session:
        """记录事务操作的会话替身。"""

        async def __aenter__(self):
            """进入会话。"""
            return self

        async def __aexit__(self, *args):
            """退出会话。"""
            actions.append("close")

        async def commit(self):
            """记录提交。"""
            actions.append("commit")

        async def rollback(self):
            """记录回滚。"""
            actions.append("rollback")

    class App:
        """提供会话工厂的应用替身。"""

        state = type("State", (), {"database_session_factory": Session})()

    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [], "app": App()}
    )

    async def exercise() -> None:
        """分别执行正常请求和抛错请求。"""
        generator = get_db(request)
        await anext(generator)
        with pytest.raises(StopAsyncIteration):
            await anext(generator)
        generator = get_db(request)
        await anext(generator)
        with pytest.raises(ValueError, match="failed"):
            await generator.athrow(ValueError("failed"))

    asyncio.run(exercise())
    assert actions == ["commit", "close", "rollback", "close"]
