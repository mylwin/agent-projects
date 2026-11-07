# 接口文档

本文档记录当前已实现接口与保存行为。

- Base URL：`http://127.0.0.1:8000`
- 请求类型：`application/json`
- 已实现：健康检查、用户认证、计划读写、同步生成及生成轨迹

示例中的地点、日期、费用和模型输出仅用于说明结构，不代表真实查询结果。

## 通用响应结构

成功：

```json
{
  "success": true,
  "data": {}
}
```

失败：

```json
{
  "success": false,
  "error": {
    "code": "invalid_request",
    "message": "请求参数不合法：destination",
    "stage": null
  }
}
```

- `error.code`：稳定的机器可读错误码。
- `error.message`：面向用户的中文说明，已脱敏。
- `error.stage`：规划失败阶段；非规划错误为 `null`。

## 接口状态总览

| 状态 | 方法 | 路径 | 用途 |
| --- | --- | --- | --- |
| 已实现 | GET | `/api/health` | 健康检查与公开配置 |
| 已实现 | POST | `/api/plans/generate` | 生成行程；携带保存字段时写入计划和版本 |
| 已实现 | POST | `/api/auth/register` | 用户注册 |
| 已实现 | POST | `/api/auth/login` | 用户名/密码登录 |
| 已实现 | POST | `/api/auth/logout` | 退出登录 |
| 已实现 | GET | `/api/auth/me` | 当前登录用户 |
| 已实现 | GET | `/api/projects` | 当前用户的分页计划列表 |
| 已实现 | GET | `/api/projects/{project_id}` | 计划详情和版本列表 |
| 已实现 | GET | `/api/projects/{project_id}/revisions/{revision_id}` | 单个版本完整结果 |
| 已实现 | POST | `/api/projects/{project_id}/final` | 设置最终方案 |
| 已实现 | GET | `/api/projects/{project_id}/runs/{run_id}/trace` | 查看已保存的研究、工具证据和公开推理 |

---

## 1. 健康检查（已实现）

### GET `/api/health`

检查后端是否加载了模型和地图配置，不调用外部服务。

请求参数：无。

成功示例：

```json
{
  "success": true,
  "data": {
    "status": "ok",
    "map_provider": "amap",
    "model": "qwen-plus"
  }
}
```

配置缺失示例：

```json
{
  "success": false,
  "error": {
    "code": "configuration_error",
    "message": "缺少环境变量：MODEL_API_KEY",
    "stage": null
  }
}
```

| HTTP | code | 说明 |
| --- | --- | --- |
| 200 | - | 配置已加载 |
| 503 | `configuration_error` | 必需环境变量缺失或配置非法 |

---

## 2. 生成行程（已实现）

### POST `/api/plans/generate`

同步生成一次完整行程。不携带 `name` 或 `project_id` 时不要求登录，也不写入数据库；携带其中一个字段时按第 5 节保存。

请求体：现有 `TripRequest` 扁平结构。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `destination` | string | 是 | 国内单目的地，1–100 字符 |
| `start_date` | string | 是 | 首日日期，格式 `YYYY-MM-DD` |
| `day_count` | integer | 是 | 连续天数，1–5 |
| `travelers` | integer | 是 | 全团人数，1–12 |
| `budget` | string/number | 是 | 全团人民币预算，大于 0，最多两位小数 |
| `pace` | string | 否 | `relaxed`、`balanced`、`packed`，默认 `balanced` |
| `interests` | string[] | 否 | 兴趣关键词，最多 10 项 |
| `instruction` | string | 否 | 补充要求，最多 500 字符 |

请求示例：

```json
{
  "destination": "成都",
  "start_date": "2027-03-12",
  "day_count": 1,
  "travelers": 2,
  "budget": "3000.00",
  "pace": "relaxed",
  "interests": ["当地小吃"],
  "instruction": "安排轻松一点，喜欢当地小吃"
}
```

