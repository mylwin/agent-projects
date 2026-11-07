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

from backend.api.exception_handlers import register_exception_handlers
from backend.api.middleware import register_auth_middleware
from backend.api.routes import auth, conversation, health, plans, projects
from backend.config.database import (
    create_database_engine,
    create_session_factory,
)
from backend.config.env import load_env


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    为当前应用实例创建生成并发限制。

    :param app: 当前 FastAPI 应用。
    :return: 生命周期上下文。
    """
    load_env()
    app.state.generation_limit = asyncio.Semaphore(2)
    app.state.database_engine = create_database_engine()
    app.state.database_session_factory = (
        create_session_factory(app.state.database_engine)
        if app.state.database_engine is not None
        else None
    )
    try:
        yield
    finally:
        if app.state.database_engine is not None:
            await app.state.database_engine.dispose()


app = FastAPI(title="TripWeave API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(plans.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(conversation.router, prefix="/api")
register_exception_handlers(app)
register_auth_middleware(app)


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
