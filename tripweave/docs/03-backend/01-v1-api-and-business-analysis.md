# 首版后端接口与业务逻辑分析

日期：2026-11-04。状态：待实现的接口设计与验收基线，不代表后端已提供这些能力。

同日范围与顺序更新：用户已明确先独立设计/验证 Agent，再接入业务后端；目的地扩大到全国国内范围，取消苏州白名单。详见 [Agent State 与输入输出设计](02-agent-state-and-contract.md)。本文件保留当前前端现状分析，后端目标范围、首版天数与实施顺序按该更新同步调整；接口仍未实现。

本文以当前前端源码为需求证据，沿用 [系统架构](../01-architecture/02-system-architecture.md) 的 Python + FastAPI、LangChain 单 Planner、PostgreSQL 和请求内执行方式，补齐页面接入所需的接口、数据模型与业务约束。接口前缀固定为 `/api/v1`，下文路径均包含此前缀。

## 1. 结论与阅读顺序

首版需要提供 **13 个业务接口**，覆盖计划、活动编辑、版本、最终方案、对话、待处理要求及规划运行。模型、天气和地图查询是后端内部依赖，当前页面不需要直接调用供应商工具接口。

建议先完成“独立 Agent 输入输出与 State → 校验器/工具替身 → 全国目的地解析与真实规划验证”，通过后再按“计划容器与空状态 → 正式版本与手动编辑 → 消息及待处理要求 → 规划接口与 SSE → 取消及故障恢复”接入业务。Agent 直接返回领域结果，不先依赖数据库或 HTTP。

本次分析的主要决策：

- `PlanProject` 对应后端一个 `trip` 业务聚合，不再额外创建一套同义的 `projects` 资源。
- 创建计划只创建需求容器；首份行程由独立生成请求产生，不复制样本假装生成成功。
- “最新版本”和“最终方案”分别引用已有快照；选定最终方案不改变最新版本，也不新增版本。
- 每次有效手动编辑或助手调整自动提交新版本，无变化不产生版本。
- “继续调整”重新发起一次受控运行，保留原用户消息，不承诺恢复中断的模型内部执行位置。
- 后端保存真实坐标、结构化时间与精确金额；前端展示模型通过 API 适配层转换。

章节导航：第 2–3 节是前端证据与范围；第 4–5 节定义数据；第 6 节逐项定义接口；第 7–9 节说明运行、事务与错误；第 10–12 节说明代码落点、前端迁移和验收。

## 2. 前端现状与需求证据

### 2.1 已读取的实现

以下文件均为相对 `tripweave/` 的真实源码位置；它们比旧文档中的目标能力更能说明当前页面需要什么。

| 源码 | 观察到的行为 | 后端含义 |
| --- | --- | --- |
| `frontend/src/types/trip.ts` | 定义活动、旅行日、行程、消息、版本与计划 | 服务端需要对应资源与明确响应结构 |
| `frontend/src/api/workspaceStore.ts` | 一次保存整个工作区；自动归档快照；兼容旧数据 | 改成服务端局部写入、事务提交、不可变版本 |
| `frontend/src/pages/PlansPage.tsx` | 按名称/目的地搜索，按更新时间排序，预览最近两版 | 列表直接返回卡片摘要，避免逐计划请求详情 |
| 同上 | 新建只允许苏州、1–3 天、1–12 人，复制样本及调整日期/费用 | 真正创建与生成分开，输入在服务端再次校验 |
| `frontend/src/pages/PlannerPage.tsx` | 展示日程、活动、地图、费用、版本；修改活动三个字段 | 详情、历史快照与局部编辑接口 |
| 同上 | 任意版本可选为最终方案；离开前提示选择 | 最终版本指针单独持久化；跳转提醒留在前端 |
| 同上 | 删除当天待处理要求 | 稳定要求 ID 与移除接口，不能按数组下标删除 |
| `frontend/src/components/AssistantPanel.tsx` | 用户输入绑定当前天；停止、继续、查看回复对应版本 | 运行绑定目标天、要求、消息及正式结果版本 |
| `frontend/src/utils/localPlanner.ts` | 三类本地规则；未知表达保留要求；无变化不新增版本 | 用真实 Planner 替换，继续保留未解决要求与无变化语义 |
| `frontend/src/components/RouteMap.tsx` | `point` 直接用于 400 × 280 SVG | 当前点是像素坐标，不能当作经纬度 |
| `frontend/src/router/App.tsx` | 依赖完整本地工作区定位项目；不存在时直接显示未找到 | 接口接入后区分加载、404 与网络失败 |

### 2.2 页面行为与接口映射

| 页面/操作 | 后端读写 | 成功后前端动作 |
| --- | --- | --- |
| 打开计划列表、搜索 | 查询计划摘要 | 替换列表；保留搜索输入 |
| 新建文件夹 | 创建需求容器 | 跳转详情，显示尚未生成状态 |
| 首次生成 | 发起 `generate` 运行 | 展示进度，提交后加载正式版本 |
| 打开详情或刷新 | 查询容器及最新快照 | 恢复最新行程、最终指针和运行提示 |
| 切换日期、选中地点、收起侧栏 | 无 | 只改变 UI 状态 |
| 查看历史、点击消息结果 | 查询指定版本 | 行程只读，对话仍属于整个计划 |
| 手动编辑活动 | 修改最新版本中的指定活动 | 用新版本刷新当前行程 |
| 发送调整要求 | 创建要求、用户消息及运行 | 按真实事件显示进度 |
| 删除待处理项 | 将要求标记移除 | 清单移除，对话保留 |
| 停止或离开运行页面 | 取消运行；断连也尽力取消 | 查询终态，保留要求与旧行程 |
| 继续未完成调整 | 对同一要求重新运行 | 不重复创建原用户消息 |
| 选为最终方案 | 更新最终版本引用 | 刷新列表与详情的最终标记 |
| 选定并返回 | 先完成最终方案写入 | 收到成功响应后才跳转 |
| 出行信息弹窗 | 使用正在查看的快照 | 无需单独请求弹窗接口 |

## 3. 首版范围与明确取舍

### 3.1 首次接入范围

Agent 与后端目标覆盖**全国国内目的地、1–5 天、1–12 人**，首版一次规划一个目的地区域；不使用苏州白名单。当前页面的苏州与 1–3 天仍只是前端演示范围。目的地应解析城市/区县/景区并消歧，过大区域或多城市要求先澄清；境外目的地明确拒绝。国内目的地缺少供应商必要能力时返回能力缺口，不将其错误标成境外，也不静默换成苏州。接入页面时同步扩展目的地输入及天数控件。

