"""规划失败的业务异常与终端诊断脱敏。"""

import re
from collections.abc import Sequence


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """隐藏已知凭据、完整 URL 和常见认证字段，保留可定位问题的错误说明。"""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[已隐藏]")
    text = re.sub(r"https?://[^\s\"'<>]+", "[已隐藏地址]", text)
    text = re.sub(r"(?i)bearer\s+[^\s,;\"\']+", "Bearer [已隐藏]", text)
    text = re.sub(
        r"(?i)([\"\']?(?:api[_-]?key|authorization|\bak)[\"\']?\s*[=:]\s*[\"\']?)[^\s,;\"\']+",
        r"\1[已隐藏]",
        text,
    )
    return text


class PlanningError(RuntimeError):
    """保留失败阶段和底层异常类型，让 CLI 无需打印原始堆栈也能定位问题。"""

    def __init__(
        self, stage: str, error: BaseException, secrets: Sequence[str] = ()
    ) -> None:
        """展开 MCP 的异常组；再次包装时保留业务阶段并补充已知凭据脱敏。"""
        while isinstance(error, BaseExceptionGroup):
            error = error.exceptions[0]
        if isinstance(error, PlanningError):
            stage, error = error.stage, error.original
        self.stage = stage
        self.original = error
        name = type(error).__name__
        hints = {
            "ModelCallLimitExceededError": "模型调用达到单 Agent 的 6 次上限。",
            "ToolCallLimitExceededError": "工具调用达到单 Agent 的 8 次上限。",
            "GraphRecursionError": "Agent 达到运行步数上限。",
        }
        detail = hints.get(name, str(error).strip() or "服务未提供错误详情")
        super().__init__(f"{stage}失败 [{name}]：{redact(detail, secrets)}")
