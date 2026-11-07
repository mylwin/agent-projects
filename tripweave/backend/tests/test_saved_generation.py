"""生成并保存接口的登录、成功及失败边界。"""

import asyncio
from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from backend.api import middleware
from backend.api.app import app
from backend.api.dependencies import get_settings
from backend.api.routes import plans
from backend.config.planner import PlannerSettings
from backend.errors import ApiException, PlanningError
from backend.models.user import User
from backend.schemas.api import ApiError
from backend.schemas.projects import GeneratePlanData
from backend.services.model_trace import ModelTrace
from backend.tests.test_api import REQUEST, fake_generate, make_result


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    """用替身隔离数据库、模型和地图服务。"""

    async def logged_in(_request):
        """为请求注入已验证用户。"""
        return User(id=1, username="alice", password_hash="stored")

    monkeypatch.setattr(middleware, "resolve_current_user", logged_in)
    app.dependency_overrides[get_settings] = lambda: PlannerSettings("model", "map")
    with TestClient(app) as http:
        app.state.database_session_factory = object()
        yield http
    app.dependency_overrides.clear()


def test_create_saved_plan(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """新计划会创建运行并返回持久化标识。"""
    calls: list[str] = []

    async def start_run(_factory, user_id, project_id, request, _model, _map, timeout):
        """确认运行归属和计划输入。"""
        assert timeout > 0
        assert (user_id, project_id, request.destination) == (1, None, "成都")
        calls.append("start")
        return 56

    async def save_result(
        _factory, user_id, project_id, name, _request, run_id, result, model_calls
    ):
        """确认成功后保存版本。"""
        assert (user_id, project_id, name, run_id) == (1, None, "成都周末", 56)
        assert isinstance(model_calls, list)
        calls.append("save")
        return (
            GeneratePlanData(
                **result.model_dump(), project_id=12, revision_id=34, run_id=56
            ),
            None,
        )

    monkeypatch.setattr(plans.saved_generation, "start_run", start_run)
    monkeypatch.setattr(plans.saved_generation, "save_result", save_result)
    monkeypatch.setattr(plans, "generate_trip", fake_generate(make_result()))
    response = client.post("/api/plans/generate", json={**REQUEST, "name": "成都周末"})
    assert response.status_code == 200
    assert response.json()["data"]["project_id"] == 12
    assert response.json()["data"]["revision_id"] == 34
    assert calls == ["start", "save"]


def test_saved_plan_requires_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """保存请求没有登录态时立即拒绝。"""

    async def anonymous(_request):
        """模拟未登录请求。"""
        return None

    monkeypatch.setattr(middleware, "resolve_current_user", anonymous)
    response = client.post("/api/plans/generate", json={**REQUEST, "name": "成都周末"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_existing_project_is_owner_scoped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """向不存在或不属于自己的计划追加版本会返回 404。"""

    async def missing(_factory, user_id, project_id):
        """模拟用户查不到目标计划。"""
        assert (user_id, project_id) == (1, 99)
        return False

    monkeypatch.setattr(plans.saved_generation, "existing_project", missing)
    response = client.post("/api/plans/generate", json={**REQUEST, "project_id": 99})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"


def test_failed_generation_records_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模型失败会标记运行且不会保存版本。"""
    failed: list[tuple[int, str, str | None]] = []

    async def start_run(*_args):
        """返回替身运行 ID。"""
        return 56

    async def mark_failed(_factory, run_id, code, stage):
        """记录失败类型以供断言。"""
        failed.append((run_id, code, stage))

    monkeypatch.setattr(plans.saved_generation, "start_run", start_run)
    monkeypatch.setattr(plans.saved_generation, "mark_failed", mark_failed)
    monkeypatch.setattr(
        plans,
        "generate_trip",
        fake_generate(error=PlanningError("weather 研究", RuntimeError("失败"))),
    )
    response = client.post("/api/plans/generate", json={**REQUEST, "name": "成都周末"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_failed"
    assert failed == [(56, "upstream_failed", "weather 研究")]


def test_expired_save_preserves_conflict_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """持久化阶段的任务失效仍返回409，不能误报成服务器故障。"""

    async def start(*_args):
        return 56

    async def save(*_args):
        raise ApiException(
            409, ApiError(code="generation_interrupted", message="生成已过期")
        )

    async def failed(*_args):
        return None

    monkeypatch.setattr(plans.saved_generation, "start_run", start)
    monkeypatch.setattr(plans.saved_generation, "save_result", save)
    monkeypatch.setattr(plans.saved_generation, "mark_failed", failed)
    monkeypatch.setattr(plans, "generate_trip", fake_generate(make_result()))
    response = client.post("/api/plans/generate", json={**REQUEST, "name": "成都周末"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "generation_interrupted"


def test_model_trace_keeps_only_public_redacted_output() -> None:
    """轨迹只保留公开正文和工具名，并移除凭据。"""
    trace = ModelTrace("test-model", ("secret-key",))
    run_id = uuid4()
    asyncio.run(trace.on_chat_model_start({}, [], run_id=run_id))
    message = AIMessage(
        content="到访成都 secret-key",
        additional_kwargs={"reasoning_content": "公开思考 secret-key"},
        tool_calls=[
            {"name": "search", "args": {"token": "secret-key"}, "id": "tool-1"}
        ],
    )
    asyncio.run(
        trace.on_llm_end(
            LLMResult(generations=[[ChatGeneration(message=message)]]),
            run_id=run_id,
            tags=["agent:planner"],
        )
    )
    assert len(trace.calls) == 1
    call = trace.calls[0]
    assert call["agent"] == "planner"
    assert "secret-key" not in str(call)
    assert call["tool_calls"] == [{"name": "search", "id": "tool-1"}]