预算按人民币全团口径，100–1,000,000 元；不含往返大交通。住宿可以属于全团预算，但当前生成器暂不提供可靠住宿报价，必须列为未估算项目。活动费用合计不等于全程总花费。

首版为本地单用户开发场景，后端注入固定开发身份，数据库仍保留 `owner_id`；生产多用户接入前替换为认证依赖。所有按 ID 访问均在服务端按该身份过滤，客户端不得指定 `owner_id`。这只是资源归属边界，不代表登录已实现。

### 3.2 暂不增加的接口

- 页面没有计划删除、重命名、活动增删或拖动入口，首版不为这些操作额外增加接口。
- 示例提示、静态封面、图标与 UI 偏好由前端提供，不设远程配置接口。
- 地点搜索、天气、路线计算由 Planner/校验服务内部调用；接入真实地图展示时使用详情携带的数据。
- 不提供任意上传并覆盖整个 `PlanProject` 的接口，不把浏览器对象直接当作可信数据库内容。
- 不提供图执行断点恢复、后台离线运行、token 回放或持久事件订阅接口。

## 4. 数据契约与前端字段映射

### 4.1 通用约定

- HTTP JSON 使用 `snake_case`；前端在 `frontend/src/api/` 映射成所需的 `camelCase`。保留已约定的运行路径及事件名。
- 资源 ID 为服务端生成的不透明字符串，正式环境建议 UUID。`revision_id` 是全局快照 ID，`revision` 是计划内连续整数版本号，两者不可混用。
- 所有时间戳使用带时区的 RFC 3339 字符串；日期用 `YYYY-MM-DD`；旅行时区首版为 `Asia/Shanghai`。`created_at` 决定消息时间，不能存“刚刚”作为唯一时间信息。
- 金额使用十进制字符串，如 `"3000.00"`，后端用 Decimal/数据库 NUMERIC；货币固定 `CNY`。前端展示时转换，禁止把浮点累加作为正式汇总依据。
- 不适用或未知字段明确为 `null`；空集合为 `[]`，不通过缺字段表达加载状态。
- 单资源成功直接返回资源对象；集合返回 `{items, next_cursor}` 并按需要增加计数。后续 OpenAPI 应据此生成前端传输类型。
- `revision` 只随正式行程变化；`row_version` 是计划聚合的乐观锁整数，任何持久化业务写入均递增，包括消息、要求、运行状态和最终指针。单次事务写多个子资源只递增一次。
- `updated_at` 反映用户可见业务变更：创建、接受指令、结果提交、要求移除及最终选择；查询、心跳和单纯执行阶段切换不更新它，避免卡片因轮询频繁重排。
- 非法游标、负数分页长度和未识别的状态过滤返回 422；不能悄悄换成第一页。游标不是权限凭据，翻页仍检查 owner。

### 4.2 领域对象

| 对象 | 必需字段/规则 |
| --- | --- |
| `TripRequirements` | `destination, start_date, day_count, travelers, budget, currency, budget_scope, timezone`；`preferences` 为字符串数组，首版可为空 |
| 计划容器 | `id, name, requirements, created_at, updated_at, row_version, latest_revision, latest_revision_id, final_revision_id, itinerary, active_run, pending_request` |
| 版本摘要 | `id, revision, parent_revision_id, title, source, created_at, validation_status, warnings`；`source=planner/manual` |
| 版本详情 | 版本摘要加 `trip_id, itinerary`；快照创建后不可修改 |
| 消息 | `id, trip_id, sequence, role, content, created_at, run_id, request_id, revision_id`；可空关联显式为 null；`role=user/assistant` |
| 调整要求 | `id, trip_id, operation, text, day_id, source_message_id, status, last_run_id, created_at, updated_at` |
| 运行 | `id, trip_id, request_id, client_request_id, operation, base_revision, status, stage, outcome, result_revision_id, reply_message_id, input_required, error, created_at, started_at, finished_at` |

`latest_revision=0`、两个版本 ID 为 null、`itinerary=null` 表示尚未产生正式行程。`active_run` 返回 `{id,status,stage,request_id}` 或 null；`pending_request` 返回最近一条可重试要求的 `{id,text,day_id,operation}` 或 null。完整未解决要求另行分页查询，不能由 `pending_request` 替代。

`outcome` 终态枚举为 `updated/unchanged/input_required`，失败/取消时为 null；`input_required` 为 `{fields:[{name,question}],request_id}` 或 null。`fields[].name` 是稳定字段标识，不能包含模型任意生成的对象路径。

### 4.3 行程快照结构

| 层级 | 字段与含义 |
| --- | --- |
| 行程 | `schema_version=1, trip_id, destination, destination_ref, travelers, budget, currency, budget_scope, timezone, days, cost_summary, warnings`；destination_ref 为国内目的地区域解析摘要，详见 Agent State 设计 |
| 每天 | `id` 为连续的 1-based 整数；`date,label,title,description,activities,route,weather` |
| 活动 | `id,title,description,kind,time,start_time,end_time,location,estimated_cost,cost_status,place,source,fetched_at` |
| 地点 | `poi_id,name,address,longitude,latitude,coordinate_system,source,fetched_at`；自由活动 `place=null` |
| 路线 | `status,distance_m,duration_s,legs,source,fetched_at`；每段含 `from_activity_id,to_activity_id,mode,distance_m,duration_s,polyline` |
| 天气 | `status,date,summary,source,fetched_at`；查不到或超预报范围时状态说明原因，其余可空 |
| 费用汇总 | `activity_cost_total,unknown_activity_count,unestimated_categories,budget_status` |
| 警告 | `code,message,day_id,activity_id`；后两者可空，界面显示人类可读文本 |

行程与嵌套对象中的 `source` 为来源代码字符串，例如 `amap/planner_estimate/user`，`fetched_at` 为对应来源的获取时间或 null；它不表示数据一定经过验证。版本摘要的 `source` 则专指版本创建方式。活动 `kind` 沿用现有图标代码并增加 `free`，未知代码前端继续使用通用图标。`weather.status=available/unavailable/out_of_range`；可用时 summary 为文本，未获取时保留 null。

时间约束：`start_time/end_time` 为本地 `HH:mm`，必须成对存在，首版不支持跨日活动；`time` 是后端生成的展示文本。待定时间两者均为 null，`time="时间待定"`，必须附 `TIME_UNVERIFIED` 警告。时间冲突依结构化时间检查，不解析任意自然语言字符串。

