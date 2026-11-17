from dataclasses import dataclass
from typing import Annotated, Any, Literal

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class InsuranceAgentContext:
    """保险顾问Agent运行时上下文"""

    user_id: int


# 路由意图识别常量
Intent = Literal[
    "chitchat",  # 闲聊
    "recommendation_plan",  # 保险方案推荐
    "claim",  # 保险理赔
    "human_handoff",  # 人工转接
    "fallback",  # 意图识别失败兜底
]

AdditionalInfo = dict[str, Any]


def merge_additional_info(
    previous: dict[str, AdditionalInfo], current: dict[str, AdditionalInfo]
) -> dict[str, AdditionalInfo]:
    """按照AI消息的id合并会话中的引用消息"""
    return {
        **previous,
        **current,
    }


class RouteResult(BaseModel):
    """意图识别结果"""

    intent: Intent = Field(description="意图,本轮消息应该进入的工作流")
    reason: str = Field(description="选择该路由的理由")


class InsuranceAgentState(MessagesState):
    """保险顾问主Graph状态"""

    previous_workflow: Intent
    active_workflow: Intent
    # TODO(citation-flow): 增加可持久化的来源注册表与待确认方案快照；additional_info
    # 仅保存每条回答实际使用的来源/产品，父子图和 interrupt/resume 共享明确的状态契约。
    additional_info: Annotated[dict[str, AdditionalInfo], merge_additional_info]
