from pathlib import Path
from typing import Annotated
from uuid import UUID

from app.infra.database import get_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.claim.exceptions import ApplicationFormNotFoundError
from app.modules.claim.schemas import (
    ClaimData,
    ClaimGuideData,
    ClaimListData,
    ClaimStatus,
)
from app.modules.claim.service import ClaimService
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["理赔接口"])
APPLICATION_FORM_PATH = Path(__file__).parent / "assets" / "claim-application-form.pdf"


def get_claim_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClaimService:
    """使用请求级数据库会话创建理赔服务。"""
    return ClaimService(session)


@router.get("/claims", response_model=ClaimListData)
async def list_claims(
    user: CurrentUser,
    service: Annotated[ClaimService, Depends(get_claim_service)],
    policy_id: UUID | None = None,
    status: ClaimStatus | None = None,
) -> ClaimListData:
    """查询当前用户的理赔记录，支持按保单和状态筛选。"""
    return await service.list_claims(user.id, policy_id, status)


@router.get("/claims/{claim_id}", response_model=ClaimData)
async def get_claim(
    claim_id: UUID,
    user: CurrentUser,
    service: Annotated[ClaimService, Depends(get_claim_service)],
) -> ClaimData:
    """查询当前用户指定 UUID 的理赔记录。"""
    return await service.get_claim(claim_id, user.id)


@router.get(
    "/claim-guides/application-form",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
def download_application_form() -> FileResponse:
    """公开下载教学理赔申请表。"""
    if not APPLICATION_FORM_PATH.is_file():
        raise ApplicationFormNotFoundError
    return FileResponse(
        APPLICATION_FORM_PATH,
        media_type="application/pdf",
        filename=APPLICATION_FORM_PATH.name,
    )


@router.get("/claim-guides/{policy_id}", response_model=ClaimGuideData)
async def get_claim_guide(
    policy_id: UUID,
    user: CurrentUser,
    service: Annotated[ClaimService, Depends(get_claim_service)],
) -> ClaimGuideData:
    """查询当前用户保单对应的理赔步骤和材料。"""
    return await service.get_guide(policy_id, user.id)
