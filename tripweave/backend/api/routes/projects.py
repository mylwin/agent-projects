"""当前用户的旅行项目与版本接口。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_user
from backend.config.database import get_db
from backend.crud import projects as projects_crud
from backend.errors.api import ApiException
from backend.models.user import User
from backend.schemas.api import ApiError, ApiFailure, ApiSuccess
from backend.schemas.projects import (
    ProjectDetail,
    ProjectsListData,
    ProjectSummary,
    RevisionDetail,
    RunTrace,
    SaveRevisionRequest,
    SetFinalRevisionRequest,
)
from backend.services import projects as projects_service

router = APIRouter(prefix="/projects", tags=["projects"])
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiFailure},
    404: {"model": ApiFailure},
}


@router.get("", response_model=ApiSuccess[ProjectsListData], responses=ERROR_RESPONSES)
async def list_projects(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10,
) -> ApiSuccess[ProjectsListData]:
    """分页返回当前用户的项目列表。"""
    return ApiSuccess(
        data=await projects_service.list_projects(db, user.id, page, page_size)
    )


@router.get(
    "/{project_id}", response_model=ApiSuccess[ProjectDetail], responses=ERROR_RESPONSES
)
async def get_project(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[int, Path(ge=1)],
) -> ApiSuccess[ProjectDetail]:
    """返回当前用户的项目摘要及版本列表。"""
    project = await projects_crud.get_project(db, user.id, project_id)
    if project is None:
        raise ApiException(
            404, ApiError(code="project_not_found", message="计划不存在")
        )
    return ApiSuccess(data=await projects_service.project_detail(db, project))


@router.get(
    "/{project_id}/revisions/{revision_id}",
    response_model=ApiSuccess[RevisionDetail],
    responses=ERROR_RESPONSES,
)
async def get_revision(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[int, Path(ge=1)],
    revision_id: Annotated[int, Path(ge=1)],
) -> ApiSuccess[RevisionDetail]:
    """返回当前用户指定项目中的完整版本。"""
    project = await projects_crud.get_project(db, user.id, project_id)
    if project is None:
        raise ApiException(
            404, ApiError(code="project_not_found", message="计划不存在")
        )
    revision = await projects_crud.get_revision(db, project.id, revision_id)
    if revision is None:
        raise ApiException(
            404, ApiError(code="revision_not_found", message="版本不存在")
        )
    return ApiSuccess(
        data=await projects_service.revision_detail(db, revision, user.id)
    )


@router.post(
    "/{project_id}/final",
    response_model=ApiSuccess[ProjectSummary],
    responses=ERROR_RESPONSES,
)
async def set_final_revision(
    body: SetFinalRevisionRequest,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[int, Path(ge=1)],
) -> ApiSuccess[ProjectSummary]:
    """将当前用户项目中的指定版本设为最终方案。"""
    project = await projects_crud.get_project(db, user.id, project_id)
    if project is None:
        raise ApiException(
            404, ApiError(code="project_not_found", message="计划不存在")
        )
    revision = await projects_crud.get_revision(db, project.id, body.revision_id)
    if revision is None:
        raise ApiException(
            404, ApiError(code="revision_not_found", message="版本不存在")
        )
    return ApiSuccess(
        data=await projects_service.choose_final_revision(db, project, revision)
    )


@router.get(
    "/{project_id}/runs/{run_id}/trace",
    response_model=ApiSuccess[RunTrace],
    responses=ERROR_RESPONSES,
)
async def get_run_trace(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[int, Path(ge=1)],
    run_id: Annotated[int, Path(ge=1)],
) -> ApiSuccess[RunTrace]:
    """返回当前用户指定项目中的公开生成轨迹。"""
    project = await projects_crud.get_project(db, user.id, project_id)
    if project is None:
        raise ApiException(
            404, ApiError(code="project_not_found", message="计划不存在")
        )
    run = await projects_crud.get_run(db, user.id, project.id, run_id)
    if run is None:
        raise ApiException(
            404, ApiError(code="run_not_found", message="生成记录不存在")
        )
    return ApiSuccess(data=await projects_service.run_trace(db, project, run))


@router.delete(
    "/{project_id}",
    response_model=ApiSuccess[None],
    responses={**ERROR_RESPONSES, 409: {"model": ApiFailure}},
)
async def delete_project(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[int, Path(ge=1)],
) -> ApiSuccess[None]:
    """删除当前用户计划及其全部版本、运行、研究资料和模型轨迹。"""
    await projects_service.delete_project(db, user.id, project_id)
    return ApiSuccess(data=None)


@router.post("/{project_id}/revisions", response_model=ApiSuccess[RevisionDetail])
async def save_revision(
    body: SaveRevisionRequest,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[int, Path(ge=1)],
) -> ApiSuccess[RevisionDetail]:
    """保存当前计划的手动编辑快照，历史版本只读。"""
    return ApiSuccess(
        data=await projects_service.save_manual_revision(
            db, user.id, project_id, body.base_revision_id, body.trip
        )
    )
