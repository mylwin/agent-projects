"""验证流式生成的实时性、错误、保存和中断清理，所有外部服务均使用替身。"""

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import ToolMessage

from backend.api.routes import plans
from backend.errors import ApiException, PlanningError
from backend.schemas.api import ApiSuccess
from backend.schemas.projects import GeneratePlanData
from backend.services.generation_stream import GenerationStream
from backend.tests import test_saved_generation
from backend.tests.test_api import REQUEST, fake_generate, make_result

client = test_saved_generation.client


def frames(text: str) -> list[dict]:
    """读取测试响应中的 SSE 数据帧。"""
    return [
        json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
    ]


def test_progress_arrives_before_generation_finishes() -> None:
    """任务仍被阻塞时，调用方已经读到实际进度，排除完成后重播。"""

    async def scenario() -> None:
        """以事件门闩阻塞最终结果，逐帧验证实时交付。"""
        stream = GenerationStream("test", ())
        finish = asyncio.Event()

        async def generate():
            """发送进度后等待测试放行。"""
            stream.progress("正在查询天气")
            await finish.wait()
            return ApiSuccess(data=make_result())

        iterator = stream.iterate(generate)
        assert frames(await anext(iterator))[0]["event"] == "started"
        progress = await asyncio.wait_for(anext(iterator), timeout=1)
        assert frames(progress)[0]["message"] == "正在查询天气"
        assert not finish.is_set()
        finish.set()
        assert frames(await anext(iterator))[0]["event"] == "complete"
        await iterator.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("accept", ["application/json", "text/event-stream"])
def test_saved_result_uses_same_persistence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, accept: str
) -> None:
    """两种传输都先保存再成功，并且只调用一次模型和保存。"""
    calls = []

    async def start(*_args):
        """隔离运行记录写入。"""
        calls.append("start")
        return 56

    async def save(*args):
        """保存时确认模型已完成。"""
        calls.append("save")
        return GeneratePlanData(
            **args[6].model_dump(), project_id=12, revision_id=34, run_id=56
        )

    monkeypatch.setattr(plans.saved_generation, "start_run", start)
    monkeypatch.setattr(plans.saved_generation, "save_result", save)
    monkeypatch.setattr(plans, "generate_trip", fake_generate(make_result()))
    response = client.post(
        "/api/plans/generate",
        json={**REQUEST, "name": "成都"},
        headers={"Accept": accept},
    )
    if accept == "text/event-stream":
        assert response.headers["x-accel-buffering"] == "no"
        events = frames(response.text)
        assert events[0]["event"] == "started"
        assert any(event.get("message") == "测试进度" for event in events)
        assert events[-2]["message"] == "正在保存行程和研究资料"
        assert events[-1]["event"] == "complete"
        data = events[-1]["data"]
    else:
        data = response.json()["data"]
    assert data["revision_id"] == 34
    assert calls == ["start", "save"]


@pytest.mark.parametrize(
    "error,code",
    [
        (TimeoutError(), "planning_timeout"),
        (PlanningError("天气研究", RuntimeError("上游失败")), "upstream_failed"),
        (RuntimeError("secret-value"), "internal_error"),
    ],
)
def test_failure_ends_stream(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, code: str
) -> None:
    """开始响应后用 error 事件结束，不再发送成功事件或原始内部异常。"""
    monkeypatch.setattr(plans, "generate_trip", fake_generate(error=error))
    response = client.post(
        "/api/plans/generate", json=REQUEST, headers={"Accept": "text/event-stream"}
    )
    assert response.status_code == 200
    events = frames(response.text)
    assert events[-1]["event"] == "error"
    assert events[-1]["error"]["code"] == code
    assert not any(event["event"] == "complete" for event in events)
    assert "secret-value" not in response.text


