"""MySQL 异步连接配置。"""

import os
from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.errors.api import ApiException


def create_database_engine() -> AsyncEngine | None:
    """
    根据环境变量创建延迟连接的数据库引擎。

    未设置 DB_NAME 时不启用数据库；启用时必须提供用户名和密码。
    :return: 异步引擎，未启用时为 None。
    :raises ValueError: 数据库配置不完整或端口无效时抛出。
    """
    name = os.getenv("DB_NAME", "").strip()
    if not name:
        return None
    user = os.getenv("DB_USER", "").strip()
    password = os.getenv("DB_PASSWORD", "")
    if not user or not password:
        raise ValueError("设置 DB_NAME 后必须填写 DB_USER 和 DB_PASSWORD")
    try:
        port = int(os.getenv("DB_PORT", "3306"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("DB_PORT 必须是 1 到 65535 之间的整数") from None
    url = URL.create(
        "mysql+aiomysql",
        username=user,
        password=password,
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=port,
        database=name,
        query={"charset": "utf8mb4"},
    )
    return create_async_engine(
        url, pool_pre_ping=True, connect_args={"connect_timeout": 10}
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    为应用创建统一的异步会话工厂。

    :param engine: 应用生命周期内的数据库引擎。
    :return: 每次调用都创建独立会话的工厂。
    """
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    """
    提供请求级会话，成功时提交，失败时回滚。

    :param request: 当前 HTTP 请求。
    :return: 当前请求的异步数据库会话。
    :raises ApiException: 数据库未配置时抛出。
    """
    factory = getattr(request.app.state, "database_session_factory", None)
    if factory is None:
        raise ApiException.configuration("未配置数据库连接")
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
