"""旅行项目、版本与公开轨迹的业务编排。"""

from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import projects as projects_crud
from backend.errors.api import ApiException
from backend.models.generation_run import GenerationRun
from backend.models.plan_revision import PlanRevision
from backend.models.project import Project
from backend.schemas.api import ApiError
from backend.schemas.projects import (
    ModelCallTrace,
    ProjectDetail,
    ProjectsListData,
    ProjectSummary,
    RevisionDetail,
    RevisionSummary,
    RunTrace,
)
from backend.schemas.trip import PlanResult, ResearchReport, ToolEvidence


def project_summary(project: Project, revision_count: int) -> ProjectSummary:
    """构造不含行程快照的项目摘要。"""
    return ProjectSummary(
        id=project.id,
        name=project.name,
        destination=project.destination,
        updated_at=project.updated_at,
        final_revision_id=project.final_revision_id,
        revision_count=revision_count,
    )


async def list_projects(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> ProjectsListData:
    """
    分页返回当前用户的项目与版本数量。

    参数：
    - user_id: 当前用户 ID
    - page: 页码
    - page_size: 每页项目数量
    """
    rows, total = await projects_crud.list_projects(db, user_id, page, page_size)
    return ProjectsListData(
        items=[project_summary(project, count) for project, count in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def project_detail(db: AsyncSession, project: Project) -> ProjectDetail:
    """组装项目摘要与按版本号排列的版本列表。"""
    revisions = await projects_crud.list_revisions(db, project.id)
    return ProjectDetail(
        **project_summary(project, len(revisions)).model_dump(),
        revisions=[
            RevisionSummary(
                id=revision.id,
                number=revision.number,
                title=revision.title,
                created_at=revision.created_at,
                generation_run_id=revision.generation_run_id,
            )
            for revision in revisions
        ],
    )


async def research_for_run(db: AsyncSession, run_id: int) -> list[ResearchReport]:
    """组装生成运行的研究摘要和原始工具证据。"""
    research_rows = await projects_crud.list_research(db, run_id)
    return [
        ResearchReport.model_validate(
            {
                "topic": report.topic,
                "summary": report.summary,
                "warnings": report.warnings,
                "evidence": [
                    ToolEvidence(
                        tool=item.tool,
                        content=item.content,
                        structured_content=item.structured_content,
                        fetched_at=item.fetched_at.replace(tzinfo=UTC)
                        if item.fetched_at.tzinfo is None
                        else item.fetched_at,
                    )
                    for item in evidence
                ],
            }
        )
        for report, evidence in research_rows
    ]


async def revision_detail(
    db: AsyncSession, revision: PlanRevision, user_id: int
) -> RevisionDetail:
    """组装版本快照及当前用户生成运行的研究资料。"""
    research: list[ResearchReport] = []
    if revision.generation_run_id is not None:
        run = await projects_crud.get_run(
            db, user_id, revision.project_id, revision.generation_run_id
        )
        if run is not None:
            research = await research_for_run(db, run.id)
    return RevisionDetail(
        id=revision.id,
        project_id=revision.project_id,
        number=revision.number,
        title=revision.title,
        created_at=revision.created_at,
        result=PlanResult.model_validate(
            {
                "trip": revision.trip,
                "places": revision.places,
                "warnings": revision.warnings,
                "reply": revision.reply or "",
                "research": research,
            }
        ),
    )


async def choose_final_revision(
    db: AsyncSession, project: Project, revision: PlanRevision
) -> ProjectSummary:
    """把项目内版本设为最终方案并返回更新后的摘要。"""
    await projects_crud.set_final_revision(db, project, revision.id)
    revisions = await projects_crud.list_revisions(db, project.id)
    return project_summary(project, len(revisions))


async def run_trace(db: AsyncSession, project: Project, run: GenerationRun) -> RunTrace:
    """组装一次生成运行中的研究及模型公开轨迹。"""
    calls = await projects_crud.list_model_calls(db, run.id)
    return RunTrace(
        run_id=run.id,
        project_id=project.id,
        status=run.status,
        error_stage=run.error_stage,
        error_code=run.error_code,
        error_message=run.error_message,
        research=await research_for_run(db, run.id),
        model_calls=[
            ModelCallTrace(
                agent=call.agent,
                call_index=call.call_index,
                model_name=call.model_name,
                provider=call.provider,
                reasoning=call.reasoning,
                content=call.content,
                tool_calls=call.tool_calls,
                started_at=call.started_at,
                finished_at=call.finished_at,
                duration_ms=call.duration_ms,
            )
            for call in calls
        ],
    )


async def delete_project(db: AsyncSession, user_id: int, project_id: int) -> None:
    """校验归属并整项删除计划；不提供单独删除版本的操作。"""
    project = await projects_crud.lock_project(db, user_id, project_id)
    if project is None:
        raise ApiException(
            404, ApiError(code="project_not_found", message="计划不存在")
        )
    if await projects_crud.has_running_generation(db, project.id):
        raise ApiException(
            409,
            ApiError(
                code="project_generating",
                message="计划正在生成，请等待生成结束后再删除",
            ),
        )
    await projects_crud.delete_project(db, project.id)