def test_validation_rejected_before_stream(client: TestClient) -> None:
    """校验失败仍返回 HTTP 错误和统一 JSON。"""
    response = client.post(
        "/api/plans/generate", json={}, headers={"Accept": "text/event-stream"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_callback_reports_real_tool_error_and_redacts_name() -> None:
    """实际工具错误不会被当成成功；不发送工具参数、原文或密钥。"""

    async def scenario() -> None:
        """注入工具生命周期回调，读取队列中的公开事件。"""
        stream = GenerationStream("test", ("secret-key",))
        run_id = uuid4()
        await stream.on_tool_start(
            {"name": "search-secret-key"},
            "private-input",
            run_id=run_id,
            tags=["agent:weather"],
        )
        await stream.on_tool_end(
            ToolMessage(content="private-output", tool_call_id="1", status="error"),
            run_id=run_id,
        )
        events = [stream.events.get_nowait(), stream.events.get_nowait()]
        assert [event["event"] for event in events] == ["tool_start", "tool_error"]
        assert events[0]["call_id"] == events[1]["call_id"]
        assert "secret-key" not in str(events)
        assert "private" not in str(events)

    asyncio.run(scenario())


def test_iterator_disconnect_cancels_worker() -> None:
    """消费者关闭流时，后台生成任务不会继续运行。"""

    async def scenario() -> None:
        """关闭迭代器后检查生成协程的清理逻辑已运行。"""
        stream = GenerationStream("test", ())
        stopped = asyncio.Event()

        async def generate():
            """发送进度后一直等待，模拟正在进行的模型请求。"""
            try:
                stream.progress("正在生成")
                await asyncio.Event().wait()
                raise AssertionError("不应完成")
            finally:
                stopped.set()

        iterator = stream.iterate(generate)
        await anext(iterator)
        await anext(iterator)
        await iterator.aclose()
        assert stopped.is_set()

    asyncio.run(scenario())


def test_stream_reports_busy_error() -> None:
    """响应启动后遭遇并发上限时，同样有明确终态。"""

    async def scenario() -> None:
        """模拟另一请求先占用可用名额。"""
        stream = GenerationStream("test", ())

        async def generate():
            """模拟执行前的并发检查。"""
            raise ApiException.busy()

        events = [frames(frame)[0] async for frame in stream.iterate(generate)]
        assert events[-1]["error"]["code"] == "busy"

    asyncio.run(scenario())


def test_disconnect_records_failure_and_releases_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """通过 ASGI 断开信号验证运行落盘和并发名额释放。"""
    from fastapi import Request
    from fastapi.responses import StreamingResponse

    from backend.config.planner import PlannerSettings
    from backend.models.user import User
    from backend.schemas.projects import GeneratePlanRequest

    async def scenario() -> None:
        """实际驱动 StreamingResponse，在收到业务进度后断开连接。"""
        failed = []
        disconnect = asyncio.Event()
        limit = asyncio.Semaphore(1)

        async def start(*_args):
            """隔离运行记录。"""
            return 56

        async def mark_failed(_factory, run_id, code, stage):
            """记录取消落盘信息。"""
            failed.append((run_id, code))

        async def generate(_request, _settings, on_progress=print, callback=None):
            """在取消前保持任务运行。"""
            on_progress("业务进度")
            await asyncio.Event().wait()
            raise AssertionError("不应运行到这里")

        async def receive():
            """业务进度交付后发送真正的 ASGI 断开消息。"""
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            """收到进度后立即触发断开，不等待完整结果。"""
            if "业务进度".encode() in message.get("body", b""):
                disconnect.set()

        monkeypatch.setattr(plans.saved_generation, "start_run", start)
        monkeypatch.setattr(plans.saved_generation, "mark_failed", mark_failed)
        monkeypatch.setattr(plans, "generate_trip", generate)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "headers": [(b"accept", b"text/event-stream")],
            "state": {
                "current_user": User(id=1, username="test", password_hash="unused")
            },
            "app": type(
                "TestApp",
                (),
                {"state": type("State", (), {"database_session_factory": object()})()},
            )(),
        }
        response = await plans.generate(
            GeneratePlanRequest.model_validate({**REQUEST, "name": "测试"}),
            Request(scope),
            PlannerSettings("model", "map"),
            limit,
        )
        assert isinstance(response, StreamingResponse)
        await asyncio.wait_for(response(scope, receive, send), timeout=2)
        assert failed == [(56, "generation_cancelled")]
        assert not limit.locked()

    asyncio.run(scenario())


def test_save_failure_never_emits_complete(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模型成功而持久化失败时，仍必须结束为失败。"""
    failures = []

    async def start(*_args):
        """隔离运行创建。"""
        return 56

    async def save(*_args):
        """模拟事务提交失败。"""
        raise RuntimeError("数据库内部细节")

    async def mark_failed(_factory, run_id, code, stage):
        """记录保存阶段的失败。"""
        failures.append((run_id, code, stage))

    monkeypatch.setattr(plans.saved_generation, "start_run", start)
    monkeypatch.setattr(plans.saved_generation, "save_result", save)
    monkeypatch.setattr(plans.saved_generation, "mark_failed", mark_failed)
    monkeypatch.setattr(plans, "generate_trip", fake_generate(make_result()))
    response = client.post(
        "/api/plans/generate",
        json={**REQUEST, "name": "测试"},
        headers={"Accept": "text/event-stream"},
    )
    events = frames(response.text)
    assert events[-1]["event"] == "error"
    assert not any(event["event"] == "complete" for event in events)
    assert failures == [(56, "save_failed", "持久化")]
    assert "数据库内部细节" not in response.text
