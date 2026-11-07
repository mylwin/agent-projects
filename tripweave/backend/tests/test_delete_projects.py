"""验证整项删除的权限、关联清理、事务回滚与正在生成的冲突保护。"""

import asyncio
from collections.abc import Generator
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from backend.api import middleware
from backend.crud import projects as crud
from backend.errors import ApiException
from backend.models.project import Project
from backend.services import projects
from backend.tests import test_projects

client = test_projects.client


@pytest.fixture
def database() -> Generator[tuple[AsyncSession, Session]]:
    """使用带外键限制的内存 SQLite 实际执行删除 SQL，不连接真实数据库。"""
    engine = create_engine("sqlite://")
    definitions = (
        "CREATE TABLE tb_project (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, destination TEXT, final_revision_id INTEGER, created_at DATETIME, updated_at DATETIME)",
        "CREATE TABLE tb_generation_run (id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES tb_project(id), user_id INTEGER, status TEXT, deadline_at DATETIME, finished_at DATETIME, error_code TEXT, error_stage TEXT, error_message TEXT)",
        "CREATE TABLE tb_plan_revision (id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES tb_project(id), generation_run_id INTEGER REFERENCES tb_generation_run(id))",
        "CREATE TABLE tb_research_report (id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES tb_generation_run(id))",
        "CREATE TABLE tb_tool_evidence (id INTEGER PRIMARY KEY, report_id INTEGER REFERENCES tb_research_report(id))",
        "CREATE TABLE tb_conversation_turn (id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES tb_project(id), status TEXT, deadline_at DATETIME, error_code TEXT, finished_at DATETIME)",
        "CREATE TABLE tb_model_call (id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES tb_generation_run(id))",
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for definition in definitions:
            connection.exec_driver_sql(definition)
        for project_id in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO tb_project VALUES (:id, :id, '测试计划', '成都', :final, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": project_id, "final": project_id * 10},
            )
            for index in range(2):
                row_id = project_id * 10 + index
                connection.execute(
                    text(
                        "INSERT INTO tb_generation_run (id, project_id, user_id, status) VALUES (:id, :project, :project, :status)"
                    ),
                    {
                        "id": row_id,
                        "project": project_id,
                        "status": "succeeded" if index == 0 else "failed",
                    },
                )
                connection.execute(
                    text("INSERT INTO tb_plan_revision VALUES (:id, :project, :id)"),
                    {"id": row_id, "project": project_id},
                )
                connection.execute(
                    text("INSERT INTO tb_research_report VALUES (:id, :id)"),
                    {"id": row_id},
                )
                connection.execute(
                    text("INSERT INTO tb_tool_evidence VALUES (:id, :id)"),
                    {"id": row_id},
                )
                connection.execute(
                    text("INSERT INTO tb_model_call VALUES (:id, :id)"), {"id": row_id}
                )
    with Session(engine) as session:

        class AsyncDatabase:
            """将同步内存会话适配到生产代码使用的异步接口。"""

            async def scalar(self, statement):
                """实际执行 ORM 查询。"""
                return session.scalar(statement)

            async def execute(self, statement):
                """实际执行 ORM 删除语句。"""
                return session.execute(statement)

        yield cast(AsyncSession, AsyncDatabase()), session
    engine.dispose()


def counts(session: Session) -> list[int]:
    """读取各关联表数量，用于验证整项清理或完整回滚。"""
    return [
        session.scalar(text(f"SELECT count(*) FROM {table}"))
        for table in (
            "tb_project",
            "tb_generation_run",
            "tb_plan_revision",
            "tb_research_report",
            "tb_tool_evidence",
            "tb_model_call",
        )
    ]


def test_deletes_all_children_and_preserves_other_owner(database) -> None:
    """删除多个版本、成功和失败运行及其资料，另一用户的数据完整保留。"""
    db, session = database
    with session.begin():
        asyncio.run(projects.delete_project(db, 1, 1))
    assert counts(session) == [1, 2, 2, 2, 2, 2]
    assert session.scalar(text("SELECT id FROM tb_project")) == 2
    assert session.scalar(text("SELECT min(project_id) FROM tb_plan_revision")) == 2


@pytest.mark.parametrize("user_id,project_id", [(1, 2), (1, 99)])
def test_missing_and_foreign_project_are_not_deleted(
    database, user_id, project_id
) -> None:
    """越权与不存在使用相同错误，不泄漏归属也不删除任何行。"""
    db, session = database
    with pytest.raises(ApiException) as caught, session.begin():
        asyncio.run(projects.delete_project(db, user_id, project_id))
    assert caught.value.status_code == 404
    assert counts(session) == [2, 4, 4, 4, 4, 4]


def test_running_generation_blocks_deletion(database) -> None:
    """有运行中任务时返回冲突，原项目及全部版本保持完整。"""
    db, session = database
    with session.begin():
        session.execute(
            text(
                "UPDATE tb_generation_run SET status='running', deadline_at=datetime('now', '+5 minutes') WHERE id=10"
            )
        )
    with pytest.raises(ApiException) as caught, session.begin():
        asyncio.run(projects.delete_project(db, 1, 1))
    assert caught.value.status_code == 409
    assert caught.value.error.code == "project_generating"
    assert counts(session) == [2, 4, 4, 4, 4, 4]


def test_partial_delete_failure_rolls_back_everything(
    database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """关联记录已经删除后发生异常，事务仍恢复所有资料。"""
    db, session = database
    execute = db.execute
    executed = 0

    async def fail_midway(statement):
        """第三条删除语句失败，确保不是只测试删除之前的错误。"""
        nonlocal executed
        executed += 1
        if executed == 4:
            raise RuntimeError("模拟删除失败")
        return await execute(statement)

    monkeypatch.setattr(db, "execute", fail_midway)
    with pytest.raises(RuntimeError), session.begin():
        asyncio.run(projects.delete_project(db, 1, 1))
    assert executed == 4
    assert counts(session) == [2, 4, 4, 4, 4, 4]


def test_delete_endpoint_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """接口传入用户归属，并在整项删除后返回统一成功体。"""
    deleted = []

    async def lock(_db, user_id, project_id):
        """只返回当前用户的计划。"""
        assert (user_id, project_id) == (1, 12)
        return Project(id=12, user_id=1)

    async def idle(_db, project_id):
        """模拟项目没有生成任务。"""
        return False

    async def remove(_db, project_id):
        """记录服务实际执行的删除。"""
        deleted.append(project_id)

    monkeypatch.setattr(crud, "lock_project", lock)
    monkeypatch.setattr(crud, "has_active_request", idle)
    monkeypatch.setattr(crud, "delete_project", remove)
    response = client.delete("/api/projects/12")
    assert response.status_code == 200
    assert response.json() == {"success": True, "data": None}
    assert deleted == [12]


def test_delete_endpoint_requires_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未登录时拒绝删除。"""

    async def anonymous(_request):
        """模拟未登录请求。"""
        return None

    monkeypatch.setattr(middleware, "resolve_current_user", anonymous)
    assert client.delete("/api/projects/12").status_code == 401


@pytest.mark.parametrize("project_id,expected", [(12, 409), (99, 404)])
def test_delete_endpoint_conflict_and_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, project_id: int, expected: int
) -> None:
    """运行冲突及项目不存在返回稳定错误码。"""

    async def lock(_db, user_id, requested_id):
        """按所属用户隔离项目。"""
        return Project(id=12, user_id=1) if (user_id, requested_id) == (1, 12) else None

    async def running(_db, requested_id):
        """模拟已有生成任务。"""
        return True

    monkeypatch.setattr(crud, "lock_project", lock)
    monkeypatch.setattr(crud, "has_active_request", running)
    response = client.delete(f"/api/projects/{project_id}")
    assert response.status_code == expected


def test_empty_project_can_be_deleted(database) -> None:
    """没有版本或运行的计划也可正常删除。"""
    db, session = database
    with session.begin():
        session.execute(
            text("INSERT INTO tb_project (id,user_id,name) VALUES (3,1,'空计划')")
        )
    with session.begin():
        asyncio.run(projects.delete_project(db, 1, 3))
    assert counts(session) == [2, 4, 4, 4, 4, 4]


def test_generation_start_rejects_deleted_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预检通过后若计划已被删除，创建运行必须重新校验且不能留下新记录。"""
    from contextlib import asynccontextmanager

    from backend.schemas.trip import TripRequest
    from backend.services import saved_generation
    from backend.tests.test_api import REQUEST

    @asynccontextmanager
    async def transaction(_factory):
        """提供不具备写入能力的会话，确保删除后不会继续写入。"""
        yield object()

    async def missing(_db, user_id, project_id):
        """模拟获取行锁时项目已消失。"""
        assert (user_id, project_id) == (1, 12)
        return None

    monkeypatch.setattr(saved_generation, "db_transaction", transaction)
    monkeypatch.setattr(saved_generation, "lock_project", missing)
    with pytest.raises(ApiException) as caught:
        asyncio.run(
            saved_generation.start_run(
                async_sessionmaker(),
                1,
                12,
                TripRequest.model_validate(REQUEST),
                "model",
                "amap",
            )
        )
    assert caught.value.status_code == 404
