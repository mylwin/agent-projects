"""结构化 Agent 循环的返回值。"""

from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class AgentRunResult:
    """
    一次结构化 Agent 循环的结果。

    Attributes:
        response: 已校验的结构化结果。
        reasoning: 本轮累计的思考链文本，供应商不支持时为空。
        message: 本轮累计的面向用户回复，模型没有正文时为空。
        call_index: 最后一次模型调用的序号，供程序兜底消息关联。
    """

    response: BaseModel
    reasoning: str
    message: str
    call_index: int
