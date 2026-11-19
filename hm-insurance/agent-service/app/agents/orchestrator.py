from typing import cast

from app.agents.chitchat import init_chitchat_agent
from app.agents.insurance_advisor import init_insurance_advisor
from app.agents.intent_router import intent_router
from app.agents.schemas import InsuranceAgentState, Intent
from langchain.messages import AIMessage, AnyMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command


# 1.定义节点
async def route_node(state: InsuranceAgentState) -> Command[Intent]:
    """意图识别节点"""
    # 1.1.获取上一轮会话的工作流
    previous_workflow = state.get("active_workflow")
    # 1.2.获取上轮AI消息
    previous_ai_message = find_previous_ai_message(state["messages"])
    # 1.3拼接上下文
    context = (
        f"上一轮对话工作流:{previous_workflow}\n上轮AI消息:{previous_ai_message}\n"
    )
    # 1.4意图识别
    user_message = state["messages"][-1].content
    if isinstance(user_message, list):
        user_message = "".join(
            part if isinstance(part, str) else str(part.get("text", ""))
            for part in user_message
        )
    intent_result = await intent_router.route(user_message, context)

    # 1.4.1.如果是str,说明是寒暄,直接固定回复
    if isinstance(intent_result, str):
        return Command[Intent](
            update={
                "messages": [AIMessage(content=intent_result)],
                "active_workflow": "chitchat",
                "previous_workflow": previous_workflow,
            },
            goto=cast(Intent, END),
        )

    # 4.2.记录上一轮工作流和本轮工作流
    intent = intent_result.intent if intent_result is not None else "fallback"
    return Command(
        update={
            "active_workflow": intent,
            "previous_workflow": previous_workflow,
        },
        goto=intent,
    )


def find_previous_ai_message(messages: list[AnyMessage]) -> str | None:
    """查找本轮用户之前最近一条可以展示的AI回复"""
    for message in reversed(messages[:-1]):
        # 跳过非AI消息
        if not isinstance(message, AIMessage):
            continue
        # 跳过tool消息
        if message.tool_calls:
            continue
        # 返回AI消息
        if message.text:
            return message.text

    return None


# 1.3.闲聊节点
async def chitchat_node(state: InsuranceAgentState) -> dict:
    return {"messages": [AIMessage("你好，今天想聊点什么？")]}


# 1.4.保险推荐节点
async def recommendation_node(state: InsuranceAgentState) -> dict:
    return {"messages": [AIMessage("保险推荐工作流暂未接入。")]}


# 1.5.理赔节点
async def claim_node(state: InsuranceAgentState) -> dict:
    return {"messages": [AIMessage("理赔工作流暂未接入。")]}


# 1.6.人工节点
def human_handoff_node(state: InsuranceAgentState) -> dict:
    return {"messages": [AIMessage("已记录转人工请求，后续可接入人工客服系统。")]}


# 1.7.fallback节点
def fallback_node(state: InsuranceAgentState) -> dict:
    return {
        "messages": [
            AIMessage(
                "我还不能确定你的需求，请说明是想咨询保险、推荐方案还是办理理赔。"
            )
        ]
    }


# 2.主Graph
def init_insurance_orchestrator(checkpointer: AsyncPostgresSaver):
    """初始化保险顾问主Graph"""

    builder = StateGraph(
        InsuranceAgentState,
    )
    builder.add_node("route", route_node)
    builder.add_node("chitchat", init_chitchat_agent())
    builder.add_node("recommendation_plan", init_insurance_advisor())
    builder.add_node("claim", claim_node)
    builder.add_node("human_handoff", human_handoff_node)
    builder.add_node("fallback", fallback_node)

    builder.add_edge(START, "route")
    builder.add_edge("chitchat", END)
    builder.add_edge("recommendation_plan", END)
    builder.add_edge("claim", END)
    builder.add_edge("human_handoff", END)
    builder.add_edge("fallback", END)

    return builder.compile(checkpointer=checkpointer)
