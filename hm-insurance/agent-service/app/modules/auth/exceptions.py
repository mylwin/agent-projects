from app.core.exceptions import ApplicationError


class ChatThreadNotFoundError(ApplicationError):
    """会话不存在或不属于当前用户"""

    status_code = 400
    code = "CHAT_THREAD_NOT_FOUND"
    message = "会话不存在或不属于当前用户"


class CheckpointerNotConfiguredError(ApplicationError):
    """Agent 未配置有效的检查点存储"""

    status_code = 500
    code = "CHECKPOINTER_NOT_CONFIGURED"
    message = "Agent 未配置有效的检查点存储"
