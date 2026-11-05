"""把 MCP 已返回的地点事实映射到展示模型，不调用地图 API 或转换坐标。"""

import json
from datetime import datetime
from typing import Any

from backend.schemas.trip import Place, ResearchReport


def collect_places(reports: list[ResearchReport], provider: str) -> dict[str, Place]:
    """只读取工具原文或 structuredContent，绝不从模型摘要提取地点和坐标。"""
    places: dict[str, Place] = {}
    for report in reports:
        if report.topic == "weather":
            continue
        for evidence in report.evidence:
            payloads: list[Any] = []
            if evidence.structured_content is not None:
                payloads.append(evidence.structured_content)
            try:
                payloads.append(json.loads(evidence.content))
            except ValueError:
                pass
            while payloads:
                item = payloads.pop()
                if isinstance(item, list):
                    payloads.extend(item)
                    continue
                if not isinstance(item, dict):
                    continue
                # MCP 文本块可以包含 JSON；其余字段只作容器遍历，不猜测普通文本。
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    try:
                        payloads.append(json.loads(item["text"]))
                    except ValueError:
                        pass
                payloads.extend(
                    value for value in item.values() if isinstance(value, (list, dict))
                )
                place = _read_place(item, provider, evidence.fetched_at)
                if place is not None:
                    places[place.id] = place
    return places


def _read_place(
    item: dict[str, Any], provider: str, fetched_at: datetime
) -> Place | None:
    """兼容两家 MCP 的地点字段名；缺 ID 或有效坐标时保留未知，不让模型补值。"""
    location = item.get("location")
    if isinstance(location, str):
        coordinates = location.split(",")
        if len(coordinates) != 2:
            return None
        longitude, latitude = coordinates
    elif isinstance(location, dict):
        longitude = location.get("lng", location.get("longitude"))
        latitude = location.get("lat", location.get("latitude"))
    else:
        return None
    try:
        coordinate_system = "GCJ-02" if provider == "amap" else "BD-09"
        declared_system = item.get("coordinate_system", item.get("coord_type"))
        if declared_system is not None:
            systems = {
                "gcj02ll": "GCJ-02",
                "bd09ll": "BD-09",
                "GCJ-02": "GCJ-02",
                "BD-09": "BD-09",
            }
            if declared_system not in systems:
                return None
            coordinate_system = systems[declared_system]
        # 外部原始字段在边界统一校验；进入业务层后才视为完整的 Place。
        return Place.model_validate(
            {
                "id": item.get("id", item.get("uid")),
                "name": item.get("name"),
                "address": item.get("address")
                if isinstance(item.get("address"), str)
                else "",
                "longitude": longitude,
                "latitude": latitude,
                "coordinate_system": coordinate_system,
                "source": provider,
                "fetched_at": fetched_at,
            }
        )

    except (TypeError, ValueError):
        return None