成功响应结构：`ApiSuccess[PlanResult]`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data.trip` | object | 前端展示行程 `Trip` |
| `data.places` | array | 行程实际引用的地图地点事实 |
| `data.warnings` | string[] | 未核验费用、路线、天气、住宿等提示 |
| `data.reply` | string | 程序生成的结果摘要，不是模型推理 |
| `data.research` | array | 三个研究主题的摘要、证据和 warning |

`Trip` 关键字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schemaVersion` | integer | 前端结构版本，当前为 1 |
| `id` | string | 本次结果 UUID，保存层可替换 |
| `destination` | string | 目的地 |
| `travelers` | integer | 人数 |
| `budget` | number | 全团预算 |
| `currency` | string | 当前固定 `CNY` |
| `days` | array | 每日行程 |

`days[]` 关键字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | integer | 从 1 开始的行程序号 |
| `date` | string | `YYYY-MM-DD` |
| `label` | string | 如“第 1 天” |
| `title` / `description` | string | 单日主题与说明 |
| `distance` | string | 当前固定“待核实” |
| `activities` | array | 当日活动 |

`activities[]` 关键字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 程序生成的活动 ID |
| `time` | string | `HH:MM` |
| `title` / `description` | string | 活动内容 |
| `location` | string | 地点名称与地址展示文本 |
| `kind` | string | 活动类别 |
| `cost` | number/null | 未查询费用时为 `null` |
| `point` | array/null | SVG 像素坐标，当前为 `null`，不是经纬度 |
| `placeId` | string | 对应 `places[]` 的 ID |

`places[]` 关键字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` / `name` / `address` | string | 地图地点事实 |
| `longitude` / `latitude` | number | 供应商坐标 |
| `coordinate_system` | string | `GCJ-02` 或 `BD-09` |
| `source` | string | `amap` 或 `baidu` |
| `fetched_at` | string | 程序接收工具证据的时间 |

`research[]` 关键字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `topic` | string | `attractions`、`weather` 或 `hotels` |
| `summary` | string | 研究摘要；无有效资料时明确未知 |
| `evidence` | array | 成功工具调用的原文与接收时间 |
| `warnings` | string[] | 该主题的缺失或失败说明 |

成功响应示例（示例数据）：

```json
{
  "success": true,
  "data": {
    "trip": {
      "schemaVersion": 1,
      "id": "9b7c6f6e-3d1a-4e8e-9f30-2f2e9d1a8c11",
      "destination": "成都",
      "travelers": 2,
      "budget": 3000.0,
      "currency": "CNY",
      "days": [
        {
          "id": 1,
          "date": "2027-03-12",
          "label": "第 1 天",
          "title": "城市慢游",
          "description": "安排少量活动，路线和费用待核实。",
          "distance": "待核实",
          "activities": [
            {
              "id": "day-1-activity-1",
              "time": "10:00",
              "title": "宽窄巷子漫步",
              "description": "以街区漫步为主，开放情况需确认。",
              "location": "宽窄巷子 四川省成都市青羊区",
              "kind": "walk",
              "cost": null,
              "point": null,
              "placeId": "amap-poi-1"
            }
          ]
        }
      ]
    },
    "places": [
      {
        "id": "amap-poi-1",
        "name": "宽窄巷子",
        "address": "四川省成都市青羊区",
        "longitude": 104.05,
        "latitude": 30.67,
        "coordinate_system": "GCJ-02",
        "source": "amap",
        "fetched_at": "2026-11-05T09:00:00+00:00"
      }
    ],
    "warnings": [
      "活动费用尚未查询，cost 为 null；全团预算不含往返大交通。",
      "地点坐标来自地图查询；point 尚未投影，路线与交通耗时待核实。"
    ],
    "reply": "已为成都生成1天行程草稿，引用1个查询地点。",
    "research": [
      {
        "topic": "attractions",
        "summary": "查询到宽窄巷子候选，地址与 GCJ-02 坐标已记录。",
        "evidence": [
          {
            "tool": "maps_text_search",
            "content": "{\"pois\":[{\"id\":\"amap-poi-1\",\"name\":\"宽窄巷子\"}]}",
            "structured_content": null,
            "fetched_at": "2026-11-05T09:00:00+00:00"
          }
        ],
        "warnings": []
      },
      {
        "topic": "weather",
        "summary": "预报未覆盖出行日期，天气未知。",
        "evidence": [],
        "warnings": ["weather：天气预报未覆盖出行日期。"]
      },
      {
        "topic": "hotels",
        "summary": "已查询住宿候选，实时房价和可订状态未知。",
        "evidence": [],
        "warnings": ["hotels：酒店价格与余房需另行确认。"]
      }
    ]
  }
}
```

失败示例：

```json
{
  "success": false,
  "error": {
    "code": "planning_rejected",
    "message": "行程规划失败 [ValueError]：目的地没有查询到可用地点，无法生成行程",
    "stage": "行程规划"
  }
}
```

| HTTP | code | 说明 |
| --- | --- | --- |
| 422 | `invalid_request` | 请求字段不合法 |
| 422 | `planning_rejected` | 需求有效，但无法生成行程 |
| 429 | `busy` | 并发生成任务已满 |
| 500 | `internal_error` | 未处理异常 |
| 502 | `upstream_failed` | 模型或地图服务失败 |
| 503 | `configuration_error` | 运行配置缺失 |
| 504 | `planning_timeout` | 规划超时 |

---

## 3. 登录接口

注册和登录成功后写入有效期为 7 天的签名 Cookie。配置数据库及至少 32 字节的 `AUTH_SECRET_KEY`；生产环境使用随机密钥、HTTPS 并设置 `AUTH_COOKIE_SECURE=true`。Cookie 不包含密码，退出只清除浏览器 Cookie，无法撤销已复制的 Cookie。

### POST `/api/auth/register`

成功返回 HTTP 201。密码使用随机盐和 scrypt 哈希后保存。

创建用户并建立登录态。无需已有登录态；请求使用 `Content-Type: application/json`，前端携带 Cookie（`credentials: include`）。

请求体：

```json
{
  "username": "mylwin",
  "password": "example-pass-123",
  "confirm_password": "example-pass-123"
}
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `username` | string | 是 | 前端去除首尾空白后要求 2–50 个字符；用户名需唯一 |
| `password` | string | 是 | 6–72 个字符，UTF-8 编码最多 72 字节，不去除空白；不在响应中返回 |
| `confirm_password` | string | 是 | 与密码一致，不去除空白 |

