from uuid import UUID

from app.infra.exceptions import CheckpointerNotConfiguredError
from app.modules.chat_thread.exceptions import ChatThreadNotFoundError
from app.modules.chat_thread.schemas import ChatHistoryResponse, ChatMessageResponse
from langchain.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ChatThread
from .repository import ChatThreadRepository


class ChatThreadService:
    """聊天会话服务"""

    def __init__(self, session: AsyncSession, agent: CompiledStateGraph):
        self.session = session
        self.repository = ChatThreadRepository(session)
        self.agent = agent

    async def add(self, user_id: int, title: str):
        """创建聊天会话"""
        # 用上下文管理，开启事务，运行完成，自动commit，出现异常，自动rollback
        async with self.session.begin():
            # 创建对象，对象 映射 到数据库 一条数据
            chat_thread = ChatThread(user_id=user_id, title=title)
            # 新增对象，就是插入一条数据
            await self.repository.add(chat_thread)

            return chat_thread

    async def list_by_user(self, user_id: int) -> list[ChatThread]:
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

            # 2.删除 checkpointer 数据
            checkpointer = self.agent.checkpointer
            if not isinstance(checkpointer, BaseCheckpointSaver):
                raise CheckpointerNotConfiguredError
            await checkpointer.adelete_thread(str(thread_id))

            # 3.删除会话元数据
            await self.repository.delete(chat_thread)

    async def get_history(self, thread_id: UUID, user_id: int) -> ChatHistoryResponse:
        """获取 chat thread 历史"""
        # 1.先判断当前会话是否属于当前用户
        chat_thread = await self.repository.find_owned(thread_id, user_id)
        if chat_thread is None:
            raise ChatThreadNotFoundError

        # 2.获取 agent 的最新状态
        config: RunnableConfig = {"configurable": {"thread_id": str(thread_id)}}
        snapshot = await self.agent.aget_state(config)
        additional_info = snapshot.values.get("additional_info", {})

        # 3.只返回用户和 AI 消息
        messages = []
        for message in snapshot.values.get("messages", []):
            if isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            else:
                continue

            # 将每轮新增的文本片段添加到消息
            if message.text:
                messages.append(
                    ChatMessageResponse(
                        role=role,
                        content=message.text,
                        additional_info=(
                            additional_info.get(message.id)
                            if isinstance(message, AIMessage) and message.id
                            else None
                        ),
                    )
                )
        # 4.处理interrupt
        interrupts = None
        if hasattr(snapshot, "interrupts") and snapshot.interrupts:
            interrupts = snapshot.interrupts
        elif hasattr(snapshot, "tasks") and snapshot.tasks:
            for task in snapshot.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupts = task.interrupts
                    break
        # 返回结果
        return ChatHistoryResponse(
            thread_id=thread_id,
            messages=messages,
            interrupt=interrupts[0].value if interrupts else None,
        )