费用约束：`estimated_cost` 为全团费用字符串或 null；`cost_status=estimated/unknown`。明确免费时可以为 `"0.00"`，未知不能写零。`activity_cost_total` 只合计已知活动费用，存在未知项时配合 `unknown_activity_count` 展示“已知费用小计”。`budget_status=within_known_items/over_budget/incomplete`；未估算住宿时不能宣称全程满足预算。已知费用超过预算属于硬错误，正式生成应修复或失败。

路线约束：`status=verified/partial/unavailable/not_applicable`。零或一个有效地点无需路线查询，距离可以为零；多个地点缺失必要路径时不得伪造折线和耗时。`polyline` 为供应商坐标序列或 null，不是 SVG 点。坐标系首版为 `GCJ-02`，标明数据源；自由活动不强造 POI。

`validation_status=validated/with_warnings` 描述快照整体校验；通过硬规则但仍有未知价格、时间或开放信息可带警告保存。必要地点无法确认、路线核验失败导致无法判断可行性时，不保存正式生成结果；保留旧版本并返回可解释失败。`route.partial/unavailable` 可用于历史导入或只读展示，不能被首版生成提交器当作已核验路线。禁止仅凭存在坐标就推导地点开放、预约成功或价格已确认。

### 4.4 现有前端类型如何转换

| 前端字段 | 后端来源/变化 |
| --- | --- |
| `PlanProject.id/name/createdAt/updatedAt` | 容器同义字段；名称独立于目的地 |
| `PlanProject.trip` | 当前 `itinerary` 的展示投影；接入前必须支持 null 空状态 |
| `revisions[]` | 版本摘要列表；当前页与历史详情分开缓存，不在列表中加载每份完整快照 |
| `finalRevisionId` | `final_revision_id`；不通过最后一条版本推断 |
| `draft` | 新服务端写入没有未归档行程；仅保留旧数据迁移兼容，不作为正式状态 |
| `requests[]` | 未解决要求列表，新增 `id/status`，移除按 ID 执行 |
| `pending` | 从 `active_run/pending_request` 派生；新增运行 ID、要求 ID，不能只保存文字 |
| `Message.time/revisionId` | `created_at` 格式化为时间；`revision_id` 对应结果入口 |
| `TripDay.distance` | `route.distance_m / 1000` 展示；未知为“待核实” |
| `Activity.cost` | 已知时从 `estimated_cost` 转展示数值；未知时需要可空类型，不能强制转零 |
| `Activity.point` | 旧样本继续是 SVG 点；正式响应用 `place`，须更换/适配地图组件 |
| `Activity.time` | 服务端结构化时间生成的展示字段 |

地图两种数据不能混用：保留演示 SVG 时由前端单独投影到画布，或换真实地图 SDK；后端不为适配当前 SVG 保存像素坐标。静态园林封面可暂时沿用苏州素材，后端无须生成图片。

## 5. 接口总表

以下“必需”均针对首版完整接入；列表、消息、要求和版本采用分页，前端必须处理 `next_cursor`。

| # | 方法与路径 | 用途 | 主要业务模块 |
| --- | --- | --- | --- |
| 1 | `GET /api/v1/trips` | 列表、搜索、卡片汇总 | trip_service |
| 2 | `POST /api/v1/trips` | 创建计划容器 | trip_service |
| 3 | `GET /api/v1/trips/{id}` | 详情与刷新恢复 | trip_service |
| 4 | `PATCH /api/v1/trips/{id}/days/{day_id}/activities/{activity_id}` | 手动修改活动并自动归档 | revision_service |
| 5 | `GET /api/v1/trips/{id}/revisions` | 版本摘要列表 | revision_service |
| 6 | `GET /api/v1/trips/{id}/revisions/{revision}` | 指定历史快照 | revision_service |
| 7 | `PUT /api/v1/trips/{id}/final-revision` | 选定已有版本 | revision_service |
| 8 | `GET /api/v1/trips/{id}/messages` | 分页对话历史 | conversation_service |
| 9 | `GET /api/v1/trips/{id}/requests` | 未解决调整清单 | conversation_service |
| 10 | `DELETE /api/v1/trips/{id}/requests/{request_id}` | 移除清单项 | conversation_service |
| 11 | `POST /api/v1/trips/{id}/runs:stream` | 生成、对话修改与重试 | planning_service |
| 12 | `GET /api/v1/runs/{run_id}` | 查询执行状态及正式结果 | run_service |
| 13 | `POST /api/v1/runs/{run_id}/cancel` | 请求停止运行 | run_service |

注意：版本详情路径中的 `{revision}` 沿用架构文档路径，具体取值约定为**版本 ID**，不是版本序号；前端 `?revision=` 也传同一 ID。`base_revision` 则始终是整数序号。框架路由参数可在代码中命名 `revision_id`，外部 URL 结构不变。

## 6. 逐项接口与对应业务逻辑

### 6.1 计划列表

`GET /api/v1/trips?q=苏州&limit=20&cursor=...`

- `q` 可省略，去除两端空白后最长 100 字；按计划名称或目的地包含匹配，不将输入拼成 SQL。
- `limit` 默认 20，范围 1–100；按 `updated_at DESC, id DESC` 做不透明游标分页。
- 返回 `{items, next_cursor, total_count, matched_count}`；前两个计数分别为当前用户全部计划数及搜索匹配数。列表翻页期间发生更新可能导致卡片移动，前端按 ID 去重，重新进入时从第一页刷新，不承诺跨请求快照。
- 每个摘要含 `id,name,created_at,updated_at,row_version,requirements,latest_revision_id,final_revision_id,revision_count,message_count,has_pending_request,active_run,display_summary,recent_revisions`。
- `recent_revisions` 最多两条，按版本倒序，每项为 `{id,revision,title,created_at}`；`display_summary` 含 `destination,start_date,day_count,travelers,budget,currency`。
- 卡片概况优先从最终版本提取，否则从最新版本提取，尚无版本则从需求提取。最近两份结果始终按最新版本排序，不围绕最终方案重新排列。
- `message_count` 只统计已持久化的用户/助手消息，不含内部模型消息和流式片段。汇总批量查询，不对每个卡片调用模型或地图。

### 6.2 创建计划

`POST /api/v1/trips`，必需请求头 `Idempotency-Key`。请求示例：

```json
{
  "name": "周末苏州慢游",
  "destination": "苏州",
  "start_date": "2027-03-12",
  "day_count": 3,
  "travelers": 2,
  "budget": "3000.00",
  "currency": "CNY",
  "preferences": []
}
```