注册表单在前端检查两次密码是否一致，后端请求模型也会校验；字符长度按 Unicode 码点计算。

成功响应示例（前端期望 `success: true`，并读取 `data.id` 和 `data.username`）：

```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "mylwin"
  }
}
```

成功后设置签名登录 Cookie，供后续请求使用，格式见下方登录接口。用户名已存在时返回 409 `username_taken`，请求校验失败按通用格式返回 422 `invalid_request`。前端从失败响应读取 `error.code` 和 `error.message`。

### POST `/api/auth/login`

请求体包含 `username` 和 `password`。成功后响应：

```json
{
  "success": true,
  "data": {
    "id": 1,
    "username": "mylwin"
  }
}
```

响应头会设置登录 Cookie（示例）：

```http
Set-Cookie: tripweave_session=<signed-value>; HttpOnly; SameSite=Lax; Path=/
```

错误：401 `invalid_credentials`。

### POST `/api/auth/logout`

请求体：无。成功响应：

```json
{
  "success": true,
  "data": null
}
```

### GET `/api/auth/me`

请求参数：无。成功响应同登录响应；未登录返回 401 `unauthorized`。

---

## 4. 计划与版本接口

以下接口都要求登录；只能访问当前用户自己的计划。

### GET `/api/projects`

可选查询参数：`page`（页码，默认 1）和 `pageSize`（每页数量，默认 10，最大 100）。按更新时间和项目 ID 倒序排列。

