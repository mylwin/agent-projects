"""仅从已知天气工具的逐日字段生成摘要，不采用模型推测。"""

import json
import math
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

from backend.schemas.trip import ToolEvidence, TripRequest

WEATHER_FIELDS = {
    "maps_weather": {
        "dayweather": "白天天气",
        "nightweather": "夜间天气",
        "daytemp": "白天气温",
        "nighttemp": "夜间气温",
        "daywind": "白天风向",
        "nightwind": "夜间风向",
        "daypower": "白天风力",
        "nightpower": "夜间风力",
    },
    "map_weather": {
        "text_day": "白天天气",
        "text_night": "夜间天气",
        "high": "最高气温",
        "low": "最低气温",
        "wd_day": "白天风向",
        "wd_night": "夜间风向",
        "wc_day": "白天风力",
        "wc_night": "夜间风力",
    },
}
WEATHER_TOOLS = set(WEATHER_FIELDS)
TEMPERATURE_FIELDS = {"daytemp", "nighttemp", "high", "low"}
UNKNOWN_VALUES = {"", "-", "--", "未知", "暂无", "null", "none", "n/a"}


def _payloads(evidence: ToolEvidence) -> Iterator[dict[str, Any]]:
    """读取结构化内容和 MCP JSON 文本块，不递归搜索未知容器。"""
    if evidence.structured_content is not None:
        yield evidence.structured_content
    try:
        content = json.loads(evidence.content)
    except ValueError:
        return
    if isinstance(content, dict):
        yield content
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text")
            if not isinstance(text, str):
                continue
            try:
                payload = json.loads(text)
            except ValueError:
                continue
            if isinstance(payload, dict):
                yield payload


def _forecast_rows(tool: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """只认高德 forecasts/casts 和百度 result/forecasts，不认实况或更新时间。"""
    if tool == "maps_weather":
        if "status" in payload and str(payload["status"]) != "1":
            return
        forecasts = payload.get("forecasts")
        if not isinstance(forecasts, list):
            return
        for forecast in forecasts:
            if not isinstance(forecast, dict):
                continue
            casts = forecast.get("casts")
            if isinstance(casts, list):
                yield from (row for row in casts if isinstance(row, dict))
    elif tool == "map_weather":
        if "status" in payload and str(payload["status"]) != "0":
            return
        result = payload.get("result")
        if not isinstance(result, dict):
            return
        forecasts = result.get("forecasts")
        if isinstance(forecasts, list):
            yield from (row for row in forecasts if isinstance(row, dict))


def _field_value(field: str, value: object) -> str | None:
    """校验天气字段标量，缺值不补零，温度仅接受有限数值且不补单位。"""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    if text.lower() in UNKNOWN_VALUES:
        return None
    if field in TEMPERATURE_FIELDS:
        try:
            if not math.isfinite(float(text)):
                return None
        except ValueError:
            return None
    elif not isinstance(value, str):
        return None
    return text


def summarize_weather(
    request: TripRequest, evidence: list[ToolEvidence]
) -> tuple[str, list[str]]:
    """按请求的连续出行日期汇总有效逐日字段，缺少覆盖的日期明确标未知。"""
    days: dict[str, list[str]] = {
        (request.start_date + timedelta(days=offset)).isoformat(): []
        for offset in range(request.day_count)
    }
    for item in evidence:
        if item.tool not in WEATHER_TOOLS:
            continue
        for payload in _payloads(item):
            for row in _forecast_rows(item.tool, payload):
                forecast_date = row.get("date")
                if not isinstance(forecast_date, str):
                    continue
                try:
                    parsed_date = date.fromisoformat(forecast_date)
                except ValueError:
                    continue
                if (
                    parsed_date.isoformat() != forecast_date
                    or forecast_date not in days
                ):
                    continue
                fields = [
                    f"{label}：{value}"
                    for field, label in WEATHER_FIELDS[item.tool].items()
                    if (value := _field_value(field, row.get(field))) is not None
                ]
                if fields:
                    detail = f"[{item.tool}] " + "；".join(fields)
                    if detail not in days[forecast_date]:
                        days[forecast_date].append(detail)
    summary = []
    missing = []
    for day, details in days.items():
        if details:
            summary.append(f"{day}：" + " / ".join(details))
        else:
            summary.append(f"{day}：天气未知（有效逐日预报未覆盖）。")
            missing.append(day)
    warnings = (
        [f"weather：以下出行日期缺少有效逐日天气预报，天气未知：{'、'.join(missing)}。"]
        if missing
        else []
    )
    return "\n".join(summary), warnings
