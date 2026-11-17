from app.core.exceptions import ApplicationError


class CheckpointerNotConfiguredError(ApplicationError):
    """Agent 未配置有效的检查点存储"""

    status_code = 500
    code = "CHECKPOINTER_NOT_CONFIGURED"
    message = "Agent 未配置有效的检查点存储"