成功响应示例：

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 12,
        "name": "成都三日",
        "destination": "成都",
        "updated_at": "2026-11-05T09:00:00Z",
        "final_revision_id": 34,
        "revision_count": 2
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 10
  }
}
```

### GET `/api/projects/{project_id}`

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `project_id` | integer | 计划 ID |

成功响应示例：

```json
{
  "success": true,
  "data": {
    "id": 12,
    "name": "成都三日",
    "destination": "成都",
    "updated_at": "2026-11-05T09:00:00+00:00",
    "final_revision_id": 34,
    "revision_count": 1,
    "revisions": [
      {
        "id": 34,
        "number": 2,
        "title": "AI 初稿",
        "created_at": "2026-11-05T09:00:00+00:00",
        "generation_run_id": 56
      }
    ]
  }
}
```

### GET `/api/projects/{project_id}/revisions/{revision_id}`

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `project_id` | integer | 计划 ID |
| `revision_id` | integer | 版本 ID |

成功响应的 `data.result` 是现有 `PlanResult`，结构与第 2 节成功响应中的 `data` 相同：

```json
{
  "success": true,
  "data": {
    "id": 34,
    "project_id": 12,
    "number": 2,
    "title": "AI 初稿",
    "created_at": "2026-11-05T09:00:00+00:00",
    "result": {
      "trip": {},
      "places": [],
      "warnings": [],
      "reply": "",
      "research": []
    }
  }
}
```

### POST `/api/projects/{project_id}/final`

请求：

```json
{
  "revision_id": 34
}
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `revision_id` | integer | 是 | 要设为最终方案的版本 |

成功响应为更新后的 `ProjectSummary`。

---

## 5. 生成并保存（已实现）

### POST `/api/plans/generate`

持久化版本沿用当前路径，必须登录且配置数据库。请求体在现有 `TripRequest` 上增加一个保存字段：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| 原有 `TripRequest` 字段 | - | 是 | 与第 2 节相同 |
| `project_id` | integer/null | 否 | 已有且属于当前用户的计划 ID；与 `name` 二选一 |
| `name` | string/null | 否 | 新计划名称，1–40 字符；与 `project_id` 二选一 |

请求示例（新建计划）：

```json
{
  "destination": "成都",
  "start_date": "2027-03-12",
  "day_count": 1,
  "travelers": 2,
  "budget": "3000.00",
  "pace": "relaxed",
  "interests": ["当地小吃"],
  "instruction": "安排轻松一点",
  "name": "成都一日"
}
```

成功响应的 `data` 在现有 `PlanResult` 基础上增加：

```json
{
  "project_id": 12,
  "revision_id": 34,
  "run_id": 56,
  "trip": {},
  "places": [],
  "warnings": [],
  "reply": "",
  "research": []
}
```

其中 `trip`、`places`、`warnings`、`reply`、`research` 与第 2 节完全相同。服务端在调用模型前创建运行记录，成功后原子保存计划、版本快照、研究证据和实际收到的公开模型内容；失败时记录运行错误。新计划的失败记录没有项目 ID，因此无法从项目轨迹接口读取。

---

## 6. 生成轨迹

### GET `/api/projects/{project_id}/runs/{run_id}/trace`

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `project_id` | integer | 计划 ID |
| `run_id` | integer | 一次生成运行 ID |

成功响应示例：

```json
{
  "success": true,
  "data": {
    "run_id": 56,
    "project_id": 12,
    "status": "succeeded",
    "error_stage": null,
    "error_code": null,
    "error_message": null,
    "research": [
      {
        "topic": "attractions",
        "summary": "查询到 1 个景点候选。",
        "evidence": [],
        "warnings": []
      }
    ],
    "model_calls": [
      {
        "agent": "weather",
        "call_index": 2,
        "model_name": "qwen-plus",
        "provider": "dashscope",
        "reasoning": "供应商公开返回的推理内容（如果有）",
        "content": "天气预报未覆盖出行日期。",
        "tool_calls": [],
        "started_at": "2026-11-05T09:00:00+00:00",
        "finished_at": "2026-11-05T09:00:03+00:00",
        "duration_ms": 3000
      }
    ]
  }
}
```

