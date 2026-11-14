from typing import Annotated
from uuid import UUID

from app.infra.database import get_session
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import ChatThreadCreate, ChatThreadResponse
from .service import ChatThreadService

# 创建路由对象
router = APIRouter(prefix="/api/v1/chat-threads", tags=["chat-threads"])


def get_service(session: Annotated[AsyncSession, Depends(get_session)]):
    """获取 chat thread 服务对象"""
    return ChatThreadService(session)


@router.post("", response_model=ChatThreadResponse)
async def create_chat_thread(
    request: ChatThreadCreate,
    user_id: Annotated[int, Header(alias="x-user-id")],
    service: Annotated[ChatThreadService, Depends(get_service)],
):
    """创建 chat thread"""
    return await service.add(user_id, request.title)


@router.get("", response_model=list[ChatThreadResponse])
async def list_chat_threads(
    user_id: Annotated[int, Header(alias="x-user-id")],
    service: Annotated[ChatThreadService, Depends(get_service)],
) -> list[ChatThreadResponse]:
    """查询 chat thread 列表"""
    results = await service.list_by_user(user_id)
    # 列表为空时返回空列表
    if results is None:
        return []
    # 列表不为空时返回列表
    return [
        ChatThreadResponse.model_validate(chat_thread, from_attributes=True)
        for chat_thread in results
    ]


@router.patch("/{thread_id}", response_model=ChatThreadResponse)
async def rename_chat_thread(
    thread_id: UUID,
    request: ChatThreadCreate,
    user_id: Annotated[int, Header(alias="x-user-id")],
    service: Annotated[ChatThreadService, Depends(get_service)],
) -> ChatThreadResponse:
    """重命名指定 chat thread"""
    chat_thread = await service.rename(thread_id, user_id, request.title)
    return ChatThreadResponse.model_validate(chat_thread, from_attributes=True)


@router.delete(
    "/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_thread(
    thread_id: UUID,
    user_id: Annotated[int, Header(alias="x-user-id")],
    service: Annotated[ChatThreadService, Depends(get_service)],
) -> None:
    """删除指定 chat thread"""
    await service.delete(thread_id, user_id)
