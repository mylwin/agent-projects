import logging
import sys

import structlog


def _log_level(level: str) -> int:
    """将字符串日志级别转换为 logging 常量。"""
    return getattr(logging, level.strip().upper(), logging.INFO)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取 structlog 日志器。"""
    return structlog.get_logger(name)


def setup_logging(log_level: str = "INFO") -> None:
    """初始化 structlog 与标准库 logging 的集成配置。"""
    level = _log_level(log_level)

    # 配置 python 标准日志
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger.addHandler(console_handler)

    # 配置 structlog
    processors = [
        # 合并 request_id、conversation_id 等上下文变量
        structlog.contextvars.merge_contextvars,
        # 添加 Logger 名称
        structlog.stdlib.add_logger_name,
        # 添加日志级别
        structlog.stdlib.add_log_level,
        # 添加时间
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        # 允许添加占位符参数
        structlog.stdlib.PositionalArgumentsFormatter(),
        # 渲染 stack_info=True
        structlog.processors.StackInfoRenderer(),
        # 渲染异常堆栈
        structlog.processors.format_exc_info,
        # 彩色控制台渲染
        structlog.dev.ConsoleRenderer(colors=True),
    ]

    # structlog 配置
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 控制第三方库日志数量
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if level == logging.DEBUG else logging.WARNING
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
