"""Agent 执行过程中的错误类型。"""


class AgentBudgetError(RuntimeError):
    """模型循环用尽步数或调用次数，仍没有提交结构化结果。"""