校验名称去空白后 1–40 字、真实日历日期、1–5 天、1–12 位整数人数和预算范围/小数位。日期范围暂沿用表单的 2026-01-01 至 2100-12-28，并确保最后一天不超过 2100-12-31；不把页面默认日期硬编码为后端默认。历史日期可用于记录和回看，新生成的未来旅行需提供适用日期，不伪造过去的实时数据。

`preferences` 可省略或为空，最多 20 项、每项去空白后 1–100 字。金额最多两位小数，额外字段和前端自行提交的版本/最终指针均拒绝，不做隐式写入。

地点服务规范化全国国内目的地并做行政区消歧；“苏州/苏州市”只是归一示例，不是允许名单。歧义目的地可以先创建需求容器，在生成前要求补充；已确定境外范围则拒绝。客户端不传任意坐标。服务端补默认 `budget_scope="group_excluding_intercity"`、时区及 owner，转换为 Agent 输入时按其契约组装嵌套需求。

在一个短事务内创建计划和确定性的欢迎消息。返回 `201`、详情对象及 `Location`。此时 `latest_revision=0,itinerary=null,final_revision_id=null`，欢迎消息 `revision_id=null`。不创建“初始行程”快照，不自动调用模型。前端跳转后提供“生成行程”按钮，复用第 6.9 节接口。

最小创建响应示例（ID 为说明用占位值）：

```json
{
  "id": "trip-example-1",
  "name": "周末苏州慢游",
  "requirements": {
    "destination": "苏州",
    "start_date": "2027-03-12",
    "day_count": 3,
    "travelers": 2,
    "budget": "3000.00",
    "currency": "CNY",
    "budget_scope": "group_excluding_intercity",
    "timezone": "Asia/Shanghai",
    "preferences": []
  },
  "created_at": "2026-11-04T03:00:00Z",
  "updated_at": "2026-11-04T03:00:00Z",
  "row_version": 1,
  "latest_revision": 0,
  "latest_revision_id": null,
  "final_revision_id": null,
  "itinerary": null,
  "active_run": null,
  "pending_request": null,
  "revision_count": 0,
  "message_count": 1
}
```

幂等重放返回首次保存的响应，不重复创建计划；同一 key 不同正文返回 `409 IDEMPOTENCY_KEY_REUSED`。相同名称允许创建不同计划，名称不是唯一键。

### 6.3 计划详情

`GET /api/v1/trips/{id}`，返回第 4.2 节容器对象。`itinerary` 只包含最新正式快照，`requirements` 是最新规范化需求，不随浏览历史版本改变。

详情还返回 `revision_count,message_count`。消息、版本与要求通过各自分页接口获取，避免把工作区或所有快照塞入一次详情响应。首次打开可并行加载详情及三个集合；只有历史视图才另取指定版本。

无版本时显示生成入口；存在活动运行时显示状态并查询运行，不重复启动。查不到本身份拥有的计划返回 404；网络失败不是“项目不存在”。

### 6.4 手动编辑活动

`PATCH /api/v1/trips/{id}/days/{day_id}/activities/{activity_id}`，必需 `Idempotency-Key`：

```json
{
  "base_revision": 2,
  "title": "午餐 · 清淡苏帮菜",
  "description": "少油少盐，价格与营业时间出发前再核实。",
  "start_time": "12:00",
  "end_time": "13:00"
}
```

- `base_revision` 必填；其余字段按 PATCH 语义可省略，至少提供一个；标题非空且 ≤45 字，笔记 ≤180 字。拒绝额外字段。
- 时间必须成对提供且开始早于结束；当前任意文本 `time` 编辑器需改为时间输入，不能仅保存字符串再宣称已完成可行性校验。
- 只允许基于最新版本编辑。按 trip/day/activity 三层归属查找，不能修改其他计划活动；存在活动运行返回 `409 RUN_ACTIVE`。
- 标题是用户活动别名，不能借改标题悄悄换地点。`place/location/cost/kind` 不在本接口可写范围，替换地点交给助手调整。
- 用最新快照复制后应用字段，检查时序与已知交通缓冲；只改文字无需再次查询地图。若所需数据缺失则带校验警告，不显示“实时路线已核验”。
- 与原快照无变化返回 `200 {changed:false, latest_revision, latest_revision_id, row_version}`，不新建版本、不更新时间。
- 有变化时在事务内重新检查基础版本和运行锁，写完整新快照、递增序号和聚合锁，保留最终指针。返回 `200 {changed:true, revision:<版本详情>, row_version}`。
- 不因手动编辑自动生成助手消息。保存失败保留前端表单输入，不能先关闭弹窗并宣称自动记录成功。

### 6.5 版本列表与详情

`GET /api/v1/trips/{id}/revisions?limit=20&cursor=...`：按 `revision DESC` 分页，返回 `{items,next_cursor,total_count}`。摘要不含完整 `itinerary`。

`GET /api/v1/trips/{id}/revisions/{revision}`：返回不可变版本详情；检查版本属于该计划。无效 ID 返回 404，前端显示“版本不存在”，不静默回退最新行程。

历史页只替换当前显示的行程及弹窗数据，对话始终是整个计划的历史；前端禁用手动编辑和发送调整。首版后端修改入口也只接受最新 `base_revision`，不提供从历史分叉编辑能力。版本读取不更新计划 `updated_at`。

### 6.6 选为最终方案

`PUT /api/v1/trips/{id}/final-revision`，必需 `Idempotency-Key`：

```json
{"revision_id":"rev-example-2","expected_row_version":8}
```

检查目标属于本计划、已正式提交，且不存在活动运行；在短事务内检查 `row_version` 后更新 `final_revision_id`。允许选择旧版本；不覆盖 `latest_revision_id`、不改变需求、不新增快照。

返回 `200 {trip_id,final_revision_id,latest_revision_id,row_version,updated_at}`。同 key 重放返回原结果；新 key 重复选择相同版本时，若期望锁版本匹配则是无变化成功，否则返回冲突供刷新。首版不提供清空最终指针入口。

“选定并返回”必须等待成功才导航；失败留在原页并显示重试。跳过选择返回不调用本接口。`expected_row_version` 取最近详情，冲突后刷新，不能用旧请求静默覆盖另一页面的选择。

### 6.7 消息与待处理要求

`GET /api/v1/trips/{id}/messages?limit=50&before_sequence=...`：默认取最近 50 条，最大 100；返回 `{items,next_cursor,total_count}`。`items` 按 `sequence ASC` 便于渲染；`next_cursor` 为更早一页的 `before_sequence` 值。序号在计划内单调递增，消息内容按纯文本处理。

