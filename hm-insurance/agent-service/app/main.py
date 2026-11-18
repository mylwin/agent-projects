import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]

# 支持直接运行 app/main.py，包括从项目外部目录启动。
if __package__ in (None, "") and str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import uvicorn
from app.agents.orchestrator import init_insurance_orchestrator
from app.core.config import settings
from app.core.exception_handlers import build_validation_error_response
from app.core.exceptions import ApplicationError
from app.core.logging import get_logger, setup_logging
from app.infra.checkpointer import close_checkpointer, init_checkpointer
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.chat_thread.router import router as chat_thread_router
from app.modules.product.router import router as product_router
from fastapi import FastAPI, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 初始化日志系统
setup_logging(settings.logging.level)
logger = get_logger(__name__)


# 生命周期
@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务启动时执行"""
    logger.info(f"【{settings.app.name}] 服务启动中...")
    from app.infra.database import check_database, close_database
    from app.rag import close_rag

    try:
        # 1.检查业务数据库连接
        await check_database()
        # 2.初始化数据检查点
        checkpointer = await init_checkpointer()
        # 3.初始化保险顾问 Agent(graph)
        # app.state.agent = init_insurance_agent(checkpointer)
        app.state.agent = init_insurance_orchestrator(checkpointer)
        yield
    finally:
        logger.info(f"【{settings.app.name}] 服务关闭中...")
        # 4.关键Rag资源
        close_rag()
        # 5.关闭数据检查点
        await close_checkpointer()
        # 6.关闭数据库连接
        await close_database()


# 创建 app
app = FastAPI(
    title=settings.app.name,
    debug=settings.app.debug,
    lifespan=lifespan,
)

# 绑定路由
app.include_router(router=auth_router)
app.include_router(router=product_router)
app.include_router(router=chat_thread_router)
app.include_router(router=chat_router)


# 统一处理异常信息
@app.exception_handler(RequestValidationError)
def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return build_validation_error_response(exc)


@app.exception_handler(ApplicationError)
def handle_exception(request: Request, exc: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
        },
    )


@app.get("/health", summary="服务健康检查接口")
async def check_health() -> dict[str, str]:
    """服务健康检查接口"""
    logger.info("服务健康检查接口")
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=True,
        app_dir=str(SERVICE_ROOT),
        reload_dirs=[str(SERVICE_ROOT / "app")],
    )
