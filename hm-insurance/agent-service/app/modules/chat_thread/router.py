from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database import get_session
from app.modules.auth.dependencies import CurrentUser

from .schemas import ChatHistoryResponse, ChatThreadCreate, ChatThreadResponse
from .service import ChatThreadService

# 创建路由对象
router = APIRouter(prefix="/api/v1/chat-threads", tags=["会话管理接口"])


def get_service(
    session: Annotated[AsyncSession, Depends(get_session)], request: Request
):
    """获取 chat thread 服务对象"""
    return ChatThreadService(session, request.app.state.agent)


@router.post("", response_model=ChatThreadResponse)
async def create_chat_thread(
    request: ChatThreadCreate,
    user: CurrentUser,
    service: Annotated[ChatThreadService, Depends(get_service)],
):
    """创建 chat thread"""
    return await service.add(user.id, request.title)


@router.get("", response_model=list[ChatThreadResponse])
async def list_chat_threads(
    user: CurrentUser,
    service: Annotated[ChatThreadService, Depends(get_service)],
) -> list[ChatThreadResponse]:
    """查询 chat thread 列表"""
    results = await service.list_by_user(user.id)
    return [
        ChatThreadResponse.model_validate(chat_thread, from_attributes=True)
        for chat_thread in results
    ]


@router.patch("/{thread_id}", response_model=ChatThreadResponse)
async def rename_chat_thread(
    thread_id: UUID,
    request: ChatThreadCreate,
    user: CurrentUser,
    service: Annotated[ChatThreadService, Depends(get_service)],
) -> ChatThreadResponse:
    """重命名指定 chat thread"""
    chat_thread = await service.rename(thread_id, user.id, request.title)
    return ChatThreadResponse.model_validate(chat_thread, from_attributes=True)


@router.delete(
    "/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_thread(
    thread_id: UUID,
    user: CurrentUser,
    service: Annotated[ChatThreadService, Depends(get_service)],
) -> None:
    """删除指定 chat thread"""
    await service.delete(thread_id, user.id)


@router.get("/{thread_id}/messages", response_model=ChatHistoryResponse)
async def get_chat_history(
    thread_id: UUID,
    user: CurrentUser,
    service: Annotated[ChatThreadService, Depends(get_service)],
) -> ChatHistoryResponse:
    """获取指定 chat thread 的聊天记录"""
    return await service.get_history(thread_id, user.id)