- `reasoning` 为 `null` 表示供应商没有返回公开推理，不代表没有思考过程。
- 原始工具原文在 `research[].evidence` 中；不展示隐藏 chain-of-thought。
- 仅返回已存入数据库的内容；未保存的运行无法通过此接口查询。

---

## 7. 错误码汇总

| HTTP | code | 说明 |
| --- | --- | --- |
| 401 | `unauthorized` | 未登录或 Cookie 无效 |
| 401 | `invalid_credentials` | 用户名或密码错误 |
| 404 | `project_not_found` | 计划不存在或不属于当前用户 |
| 404 | `revision_not_found` | 版本不存在或不属于当前用户 |
| 404 | `run_not_found` | 生成记录不存在或不属于当前用户 |
| 404 | `not_found` | 接口路径不存在 |
| 405 | `http_error` | 请求方法不允许 |
| 409 | `username_taken` | 用户名已存在 |
| 422 | `invalid_request` | 请求字段或跨字段校验失败 |
| 422 | `planning_rejected` | 需求有效，但无法生成行程 |
| 429 | `busy` | 并发生成任务已满 |
| 500 | `internal_error` | 未处理异常 |
| 502 | `upstream_failed` | 模型或地图服务失败 |
| 503 | `configuration_error` | 运行配置缺失 |
| 504 | `planning_timeout` | 规划超时 |

## 8. 当前边界

- 用户认证使用 MySQL；同步生成接口不保存结果。
- 计划和版本只读接口、最终方案接口及生成持久化已实现。
- 生成接口是同步的，可能持续数十秒到数分钟；暂无 SSE、异步任务或取消接口。
- 暂无局部修改、服务端对话、分享协作和 token 刷新/撤销接口。


## 生成接口的流式进度

`POST /api/plans/generate` 使用相同请求体，增加 `Accept: text/event-stream` 即返回 SSE。
不指定该请求头时继续返回原有统一 JSON，不增加额外模型调用。

认证、输入校验、项目归属、配置及初步并发检查失败时，仍返回相应 HTTP 状态和统一 JSON。
流开始后的失败通过 `error` 终态事件表示，此时 HTTP 状态已经是 200，不能再依赖状态码判断生成成功。

每帧包含 `event:` 和 JSON `data:`，以空行结束。JSON 内也包含同名 `event` 字段：

```text
event: progress
data: {"event":"progress","message":"正在查询天气"}

event: tool_start
data: {"event":"tool_start","message":"景点研究：正在调用地点搜索","call_id":"本次工具调用 UUID"}
```

| 事件 | 内容与含义 |
| --- | --- |
| `started` | 开始执行；不代表已经生成成功 |
| `progress` | 实际规划阶段、校验和保存进度 |
| `model_start` / `model_end` | 实际模型调用开始与完成 |
| `tool_start` / `tool_end` / `tool_error` | 实际工具调用状态，通过 `call_id` 关联；单次工具失败可由 Agent 恢复，不代表整轮结束 |
| `complete` | 唯一成功终态，`data` 与原 JSON 成功体的 `data` 相同；保存请求只在提交成功后发送 |
| `error` | 失败终态，`error` 含原有 `code`、`message`、`stage`；客户端结束等待 |

空闲时每 15 秒发送 `: heartbeat` 注释，不代表阶段进度。响应禁用缓存，并发送
`X-Accel-Buffering: no`；部署代理也应支持流式转发、避免缓冲和短空闲超时。

流内不发送工具参数、工具原文、模型正文分片或推理，也不把未完成的结构化参数展示为正式行程。
未收到 `complete` 就断流属于结果未确认，页面提示检查计划列表后再重试；不会自动重发昂贵的生成请求。
连接断开时取消请求关联任务、释放并发名额，并尝试把尚在运行的记录标记为失败，错误码为
`generation_cancelled`。已成功提交的版本不被覆盖。本轮不提供后台继续执行、事件重放或断线续传。
