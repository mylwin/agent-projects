"""规划失败的业务异常与终端诊断脱敏。"""

import re
from collections.abc import Sequence


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """
    隐藏已知凭据、完整 URL 和常见认证字段，保留可定位问题的错误说明。

    :param text: 待输出的诊断文本。
    :param secrets: 需要额外隐藏的已知凭据，空值忽略。
    :return: 隐藏已知凭据、URL 和常见认证字段后的文本。
    """
    # 遍历需要额外隐藏的凭据
    for secret in secrets:
        # 如果凭据非空，将凭据替换为 [已隐藏]
        if secret:
            text = text.replace(secret, "[已隐藏]")
    # 隐藏 URL 和常见认证字段
    text = re.sub(r"https?://[^\s\"'<>]+", "[已隐藏地址]", text)
    text = re.sub(r"(?i)bearer\s+[^\s,;\"\']+", "Bearer [已隐藏]", text)
    text = re.sub(
        r"(?i)([\"\']?(?:api[_-]?key|authorization|\bak)[\"\']?\s*[=:]\s*[\"\']?)[^\s,;\"\']+",
        r"\1[已隐藏]",
        text,
    )
    return text


class PlanningError(RuntimeError):
    """
    保留失败阶段和底层异常类型，让 CLI 无需打印原始堆栈也能定位问题。

    Attributes:
        stage: 原始失败阶段，重复包装时保持不变。
        original: 展开异常组或业务包装后的底层异常。
    """

    def __init__(
        self, stage: str, error: BaseException, secrets: Sequence[str] = ()
    ) -> None:
        """
        展开 MCP 的异常组；再次包装时保留业务阶段并补充已知凭据脱敏。

        :param stage: 当前失败阶段；包装已有 PlanningError 时沿用原阶段。
        :param error: 底层异常或异常组；异常组逐层取第一个异常。
        :param secrets: 构造诊断消息时需要隐藏的已知凭据。
        """
        # 如果底层异常为异常组，则展开异常组并取第一个异常
        while isinstance(error, BaseExceptionGroup):
            error = error.exceptions[0]
        # 如果当前异常为 PlanningError，则保留业务阶段并展开异常组
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
