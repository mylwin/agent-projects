"""FastAPI 应用装配：生命周期与路由注册。"""

import asyncio
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

if __package__ in {None, ""}:
    # 直接执行本文件时补充项目根目录，保证 backend 包可导入。
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.api.exception_handlers import register_exception_handlers  # noqa: E402
from backend.api.routes import health, plans  # noqa: E402
from backend.config.env import load_env  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    为当前应用实例创建生成并发限制。

    :param app: 当前 FastAPI 应用。
    :return: 生命周期上下文。
    """
    load_env()
    app.state.generation_limit = asyncio.Semaphore(2)
    yield


app = FastAPI(title="TripWeave API", version="0.1.0", lifespan=lifespan)
app.include_router(health.router, prefix="/api")
app.include_router(plans.router, prefix="/api")
register_exception_handlers(app)


if __name__ == "__main__":
    import uvicorn

    root = Path(__file__).resolve().parents[2]
    uvicorn.run(
        "backend.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(root / "backend")],
        app_dir=str(root),
        log_level="info",
    )
