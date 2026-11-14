from collections.abc import AsyncGenerator

from app.modules.auth.exceptions import ChatThreadNotFoundError
from app.modules.chat.schemas import ChatRequest
from app.modules.chat_thread.repository import ChatThreadRepository
from fastapi.sse import ServerSentEvent
from langchain.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession


class ChatService:
    """聊天服务"""

    def __init__(self, session: AsyncSession, agent: CompiledStateGraph):
        self.repository = ChatThreadRepository(session)
        self.agent = agent

    async def chat_stream(
        self, user_id: int, request: ChatRequest
    ) -> AsyncGenerator[ServerSentEvent, None]:
        """流式聊天"""
        # 1.校验当前会话是否属于当前用户
        thread = await self.repository.find_owned(request.thread_id, user_id)
        # 如果找不到会话或者会话不属于当前用户，则返回错误
        if not thread:
            raise ChatThreadNotFoundError

        # 2.准备 Agent 输入
        # 消息输入
        _input = {"messages": [HumanMessage(content=request.message)]}
        # 会话 ID
        config: RunnableConfig = {"configurable": {"thread_id": str(request.thread_id)}}

        # 3.使用 v3 协议获取异步事件流
        stream = await self.agent.astream_events(
            _input,
            config,
            version="v3",
        )

        # 4.只读取消息中的文本增量
        async for message in stream.messages:
            async for text in message.text:
                yield ServerSentEvent(data=text, event="message")

        # 5.返回结束事件
        yield ServerSentEvent(data="[DONE]", event="done")
