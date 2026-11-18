from typing import NotRequired

from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, SystemMessage
from langgraph.graph import StateGraph

from app.agents.schemas import InsuranceAgentState
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_MESSAGE = """
你是保险智能客服，负责处理与保险业务无关的普通聊天。

要求：
1. 回复友好、自然，最多两句话(50字以内)。
2. 不假装有个人经历、情感、实时信息或外部能力。
3. 不回答医疗、法律、投资等高风险专业建议。
4. 每次回复都自然引导用户回到保险产品、投保或理赔业务。
5. 超出能力范围时，如实说明无法提供。
""".strip()

# 最大闲聊的回复次数
MAX_CHITCHAT_COUNT = 3


class ChitchatState(InsuranceAgentState):
    """闲聊子agent的状态"""

    chitchat_count: NotRequired[int]


class ChitchatAgent:
    """闲聊子agent"""

    def __init__(self) -> None:
        self.model = init_chat_model(
            model=settings.llm.chat_model,
            model_provider="deepseek",
            api_key=settings.llm.api_key,
            extra_body={"thinking": {"type": "disabled"}},
        )

    async def handle_chitchat(self, state: ChitchatState) -> dict:
        count = state.get("chitchat_count", 0)

        # 上一轮不是闲聊,重新计数
        if state.get("previous_workflow") != "chitchat":
            count = 0

        logger.info("处理闲聊消息", chitchat_count=count)

        # 如果闲聊次数超过最大次数,则固定回复消息
        if count >= MAX_CHITCHAT_COUNT:
            return {
                "messages": [
                    AIMessage(
                        "我主要协助处理保险产品、投保和理赔咨询，请告诉我想办理或了解的事项。我会尽力帮您解决问题😄"
                    )
                ]
            }

        # 进行闲聊
        response = await self.model.ainvoke(
            [SystemMessage(content=SYSTEM_MESSAGE), *state["messages"]]
        )

        # 返回结果
        return {"messages": [response], "chitchat_count": count + 1}

    def build(self):
        """构建闲聊子agent"""
        builder = StateGraph(ChitchatState)
        builder.add_node("handle_chitchat", self.handle_chitchat)
        builder.set_entry_point("handle_chitchat")
        builder.set_finish_point("handle_chitchat")

        # 使用父Graph提供的Checkpointer，保存子图私有状态
        return builder.compile(checkpointer=True)


def init_chitchat_agent():
    """初始化闲聊子agent"""
    logger.info("闲聊子 Agent 初始化完成~✅️")
    return ChitchatAgent().build()
