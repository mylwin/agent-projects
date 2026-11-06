"""项目接口的权限、分页和版本响应测试。"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.api import middleware
from backend.api.app import app
from backend.config.database import get_db
from backend.crud import projects as projects_crud
from backend.models.generation_run import GenerationRun
from backend.models.model_call import ModelCall
from backend.models.plan_revision import PlanRevision
from backend.models.project import Project
from backend.models.user import User
from backend.tests.test_api import make_result


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """提供隔离的项目接口客户端。"""
    user = User(id=1, username="alice", password_hash="stored")

    async def logged_in(_request):
        """模拟中间件中的已验证用户。"""
        return user

    monkeypatch.setattr(middleware, "resolve_current_user", logged_in)
    app.dependency_overrides[get_db] = lambda: object()
    with TestClient(app) as http:
        yield http
    app.dependency_overrides.clear()


def test_projects_list_and_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """列表分页并返回当前用户项目的版本摘要。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    project = Project(
        id=12, user_id=1, name="成都三日", destination="成都", updated_at=now
    )
    revision = PlanRevision(
        id=34, project_id=12, number=2, title="AI 初稿", created_at=now
    )

    async def list_projects(_db, user_id, page, page_size):
        """记录分页参数并返回一条项目。"""
        assert (user_id, page, page_size) == (1, 2, 5)
        return [(project, 1)], 6

    async def get_project(_db, user_id, project_id):
        """按所属用户和项目 ID 查询。"""
        assert (user_id, project_id) == (1, 12)
        return project

    async def list_revisions(_db, project_id):
        """返回项目版本。"""
        assert project_id == 12
        return [revision]

    monkeypatch.setattr(projects_crud, "list_projects", list_projects)
    monkeypatch.setattr(projects_crud, "get_project", get_project)
    monkeypatch.setattr(projects_crud, "list_revisions", list_revisions)
    response = client.get("/api/projects?page=2&pageSize=5")
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 6
    assert response.json()["data"]["items"][0]["revision_count"] == 1
    response = client.get("/api/projects/12")
    assert response.status_code == 200
    assert response.json()["data"]["revisions"][0]["id"] == 34
    assert response.json()["data"]["updated_at"].endswith("Z")


def test_revision_and_final_are_project_scoped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """只返回本用户的版本，并拒绝外项目版本成为最终方案。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    project = Project(
        id=12, user_id=1, name="成都三日", destination="成都", updated_at=now
    )
    result = make_result()
    revision = PlanRevision(
        id=34,
        project_id=12,
        number=2,
        title="AI 初稿",
        created_at=now,
        trip=result.trip.model_dump(mode="json"),
        places=[],
        warnings=[],
        reply="已完成",
    )

    async def get_project(_db, user_id, project_id):
        """隔离其他用户的项目。"""
        return project if (user_id, project_id) == (1, 12) else None

    async def get_revision(_db, project_id, revision_id):
        """隔离其他项目的版本。"""
        return revision if (project_id, revision_id) == (12, 34) else None

    async def list_revisions(_db, project_id):
        """返回一个版本。"""
        return [revision]

    async def set_final(_db, project, revision_id):
        """记录最终版本。"""
        project.final_revision_id = revision_id

    monkeypatch.setattr(projects_crud, "get_project", get_project)
    monkeypatch.setattr(projects_crud, "get_revision", get_revision)
    monkeypatch.setattr(projects_crud, "list_revisions", list_revisions)
    monkeypatch.setattr(projects_crud, "set_final_revision", set_final)
    assert client.get("/api/projects/99").json()["error"]["code"] == "project_not_found"
    assert (
        client.get("/api/projects/12/revisions/99").json()["error"]["code"]
        == "revision_not_found"
    )
    response = client.get("/api/projects/12/revisions/34")
    assert response.status_code == 200
    assert response.json()["data"]["result"]["trip"]["destination"] == "成都"
    assert (
        client.post("/api/projects/12/final", json={"revision_id": 99}).status_code
        == 404
    )
    response = client.post("/api/projects/12/final", json={"revision_id": 34})
    assert response.status_code == 200
    assert response.json()["data"]["final_revision_id"] == 34


def test_projects_require_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """中间件未识别用户时拒绝访问项目。"""

    async def anonymous(_request):
        """模拟未登录请求。"""
        return None

    monkeypatch.setattr(middleware, "resolve_current_user", anonymous)
    response = client.get("/api/projects")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_trace_is_scoped_to_current_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """轨迹只允许当前用户访问，公开模型调用内容按契约返回。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    project = Project(
        id=12, user_id=1, name="成都三日", destination="成都", updated_at=now
    )
    run = GenerationRun(id=56, project_id=12, user_id=1, status="succeeded")
    call = ModelCall(
        id=1,
        run_id=56,
        agent="planner",
        call_index=1,
        model_name="qwen-plus",
        started_at=now,
        reasoning=None,
        tool_calls=[],
    )

    async def get_project(_db, user_id, project_id):
        """只返回当前用户项目。"""
        return project if (user_id, project_id) == (1, 12) else None

    async def get_run(_db, user_id, project_id, run_id):
        """确认查询同时限制用户、项目和运行。"""
        return run if (user_id, project_id, run_id) == (1, 12, 56) else None

    async def list_model_calls(_db, run_id):
        """返回一条公开模型调用。"""
        return [call]

    async def list_research(_db, run_id):
        """当前运行没有研究摘要。"""
        return []

    monkeypatch.setattr(projects_crud, "get_project", get_project)
    monkeypatch.setattr(projects_crud, "get_run", get_run)
    monkeypatch.setattr(projects_crud, "list_model_calls", list_model_calls)
    monkeypatch.setattr(projects_crud, "list_research", list_research)
    assert (
        client.get("/api/projects/12/runs/99/trace").json()["error"]["code"]
        == "run_not_found"
    )
    response = client.get("/api/projects/12/runs/56/trace")
    assert response.status_code == 200
    assert response.json()["data"]["model_calls"][0]["agent"] == "planner"
