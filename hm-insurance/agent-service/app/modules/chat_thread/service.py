from uuid import UUID

from app.modules.auth.exceptions import ChatThreadNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ChatThread
from .repository import ChatThreadRepository


class ChatThreadService:
    """聊天会话服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = ChatThreadRepository(session)

    async def add(self, user_id: int, title: str):
        """创建聊天会话"""
        # 用上下文管理，开启事务，运行完成，自动commit，出现异常，自动rollback
        async with self.session.begin():
            # 创建对象，对象 映射 到数据库 一条数据
            chat_thread = ChatThread(user_id=user_id, title=title)
            # 新增对象，就是插入一条数据
            await self.repository.add(chat_thread)

            return chat_thread

    async def list_by_user(self, user_id: int) -> list[ChatThread] | None:
        """列出用户所有会话"""
        return await self.repository.list_by_user(user_id)

    async def rename(
        self, thread_id: UUID, user_id: int, title: str
    ) -> ChatThread | None:
        """重命名 chat thread"""
        async with self.session.begin():
            # 1.先判断当前会话是否属于当前用户
            chat_thread = await self.repository.find_owned(thread_id, user_id)
            # 如果不属于当前用户，则抛出异常
            if chat_thread is None:
                raise ChatThreadNotFoundError

            # 2.查询后修改字段，触发数据库更新
            chat_thread.title = title

            # 3.刷新数据
            await self.session.flush()
            await self.session.refresh(chat_thread)

            # 4.返回修改后的数据
            return chat_thread

    async def delete(self, thread_id: UUID, user_id: int) -> None:
        """删除 chat thread"""
        async with self.session.begin():
            # 1.先判断当前会话是否属于当前用户
            chat_thread = await self.repository.find_owned(thread_id, user_id)
            # 如果不属于当前用户，则抛出异常
            if chat_thread is None:
                raise ChatThreadNotFoundError
            # 2.删除数据
            await self.repository.delete(chat_thread)
