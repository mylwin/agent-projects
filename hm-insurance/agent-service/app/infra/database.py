from collections.abc import AsyncGenerator

from app.core.config import settings
from app.core.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = get_logger(__name__)

# 数据库连接地址
if not settings.db or not settings.db.url:
    raise RuntimeError("db.url 未配置，数据库初始化失败")
DATABASE_URL = settings.db.url

# 创建异步数据库引擎
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=settings.db.echo,  # 是否打印SQL语句
    pool_size=settings.db.pool_size,  # 连接池大小
    max_overflow=settings.db.max_overflow,  # 连接池溢出时，允许创建的连接数
    pool_recycle=settings.db.pool_recycle,  # 连接池中连接的闲置时间，超过这个时间就检查连接是否可用
    pool_pre_ping=True,  # 创建连接时，检查连接是否可用
    connect_args={"server_settings": {"timezone": "Asia/Shanghai"}},
)

# 创建异步 Session工厂
AsyncSessionFactory = async_sessionmaker(
    engine,
    autoflush=False,  # 是否自动刷新对象
    expire_on_commit=False,  # commit 后保留 ORM 对象中的属性
)


# 获取 session 的工具
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """为每个 FastAPI 请求创建独立的 AsyncSession，适用于依赖注入。"""
    async with AsyncSessionFactory() as session:
        yield session


# 释放数据库连接池
async def close_database() -> None:
    """关闭数据库引擎并释放连接池中的连接。应在应用关闭时调用。"""
    await engine.dispose()
    logger.info("数据库连接池已关闭~")


# 数据库健康检查
async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    logger.info("数据库连接池初始化成功~✅")
