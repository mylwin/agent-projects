"""用合成工具证据验证天气日期和字段边界，不调用模型或地图。"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from backend.agents.weather import summarize_weather
from backend.schemas.trip import ToolEvidence, TripRequest


@pytest.fixture
def request_data() -> TripRequest:
    """构造跨闰日和月份的三日请求。"""
    return TripRequest(
        destination="测试城市",
        start_date=date(2028, 2, 28),
        day_count=3,
        travelers=1,
        budget=Decimal("1000"),
    )


def make_payload(tool: str, rows: list[dict[str, Any]]) -> dict:
    """仅构造两家供应商已知的逐日预报路径。"""
    if tool == "maps_weather":
        return {"status": "1", "forecasts": [{"casts": rows}]}
    return {"status": 0, "result": {"forecasts": rows}}


def make_evidence(tool: str, payload: dict) -> ToolEvidence:
    """结构化内容与 JSON 文本块共存，固定采集时间以检查原文保留。"""
    return ToolEvidence(
        tool=tool,
        content=json.dumps([{"type": "text", "text": json.dumps(payload)}]),
        structured_content=payload,
        fetched_at=datetime(2028, 2, 27, tzinfo=UTC),
    )


@pytest.mark.parametrize("tool", ["maps_weather", "map_weather"])
@pytest.mark.parametrize("encoding", ["structured", "json", "text_blocks", "both"])
def test_daily_fields_and_content_encodings(
    request_data: TripRequest, tool: str, encoding: str
) -> None:
    """实际天气字段覆盖三日，保留零温度、不补缺值与单位、去除双通道重复。"""
    fields = (
        {"dayweather": "雨", "nightweather": "阴", "daytemp": "8", "nighttemp": 0}
        if tool == "maps_weather"
        else {"text_day": "雨", "text_night": "阴", "high": "8", "low": 0}
    )
    rows = [
        {"date": day, **fields} for day in ("2028-02-28", "2028-02-29", "2028-03-01")
    ]
    payload = make_payload(tool, rows)
    evidence = make_evidence(tool, payload)
    if encoding == "structured":
        evidence.content = "普通文本不能证明天气"
    elif encoding == "json":
        evidence.structured_content = None
        evidence.content = json.dumps(payload)
    elif encoding == "text_blocks":
        evidence.structured_content = None
    original = evidence.model_dump_json()
    summary, warnings = summarize_weather(request_data, [evidence])
    assert not warnings
    assert summary.count("白天天气：雨") == 3
    assert summary.count("夜间天气：阴") == 3
    assert summary.count("气温：0") == 3
    assert "°" not in summary and "℃" not in summary
    assert "未知" not in summary
    assert evidence.model_dump_json() == original


@pytest.mark.parametrize("tool", ["maps_weather", "map_weather"])
@pytest.mark.parametrize(
    "forecast_date",
    [
        None,
        True,
        20280228,
        "",
        "明天",
        "2026-11-05",
        "2027-02-29",
        "2028-02-30",
        "20280228",
        "2028-W09-1",
        "2028-02-28T00:00:00",
        "2028-03-02",
    ],
)
def test_invalid_or_uncovered_dates_are_unknown(
    request_data: TripRequest, tool: str, forecast_date: object
) -> None:
    """无效日期、区间外日期、周日期、时间戳均不能覆盖请求日期。"""
    field = "dayweather" if tool == "maps_weather" else "text_day"
    evidence = make_evidence(
        tool, make_payload(tool, [{"date": forecast_date, field: "晴"}])
    )
    summary, warnings = summarize_weather(request_data, [evidence])
    assert summary.count("天气未知") == 3
    assert "晴" not in summary
    assert all(day in warnings[0] for day in ("2028-02-28", "2028-02-29", "2028-03-01"))


@pytest.mark.parametrize("tool", ["maps_weather", "map_weather"])
@pytest.mark.parametrize(
    "value", [None, "", "未知", "--", "NaN", "Infinity", True, [], {}]
)
def test_missing_or_invalid_weather_fields_are_unknown(
    request_data: TripRequest, tool: str, value: object
) -> None:
    """有日期但无实际天气字段或温度非法时不得视作预报覆盖。"""
    temperature = "daytemp" if tool == "maps_weather" else "high"
    row = {"date": "2028-02-28", "city": "晴城", "weather": "晴", temperature: value}
    summary, warnings = summarize_weather(
        request_data, [make_evidence(tool, make_payload(tool, [row]))]
    )
    assert summary.count("天气未知") == 3
    assert "晴" not in summary and "气温" not in summary
    assert warnings


@pytest.mark.parametrize("tool", ["maps_weather", "map_weather"])
def test_partial_fields_and_complementary_content(
    request_data: TripRequest, tool: str
) -> None:
    """两种内容通道均读取，但不借实况、更新时间或地理编码补齐缺日。"""
    field = "dayweather" if tool == "maps_weather" else "text_day"
    structured = make_payload(tool, [{"date": "2028-02-28", field: "雨"}])
    text_payload = make_payload(tool, [{"date": "2028-02-29", field: "雪"}])
    structured["date"] = "2028-03-01"
    structured["reporttime"] = "2028-03-01 09:00:00"
    if tool == "maps_weather":
        structured["lives"] = [{"date": "2028-03-01", "weather": "晴"}]
    else:
        structured["result"]["now"] = {
            "date": "2028-03-01",
            "uptime": "20280301090000",
            "text": "晴",
        }
    evidence = make_evidence(tool, structured)
    evidence.content = json.dumps(
        [
            {"type": "text", "text": "预报2028-03-01晴"},
            {"type": "text", "text": "{invalid json"},
            {
                "type": "image",
                "text": json.dumps(
                    make_payload(tool, [{"date": "2028-03-01", field: "晴"}])
                ),
            },
            {"type": "text", "text": json.dumps(text_payload)},
        ]
    )
    geocode = make_evidence(
        "maps_geo" if tool == "maps_weather" else "map_geocode", {"date": "2028-03-01"}
    )
    summary, warnings = summarize_weather(request_data, [geocode, evidence])
    assert "2028-02-28：" in summary and "白天天气：雨" in summary
    assert "2028-02-29：" in summary and "白天天气：雪" in summary
    assert "2028-03-01：天气未知" in summary
    assert "晴" not in summary and "气温" not in summary
    assert "2028-02-28" not in warnings[0] and "2028-02-29" not in warnings[0]
    assert "2028-03-01" in warnings[0]


@pytest.mark.parametrize("tool", ["maps_weather", "map_weather"])
@pytest.mark.parametrize(
    "shape", ["empty", "no_fields", "malformed", "unknown", "current", "error"]
)
def test_unusable_forecast_structures_are_unknown(
    request_data: TripRequest, tool: str, shape: str
) -> None:
    """空、无天气字段、未知嵌套、实况和失败返回均保守判为未知。"""
    field = "dayweather" if tool == "maps_weather" else "text_day"
    row = {"date": "2028-02-28", field: "晴"}
    payload = make_payload(tool, [row])
    if shape == "empty":
        payload = make_payload(tool, [])
    elif shape == "no_fields":
        payload = make_payload(tool, [{"date": "2028-02-28"}])
    elif shape == "malformed":
        payload = {"forecasts": {"casts": [row]}, "result": {"forecasts": row}}
    elif shape == "unknown":
        payload = {"data": payload, "forecast": [row]}
    elif shape == "current":
        payload = {"date": "2028-02-28", "lives": [row], "result": {"now": row}}
    elif shape == "error":
        payload["status"] = "0" if tool == "maps_weather" else 1
    summary, warnings = summarize_weather(request_data, [make_evidence(tool, payload)])
    assert summary.count("天气未知") == 3
    assert "晴" not in summary
    assert warnings


@pytest.mark.parametrize("tool", ["maps_geo", "map_geocode", "unknown_weather"])
def test_non_weather_tools_cannot_prove_weather(
    request_data: TripRequest, tool: str
) -> None:
    """即使非天气工具带有日期和完整预报结构，也不能作为天气证据。"""
    payload = {
        "date": "2028-02-28",
        "forecasts": [{"casts": [{"date": "2028-02-28", "dayweather": "晴"}]}],
        "result": {"forecasts": [{"date": "2028-02-28", "text_day": "晴"}]},
    }
    summary, warnings = summarize_weather(request_data, [make_evidence(tool, payload)])
    assert summary.count("天气未知") == 3
    assert "晴" not in summary
    assert warnings
