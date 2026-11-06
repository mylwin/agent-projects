"""用户表的数据库读写。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


async def create_user(session: AsyncSession, username: str, password_hash: str) -> User:
    """
    插入用户并刷新主键，事务由 get_db 统一提交。

    :param session: 数据库会话。
    :param username: 用户名。
    :param password_hash: 密码哈希。
    :return: 新用户。
    """
    user = User(
        username=username,
        password_hash=password_hash,
        last_login_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(user)
    await session.flush()
    return user


async def record_login(session: AsyncSession, user: User) -> None:
    """
    更新最近登录时间；MySQL DATETIME(6) 按 UTC 保存。

    :param session: 数据库会话。
    :param user: 已通过密码校验的用户。
    """
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    await session.flush()


async def find_user_by_username(session: AsyncSession, username: str) -> User | None:
    """
    按用户名查找用户，使用数据库排序规则处理大小写。

    :param session: 数据库会话。
    :param username: 用户名。
    :return: 用户对象，不存在则返回 None。
    """
    return await session.scalar(select(User).where(User.username == username))


async def find_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """
    按主键读取用户。

    :param session: 数据库会话。
    :param user_id: 用户 ID。
    :return: 用户对象，不存在则返回 None。
    """
    return await session.get(User, user_id)
