# 接口请求与响应 Schema 设计

状态：认证、计划读写、生成保存和轨迹读取已实现；后续扩展仍按本设计讨论。数据库设计见 [05-database.md](05-database.md)，初始化 SQL 见 [resource/schema.sql](../resource/schema.sql)，具体请求/响应示例见 [07-api-reference.md](07-api-reference.md)。

## 范围

本阶段只设计：

- 用户名/密码登录，不建 token/session 表。
- 计划列表、计划详情、版本和最终方案，以及删除整个计划（包含全部版本）。
- 生成计划并保存结果。
- 查看研究摘要、工具证据和供应商公开返回的推理。

不包含：token 刷新与撤销、分享协作和持久化异步任务。
服务端对话、局部调整、手动编辑快照与显式完整重新规划已实现。生成接口已支持请求 `Accept: text/event-stream` 获取 SSE 进度。

## 复用现有模型

以下模型继续使用后端现有定义，不重复建一套：

- `TripRequest`、`Trip`、`Place`
- `PlanResult`、`ResearchReport`、`ToolEvidence`
- `ApiSuccess[T]`、`ApiFailure`、`ApiError`

接口成功响应仍为：

```json
{ "success": true, "data": {} }
```

失败响应仍为：

```json
{ "success": false, "error": { "code": "", "message": "", "stage": null } }
```

## 1. 登录 Schema

建议文件：`backend/schemas/account.py`

```python
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class CredentialsRequest(BaseModel):
    """注册或登录时提交的用户名和密码。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=50)
    password: SecretStr = Field(min_length=8, max_length=128)


class UserSummary(BaseModel):
    """返回给前端的用户公开信息，不包含密码哈希。"""

    id: int
    username: str
```

说明：

- 注册和登录共用 `CredentialsRequest`。
- 响应不返回 token；登录成功后由接口层写入签名 Cookie。
- `password_hash` 仅存在于 `tb_user`，任何响应模型都不能包含它。

## 2. 计划与生成 Schema

建议文件：`backend/schemas/projects.py`

```python
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.schemas.trip import PlanResult, ResearchReport, TripRequest


class GeneratePlanRequest(TripRequest):
    """在现有旅行需求上增加保存目标。"""

    model_config = ConfigDict(extra="forbid")

    project_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode="after")
    def require_name_for_new_project(self) -> Self:
        """新建计划时必须有名称，追加版本时沿用原计划名称。"""
        if self.project_id is None and not self.name:
            raise ValueError("新建计划时 name 不能为空")
        return self


class GeneratePlanData(PlanResult):
    """生成结果及对应的服务端持久化标识。"""

    project_id: int
    revision_id: int
    run_id: int


class RevisionSummary(BaseModel):
    """计划版本列表项，不携带完整行程。"""

    id: int
    number: int
    title: str
    created_at: AwareDatetime
    generation_run_id: int | None = None


class ProjectSummary(BaseModel):
    """计划列表项。"""

    id: int
    name: str
    destination: str
    updated_at: AwareDatetime
    final_revision_id: int | None = None
    revision_count: int = 0


class ProjectDetail(ProjectSummary):
    """计划详情及版本列表。"""

    revisions: list[RevisionSummary]


class RevisionDetail(BaseModel):
    """单个版本的完整展示数据。"""

    id: int
    project_id: int
    number: int
    title: str
    created_at: AwareDatetime
    result: PlanResult


class SetFinalRevisionRequest(BaseModel):
    """把指定版本设为最终方案。"""

    model_config = ConfigDict(extra="forbid")

    revision_id: int = Field(ge=1)


class ModelCallTrace(BaseModel):
    """单轮模型调用的公开轨迹。"""

    agent: Literal["attractions", "weather", "hotels", "planner"]
    call_index: int
    model_name: str
    provider: str | None = None
    reasoning: str | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    duration_ms: int | None = None


class RunTrace(BaseModel):
    """一次生成运行的研究摘要、工具证据和模型轨迹。"""

    run_id: int
    project_id: int | None = None
    status: Literal["running", "succeeded", "failed"]
    error_stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    research: list[ResearchReport] = Field(default_factory=list)
    model_calls: list[ModelCallTrace] = Field(default_factory=list)
```

