"""旅行项目、版本与公开轨迹的业务编排。"""

import re
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config.database import db_transaction
from backend.crud import projects as projects_crud
from backend.errors.api import ApiException
from backend.models.generation_run import GenerationRun
from backend.models.plan_revision import PlanRevision
from backend.models.project import Project
from backend.schemas.api import ApiError
from backend.schemas.conversation import AdjustTrip
from backend.schemas.projects import (
    ModelCallTrace,
    ProjectDetail,
    ProjectsListData,
    ProjectSummary,
    RevisionDetail,
    RevisionSummary,
    RunTrace,
)
from backend.schemas.trip import PlanResult, ResearchReport, ToolEvidence, Trip


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
        generation_run_id=revision.generation_run_id,
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
    if await projects_crud.has_active_request(db, project.id):
        raise ApiException(
            409,
            ApiError(
                code="project_generating",
                message="计划正在生成，请等待生成结束后再删除",
            ),
        )
    await projects_crud.delete_project(db, project.id)


async def save_manual_revision(
    db: AsyncSession, user_id: int, project_id: int, base_revision_id: int, trip: Trip
) -> RevisionDetail:
    """在最新版本上保存活动文字和时间，拒绝覆盖其他标签页的新版本及事实字段。"""
    project = await projects_crud.lock_project(db, user_id, project_id)
    if project is None:
        raise ApiException(
            404, ApiError(code="project_not_found", message="计划不存在")
        )
    if await projects_crud.has_active_request(db, project_id):
        raise ApiException(
            409, ApiError(code="project_busy", message="请等待当前请求完成后再编辑")
        )
    revisions = await projects_crud.list_revisions(db, project_id)
    if not revisions or revisions[0].id != base_revision_id:
        raise ApiException(
            409,
            ApiError(
                code="revision_conflict", message="当前计划已有新版本，请刷新后再编辑"
            ),
        )
    base = revisions[0]
    original = Trip.model_validate(base.trip)
    invalid = trip.model_dump(exclude={"days"}) != original.model_dump(
        exclude={"days"}
    ) or len(trip.days) != len(original.days)
    for day, before in zip(trip.days, original.days, strict=False):
        invalid |= day.model_dump(exclude={"activities"}) != before.model_dump(
            exclude={"activities"}
        ) or len(day.activities) != len(before.activities)
        times = [activity.time for activity in day.activities]
        invalid |= times != sorted(set(times))
        for activity, previous in zip(day.activities, before.activities, strict=False):
            invalid |= activity.model_dump(
                exclude={"title", "description", "time"}
            ) != previous.model_dump(exclude={"title", "description", "time"})
            invalid |= not (
                0 < len(activity.title.strip()) <= 200
                and len(activity.description) <= 500
                and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", activity.time)
            )
    if invalid:
        raise ApiException(
            422,
            ApiError(
                code="invalid_revision",
                message="仅可修改原活动的标题、说明和 HH:MM 时间；时间须按顺序排列且不能重复",
            ),
        )
    if trip == original:
        return await revision_detail(db, base, user_id)
    revision = await projects_crud.create_revision(
        db,
        project_id=project_id,
        number=base.number + 1,
        title="手动调整行程",
        schema_version=trip.schemaVersion,
        trip=trip.model_dump(mode="json"),
        places=base.places,
        warnings=base.warnings,
        reply=base.reply,
        generation_run_id=base.generation_run_id,
    )
    await projects_crud.touch_project(db, project)
    return await revision_detail(db, revision, user_id)


@dataclass(frozen=True)
class AdjustmentSaved:
    """局部调整保存后的版本标识。"""

    revision_id: int
    revision_number: int


def adjusted_trip(trip: Trip, adjustment: AdjustTrip) -> Trip:
    """
    校验局部调整并返回新行程，不读写数据库。

    只能调整当前版本某一天已有的活动：时间和标题可改、说明可改或清空，
    未列出的活动会被移除；地点、费用、日期和行程标识保持不变。

    :param trip: 当前版本已保存的行程。
    :param adjustment: 模型提出的单日调整，活动列表是调整后的完整安排。
    :return: 调整后的行程；内容没有变化时返回原对象。
    :raises ValueError: 日期不存在、活动不属于该日、活动重复或时间无序时抛出。
    """
    day = next((entry for entry in trip.days if entry.id == adjustment.day_id), None)
    if day is None:
        raise ValueError("只能调整当前行程中已有的日期")
    existing = {activity.id: activity for activity in day.activities}
    ids = [activity.id for activity in adjustment.activities]
    if len(set(ids)) != len(ids):
        raise ValueError("同一活动不能重复调整")
    if any(activity_id not in existing for activity_id in ids):
        raise ValueError("只能调整当前行程中已有的活动，不能新增地点或活动")
    times = [
        activity.time or existing[activity.id].time
        for activity in adjustment.activities
    ]
    if times != sorted(set(times)):
        raise ValueError("调整后的活动时间必须按顺序排列且不能重复")
    activities = []
    for item in adjustment.activities:
        changes = {
            field: value
            for field, value in (
                ("time", item.time),
                ("title", item.title),
                ("description", item.description),
            )
            if value is not None
        }
        activities.append(existing[item.id].model_copy(update=changes))
    updated_day = day.model_copy(update={"activities": activities})
    if updated_day == day:
        return trip
    return trip.model_copy(
        update={
            "days": [
                updated_day if entry.id == adjustment.day_id else entry
                for entry in trip.days
            ]
        }
    )


async def save_assistant_adjustment(
    factory: async_sessionmaker[AsyncSession],
    user_id: int,
    project_id: int,
    base_revision_id: int,
    adjustment: AdjustTrip,
) -> AdjustmentSaved | None:
    """
    在最新版本上保存一次局部调整，校验失败或内容未变时不写新版本。

    对话轮次运行期间同一项目的编辑会被并发检查挡住，因此这里只需重新确认
    依据版本仍是最新版本，避免用户切换旧标签页后覆盖新行程。

    :param factory: 数据库会话工厂。
    :param user_id: 当前用户 ID。
    :param project_id: 对话所属项目 ID。
    :param base_revision_id: 本轮对话依据的版本 ID。
    :param adjustment: 已通过接口模型校验的单日调整。
    :return: 新版本标识；行程没有变化时为 None。
    :raises ApiException: 项目或版本不存在、依据版本已过期时抛出。
    :raises ValueError: 调整内容违反只改活动字段的约束时抛出。
    """
    async with db_transaction(factory) as db:
        project = await projects_crud.lock_project(db, user_id, project_id)
        if project is None:
            raise ApiException(
                404, ApiError(code="project_not_found", message="计划不存在")
            )
        revisions = await projects_crud.list_revisions(db, project_id)
        if not revisions or revisions[0].id != base_revision_id:
            raise ApiException(
                409,
                ApiError(
                    code="revision_conflict",
                    message="当前计划已有新版本，请返回当前计划后再调整",
                ),
            )
        base = revisions[0]
        trip = Trip.model_validate(base.trip)
        updated = adjusted_trip(trip, adjustment)
        if updated == trip:
            return None
        revision = await projects_crud.create_revision(
            db,
            project_id=project_id,
            number=base.number + 1,
            title=f"助手调整第 {adjustment.day_id} 天",
            schema_version=updated.schemaVersion,
            trip=updated.model_dump(mode="json"),
            places=base.places,
            warnings=base.warnings,
            reply=base.reply,
            generation_run_id=base.generation_run_id,
        )
        await projects_crud.touch_project(db, project)
        return AdjustmentSaved(revision.id, revision.number)
