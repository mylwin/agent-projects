"""生成运行与项目版本的短事务持久化。"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config.database import db_transaction
from backend.crud.projects import get_project, lock_project
from backend.errors.api import ApiException
from backend.models.generation_run import GenerationRun
from backend.models.model_call import ModelCall
from backend.models.plan_revision import PlanRevision
from backend.models.project import Project
from backend.models.research_report import ResearchReport as StoredReport
from backend.models.tool_evidence import ToolEvidence as StoredEvidence
from backend.schemas.api import ApiError
from backend.schemas.projects import GeneratePlanData
from backend.schemas.trip import PlanResult, TripRequest


def utc_now() -> datetime:
    """返回可写入 MySQL DATETIME(6) 的 UTC 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


async def start_run(
    factory: async_sessionmaker[AsyncSession],
    user_id: int,
    project_id: int | None,
    request: TripRequest,
    model_name: str,
    map_provider: str,
) -> int:
    """单独提交运行记录，模型调用期间不持有事务。"""
    async with db_transaction(factory) as db:
        if (
            project_id is not None
            and await lock_project(db, user_id, project_id) is None
        ):
            raise ApiException(
                404, ApiError(code="project_not_found", message="计划不存在")
            )
        run = GenerationRun(
            project_id=project_id,
            user_id=user_id,
            request=request.model_dump(mode="json"),
            status="running",
            model_name=model_name,
            map_provider=map_provider,
        )
        db.add(run)
        await db.flush()
        return run.id


async def mark_failed(
    factory: async_sessionmaker[AsyncSession], run_id: int, code: str, stage: str | None
) -> None:
    """另开事务记录失败；断流清理不得覆盖已经成功提交的运行。"""
    async with db_transaction(factory) as db:
        run = await db.get(GenerationRun, run_id)
        if run is None or run.status != "running":
            return
        run.status = "failed"
        run.error_code = code
        run.error_stage = stage
        run.error_message = "行程生成失败，请重试"
        finished_at = utc_now()
        run.finished_at = finished_at
        if run.started_at is not None:
            run.duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)


async def save_result(
    factory: async_sessionmaker[AsyncSession],
    user_id: int,
    project_id: int | None,
    name: str | None,
    request: TripRequest,
    run_id: int,
    result: PlanResult,
    model_calls: list[dict],
) -> GeneratePlanData:
    """原子保存项目、版本、研究摘要、工具证据和运行状态。"""
    async with db_transaction(factory) as db:
        if project_id is None:
            project = Project(
                user_id=user_id,
                name=name or request.destination,
                destination=request.destination,
                updated_at=utc_now(),
            )
            db.add(project)
            await db.flush()
            number = 1
        else:
            project = await db.scalar(
                select(Project)
                .where(Project.id == project_id, Project.user_id == user_id)
                .with_for_update()
            )
            if project is None:
                raise ValueError("计划不存在")
            number = (
                await db.scalar(
                    select(func.coalesce(func.max(PlanRevision.number), 0)).where(
                        PlanRevision.project_id == project.id
                    )
                )
                or 0
            ) + 1
            project.updated_at = utc_now()
            project.destination = request.destination
        run = await db.get(GenerationRun, run_id)
        if run is None:
            raise ValueError("生成记录不存在")
        run.project_id = project.id
        revision = PlanRevision(
            project_id=project.id,
            number=number,
            title="AI 初稿" if number == 1 else f"AI 生成 · 第 {number} 版",
            schema_version=result.trip.schemaVersion,
            trip=result.trip.model_dump(mode="json"),
            places=[place.model_dump(mode="json") for place in result.places],
            warnings=result.warnings,
            reply=result.reply,
            generation_run_id=run_id,
        )
        db.add(revision)
        await db.flush()
        for report in result.research:
            stored = StoredReport(
                run_id=run_id,
                topic=report.topic,
                summary=report.summary,
                warnings=report.warnings,
            )
            db.add(stored)
            await db.flush()
            for sequence, evidence in enumerate(report.evidence, 1):
                db.add(
                    StoredEvidence(
                        report_id=stored.id,
                        sequence=sequence,
                        tool=evidence.tool,
                        content=evidence.content,
                        structured_content=evidence.structured_content,
                        fetched_at=evidence.fetched_at.astimezone(UTC).replace(
                            tzinfo=None
                        ),
                    )
                )
        for call in model_calls:
            db.add(ModelCall(run_id=run_id, **call))
        run.status = "succeeded"
        finished_at = utc_now()
        run.finished_at = finished_at
        if run.started_at is not None:
            run.duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)
        return GeneratePlanData(
            **result.model_dump(),
            project_id=project.id,
            revision_id=revision.id,
            run_id=run.id,
        )


async def existing_project(
    factory: async_sessionmaker[AsyncSession], user_id: int, project_id: int
) -> bool:
    """生成前确认目标项目属于当前用户。"""
    async with factory() as db:
        return await get_project(db, user_id, project_id) is not None