说明：

- `GeneratePlanRequest` 直接继承现有 `TripRequest`，原有字段不变，只新增可选的 `project_id` 和 `name`；现有前端请求可以平滑增加保存字段。
- `GeneratePlanData` 直接继承 `PlanResult`，前端继续读取 `data.trip`、`data.places` 等字段，只多出 `project_id`、`revision_id`、`run_id`。
- `RevisionDetail.result` 使用现有 `PlanResult`，其中 `research` 从 `tb_research_report` 和 `tb_tool_evidence` 组装。
- `ModelCallTrace.reasoning` 只放供应商公开返回的内容；没有就返回 `null`，不要补写。
- 列表接口不返回完整 `trip`，避免计划列表响应过大。

## 3. 接口清单

| 方法 | 路径 | 请求模型 | 成功响应 | 说明 |
| --- | --- | --- | --- | --- |
| POST | `/api/auth/register` | `CredentialsRequest` | `ApiSuccess[UserSummary]` | 注册；用户名已存在返回 409 |
| POST | `/api/auth/login` | `CredentialsRequest` | `ApiSuccess[UserSummary]` | 校验密码并写签名 Cookie |
| POST | `/api/auth/logout` | 无 | `ApiSuccess[None]` | 清除登录 Cookie |
| GET | `/api/auth/me` | 无 | `ApiSuccess[UserSummary]` | 获取当前登录用户 |
| GET | `/api/projects` | 无 | `ApiSuccess[list[ProjectSummary]]` | 只返回当前用户计划 |
| GET | `/api/projects/{project_id}` | 无 | `ApiSuccess[ProjectDetail]` | 计划详情与版本列表 |
| GET | `/api/projects/{project_id}/revisions/{revision_id}` | 无 | `ApiSuccess[RevisionDetail]` | 单个版本完整结果 |
| POST | `/api/projects/{project_id}/final` | `SetFinalRevisionRequest` | `ApiSuccess[ProjectSummary]` | 设置最终方案 |
| POST | `/api/plans/generate` | `GeneratePlanRequest` | `ApiSuccess[GeneratePlanData]` | 生成并保存计划 |
| GET | `/api/projects/{project_id}/runs/{run_id}/trace` | 无 | `ApiSuccess[RunTrace]` | 查看研究、工具证据和公开推理 |

除注册、登录和健康检查外，其余接口都要求已登录。

## 4. 错误码

沿用现有错误响应结构，新增：

| HTTP | code | 场景 |
| --- | --- | --- |
| 401 | `unauthorized` | 未登录或 Cookie 无效 |
| 401 | `invalid_credentials` | 用户名或密码错误 |
| 409 | `username_taken` | 注册用户名已存在 |
| 404 | `project_not_found` | 计划不存在或不属于当前用户 |
| 404 | `revision_not_found` | 版本不存在或不属于当前用户 |
| 404 | `run_not_found` | 生成记录不存在或不属于当前用户 |
| 422 | `invalid_request` | 请求字段或跨字段校验失败 |

原有的 `planning_rejected`、`upstream_failed`、`planning_timeout`、`busy` 等状态码继续用于生成接口。

## 5. 数据库映射

| 接口/能力 | 表 |
| --- | --- |
| 注册、登录、当前用户 | `tb_user` |
| 计划列表与详情 | `tb_project`、`tb_plan_revision` |
| 生成并保存 | `tb_generation_run`、`tb_plan_revision` |
| 研究摘要 | `tb_research_report` |
| 工具原文 | `tb_tool_evidence` |
| 模型正文与公开推理 | `tb_model_call` |
| 轨迹查看 | 上述运行、研究、证据和模型调用表 |

## 6. 代码落点

按当前仓库习惯，建议：

