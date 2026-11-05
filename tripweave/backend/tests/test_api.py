"""验证 FastAPI 薄入口的统一成功与失败响应契约。"""

from collections.abc import Awaitable, Callable, Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from langchain_core.callbacks import AsyncCallbackHandler

from backend.api.app import app
from backend.api.dependencies import get_settings
from backend.api.routes import plans
from backend.config.planner import PlannerSettings
from backend.errors import ApiException, PlanningError
from backend.schemas.trip import (
    PlanResult,
    Trip,
    TripActivity,
    TripDay,
    TripRequest,
)

REQUEST = {
    "destination": "成都",
    "start_date": "2027-03-12",
    "day_count": 1,
    "travelers": 2,
    "budget": "3000.00",
}


def make_result() -> PlanResult:
    """构造保留未知费用和像素坐标的成功结果。"""
    return PlanResult(
        trip=Trip(
            id="trip-test",
            destination="成都",
            travelers=2,
            budget=3000.0,
            days=[
                TripDay(
                    id=1,
                    date=date(2027, 3, 12),
                    label="第 1 天",
                    title="城市慢游",
                    description="测试行程",
                    activities=[
                        TripActivity(
                            id="day-1-activity-1",
                            time="09:00",
                            title="抵达",
                            description="测试活动",
                            location="成都 测试地址",
                            kind="walk",
                            placeId="place-test",
                        )
                    ],
                )
            ],
        ),
        places=[],
        warnings=["费用待核实"],
        reply="已生成测试行程",
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    """注入测试配置并在生命周期内运行应用。"""
    app.dependency_overrides[get_settings] = lambda: PlannerSettings(
        "test-model-key", "test-map-key"
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def fake_generate(
    result: PlanResult | None = None, error: Exception | None = None
) -> Callable[
    [TripRequest, PlannerSettings, Callable[[str], None], AsyncCallbackHandler | None],
    Awaitable[PlanResult],
]:
    """创建符合 generate_trip 签名的异步替身。"""

    async def generate(
        request: TripRequest,
        settings: PlannerSettings,
        on_progress: Callable[[str], None] = print,
        callback: AsyncCallbackHandler | None = None,
    ) -> PlanResult:
        on_progress("测试进度")
        if error:
            raise error
        assert result is not None
        return result

    return generate


def test_generate_returns_success_envelope(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """成功结果包在 data 中，未知费用和像素坐标保持 null。"""
    monkeypatch.setattr(plans, "generate_trip", fake_generate(make_result()))
    response = client.post("/api/plans/generate", json=REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert set(body) == {"success", "data"}
    activity = body["data"]["trip"]["days"][0]["activities"][0]
    assert activity["placeId"] == "place-test"
    assert activity["cost"] is None and activity["point"] is None


@pytest.mark.parametrize(
    "error,status,code",
    [
        (
            PlanningError("行程规划", ValueError("没有可用地点")),
            422,
            "planning_rejected",
        ),
        (
            PlanningError("weather 研究", RuntimeError("上游失败")),
            502,
            "upstream_failed",
        ),
        (TimeoutError(), 504, "planning_timeout"),
        (PlanningError("行程生成", TimeoutError()), 504, "planning_timeout"),
        (RuntimeError("内部细节不应暴露"), 500, "internal_error"),
    ],
)
def test_generate_returns_failure_envelope(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    error: Exception,
    status: int,
    code: str,
) -> None:
    """失败结果包在 error 中，并根据异常类型返回稳定状态码。"""
    monkeypatch.setattr(plans, "generate_trip", fake_generate(error=error))
    response = client.post("/api/plans/generate", json=REQUEST)
    assert response.status_code == status
    body = response.json()
    assert body["success"] is False
    assert set(body) == {"success", "error"}
    assert body["error"]["code"] == code
    assert "内部细节" not in response.text


def test_validation_failure_uses_failure_envelope(client: TestClient) -> None:
    """请求模型校验失败时只返回字段位置和统一错误体。"""
    response = client.post("/api/plans/generate", json={"destination": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_request"
    assert "destination" in body["error"]["message"]


def test_unknown_route_uses_failure_envelope(client: TestClient) -> None:
    """不存在的接口也返回统一失败体，而不是默认的 detail 结构。"""
    response = client.get("/api/unknown")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"


def test_health_returns_public_configuration(client: TestClient) -> None:
    """健康检查只返回供应商和模型名称，不返回密钥。"""
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "success": True,
        "data": {"status": "ok", "map_provider": "amap", "model": "qwen-plus"},
    }
    assert "test-model-key" not in response.text
    assert "test-map-key" not in response.text


def test_missing_configuration_uses_failure_envelope(client: TestClient) -> None:
    """配置缺失时返回统一失败体，而不是默认的 detail 结构。"""

    def missing_settings() -> PlannerSettings:
        raise ApiException.configuration("缺少环境变量")

    app.dependency_overrides[get_settings] = missing_settings
    response = client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "configuration_error"
