from collections.abc import AsyncGenerator

from app.agents.schemas import InsuranceAgentContext
from app.modules.auth.exceptions import ChatThreadNotFoundError
from app.modules.chat.schemas import ChatRequest
from app.modules.chat_thread.repository import ChatThreadRepository
from fastapi.sse import ServerSentEvent
from langchain.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.stream import CustomTransformer
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
        context = InsuranceAgentContext(user_id=user_id)

        # 3.使用 v3 协议获取异步事件流
        stream = await self.agent.astream_events(
            _input,
            config,
            context=context,
            version="v3",
            transformers=[CustomTransformer],
        )

        # # 4.只读取消息中的文本增量
        # async def stream_text():
        #     async for message in stream.messages:
        #         async for text in message.text:
        #             yield ServerSentEvent(data=text, event="message")

        # # 5.判断是否有custom事件
        # async def stream_custom():
        #     async for event in stream.extensions["custom"]:
        #         if event.get("type") == "additional_info":
        #             yield ServerSentEvent(
        #                 data=event.get("data"), event="additional_info"
        #             )

        # # 6.合并message和custom事件
        # merged = astream.merge(stream_text(), stream_custom())
        # async with merged.stream() as streamer:
        #     async for event in streamer:
        #         yield event

        # 4.解析父子Graph的消息
        async for event in stream:
            method = event["method"]
            # 判断事件类型，可以是messages、interrupts等等
            if method == "messages":
                data = event["params"]["data"][0]
                if isinstance(data, AIMessage):
                    yield ServerSentEvent(data=data.text, event="message")
                elif data.get("delta") and data["delta"].get("text"):
                    yield ServerSentEvent(
                        data=data["delta"].get("text"), event="message"
                    )

        # 7.返回结束事件
        yield ServerSentEvent(data="[DONE]", event="done")
