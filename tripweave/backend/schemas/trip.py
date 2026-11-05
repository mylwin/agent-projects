"""按需求、地点、模型草稿、前端结果的顺序定义数据。"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class TripRequest(BaseModel):
    """一次完整的国内单目的地旅行需求，预算为全团、不含往返大交通。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    destination: str = Field(min_length=1, max_length=100)
    start_date: date
    day_count: int = Field(ge=1, le=5, strict=True)
    travelers: int = Field(ge=1, le=12, strict=True)
    budget: Decimal = Field(
        gt=0, le=1000000, max_digits=12, decimal_places=2, allow_inf_nan=False
    )
    pace: Literal["relaxed", "balanced", "packed"] = "balanced"
    interests: list[str] = Field(default_factory=list, max_length=10)
    instruction: str = Field(default="", max_length=500)


class Place(BaseModel):
    """地图查询事实；坐标与来源由程序填入，模型只能引用地点 ID。"""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    address: str
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    coordinate_system: Literal["GCJ-02"] = "GCJ-02"
    source: Literal["amap", "baidu"] = "amap"
    fetched_at: AwareDatetime


class ActivityDraft(BaseModel):
    """模型只安排时间、活动说明与候选地点引用。"""

    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    place_id: str = Field(min_length=1)
    kind: Literal["walk", "food", "garden", "museum", "free"] = "walk"


class DayDraft(BaseModel):
    """模型安排的单日草稿。"""

    date: date
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    activities: list[ActivityDraft] = Field(min_length=1, max_length=10)


class TravelDraft(BaseModel):
    """单次模型调用返回的结构化内容。"""

    days: list[DayDraft] = Field(min_length=1, max_length=5)


class TripActivity(BaseModel):
    """前端活动；费用未知为 null，point 留给前端 SVG 投影。"""

    id: str
    time: str
    title: str
    description: str
    location: str
    kind: str
    cost: float | None = None
    point: None = None
    placeId: str


class TripDay(BaseModel):
    """前端每日行程卡片的数据。"""

    id: int
    date: date
    label: str
    title: str
    description: str
    distance: str = "待核实"
    activities: list[TripActivity]


class Trip(BaseModel):
    """对应现有前端 Trip 的展示结构，ID 可由未来保存层替换。"""

    schemaVersion: Literal[1] = 1
    id: str
    destination: str
    travelers: int
    budget: float
    currency: Literal["CNY"] = "CNY"
    days: list[TripDay]


class PlanResult(BaseModel):
    """独立 Agent 的完整结果，供 CLI 检查和后续后端接入。"""

    trip: Trip
    places: list[Place]
    warnings: list[str]
    reply: str
