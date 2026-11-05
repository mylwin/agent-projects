"""按需求、地点、模型草稿、前端结果的顺序定义数据。"""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class TripRequest(BaseModel):
    """
    一次完整的国内单目的地旅行需求，预算为全团、不含往返大交通。

    Attributes:
        destination: 国内单个目的地名称。
        start_date: 旅行首日日期。
        day_count: 连续出行天数，范围 1–5。
        travelers: 全团人数，范围 1–12。
        budget: 全团人民币预算，不含往返大交通，最多两位小数。
        pace: 行程节奏，轻松、均衡或紧凑，默认 balanced。
        interests: 兴趣关键词，最多 10 项。
        instruction: 补充要求，最多 500 字符。
    """

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
    """
    地图查询事实；坐标与来源由程序填入，模型只能引用地点 ID。

    Attributes:
        id: 地图供应商返回的地点标识。
        name: 地点名称。
        address: 工具返回的地址，未知时为空字符串。
        longitude: 供应商坐标系下的经度。
        latitude: 供应商坐标系下的纬度。
        coordinate_system: 原始坐标系，高德默认 GCJ-02，百度默认 BD-09。
        source: 地图供应商，amap 或 baidu。
        fetched_at: 程序接收工具证据的带时区时间。
    """

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    address: str
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    coordinate_system: Literal["GCJ-02", "BD-09"] = "GCJ-02"
    source: Literal["amap", "baidu"] = "amap"
    fetched_at: AwareDatetime


class ActivityDraft(BaseModel):
    """
    模型只安排时间、活动说明与候选地点引用。

    Attributes:
        time: 24 小时制活动开始时间，格式 HH:MM。
        title: 活动标题。
        description: 活动说明。
        place_id: 本轮候选地点 ID，不接受模型自造地点。
        kind: 活动类别，默认 walk。
    """

    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    place_id: str = Field(min_length=1)
    kind: Literal["walk", "food", "garden", "museum", "free"] = "walk"


class DayDraft(BaseModel):
    """
    模型安排的单日草稿。

    Attributes:
        date: 当日日期，须与需求对应。
        title: 单日主题。
        description: 单日说明，默认空字符串。
        activities: 当日活动，数量 1–10。
    """

    date: date
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    activities: list[ActivityDraft] = Field(min_length=1, max_length=10)


class TravelDraft(BaseModel):
    """
    单次模型调用返回的结构化内容。

    Attributes:
        days: 连续日期的单日草稿，数量 1–5，由业务层校验日期范围。
    """

    days: list[DayDraft] = Field(min_length=1, max_length=5)


class TripActivity(BaseModel):
    """
    前端活动；费用未知为 null，point 留给前端 SVG 投影。

    Attributes:
        id: 程序生成的活动标识。
        time: 活动开始时间，格式 HH:MM。
        title: 活动标题。
        description: 活动说明。
        location: 地点名称与地址组成的展示文本。
        kind: 前端活动类别。
        cost: 活动费用；尚未查询时为 None，序列化为 null。
        point: SVG 像素坐标占位，当前固定为 None，不填经纬度。
        placeId: 对应 Place 的地点 ID，沿用前端字段名。
    """

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
    """
    前端每日行程卡片的数据。

    Attributes:
        id: 从 1 开始的行程序号。
        date: 当日日期。
        label: “第 N 天”展示标签。
        title: 单日主题。
        description: 单日说明。
        distance: 路程展示文字，未核实时为“待核实”。
        activities: 按开始时间排列的当日活动。
    """

    id: int
    date: date
    label: str
    title: str
    description: str
    distance: str = "待核实"
    activities: list[TripActivity]


class Trip(BaseModel):
    """
    对应现有前端 Trip 的展示结构，ID 可由未来保存层替换。

    Attributes:
        schemaVersion: 前端数据结构版本，当前固定为 1。
        id: 本轮行程的唯一标识。
        destination: 旅行目的地。
        travelers: 全团人数。
        budget: 全团预算，不含往返大交通。
        currency: 货币代码，当前固定为 CNY。
        days: 按日期排列的每日行程。
    """

    schemaVersion: Literal[1] = 1
    id: str
    destination: str
    travelers: int
    budget: float
    currency: Literal["CNY"] = "CNY"
    days: list[TripDay]


class ToolEvidence(BaseModel):
    """
    MCP 工具成功返回的原始证据，不包含连接地址或密钥。

    Attributes:
        tool: 成功调用的 MCP 工具名称。
        content: 工具返回的文本，非字符串内容序列化为 JSON。
        structured_content: 工具返回的结构化内容，未提供时为 None。
        fetched_at: 程序收集该工具结果的带时区时间。
    """

    tool: str
    content: str
    structured_content: dict[str, Any] | None = None
    fetched_at: AwareDatetime


class ResearchReport(BaseModel):
    """
    独立研究 Agent 的摘要、工具证据和缺失说明。

    Attributes:
        topic: 景点、天气或住宿研究主题。
        summary: Agent 最终摘要，无工具证据时明确资料未知。
        evidence: 成功工具调用的原始证据。
        warnings: 查询失败、证据缺失等需提示的事项。
    """

    topic: Literal["attractions", "weather", "hotels"]
    summary: str
    evidence: list[ToolEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlanResult(BaseModel):
    """
    独立 Agent 的完整结果，供 CLI 检查和后续后端接入。

    Attributes:
        trip: 前端展示行程。
        places: 行程实际引用的地图地点事实。
        warnings: 尚未核验事项与研究阶段警告。
        reply: 本轮生成结果的简短说明。
        research: 各研究 Agent 的摘要、原始证据和警告。
    """

    trip: Trip
    places: list[Place]
    warnings: list[str]
    reply: str
    research: list[ResearchReport] = Field(default_factory=list)
