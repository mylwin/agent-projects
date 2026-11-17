from collections.abc import AsyncGenerator

from app.agents.evidence import collect_sources, merge_info, referenced_sources
from app.agents.schemas import AdditionalInfo, InsuranceAgentContext
from app.modules.chat.schemas import ChatRequest
from app.modules.chat_thread.exceptions import ChatThreadNotFoundError
from app.modules.chat_thread.repository import ChatThreadRepository
from fastapi.sse import ServerSentEvent
from langchain.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.stream import CustomTransformer
from langgraph.types import Command
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
        # 如果decision不为空，则使用resume参数
        if request.decision:
            _input = Command(resume=request.decision)
        # 如果decision为空，则使用message参数
        else:
            _input = {"messages": [HumanMessage(content=request.message)]}
        # 会话 ID
        config: RunnableConfig = {"configurable": {"thread_id": str(request.thread_id)}}
        context = InsuranceAgentContext(user_id=user_id)

        # 3.读取历史来源，供本轮复用
        # 取该thread的最新状态快照
        previous_state = await self.agent.aget_state(config)
        # 获取历史信息来源
        history_info = previous_state.values.get("additional_info", {})
        # 历史查询过并且保存的来源列表
        sources = collect_sources(history_info)
        # 历史消息的id列表,为了区分那些消息是当前轮新增的
        previous_ids = {
            message.id for message in previous_state.values.get("messages", [])
        }

        # 4.使用 v3 协议获取异步事件流
        stream = await self.agent.astream_events(
            _input,
            config,
            context=context,
            version="v3",
            transformers=[CustomTransformer],
        )

        final_message_id: str | None = None
        additional_info: AdditionalInfo = {}

        async for event in stream:
            method = event["method"]
            # 判断事件类型，可以是messages、interrupts等等
            if method == "messages":
                data = event["params"]["data"][0]
                if isinstance(data, AIMessage):
                    final_message_id = data.id
                    yield ServerSentEvent(data=data.text, event="message")
                elif (
                    isinstance(data, dict)
                    and data.get("delta")
                    and data["delta"].get("text")
                ):
                    yield ServerSentEvent(
                        data=data["delta"].get("text"), event="message"
                    )
                elif (
                    isinstance(data, dict)
                    and data.get("event") == "message-start"
                    and data.get("id")
                ):
                    # 第一个消息片段会传递message的id
                    final_message_id = data.get("id")
            if method == "custom":
                data = event["params"]["data"]
                if isinstance(data, dict) and data.get("type") == "additional_info":
                    # 同一轮可能查询多个产品、多个条款，需要合并而不是覆盖
                    # 本次工具调用的信息
                    info = merge_info({}, data.get("data", {}))
                    # 本轮所有的工具调用累计信息
                    additional_info = merge_info(additional_info, info)
                    yield ServerSentEvent(data=info, event="additional_info")

        # 5.按实际回答绑定来源，同时保留本轮检索结果供后续复用
        snapshot = await self.agent.aget_state(config)
        # 本轮的AI回答消息
        ai_messages = [
            message
            for message in snapshot.values.get("messages", [])
            if isinstance(message, AIMessage) and message.id not in previous_ids
        ]
        answers = [message for message in ai_messages if message.text]

        # 把本轮的来源加入到历史来源中
        sources.update(additional_info.get("sources", {}))
        # 逐条匹配正文
        message_info = {}
        for answer in answers:
            used_sources = referenced_sources(answer.text, sources)
            if used_sources and answer.id:
                message_info[answer.id] = {"sources": used_sources}

        target_id = (
            answers[-1].id
            if answers
            else ai_messages[-1].id
            if ai_messages
            else final_message_id
        )
        if target_id:
            info = merge_info(message_info.get(target_id, {}), additional_info)
            if info:
                message_info[target_id] = info

        if message_info:
            await self.agent.aupdate_state(config, {"additional_info": message_info})
            # 保存恢复时即使没有重新检索，也补发正文用到的历史来源
            for info in message_info.values():
                yield ServerSentEvent(data=info, event="additional_info")

        # 6.返回保存确认信息
        interrupts = await stream.interrupts()
        for item in interrupts:
            yield ServerSentEvent(data=item.value, event="interrupt")

        yield ServerSentEvent(data="[DONE]", event="done")
