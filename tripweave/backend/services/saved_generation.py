"""生成运行与项目版本的短事务持久化。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config.database import db_transaction
from backend.crud import conversation as conversation_crud
from backend.crud.projects import (
    get_project,
    has_active_request,
    list_revisions,
    lock_project,
)
from backend.errors.api import ApiException
from backend.models.generation_run import GenerationRun
from backend.models.model_call import ModelCall
from backend.models.plan_revision import PlanRevision
from backend.models.project import Project
from backend.models.research_report import ResearchReport as StoredReport
from backend.models.tool_evidence import ToolEvidence as StoredEvidence
from backend.schemas.api import ApiError
from backend.schemas.conversation import ConversationTurnData
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
    timeout_seconds: float = 300,
    *,
    turn_id: int | None = None,
) -> int:
    """锁内预留生成名额及截止时间；对话内生成只排除已校验的自身轮次。"""
    async with db_transaction(factory) as db:
        now = utc_now()
        deadline = now + timedelta(seconds=timeout_seconds + 30)
        if project_id is not None:
            if await lock_project(db, user_id, project_id) is None:
                raise ApiException(
                    404, ApiError(code="project_not_found", message="计划不存在")
                )
            if await has_active_request(db, project_id, exclude_turn_id=turn_id):
                raise ApiException(
                    409,
                    ApiError(
                        code="project_busy", message="当前计划仍在处理请求，请稍后重试"
                    ),
                )
            if turn_id is not None:
                turn = await conversation_crud.lock_active_turn(
                    db, turn_id, user_id, project_id, now
                )
                revisions = await list_revisions(db, project_id)
                if (
                    not turn.generate
                    or not revisions
                    or revisions[0].id != turn.base_revision_id
                ):
                    raise ApiException(
                        409,
                        ApiError(
                            code="revision_conflict",
                            message="请基于当前计划重新发起规划",
                        ),
                    )
                deadline = min(deadline, turn.deadline_at)
        run = GenerationRun(
            project_id=project_id,
            user_id=user_id,
            request=request.model_dump(mode="json"),
            status="running",
            model_name=model_name,
            map_provider=map_provider,
            started_at=now,
            deadline_at=deadline,
        )
        db.add(run)
        await db.flush()
        return run.id


async def mark_failed(
    factory: async_sessionmaker[AsyncSession], run_id: int, code: str, stage: str | None
) -> None:
    """另开事务记录失败；断流清理不得覆盖已经成功提交的运行。"""
    async with db_transaction(factory) as db:
        run = await db.scalar(
            select(GenerationRun).where(GenerationRun.id == run_id).with_for_update()
        )
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
    *,
    turn_id: int | None = None,
) -> tuple[GeneratePlanData, ConversationTurnData | None]:
    """原子保存版本、证据及终态，返回已提交结果和可选对话快照。"""
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
        now = utc_now()
        turn = (
            await conversation_crud.lock_active_turn(
                db, turn_id, user_id, project.id, now
            )
            if turn_id is not None
            else None
        )
        run = await db.scalar(
            select(GenerationRun).where(GenerationRun.id == run_id).with_for_update()
        )
        if run is None or run.user_id != user_id or run.project_id != project_id:
            raise ValueError("生成记录不存在")
        now = utc_now()
        if run.status != "running" or run.deadline_at is None or run.deadline_at <= now:
            raise ApiException(
                409,
                ApiError(
                    code="generation_interrupted",
                    message="生成已结束或超时，请重新发起",
                ),
            )
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
        if turn is not None:
            await conversation_crud.save_turn_result(
                db,
                turn,
                assistant_text=result.reply,
                status="succeeded",
                result_revision_id=revision.id,
                error_code=None,
                finished_at=finished_at,
            )
        await db.flush()
        now = utc_now()
        if run.deadline_at <= now or (turn is not None and turn.deadline_at <= now):
            raise ApiException(
                409,
                ApiError(
                    code="generation_interrupted",
                    message="保存已超过截止时间，请重新发起",
                ),
            )
        return (
            GeneratePlanData(
                **result.model_dump(),
                project_id=project.id,
                revision_id=revision.id,
                run_id=run.id,
            ),
            ConversationTurnData.model_validate(turn) if turn is not None else None,
        )


async def existing_project(
    factory: async_sessionmaker[AsyncSession], user_id: int, project_id: int
) -> bool:
    """生成前确认目标项目属于当前用户。"""
    async with factory() as db:
        return await get_project(db, user_id, project_id) is not None