`GET /api/v1/trips/{id}/requests?day_id=2&status=unresolved&limit=50&cursor=...`：默认只列未解决要求，`day_id` 可省略。`status=unresolved` 是查询别名，包含 `pending/running/needs_input/failed/cancelled/interrupted`；已解决及已移除项不在当前清单。按 `created_at ASC,id ASC` 分页。

要求持久化状态为 `pending/running/needs_input/resolved/failed/cancelled/interrupted/removed`。`generate` 要求的 `day_id=null`；当前页面的 `modify` 必须指定目标天。要求不是消息，移除要求不删消息、不删版本。

### 6.8 移除待处理要求

`DELETE /api/v1/trips/{id}/requests/{request_id}`，必需 `Idempotency-Key` 与查询参数 `expected_row_version`，返回 `204`。

检查资源归属和聚合锁；当前计划存在活动运行时统一拒绝移除，避免清单变化与上下文读取竞争。将要求标记 `removed`，不物理删除。已经移除且锁版本匹配时无变化成功；已解决项返回 `409 REQUEST_ALREADY_RESOLVED`，不把已完成结果误标为待处理。

删除只是放弃未处理要求，不代表撤销已经提交的版本。继续调整按钮只显示仍可重试的要求，不能重试已移除项。

### 6.9 发起生成或修改

`POST /api/v1/trips/{id}/runs:stream`，请求示例：

```json
{
  "client_request_id": "browser-generated-uuid",
  "base_revision": 2,
  "operation": "modify",
  "day_id": 2,
  "instruction": "第二天午餐清淡一点，其他安排尽量保留"
}
```

首份生成：`base_revision=0,operation="generate",day_id=null`，`instruction` 可为空，需求来自已保存容器；已有版本再 `generate` 返回 `409 ITINERARY_ALREADY_EXISTS`。修改：`operation="modify"`、基础版本必须 >0、当天必须存在，指令去空白后 1–500 字。

首次生成省略指令时，保存确定性的用户消息“请根据已保存的出行需求生成行程”，不创建空白对话。本次运行的输入快照同时记录规范化需求，便于追查它实际依据了哪些参数。

当前天是服务端强制的修改边界，首版不支持一句话跨多天修改。指令要求修改其他日期或全程预算/人数等全局属性时，返回 `input.required` 提示当前支持范围，不擅自扩大授权。

重试已有要求时请求改为 `{client_request_id,base_revision,request_id}`，不再提交 operation/day/instruction；服务端从要求读取原内容。要求必须属于本计划、可重试且没有活动运行。基础版本是**当前最新版本**，防止在旧快照上覆盖后来手动修改；`generate` 要求在已有行程时不可再重试。

使用新 `client_request_id` 表示用户明确发起新尝试，同一要求关联多次运行；使用相同 ID 是网络层幂等重试，不得再次调用模型。确需补充回答时，发送新的 modify/generate 请求并带 `reply_to_request_id`（必须为本计划 `needs_input` 要求），新用户消息与原要求关联；操作/目标天须匹配，从原要求加上本次回答构造上下文。这与“原样重试”互斥。原要求状态进入 running，完成或失败后按本次结果更新，不新建重复清单项。

接收顺序：

1. 认证/开发身份、资源归属、正文格式检查。
2. 查 `(trip_id,client_request_id)`；已存在且正文摘要相同则返回已有运行引用，正文不同则 409。
3. 对新运行检查基础版本、操作范围和计划活动运行限制。
4. 在同一事务内创建或复用要求、创建用户消息（原样重试不重复创建）、创建 running 运行并占用计划执行名额。
5. 开始 SSE；执行模型和查询时不持有数据库事务。
6. 强制校验、有限修复后，通过事务提交正式结果或终态，再发对应事件。

首次接受返回 `200 text/event-stream`。重复请求返回 `200 application/json {run_id,status,result_revision_id}`，前端按 Content-Type 分支处理并查询运行，不启动第二条执行流。这是对已有“重复请求返回运行引用”约定的具体化；未实现事件回放。

入口前校验失败使用正常 HTTP 错误，不能先开 SSE 再试图改变状态码。进入 SSE 后业务失败通过事件和最终运行状态表达。

### 6.10 查询与取消运行

`GET /api/v1/runs/{run_id}`：返回第 4.2 节运行对象，包含可空 `result_revision_id/reply_message_id/input_required/error`。按 trip 的 owner 检查；同身份只可查询自己的运行。

前端可在断流后每 1–2 秒查询，终态立即停止；超过总运行截止时间加清理宽限仍未终结时显示异常并允许手动刷新，不自动重复 POST。结果已提交时重新读取版本/详情/消息，即使最终 SSE 丢失也能恢复。

`POST /api/v1/runs/{run_id}/cancel`：无正文，操作本身幂等。running 改为 cancelling 并通知执行协程；返回 `202 {run_id,status:"cancelling"}`。终态返回 `200 {run_id,status}`，不更改结果。事务内状态判断保证“提交已成功”不会被取消覆盖。

前端点击停止时先尽力发取消请求，再终止本地流读取；不能仅 AbortController 就展示“服务端已停止”。离开页面同样尽力取消；服务端识别断连后取消下游并整理终态。首版没有 `resume` 接口，cancelling 也不允许立即发新运行。

## 7. Agent 业务流程与运行协议

### 7.1 模型和普通业务代码的职责

固定执行顺序：读取最新需求和版本 → 准备当前目标天与必要对话 → 单 Planner 查询并生成结构化候选 → 服务端回填真实地点 → 强制校验 → 最多一次修复 → 提交。

| 工作 | 执行者 | 约束 |
| --- | --- | --- |
| 理解自然语言、选择查询与活动组合 | LangChain Planner | 不直接写数据库，不生成权威坐标 |
| 地点/天气/路线查询 | tools → integrations/services | 来源、有效期、超时、可追溯 POI ID |
| 时间、费用、候选集合、修改范围校验 | validators | 每次提交必经，不由模型决定是否调用 |
| 版本、消息、要求、最终方案持久化 | services + crud | 事务控制；正式提交后才发成功事件 |
| 未知信息与不可满足需求 | service + Planner 说明 | 不把无法验证写成已核验，不伪造成功 |

局部修改将目标天草稿合并到最新快照；除目标天外的数据由程序逐项比较并保护。新活动生成新 ID，保留活动沿用 ID，不能把同一个 ID 赋给完全不同地点。地点依允许候选集合和供应商 ID 回填；坐标、名称与费用来源不信任模型自由文本。

初始上限沿用架构草案：每运行最多 8 次模型调用、12 次外部工具调用、120 秒总时限、最多一次结构化修复，所有重试与修复共用预算。它们是待配置和实测的起点，不是性能承诺。外部超时应短于剩余总时限；失败重试只用于可恢复查询错误。

