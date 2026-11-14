from uuid import UUID

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ChatThread


class ChatThreadRepository:
    """聊天会话数据库相关操作"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, chat_thread: ChatThread):
        """ "添加聊天会话"""
        self.session.add(chat_thread)

    async def list_by_user(self, user_id: int) -> list[ChatThread] | None:
        """获取用户所有聊天会话"""
        result = await self.session.scalars(
            Select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc(), ChatThread.created_at.desc())
        )
        return list(result.all())

    async def find_owned(self, thread_id: UUID, user_id: int) -> ChatThread | None:
        """根据用户 id 和和聊天会话 id 返回指定的聊天会话"""
        return await self.session.scalar(
            Select(ChatThread).where(
                ChatThread.id == thread_id, ChatThread.user_id == user_id
            )
        )

    async def delete(self, thread: ChatThread) -> None:
        """删除指定的聊天会话"""
        await self.session.delete(thread)
