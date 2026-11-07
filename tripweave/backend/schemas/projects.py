"""旅行项目与版本接口的数据契约。"""

from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from backend.schemas.trip import PlanResult, ResearchReport, Trip, TripRequest


class GeneratePlanRequest(TripRequest):
    """旅行需求及可选的服务端保存目标。"""

    project_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=40)


class GeneratePlanData(PlanResult):
    """已保存结果及服务端标识。"""

    project_id: int
    revision_id: int
    run_id: int


class RevisionSummary(BaseModel):
    """
    不携带行程数据的版本摘要。

    Attributes:
        id: 版本 ID。
        number: 版本编号。
        title: 版本标题。
        created_at: 创建时间。
    """

    id: int
    number: int
    title: str
    created_at: AwareDatetime
    generation_run_id: int | None = None

    @field_validator("created_at", mode="before")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        """MySQL DATETIME 按 UTC 解释。"""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class ProjectSummary(BaseModel):
    """
    计划列表中的项目摘要。

    Attributes:
        id: 项目 ID。
        name: 项目名称。
        destination: 旅行目的地。
        updated_at: 最后更新时间。
        final_revision_id: 最终版本 ID。
        revision_count: 版本数量。
    """

    id: int
    name: str
    destination: str
    updated_at: AwareDatetime
    final_revision_id: int | None = None
    revision_count: int

    @field_validator("updated_at", mode="before")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        """MySQL DATETIME 按 UTC 解释。"""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class ProjectsListData(BaseModel):
    """分页项目列表。"""

    items: list[ProjectSummary]
    total: int
    page: int
    page_size: int


class ProjectDetail(ProjectSummary):
    """项目摘要及版本列表。"""

    revisions: list[RevisionSummary]


class RevisionDetail(BaseModel):
    """
    单个版本的完整结果。

    Attributes:
        id: 版本 ID。
        project_id: 项目 ID。
        number: 版本编号。
        title: 版本标题。
        created_at: 创建时间。
        result: 版本结果。
    """

    id: int
    project_id: int
    number: int
    title: str
    created_at: AwareDatetime
    result: PlanResult
    generation_run_id: int | None = None

    @field_validator("created_at", mode="before")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        """MySQL DATETIME 按 UTC 解释。"""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class SetFinalRevisionRequest(BaseModel):
    """指定项目的最终版本。"""

    revision_id: int = Field(ge=1)


class ModelCallTrace(BaseModel):
    """
    单轮模型调用中可公开的记录。

    Attributes:
        agent: 模型调用的代理名称。
        call_index: 模型调用的序号。
        model_name: 模型名称。
        provider: 模型供应商名称。
        reasoning: 模型调用的推理结果。
        content: 模型调用的返回内容。
        tool_calls: 模型调用的调用工具列表。
        started_at: 模型调用的开始时间。
        finished_at: 模型调用的结束时间。
    """

    agent: str
    call_index: int
    model_name: str
    provider: str | None = None
    reasoning: str | None = None
    content: str | None = None
    tool_calls: list[dict] | None = None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    duration_ms: int | None = None

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        """MySQL DATETIME 按 UTC 解释。"""
        return (
            value.replace(tzinfo=UTC)
            if value is not None and value.tzinfo is None
            else value
        )


class RunTrace(BaseModel):
    """一次生成运行的研究及模型调用轨迹。"""

    run_id: int
    project_id: int
    status: str
    error_stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    research: list[ResearchReport]
    model_calls: list[ModelCallTrace]


class SaveRevisionRequest(BaseModel):
    """手动编辑仅允许修改原活动的标题、说明和时间。"""

    base_revision_id: int = Field(ge=1)
    trip: Trip
