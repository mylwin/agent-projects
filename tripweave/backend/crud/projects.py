"""旅行项目与版本的数据库读写。"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.generation_run import GenerationRun
from backend.models.model_call import ModelCall
from backend.models.plan_revision import PlanRevision
from backend.models.project import Project
from backend.models.research_report import ResearchReport
from backend.models.tool_evidence import ToolEvidence


async def list_projects(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> tuple[list[tuple[Project, int]], int]:
    """分页查询当前用户的项目及各自版本数。"""
    # 根据项目 ID 聚合版本数
    counts = (
        select(PlanRevision.project_id, func.count(PlanRevision.id).label("count"))
        .group_by(PlanRevision.project_id)
        .subquery()
    )
    # 项目 JOIN 版本数子查询，coalesce 保证无版本为 0
    base = (
        select(Project, func.coalesce(counts.c.count, 0))
        .outerjoin(counts, counts.c.project_id == Project.id)
        .where(Project.user_id == user_id)
    )
    # 排序 + 分页
    rows = await db.execute(
        base.order_by(Project.updated_at.desc(), Project.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    # 单独查总数
    total = await db.scalar(
        select(func.count(Project.id)).where(Project.user_id == user_id)
    )
    return [(project, count) for project, count in rows.all()], total or 0


async def get_project(
    db: AsyncSession, user_id: int, project_id: int
) -> Project | None:
    """只读取属于当前用户的项目。"""
    return await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )


async def list_revisions(db: AsyncSession, project_id: int) -> list[PlanRevision]:
    """按版本号倒序读取项目版本。"""
    result = await db.scalars(
        select(PlanRevision)
        .where(PlanRevision.project_id == project_id)
        .order_by(PlanRevision.number.desc(), PlanRevision.id.desc())
    )
    return list(result)


async def get_revision(
    db: AsyncSession, project_id: int, revision_id: int
) -> PlanRevision | None:
    """只读取指定项目中的版本。"""
    return await db.scalar(
        select(PlanRevision).where(
            PlanRevision.id == revision_id, PlanRevision.project_id == project_id
        )
    )


async def set_final_revision(
    db: AsyncSession, project: Project, revision_id: int
) -> None:
    """更新项目的最终版本，事务由 get_db 提交。"""
    project.final_revision_id = revision_id
    await db.flush()


async def list_research(
    db: AsyncSession, run_id: int
) -> list[tuple[ResearchReport, list[ToolEvidence]]]:
    """读取一次生成运行的研究摘要及对应工具证据。"""
    reports = list(
        await db.scalars(
            select(ResearchReport)
            .where(ResearchReport.run_id == run_id)
            .order_by(ResearchReport.id)
        )
    )
    if not reports:
        return []
    evidence = list(
        await db.scalars(
            select(ToolEvidence)
            .where(ToolEvidence.report_id.in_([report.id for report in reports]))
            .order_by(ToolEvidence.report_id, ToolEvidence.sequence, ToolEvidence.id)
        )
    )
    by_report: dict[int, list[ToolEvidence]] = {report.id: [] for report in reports}
    for item in evidence:
        by_report[item.report_id].append(item)
    return [(report, by_report[report.id]) for report in reports]


async def get_run(
    db: AsyncSession, user_id: int, project_id: int, run_id: int
) -> GenerationRun | None:
    """只读取当前用户指定项目中的生成运行。"""
    return await db.scalar(
        select(GenerationRun).where(
            GenerationRun.id == run_id,
            GenerationRun.user_id == user_id,
            GenerationRun.project_id == project_id,
        )
    )


async def list_model_calls(db: AsyncSession, run_id: int) -> list[ModelCall]:
    """按调用顺序读取公开模型轨迹。"""
    result = await db.scalars(
        select(ModelCall)
        .where(ModelCall.run_id == run_id)
        .order_by(ModelCall.started_at, ModelCall.id)
    )
    return list(result)


async def lock_project(
    db: AsyncSession, user_id: int, project_id: int
) -> Project | None:
    """锁定当前用户的项目，使删除与新生成运行的创建按序执行。"""
    return await db.scalar(
        select(Project)
        .where(Project.id == project_id, Project.user_id == user_id)
        .with_for_update()
    )


async def has_running_generation(db: AsyncSession, project_id: int) -> bool:
    """检查项目是否仍有生成任务，避免删除后再写回结果。"""
    return (
        await db.scalar(
            select(GenerationRun.id)
            .where(
                GenerationRun.project_id == project_id,
                GenerationRun.status == "running",
            )
            .limit(1)
        )
        is not None
    )


async def delete_project(db: AsyncSession, project_id: int) -> None:
    """依次清理项目的全部关联数据；事务由调用方提交或整体回滚。"""
    runs = select(GenerationRun.id).where(GenerationRun.project_id == project_id)
    reports = select(ResearchReport.id).where(ResearchReport.run_id.in_(runs))
    # ORM 只有逻辑关联，显式删除也适用于未安装外键的数据库。
    statements = (
        delete(ToolEvidence).where(ToolEvidence.report_id.in_(reports)),
        delete(ModelCall).where(ModelCall.run_id.in_(runs)),
        delete(ResearchReport).where(ResearchReport.run_id.in_(runs)),
        delete(PlanRevision).where(PlanRevision.project_id == project_id),
        delete(GenerationRun).where(GenerationRun.project_id == project_id),
        delete(Project).where(Project.id == project_id),
    )
    for statement in statements:
        await db.execute(statement.execution_options(synchronize_session=False))
