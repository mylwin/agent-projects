from typing import Annotated

from app.infra.database import get_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.chat.schemas import ChatRequest
from app.modules.chat.service import ChatService
from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

# 创建路由对象
router = APIRouter(prefix="/api/v1/chat", tags=["与 AI 对话接口"])


def get_chat_service(
    session: Annotated[AsyncSession, Depends(get_session)], request: Request
) -> ChatService:
    """
    获取 ChatService 对象
    """
    agent = request.app.state.agent
    return ChatService(session, agent)


@router.post("", response_class=EventSourceResponse)
async def chat(
    request: ChatRequest,
    user: CurrentUser,
    service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    与 AI 对话接口，采用 SSE 输出
    """
    # Generator, 用yield不断生成内容，形成动态列表
    async for sse in service.chat_stream(user.id, request):
        yield sse
