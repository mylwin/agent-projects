"""项目内持久化对话与流式回复入口。"""

import asyncio
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import (
    get_chat_settings,
    get_current_user,
    get_generation_limit,
    get_settings,
)
from backend.config.database import get_db
from backend.config.planner import PlannerSettings
from backend.errors import ApiException
from backend.models.user import User
from backend.schemas.api import ApiSuccess
from backend.schemas.conversation import ChatRequest, ConversationTurnData
from backend.services import conversation
from backend.services.generation_stream import GenerationStream

router = APIRouter(prefix="/projects", tags=["conversation"])


@router.get(
    "/{project_id}/messages", response_model=ApiSuccess[list[ConversationTurnData]]
)
async def get_messages(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[int, Path(ge=1)],
) -> ApiSuccess[list[ConversationTurnData]]:
    """读取本人计划最近 50 轮公开对话。"""
    return ApiSuccess(data=await conversation.list_turns(db, user.id, project_id))


@router.post("/{project_id}/messages", response_class=StreamingResponse)
async def send_message(
    body: ChatRequest,
    http: Request,
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[PlannerSettings, Depends(get_chat_settings)],
    limit: Annotated[asyncio.Semaphore, Depends(get_generation_limit)],
    project_id: Annotated[int, Path(ge=1)],
) -> StreamingResponse:
    """先校验项目及上下文，再逐帧返回真实正文、规划进度和持久化终态。"""
    # 如果输入是规划，则使用全局设置
    if body.generate:
        settings = get_settings()
    # 获取数据库连接
    factory = cast(
        async_sessionmaker[AsyncSession] | None,
        getattr(http.app.state, "database_session_factory", None),
    )
    if factory is None:
        raise ApiException.configuration("未配置数据库连接")
    if limit.locked():
        raise ApiException.busy()
    # 获取对话上下文
    context = await conversation.prepare_turn(
        factory, user.id, project_id, body, settings.planner_timeout_seconds
    )
    # 获取流式结果
    stream = GenerationStream(
        settings.model_name,
        (settings.model_api_key, settings.amap_api_key, settings.baidu_api_key),
    )

    async def run() -> ApiSuccess[ConversationTurnData]:
        """把本轮输入与已冻结的依据交给服务执行。"""
        return await conversation.reply(
            factory, user.id, project_id, body, context, settings, limit, stream
        )

    return StreamingResponse(
        stream.iterate(run, "旅行助手已收到消息"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