### 7.2 运行与要求状态

运行状态流转：

```text
running ──提交成功/无变化/需补充──> succeeded
   │
   ├──不可恢复错误─────────────> failed
   ├──取消请求──> cancelling ──> cancelled
   └──进程退出后清理───────────> interrupted
```

提交成功是 `succeeded + outcome=updated`；确定已满足且无变化为 `unchanged`；需补充为 `input_required`。最后一种表示**本轮已结束**，不是仍在等待的后台协程。下一条补充输入是新运行。

要求状态与运行结果：

| 运行结果 | 要求状态 | 是否新版本 |
| --- | --- | --- |
| updated | resolved | 是 |
| unchanged，确认要求已经满足 | resolved | 否 |
| input_required，语义不明/能力范围不符 | needs_input | 否 |
| failed / cancelled / interrupted | 同名状态 | 否 |
| 人工移除 | removed | 否 |

无变化但无法确认要求已满足时不能误标 resolved，应请求补充。每次运行只更新自身关联要求，不顺便批量解决当天其他清单项。

进程启动时将本进程遗留的活动运行清理为 interrupted；取消中的遗留运行也可标 interrupted，避免一直 busy。活进程还需按截止时间检查失联运行。首版单 API 实例，该逻辑不能直接用于多实例，后续需租约与执行者归属。

### 7.3 SSE 事件

事件结构沿用架构约定：`{run_id,seq,type,timestamp,payload}`。`seq` 在单运行内递增，前端仅接收当前运行并丢弃重复序号；它用于单次连接合并，不承诺持久回放。

```text
event: stage.changed
id: run-example-1:3
data: {"run_id":"run-example-1","seq":3,"type":"stage.changed","timestamp":"2026-11-04T03:00:00Z","payload":{"stage":"searching_places","message":"正在查询地点"}}

```

| 事件 | payload 关键字段 | 持久化/前端行为 |
| --- | --- | --- |
| `run.started` | `request_id,user_message_id,base_revision` | 已接收；以正式消息 ID 替换乐观消息 |
| `stage.changed` | `stage,message` | thinking/planning 等进度，由真实阶段驱动 |
| `reasoning.delta` | `text` | 运行期过程展示，默认折叠、不持久化；断线不补发 |
| `tool.started/tool.finished` | `tool_execution_id,name,status` | 简短查询进度，不暴露密钥/原始供应商响应 |
| `message.delta` | `message_id,delta` | 暂存面向用户回复，不写为正式行程 |
| `input.required` | `request_id,fields` | 结束本轮、显示补充问题，不产生版本 |
| `itinerary.committed` | `revision_id,revision` | 已提交，重新加载详情/快照 |
| `run.failed` | `error` | 已终结失败，保留旧行程和要求 |
| `run.cancelled` | `reason` | 已确认取消，而非仅收到取消请求 |
| `run.completed` | `status,outcome,result_revision_id,reply_message_id` | 最终事件，停止 busy、刷新相关集合 |

正常结束发 `run.completed`；失败/取消先发对应事件再发 completed。进程崩溃无法保证发出任何终态事件，必须通过查询恢复。心跳用 SSE 注释行，不增加业务消息。`reasoning.delta` 只用于运行期观察，不写入消息、版本或证据；前端默认折叠，断线恢复后不补发推理内容。

成功修改典型顺序：started → stage/tool → 校验 → 数据库提交 → itinerary.committed → message.delta → completed。流式文本可在提交前用于状态说明，但“已成功修改”只能在提交后发出；最终完整回复在终态事务内持久化，片段丢失后可通过消息接口恢复。

SSE 以 `fetch` POST 解析，处理 UTF-8 跨分块、多行 data、心跳、非 SSE 错误与 EOF；一个网络 chunk 不等于一个事件。收到 committed 后若用户仍在历史页，仅刷新缓存，不强制切走正在看的版本。

### 7.4 重试、继续与对话留存

新指令事务成功后用户消息立即持久化，模型失败不删除。重试同一要求复用源用户消息；补充回答新增一条用户消息。助手完整回答在运行结束时保存，成功回答可关联新版本，无变化、失败说明与补充问题的 `revision_id=null`。

为简化首版恢复，每轮最多持久化一条最终助手回复；内部工具消息不进入对话。`message.delta.message_id` 与最终保存的助手消息 ID 一致；取消/失败时用正式终态说明替代未完成预览，前端清理未持久化片段。

“停止”保留要求，返回后可以重新尝试；“移除要求”才表示不再处理。重试时展示“重新尝试”，避免暗示会从模型上次 token 或工具调用位置恢复。

## 8. 存储模型、事务与幂等

### 8.1 建议数据库实体

| 表 | 核心内容 | 关键约束 |
| --- | --- | --- |
| `trips` | owner、名称、需求 JSONB、最新版本序号/ID、最终 ID、row_version、时间 | 引用版本必须属于本 trip；最新指针与序号一致 |
| `trip_revisions` | trip、版本号、父版本、来源、标题、完整 JSONB 快照、校验状态、来源 run | `(trip_id,revision)` 唯一；有值的 source_run 唯一 |
| `messages` | trip、sequence、role、content、要求/run/版本关联、时间 | `(trip_id,sequence)` 唯一，关联资源同 trip |
| `trip_requests` | 原始指令、operation/day、源消息、状态、last_run | 源消息同 trip；移除为状态更新 |
| `runs` | trip、要求、client_request_id、规范化输入/需求快照及摘要、基础版本、状态/阶段、结果及错误、用量 | `(trip_id,client_request_id)` 唯一；每 trip 最多一个 running/cancelling |
| `tool_executions` | run、工具、耗时、状态、脱敏摘要 | 只存必要审计，不记录密钥 |
| `idempotency_records` | owner、操作与路径、key、输入摘要、原 HTTP 状态和响应 | `(owner_id,operation,key)` 唯一 |

计划内同时存在“源消息→要求→运行”关联，创建时可用预分配 UUID 和同一事务分步补关联；不要在每次写子表时各自提交。数据库外键或组合约束防止跨计划引用，不只依赖路由检查。

不需要首版把每个活动拆成关系表；不可变 JSONB 快照更符合当前完整回看需求。版本数量增长后再评估存储优化，不能以共用可变对象替代快照。

### 8.2 事务边界

