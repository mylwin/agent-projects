import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager

SERVICE_ROOT = Path(__file__).resolve().parents[1]

# 支持直接运行 app/main.py，包括从项目外部目录启动。
if __package__ in (None, "") and str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.core.config import settings
from app.core.logging import get_logger, setup_logging

# 初始化日志系统
setup_logging(settings.logging.level)
logger = get_logger(__name__)


# 生命周期
@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务启动时执行"""
    logger.info(f"【{settings.app.name}] 服务启动中...")
    from app.infra.database import check_database, close_database

    try:
        await check_database()
        yield
    finally:
        logger.info(f"【{settings.app.name}] 服务关闭中...")
        await close_database()


# 创建 app
app = FastAPI(
    title=settings.app.name,
    debug=settings.app.debug,
    lifespan=lifespan,
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