```text
backend/
  schemas/
    account.py          # 登录请求、用户摘要
    projects.py         # 计划、版本、生成、轨迹 Schema
  api/routes/
    auth.py             # 注册、登录、登出、当前用户
    projects.py         # 计划列表、详情、版本、最终方案、轨迹
    plans.py            # 扩展现有生成接口
  services/
    accounts.py         # 密码哈希校验、用户读写
    projects.py         # 计划、版本、运行和轨迹读写
  security.py           # 签名 Cookie 与密码哈希工具
  db.py                 # 数据库连接与会话；变大后再拆分
```

实现约定：

- 路由只做参数、调用服务、异常转换，不直接拼 SQL。
- 生成开始时先写 `tb_generation_run(status='running')`；模型调用期间不要持有长数据库事务；结束后再提交版本和研究轨迹。
- 生成失败时更新运行状态为 `failed`，保留脱敏错误信息；已经成功的版本不受影响。
- 服务端生成通过 `ModelTrace` 回调保存供应商公开返回的正文、推理和工具名称；终端仍使用 `ConsoleCallback`。
- 登录 Cookie 使用环境变量中的签名密钥，设置 `HttpOnly` 和 `SameSite=Lax`；生产环境再加 `Secure`。
- `resource/schema.sql` 只用于初始化；正式开发使用迁移工具管理后续变更。

## 7. 暂不实现

- token 刷新、撤销和会话表。
- 自动局部调整的待处理清单；服务端对话使用 `tb_conversation_turn` 保存。
- 新增地点、修改目的地或日期等超出局部调整的修改；这类需求仍需完整重新规划或手动编辑。
- 分享协作、多用户权限。
- 持久化异步任务、断线续传和独立取消接口。SSE 进度已实现，连接断开时取消本轮执行。


## 整项删除

`DELETE /api/projects/{project_id}` 返回 `ApiSuccess[None]`；登录与归属校验沿用现有接口。
应用层按关联顺序在同一事务中显式删除全部版本、运行、研究摘要、工具证据和模型轨迹，
不依赖数据库安装级联外键，无需修改表结构。生成运行创建与删除共用项目行锁；
生成中返回 `409 project_generating`。不提供单独删除版本。


## 对话与手动编辑

- `GET /api/projects/{id}/messages`：`ApiSuccess[list[ConversationTurnData]]`，最近 50 轮，正序。
- `POST /api/projects/{id}/messages`：`ChatRequest`，返回 SSE；普通聊天与重新生成统一入口。
- `POST /api/projects/{id}/revisions`：`SaveRevisionRequest`，返回 `ApiSuccess[RevisionDetail]`。
- `RevisionDetail` 补充 `generation_run_id`，手动版本沿用原证据和生成轨迹关联。

`ChatRequest` 含 `text`（1–2000 字符）、`base_revision_id`、`day_id` 和默认 false 的 `generate`。
普通输入绑定 `AdjustTrip` 局部调整工具：只能引用当前版本已有活动，可修改时间、标题、说明或移除活动；
地点、费用、日期和行程标识保持不变，不能新增地点。校验失败返回 `422 invalid_adjustment` 且不写版本；
内容与当前版本相同时不创建版本。历史版本只能解释和讨论，调整返回 `409 revision_conflict`。
只有 `generate=true` 才绑定完整规划工具 `GenerateFullPlan`；普通输入无法通过它创建整趟版本。
`ConversationTurnData` 包含公开用户输入、回复、依据/结果版本、日期与运行状态；不保存隐藏推理。
创建轮次先锁定本人项目；运行期间不占用数据库事务；完成提交后才发送成功终态。
同项目正在处理对话或生成时返回 409，避免并发编辑或删除。读取对话时会回收超过截止时间的运行中轮次，
刷新页面不会长期停留在“处理中”。
手动编辑携带最新版本 ID，只允许更改原活动的标题、说明和 HH:MM 时间，且保持时间有序、不重复。
地点、费用、日期和事实来源不由编辑接口改写；版本过期返回 `409 revision_conflict`。