| 操作 | 必须原子完成 |
| --- | --- |
| 新建计划 | 容器 + 欢迎消息 + 幂等结果 |
| 接受新要求 | 要求 + 用户消息 + 运行 + 活动运行名额 |
| 手动编辑 | 新版本 + 最新指针 + 聚合锁 + 幂等结果 |
| Planner 成功 | 重新验证未取消/基础版本 + 新版本 + 最新指针 + 正式助手回复 + 要求解决 + 运行成功 |
| 无变化或需补充 | 正式回复 + 要求对应状态 + 运行终态，不写版本 |
| 失败或取消 | 终态回复 + 运行状态 + 要求状态 + 释放活动名额 |
| 选定最终方案 | 检查归属/锁版本 + 最终指针 + 幂等结果 |
| 移除要求 | 要求状态 + 聚合锁 + 幂等结果 |

外部模型与地图请求在事务外执行。最终提交再次检查 `latest_revision=base_revision`，即使前端已禁用并发，也不能省略数据库检查。短事务锁定同一 trip 行，串行处理运行占位、版本提交与取消状态判断，统一锁顺序降低死锁风险。

### 8.3 幂等、冲突与取消竞争

- 同步写接口的 `Idempotency-Key` 必填，建议 UUID；重放检查先于当前版本检查。同 key 相同请求返回首次结果，包括原 row_version；客户端若需要最新状态应另行 GET。
- key 按 owner、操作和路径作用域隔离；输入摘要包括规范化正文与相关路径/查询参数，不包含密钥。相同 key 不同输入返回 409，不再执行业务。
- 幂等记录与业务结果同事务提交，首版保留与资源同生命周期，避免响应丢失后因短期清理而重复写入；并发相同 key 依唯一约束等待/读取首次结果。
- 运行的幂等记录由 runs 自身承担，不能因失败就删除。相同 ID 重发只返回原运行；明确重新尝试才换新 ID。
- 活动运行限制同时由事务检查及数据库唯一约束兜底，不依靠进程内布尔变量。
- 取消和成功提交争用同一事务边界：先提交成功则 cancel 返回 succeeded；先进入 cancelling 则结果不能再写为成功。
- 运行未结束时禁止手动编辑、最终选择和要求移除。UI 的 busy 是提示，服务端限制才是最终保障。
- `base_revision` 冲突不自动换新版本重跑；`row_version` 冲突也不自动覆盖，先刷新再由用户确认重试动作。

## 9. 错误契约与数据可信度

### 9.1 统一错误对象

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "行程已经更新，请刷新后再调整",
    "details": {"expected_revision":2,"actual_revision":3},
    "retryable": false
  },
  "request_id": "http-correlation-id"
}
```

`request_id` 是 HTTP 追踪标识，与 `trip_requests.id`、`client_request_id` 不同；运行中的 error 复用 `{code,message,details,retryable}`。不要将堆栈、模型密钥或供应商原始错误暴露给页面。

| HTTP/事件 | 错误码示例 | 页面处理 |
| --- | --- | --- |
| 422 | `VALIDATION_ERROR,UNSUPPORTED_DESTINATION` | 定位字段，保留输入；目的地错误指明确不在国内产品范围，不代表国内数据服务缺失 |
| 404 | `TRIP_NOT_FOUND,REVISION_NOT_FOUND,REQUEST_NOT_FOUND,RUN_NOT_FOUND` | 显示资源不存在，不回退虚构样本 |
| 409 | `REVISION_CONFLICT,ROW_VERSION_CONFLICT` | 刷新状态，保留未提交内容 |
| 409 | `RUN_ACTIVE` | 返回已有 run_id，显示处理中 |
| 409 | `IDEMPOTENCY_KEY_REUSED,REQUEST_NOT_RETRYABLE,ITINERARY_ALREADY_EXISTS,REQUEST_ALREADY_RESOLVED` | 显示具体原因，不自动重试 |
| 429 | `RATE_LIMITED` | 提示稍后再试，不快速循环 |
| 503 | `DEPENDENCY_UNAVAILABLE` | 入口不可用时失败；流内使用 run.failed |
| run.failed | `MODEL_TIMEOUT,TOOL_TIMEOUT,CALL_BUDGET_EXCEEDED,ITINERARY_INVALID,ITINERARY_INFEASIBLE,UNSUPPORTED_CAPABILITY,POI_UNVERIFIED,ROUTE_UNVERIFIED` | 保留旧版本和要求；可恢复错误提供重试；不可行须有硬约束冲突证据 |
| 500 | `INTERNAL_ERROR` | 返回追踪 ID，输入保留 |

标准请求体校验错误也要转换到这一结构，字段错误放 `details.fields`。`retryable=true` 是允许用户重新尝试的提示，不授权前端自动再次付费调用。SSE EOF 没有 completed 事件表示状态未知，应 GET 运行确认。

### 9.2 可信度与降级原则

- 候选地点、名称、坐标与来源共同保存；不接受模型杜撰 POI。活动标题可编辑，权威地点名称不可被标题覆盖。
- 天气超出有效期返回 unavailable 与警告，不用季节经验充当逐日预报。
- 价格和住宿未知须明确列出；已知小计低于预算不能证明全程不超预算。
- 路线工具不可用时可以给解释，但本首版不提供“未核验草稿变正式版本”的快捷路径；正式结果需满足提交规则。
- 生成失败、校验失败、断流和保存失败均不得覆盖原有效行程或自动更换最终方案。

## 10. 后端模块落点

保持现有目录骨架，不增加 `backend/app/` 或通用工作流框架。

| 目录/建议文件 | 职责 |
| --- | --- |
| `backend/main.py` | FastAPI 入口、路由注册、运行清理生命周期 |
| `routers/trips.py,revisions.py,conversations.py,runs.py` | HTTP、参数、SSE 及统一错误映射 |
| `schemas/trip.py,itinerary.py,revision.py,message.py,request.py,run.py,event.py` | API 与内部结构化数据，拒绝越权可写字段 |
| `services/trip_service.py,revision_service.py,conversation_service.py` | 容器、快照、最终选择、对话与要求用例 |
| `services/planning_service.py,run_service.py` | 调用编排、预算、取消、终态提交、事件转换 |
| `agents/planner.py` | LangChain create_agent、Prompt 与结构化草稿适配 |
| `tools/places.py,weather.py,routes.py` | 工具参数及结果适配；复用查询服务/客户端 |
| `integrations/chat_model.py,amap.py` | 模型与地图供应商调用、超时及错误转换 |
| `validators/itinerary.py,budget.py,scope.py` | 纯规则；地点、时间、费用、局部修改保护 |
| `models/,crud/,config/,migrations/` | 表、查询、连接与会话、迁移；CRUD 不自行 commit |
| `tests/` | 业务边界、接口契约、并发与外部替身验证 |

文件名是实现落点建议，按实际规模合并也可。业务服务不依赖 SSE 连接对象，Planner 不直接持有数据库会话，以便后续接入 LangGraph 或 Worker 时复用。

## 11. 前端接入改造与旧数据处理

### 11.1 必须改造的地方

1. 将 `workspaceStore` 的整包本地写入替换为 API 查询与命令，后端事实来源不再复制成第二份可独立改写的工作区。
2. 计划列表改读服务端摘要；处理初始加载、空列表、搜索失败及分页。计数来自服务端，不取当前一页长度冒充总数。
3. 新建后支持 `itinerary=null`；不能继续直接访问 `trip.days[0]` 或 `at(-1)`。显示需求概况和“生成行程”入口。
4. 将版本摘要与快照缓存分开；历史 ID 无效必须提示。`current/latest` 与 `final` 的入口继续保持当前语义。
5. 手动编辑器改为结构化时间字段，提交时携带基础版本与幂等 key；成功后关闭，失败保留表单。
6. 对话从分页消息读取，乐观用户消息用临时 ID，收到 accepted/重新查询后按正式 ID 去重；同一 request 重试不追加相同用户消息。
7. SSE 进度替换演示计时和假逐字流；无终态事件先查运行，取消与断流不等于业务成功。
8. 要求列表改用要求 ID，展示可重试/需补充状态；生成要求没有 day_id，放全局提示区而非任意一天。
9. 地图适配 `place/route`，费用支持 unknown，出行弹窗使用当前查看快照的服务器汇总；最终版本引用更新只在成功后生效。
10. 页面离开先尽力请求取消；侧栏收缩及手机切换不取消运行。刷新后读取 active_run/pending_request 恢复提示。
11. 顶部“重试保存”改成针对具体失败请求的重试，复用该请求幂等 key；不能再次上传整包本地工作区。

### 11.2 本地历史数据策略

首版不自动把 localStorage 上传正式库。保留旧键用于演示和备份，首次切换真实服务时明确展示“服务端计划与本机演示记录独立”。服务端为空显示空状态，不自动创建苏州样本。

后续若需要导入，应另行设计显式导入流程：重新分配资源 ID、校验版本/最终引用、标注来源为历史演示、拒绝将 SVG point 当地理坐标。旧 draft 需要先独立归档；不可直接用通用创建接口塞入整个对象。本次不把导入能力计入首版 13 个接口。

## 12. 实施顺序与验收清单

### 12.1 分阶段交付

| 阶段 | 交付内容 | 可观察结果 |
| --- | --- | --- |
| 0：独立 Agent | State/输入输出、校验器、查询替身、国内目的地解析与真实调用评估 | 终端可独立生成与修改，经规则及样例验证后接业务 |
| A：契约与数据库 | Schema、迁移、统一错误、归属、幂等 | 明确 Agent 结果与不可变快照的映射 |
| B：容器与读取 | 创建/列表/详情、欢迎消息、空状态 | 刷新后仍有独立计划，空行程可正常显示 |
| C：版本业务 | 版本读取、编辑、最终选择 | 可用测试夹具验证，新旧版本互不覆盖 |
| D：运行闭环 | 要求、消息、run 状态、SSE、取消 | 用替身 Planner 验证状态与提交，无付费依赖 |
| E：接入已验证 Planner | 复用独立 Agent、接入执行控制与提交事务 | 首次生成及当天修改有真实来源，不重复编写 Agent |
| F：完整联调 | 分页、断流、冲突、返回选择与地图 | 当前页面动作全部有明确成功/失败路径 |

阶段 C 的数据可由测试夹具初始化，不通过生产接口生成伪造正式行程。业务阶段 E 接入真实 Planner 之前界面明确标注模拟服务；阶段 0 的独立真实 Agent 评估不等于界面已经接入。

### 12.2 必须覆盖的业务场景

| 场景 | 预期结果 |
| --- | --- |
| 空库打开、创建后刷新 | 空列表/空行程可用，无样本冒充结果 |
| 创建响应丢失后用同 key 重试 | 只创建一个计划与一条欢迎消息 |
| 首次生成失败/成功 | 失败无版本；成功只产生第 1 版 |
| 两个计划分别对话 | 消息、要求、运行、版本互相隔离 |
| 同一请求重复提交/并发提交 | 只有一次实际执行；不同请求同 trip 拒绝并发 |
| 当天修改模型返回其他天变化 | 拒绝越界草稿，其他天保持原内容 |
| 手动有效编辑与无变化提交 | 前者新版本，后者不增加版本 |
| 改标题、未改地点 | 地点身份、坐标与权威名称保持原值 |
| 同 key 不同正文/旧基础版本提交 | 返回冲突，无额外写入或模型调用 |
| 选中旧版本后继续调整 | 最终指针保持，最新版本单独推进 |
| 最终写入失败后选定并返回 | 留在页面，不显示保存成功 |
| 非法/跨计划版本与活动 ID | 返回 404，不泄漏其他资源 |
| 停止、取消与提交同时发生 | 只产生一致终态，不出现成功后又取消 |
| 已提交但最后事件丢失 | GET run 得到正式结果并恢复页面 |
| 进程重启时有活动运行 | 标 interrupted，旧版本保留，允许重新尝试 |
| 重试/补充/移除要求 | 原样重试无重复用户消息；补充新增回答；移除不删除历史 |
| 未知价格/远期天气/路线失败 | 费用和天气明确未知；必要路线失败不提交正式版本 |
| 消息/版本/列表超过一页 | 无重复/遗漏的错误排序，数量不混用页长度 |

后端优先用业务规则单元测试、数据库事务/唯一约束集成测试和 API/SSE 契约测试；前端覆盖“创建 → 生成 → 编辑 → 版本回看 → 最终选择 → 停止/重试”的关键流程。真实模型与供应商联调单独记录，不用每次付费请求替代确定性验证。

### 12.3 完成标准与后续演进

首版完成意味着 13 个接口及对应页面接入、数据库提交规则、错误反馈和上述关键边界均可验证；仅有 Agent 返回一段文本不算完成。本文未编写后端实现、未生成 OpenAPI、未执行模型或地图联调。

后续按真实需求扩展多城市串游、全局需求编辑、活动地点替换、登录及配额，再考虑持久后台运行与显式 LangGraph 分支。全国国内范围与 1–5 天已纳入当前 Agent 目标；供应商实际覆盖以集成验证为准。已有行程业务模型不应绑定某一 Agent 运行时。
