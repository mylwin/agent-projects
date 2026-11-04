# 国内旅行 Planner 的 State 与输入输出设计

日期：2026-11-04。状态：设计稿，尚未实现 Agent、Python 模型或工具调用。

最新需求：先独立实现和验证 Agent，再接入后端业务；目的地扩大到全国国内范围，取消苏州白名单。本文细化 [首版接口分析](01-v1-api-and-business-analysis.md)，相关范围与开发顺序以本设计为准；前端当前仍是苏州演示，不代表全国能力已完成。

## 1. 设计结论与范围

一个 Planner 完成“理解需求 → 解析目的地 → 查询证据 → 生成草稿 → 强制校验 → 有限修复 → 返回结果”。普通 Python 调用器管理运行，不要求先设计 LangGraph 业务图。

首版支持选择全国国内目的地，一次规划一个目的地区域。城市、自治州、区县和景区都可作为查询输入，由地点服务解析为可查询区域；省份、“江南”等过大范围和多城市串游需要澄清。全国覆盖与多城市串游是两个维度，后者保留为后续能力，不静默缩成某一城市。

采用 `geo_scope="china_domestic"` 表示产品范围；供应商国家码、行政区码与坐标系独立记录，不把某个供应商代码枚举直接当作产品范围。港澳台等地区若所接工具缺乏数据，应返回明确的能力缺口，不能宣称境外或伪装已有覆盖。当前尚未验证任何供应商的全国可用性。

天数先沿用总体架构的 1–5 天，作为运行策略的可配置上限；人数先为 1–12 人，币种为 CNY。目的地扩大不要求继续受前端 1–3 天控件限制；实现页面接入时再同步更新控件。

核心对象分为五个：

| 对象 | 作用 | 创建/修改方 |
| --- | --- | --- |
| `PlannerInput` | 调用方提供的需求、原行程及本次修改范围 | CLI/未来业务服务；运行内不修改 |
| `PlannerContext` | 配置、查询能力和取消控制 | 宿主创建，模型不能修改 |
| `PlannerRunState` | 本轮解析、证据、草稿、校验和用量 | 调用器、工具适配器、校验器各自负责 |
| `PlannerDraft` | 模型提交的结构化候选或澄清建议 | 模型生成，程序验证 |
| `PlannerOutput` | 经程序判定后的结果、问题或失败原因 | 调用器构建，供 CLI/业务层使用 |

**模型草稿、Agent 执行状态、正式业务版本是三个不同对象。** Agent 返回可供提交的结果；版本号、数据库事务、最终方案与幂等键仍属于未来业务服务。

## 2. 通用数据约定

- 字段统一 `snake_case`；输入和输出带 `schema_version=1`，未来破坏性结构变化再升版本。
- 日期用 `YYYY-MM-DD`，行程结构化时间用本地 `HH:mm`，时区为 `Asia/Shanghai`；证据获取时间及运行时间使用带时区时间戳。
- 金额用十进制字符串，内部 Decimal；距离为整数米、时长为整数秒。未知为 null，不用零表达未知。
- 本设计的 ID 为运行中不透明标识，不假设已存在数据库。地点身份使用 `provider + provider_place_id`，活动身份使用稳定的 `activity_id`。
- 输入缺值允许进入澄清流程；类型错误、无效日历日期、负数金额等在输入校验阶段拒绝，不让模型猜测修正。
- 对外输入、草稿与输出按明确模型校验，拒绝额外字段。下面的类型表是模型规格，不是已可导入运行的 Python 源码。

## 3. 输入 PlannerInput

### 3.1 顶层字段

| 字段 | 类型/默认 | 说明 |
| --- | --- | --- |
| `schema_version` | `1` | 契约版本 |
| `operation` | `generate / modify` | 生成或修改 |
| `instruction` | `str`，默认空串，≤500 字 | 用户本轮原话；原样保留 |
| `requirements` | `TravelRequirements` | 结构化需求；允许信息未齐 |
| `baseline` | `ItinerarySnapshot / null` | 修改时必填，生成时为 null |
| `change_scope` | `ChangeScope / null` | 修改时必填，由调用方授权 |
| `conversation` | `ConversationContext`，默认空 | 有界对话上下文，不是整个工作区 |
| `pending_questions` | `ClarificationQuestion[]`，默认空 | 上轮返回且等待回答的问题，由调用方保留 |
| `clarification_answers` | `ClarificationAnswer[]`，默认空 | 对此前问题的回答，可无数据库参与 |

`baseline` 使用前文行程快照的领域字段；独立运行时 `trip_id` 允许 null，接入业务后由 service 填入。版本号和数据库 row_version 不送入模型作为可写内容，调用方在提交时另行检查。基准快照必须通过结构校验；缺少路线等证据时不能自动视为可信，重新验证所需部分。

### 3.2 TravelRequirements

| 字段 | 类型/默认 | 说明 |
| --- | --- | --- |
| `destination` | `DestinationQuery / null` | 国内目的地区域，不预设苏州 |
| `origin` | `DestinationQuery / null` | 可选出发地；首版不规划往返大交通 |
| `start_date` | `date / null` | 缺失时询问，不能用当天替代 |
| `day_count` | `int / null` | 1–5 天，上限取 Context 策略 |
| `end_date` | `date / null` | 可选，支持用户只给日期区间 |
| `travelers` | `int / null` | 全团人数，缺失时询问 |
| `budget` | `BudgetRequirement / null` | 全团预算及费用口径 |
| `preferences` | `TravelPreferences`，默认空 | 用户明确给出的偏好 |
| `constraints` | `HardConstraints`，默认空 | 必须满足的约束 |

`DestinationQuery={query,province_hint,city_hint,district_hint}`：query 为非空文本，其余为可空用户提示；提示不作为已确认行政区。内部常规单城市路径可以只传 `{"query":"成都","province_hint":null,"city_hint":null,"district_hint":null}`。

`BudgetRequirement={amount,currency,scope}`：amount 为正数金额，currency 固定 CNY，scope 为 `group_excluding_intercity / group_activities_only / group_total`。默认表单口径为第一种；自然语言“预算 3000”若没有约定口径则先询问。`group_total` 若包含当前工具无法估算的住宿/往返，结果列出未知项；不能只核算活动就声称满足总预算。

`TravelPreferences={pace,interests,food_preferences,transport_preferences,notes}`：pace 为 `relaxed/balanced/packed/null`；其余均为字符串列表。没有明确偏好时数组为空，可采用 balanced 并记录假设，不虚构用户画像。饮食偏好不等于可保证餐馆满足特殊饮食要求。

`HardConstraints`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `must_visit` | `DestinationQuery[]` | 必去地点仍需解析、消歧与查询 |
| `avoid_places` | `DestinationQuery[]` | 明确不去地点，由服务解析后执行 |
| `allowed_transport_modes` | `str[]` | walking/transit/driving；空数组表示未限定 |
| `max_daily_walking_m` | `int / null` | 大于零，步行约束依路径和可用路段证据核验 |
| `fixed_activity_ids` | `str[]` | 修改时必须原样保留的基准活动；生成时必须为空 |
| `notes` | `str[]` | 还未形式化的硬约束原话 |

不能把 `constraints.notes` 忽略后宣称约束全部满足；无法转换或验证的硬约束需要澄清或返回未验证结果原因。

### 3.3 规范化与缺失规则

1. 结构化字段与原话一致时合并；关键字段矛盾时提问，不用“最后一个字段”隐式覆盖。
2. 有 start_date 和 end_date 时算包含首尾的天数；同时给 day_count 必须一致。有 start_date 和 day_count 时计算 end_date。
3. 缺少目的地、出发日期、天数、人数、预算金额/口径时产生澄清问题；不在信息未齐时启动大批地点查询。
4. “下周末”等相对日期依据 Context.now 和 timezone 解析，记录解释；“周末两天”有歧义时明确询问日期。
5. 首版生成面向未来行程；过去日期可用于已有行程回看，不生成声称适用于过去的实时天气或价格。请求新规划过去日期时要求确认新日期。
6. 所有默认/推断记入 `Assumption={field,value,reason,source}`，source 为 `user/context/default/derived`。用户明确条件覆盖产品软默认，但不能覆盖执行预算或国内范围策略。

### 3.4 修改范围 ChangeScope

`ChangeScope={day_ids,activity_ids,preserve_other_days}`：day_ids 为非空天序号列表，首版仅允许一项；activity_ids 可为空，表示允许修改该天任意未锁定活动；非空则进一步限到这些活动；preserve_other_days 首版必须为 true。

修改时需求整体沿用 baseline；本轮 instruction 只作用于授权范围。改变目的地、日期、人数或预算口径属于全局需求变更，首版返回澄清/不支持的范围说明，不借修改某一天改写整个行程。目标天不存在、活动不属于目标天或 fixed ID 不属于 baseline 是确定的输入错误。

调用方权限范围不可由 instruction、对话或模型自行放宽。程序在草稿合并后逐项比较其他日期、固定活动及未授权活动。

### 3.5 对话与补充回答

`ConversationContext={summary,recent_turns}`：summary 为可空事实摘要；recent_turns 项为 `{role,content}`，role 只允许 user/assistant。建议最多 12 条、单条 ≤2,000 字、总上下文文本 ≤12,000 字，具体上限由策略控制。工具原文不混入用户消息。

`ClarificationAnswer={question_id,value}`：value 为用户回答字符串，question_id 必须匹配 pending_questions。两个集合均检查 ID 唯一性，未匹配的答案是输入错误；不能仅凭一个任意 ID 恢复状态。答案经过同样类型、范围与冲突校验；新一轮用合并后的完整输入重新运行。pending_questions 只表示解释上下文，不能据此放宽 change_scope 或执行策略。

## 4. 运行上下文 PlannerContext

Context 由宿主创建，不属于用户输入，也不让模型修改。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| `run_id` | str | 一次实际尝试的关联标识，CLI 也可生成 |
| `now` | 带时区 datetime | 相对日期、证据新鲜度判断，测试可注入 |
| `policy` | `RuntimePolicy` | 国内范围、长度与天数上限、调用限制 |
| `capabilities` | `ProviderCapability[]` | 工具覆盖范围、可用模式、是否启用 |
| `model_client` | 运行时对象引用 | 模型服务，不序列化进 State |
| `place_client / route_client / weather_client` | 运行时对象引用 | 查询服务与测试替身 |
| `cancellation` | 取消信号 | 在调用前及提交输出前检查 |
| `emit_event` | 可选回调 | CLI 进度；未来转接 SSE |

`RuntimePolicy` 初值：geo_scope=china_domestic、max_days=5、max_travelers=12、max_model_calls=8、max_external_calls=12、max_repairs=1、max_duration_s=120，以及候选与上下文上限。可增加 max_input/output_tokens 或成本上限；未配置成本上限不等于允许无限调用。

客户端连接、回调、凭证、取消句柄不写 JSON、不放进 Prompt。配置与依赖引用在单运行内稳定；客户端内部连接池等运行时状态独立管理。

`ProviderCapability={provider,tool,region_support,modes,status}` 中 region_support 来源于配置/实际查询，不由模型声称。供应商没有数据与目的地属于国内范围是不同判断。

## 5. 运行状态 PlannerRunState

以下是宿主侧状态结构规格，所有字段在初始化时显式存在。

```text
PlannerRunState
├── schema_version: 1
├── run_id: str
├── phase: RunPhase
├── input: PlannerInput                         # 只读输入快照
├── normalized: NormalizedRequirements | null   # 规范化后才赋值
├── clarification: ClarificationQuestion[]
├── assumptions: Assumption[]
├── destination: ResolvedDestination | null
├── evidence: EvidenceRegistry
├── loop: PlannerLoopState                     # 模型与工具循环
├── draft: PlannerDraft | null
├── candidate: ItinerarySnapshot | null         # 程序合并/回填后
├── validation: ValidationReport
├── repair_count: int
├── usage: UsageLedger
├── tool_executions: ToolExecution[]
├── output: PlannerOutput | null
└── error: PlannerError | null
```

`NormalizedRequirements` 对应输入需求的已确定版本：目的地原始查询、明确日期范围/人数/预算、解析后的偏好与硬约束。**缺必填需求时保持 null，直接 needs_input；不依赖一半为空的对象去生成行程。** 规范化不意味着目的地已解析；地点解析结果独立放 destination。

初始化：phase=received，evidence 三类索引为空，loop.messages 为空，validation.status=not_run，计数为零，其他未产生对象均为 null。每轮独立创建容器，禁止通过可变默认值共享证据或消息。

### 5.1 阶段及字段所有权

| phase | 允许写入的主要字段 | 执行方 |
| --- | --- | --- |
| `received / normalizing` | normalized、assumptions、clarification | 输入解析器与确定性校验 |
| `resolving_destination` | destination、解析证据、能力缺口 | 地点解析服务 |
| `planning` | loop.messages、draft、工具证据 | Planner 与查询适配器 |
| `validating` | candidate、validation | 回填、合并与校验服务 |
| `repairing` | repair_count、修复消息、draft | 调用器发起，Planner 生成 |
| `finished` | output | 调用器按校验结果构造 |
| `failed / cancelled` | error/output | 调用器统一收口 |

phase 是执行阶段，最终业务结果由 output.status 表达。needs_input、unchanged、infeasible 都可以结束在 finished；不能把“已结束”自动等同于“已有正式行程”。

### 5.2 LangChain 循环状态

`PlannerLoopState` 使用 LangChain 的 `AgentState`，至少包含 messages；框架结构化输出写入 `structured_response` 后，由宿主校验并转换成 draft。内部 BaseMessage 和 tool call ID 保持框架格式，不拿前端 Message 数组直接代替。

首版优先保留框架现成状态；确需在工具/中间件间共享字段时再用 AgentState 子类增加 evidence_ids 等少量字段，通过 state_schema 注册。输入/输出边界计划用 Pydantic 校验；它们不等同于框架内部的 TypedDict 状态。

整个 PlannerRunState 是宿主包裹一次规划流程的聚合，不必把它全部塞入 create_agent.state_schema。Context 通过独立运行上下文传入，避免 credentials/clients 或完整工具响应进入可序列化状态。

正常工具结果写入对应 ToolMessage，简明证据摘要可进入模型上下文；结构化注册表由宿主管理。模型不会因为“输出一个 evidence_id”就自动获得创建可信证据的权限。

### 5.3 预算与并发写入

`UsageLedger={model_calls,external_calls,input_tokens,output_tokens,started_at,deadline_at,elapsed_ms}`，用量未知时 token 可为 null。重试、草稿修复、结构化生成和目的地解析全部算入同一运行；使用替身时仍走记账路径。

每次调用前预占名额，完成后记录实际用量；外部查询失败也占一次，不回滚成未调用。deadline 用单调时钟执行，deadline_at 用于日志显示。取消和预算耗尽检查不能只写在 Prompt 中。

external_calls 按实际供应商请求计数，一个工具内部发起多个 HTTP 请求不能只算一次。12 次是沿用的起步配置，5 天多地点规划可能需要更多路线查询；应在真实评估中调整策略或使用供应商支持的批量查询，不能跳过必要校验来满足次数上限。

工具可并行读取，但计数预占、证据登记和状态补丁通过宿主加锁/串行应用，防止超额和后写覆盖。首版不需要为整份 State 自行设计图 reducer。

## 6. 全国目的地解析与工具证据

### 6.1 ResolvedDestination

字段：`destination_id,query,display_name,kind,admin_path,center,boundary_ref,scope_match,resolution_evidence_id,capability_gaps`。

- kind 为 city/prefecture/county/scenic_area；admin_path 为从大区域到当前区域的 `[{level,name,provider_code}]`。provider_code 可空，不假设所有供应商采用同一套行政区编码。
- center 为 `{longitude,latitude,coordinate_system}` 或 null；坐标来自工具查询，不能以一个经纬度矩形判断国内范围。
- scope_match 为 inside/outside/unknown。unknown 先消歧；outside 明确返回范围不支持，不调用国内行程生成。
- boundary_ref 是解析服务可用的区域范围引用，用于候选检索与校验；边界数据不足的景区/跨区地点按解析能力处理，不用中心点硬切矩形。
- capability_gaps 列出 `tool,reason`，例如目的地可解析但步行路线服务无覆盖。

同名“朝阳”、仅给“大理”、一个省份或一个连跨多市的景区：需要根据行政路径、用户提示和供应商结果判断，不依靠字符串 contains。候选地点必须落在解析后的合理规划区域；偏离区域的合理近郊点需明确范围和交通证据，不能任意扩大搜索。

### 6.2 EvidenceRegistry

证据按运行保存，不是长期知识库；采用受控有界字典：

```text
EvidenceRegistry
├── records: dict[evidence_id, EvidenceRecord]
├── places: dict[place_ref, PlaceEvidence]
├── routes: dict[route_key, RouteEvidence]
└── weather: dict[weather_key, WeatherEvidence]
```

公共 EvidenceRecord：`id,kind,provider,tool_execution_id,fetched_at,valid_for,query_summary,status`。kind=destination/place/route/weather，目的地解析的 resolution_evidence_id 指向 destination 类型记录，解析后的区域对象另存 State.destination。status=available/unavailable/out_of_range；无数据也是查询结果，但不能作为“已确认免费/开放”的依据。valid_for 是 `{start,end}` 时间区间或 null，不能把 fetched_at 当作适用日期。

| 类型 | 额外关键字段 | 核验用途 |
| --- | --- | --- |
| PlaceEvidence | place_ref、供应商地点 ID、行政路径、名称、地址、坐标及坐标系、开放/价格事实及各自来源状态 | 地点真实性、同名消歧、范围约束 |
| RouteEvidence | 起终 place_ref、mode、出发时刻/适用日期、distance_m、duration_s、polyline、路线条件 | 时间缓冲、里程、交通方式约束 |
| WeatherEvidence | destination_id、forecast_date、summary、预报有效日期范围 | 按实际预报日期决定能否使用 |

place_ref 为宿主创建的不透明 ID；route_key 含起终地点、方式、时间条件和坐标系；weather_key 含地区和日期。同名地点不是同一 place_ref；两次运行不默认共享过期路线。

每次地点查询先限制结果条数，建议单次 ≤10、运行累计 ≤50；超出预算时返回缺口，不无限增长 State。只向模型投影需要的字段；供应商原始大 JSON 留在客户端调试层，不复制到 Prompt。工具输出中的命令性文本按外部数据处理，不能覆盖系统策略或用户授权。

### 6.3 工具执行记录

`ToolExecution={id,tool_name,args_summary,status,started_at,finished_at,evidence_ids,error}`。status=running/succeeded/failed/cancelled；error 可空，摘要脱敏。保留“查了什么、查到什么、为什么失败”，不记录模型私有思维过程。

运行事件中的 `reasoning.delta` 只用于运行期过程展示，不属于 `ToolExecution`，也不写入证据或正式版本。它默认不持久化；后续前端即使展示也应默认折叠，断线恢复后不补发推理内容。阶段、回复和工具事件仍分别用 `stage.changed`、`message.delta`、`tool.started/finished` 表达。

## 7. 模型输出 PlannerDraft

PlannerDraft 使用 `kind` 区分两种互斥结构：

| kind | 内容 | 用途 |
| --- | --- | --- |
| `proposal` | `days: DraftDay[]`、`user_explanation: str` | 提交候选安排；解释不是校验结论 |
| `clarification` | `questions: ClarificationQuestion[]` | 需求歧义或关键条件不足 |

DraftDay：`day_id,title,description,activities`。日期、人数、预算从 normalized/baseline 由程序填入，模型不能改写。generate 必须包含完整天序列；modify 只包含 change_scope 授权的天。

DraftActivity：`activity_id,place_ref,title,description,kind,start_time,end_time,cost_proposal`。

- 保留活动引用已有 activity_id；新活动 activity_id=null，服务端在合并时分配。保留 ID 不允许同时替换为完全不同地点。
- 地点只能引用本轮允许集合中的 place_ref；自由活动为 null，并标记 kind=free。未知引用直接校验失败，不降级成自由活动。
- 结构化时间成对提供；模型不输出路线距离、坐标和行政区码作为权威事实。
- `cost_proposal={amount,basis,evidence_id,note}`，basis=evidence/planner_estimate/unknown。evidence 模式必须有支持该金额/计价单位的证据；模型估计只能标 estimated，必须说明是每人还是全团，最终统一为全团。unknown 时 amount/evidence_id 为 null。
- 时间待定等软缺口可保留警告；会影响必需交通/固定时段判断的缺口不能以警告绕过硬校验。

模型没有设置 validated、ready 或预算达标的权限；这些字段不在草稿 schema 中。

## 8. 程序候选、校验与修复

candidate 是宿主合并基准快照、回填地点与路线、计算费用后构建的完整 ItinerarySnapshot。模型只能提交局部草稿，candidate 才包含全部天数及可渲染的完整字段。

`ValidationReport={status,issues,checked_at}`：status=not_run/passed/passed_with_warnings/failed。issue 为：

```text
ValidationIssue
  code: str
  severity: error | warning
  field: str | null
  day_id: int | null
  activity_id: str | null
  message: str
  evidence_ids: list[str]
  repairable: bool
```

硬校验至少包括：国内范围与目的地消歧、日期/天序列、地点允许集合、坐标/来源、活动唯一 ID、时间先后与交通缓冲、必去/禁去/固定活动、修改边界、已知费用不超过预算。对步行上限只计入有证据的步行段；缺失且影响硬约束时不得显示通过。

警告包括远期天气不可用、开放信息待核实、明确估计的价格和未估算住宿。不把这些未知值补成零或“正常营业”。整个结果的“通过”只表示已列明检查通过，不保证预约、开放或供应商价格。

修复仅将结构化问题、可用证据及原授权范围发给 Planner，最多一次，调用预算不重置。修复仍失败返回 failed/VALIDATION_EXHAUSTED；不能仅凭一次生成失败断言行程在现实中不可行。

## 9. 输出 PlannerOutput

### 9.1 顶层结果

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | 1 | 输出版本 |
| `run_id` | str | 本轮关联标识 |
| `status` | `ready/unchanged/needs_input/infeasible/failed/cancelled` | 程序决定的结果 |
| `itinerary` | `ItinerarySnapshot / null` | 只有 ready 返回新的完整可提交行程 |
| `reply` | str | 可直接展示的完整中文说明 |
| `questions` | `ClarificationQuestion[]` | needs_input 时非空 |
| `changes` | `ChangeSummary[]` | 程序对 baseline/candidate 比较得出 |
| `assumptions` | `Assumption[]` | 默认、推断与费用口径 |
| `validation` | ValidationReport | 必须附带实际校验状态 |
| `warnings` | `ValidationIssue[]` | 可直接展示的警告摘要 |
| `error` | `PlannerError / null` | failed 时必填；其他结果通常为空 |
| `usage` | `UsageSummary` | 次数、token 用量、耗时，不含密钥或 Prompt |

`ClarificationQuestion={id,field,reason,question,options,required}`：options 为可空字符串数组，field 为稳定枚举路径（如 requirements.destination/start_date/budget.scope/change_scope），不执行任意模型生成的赋值路径。

`ChangeSummary={day_id,activity_id,change_type,description}`：change_type 为 added/updated/removed；生成时可列新增天的摘要，修改时只列真实差异。地点的稳定标识、费用及排序变化都参与比较，不能只比较 reply。

`PlannerError={code,message,retryable,details}`：details 为已脱敏的结构化说明。建议代码包括 INPUT_INVALID、OUTSIDE_DOMESTIC_SCOPE、UNSUPPORTED_CAPABILITY、MODEL_TIMEOUT、TOOL_TIMEOUT、CALL_BUDGET_EXCEEDED、VALIDATION_EXHAUSTED、INTERNAL_ERROR。取消用 status=cancelled，不伪装系统错误。

`UsageSummary={model_calls,external_calls,input_tokens,output_tokens,elapsed_ms}`，未提供的 token 数为 null。

### 9.2 每种结果的约束

| status | 必要条件 | itinerary / 后续动作 |
| --- | --- | --- |
| ready | 完整候选通过硬校验，无待回答的必需问题 | 返回完整快照；未来业务服务检查版本/取消后决定提交 |
| unchanged | modify 原有安排已满足要求且通过相关校验，无真实差异 | null；沿用调用方基准快照，不创建版本 |
| needs_input | 必填信息缺失、同名消歧或授权范围不匹配 | null；展示 questions，本轮结束 |
| infeasible | 有明确证据支持硬约束冲突，例如必去地点在要求时段关闭 | null；validation 给出证据，不自动放宽用户约束 |
| failed | 工具/模型/输入错误、缺少必要能力、修复耗尽 | null；保留原行程与输入 |
| cancelled | 宿主收到并处理取消信号 | null；不返回半成品作为正式结果 |

最终结果只能有一种 status，非 ready 时不夹带可误保存的半成品；需要开发调试时内部 State 保留 draft/candidate。ready、unchanged 必须有 passed 或 passed_with_warnings 的报告。问题还没解决却未改动行程不等于 unchanged。

### 9.3 行程与前端数据兼容

ItinerarySnapshot 沿用 [接口分析第 4.3 节](01-v1-api-and-business-analysis.md#43-行程快照结构)：schema_version、trip_id、destination、travelers、budget、currency、budget_scope、timezone、days、cost_summary、warnings；增加 `destination_ref` 保存本轮 ResolvedDestination 的可序列化区域信息，不保存 clients 或完整 State。

days.id 保留 1-based 页签编号，活动输出仍使用 id；草稿中的 activity_id 在构建快照时映射为 id。place_ref 对应的权威 POI、行政路径、经纬度、坐标系、来源和获取时间写入活动 place；每条路线保留证据关联。旧 location 字符串和 time 文本是这些字段的展示投影。

首版预算新增两个口径需要输出额外 `budget_scope` 枚举值，属于尚未实现契约的细化。cost_summary 应按 scope 标注未估算项；已知活动费用小计不能与不同口径预算直接作为完整费用比较。

未来 HTTP 现有的 `destination/start_date/day_count/travelers/budget/currency/preferences` 平面字段由 service 转为 PlannerInput.requirements，不要求接口照搬完整 State。默认预算口径仍映射 group_excluding_intercity；CLI 可显式选择其他口径。scope 之外的费用不计入该范围达标判断，scope 之内的未知项必须列明。

行政路径和证据摘要随快照保存足以追溯；完整 EvidenceRegistry 属于单运行调试/审计，不作为每个 API 响应的必需负载。前端地图使用经纬度，不能把当前 SVG point 原样改名。

业务版本摘要的 validation_status 从报告映射：passed → validated，passed_with_warnings → with_warnings；failed/not_run 不能创建正式版本。此处报告描述本次检查，版本摘要描述已提交快照，字段不互相覆盖。

## 10. 输入和输出示例

### 10.1 全国任意目的地生成输入

下面使用成都作为示例，不表示目的地仅允许成都；结构化需求已明确，因此原话无需重复全部字段。

```json
{
  "schema_version": 1,
  "operation": "generate",
  "instruction": "安排轻松一些，喜欢历史和当地小吃",
  "requirements": {
    "destination": {"query":"成都","province_hint":null,"city_hint":null,"district_hint":null},
    "origin": null,
    "start_date": "2027-03-12",
    "day_count": 3,
    "end_date": null,
    "travelers": 2,
    "budget": {"amount":"3000.00","currency":"CNY","scope":"group_excluding_intercity"},
    "preferences": {
      "pace":"relaxed",
      "interests":["历史","当地小吃"],
      "food_preferences":[],
      "transport_preferences":[],
      "notes":[]
    },
    "constraints": {
      "must_visit":[],
      "avoid_places":[],
      "allowed_transport_modes":["walking","transit"],
      "max_daily_walking_m":null,
      "fixed_activity_ids":[],
      "notes":[]
    }
  },
  "baseline": null,
  "change_scope": null,
  "conversation": {"summary":null,"recent_turns":[]},
  "pending_questions": [],
  "clarification_answers": []
}
```

### 10.2 信息不足的完整输出示例

此处展示一次“目的地=朝阳且无法确定哪个行政区域”的结果；示例统计仅用于说明契约，不是运行实测。没有编造一份带假坐标的成功行程作为证据。

```json
{
  "schema_version": 1,
  "run_id": "run-example-1",
  "status": "needs_input",
  "itinerary": null,
  "reply": "你说的朝阳是哪个地区？确认目的地后再为你安排。",
  "questions": [
    {
      "id": "question-example-1",
      "field": "requirements.destination",
      "reason": "AMBIGUOUS_DESTINATION",
      "question": "请补充朝阳所在的省市或完整地区名称",
      "options": null,
      "required": true
    }
  ],
  "changes": [],
  "assumptions": [],
  "validation": {"status":"not_run","issues":[],"checked_at":null},
  "warnings": [],
  "error": null,
  "usage": {"model_calls":0,"external_calls":1,"input_tokens":null,"output_tokens":null,"elapsed_ms":100}
}
```

### 10.3 局部修改结构示意

沿用完整的 PlannerInput；operation=modify，baseline 填入上轮 ready 的完整 itinerary，requirements 与 baseline 一致，instruction 为“第二天午餐清淡一点”，change_scope 如下：

```json
{"day_ids":[2],"activity_ids":[],"preserve_other_days":true}
```

运行先核验基准和目标天，读取/更新受影响证据。若真正改变，返回 ready 的完整三天快照加第二天 changes；若已满足则 unchanged，itinerary=null；若需改全团预算或第三天则 needs_input，不扩大授权。

## 11. 生命周期与业务适配

```text
输入结构校验 → 规范化/澄清 → 国内目的地解析
                                  ↓
                           查询 + Planner 草稿
                                  ↓
                           回填/合并/强制校验
                                  ↓
                         最多一次修复，再校验
                                  ↓
                           PlannerOutput
```

任意阶段均可在取消、截止时间或必要依赖失败时退出。needs_input 不保留一个挂起协程；补充答案是新的运行，重新创建本轮 State。复用基准行程需重新检查相关证据的新鲜度，不能因聊天历史还在就跳过查询。

未来业务适配：

| Agent status | 业务 run 结果 | 行程版本 |
| --- | --- | --- |
| ready | 成功提交后 succeeded / updated | 服务检查基础版本、取消及事务后创建 |
| unchanged | succeeded / unchanged | 不创建 |
| needs_input | succeeded / input_required | 不创建；清单 needs_input |
| infeasible | failed / ITINERARY_INFEASIBLE | 不创建；保留要求 |
| failed | failed / 对应 error.code | 不创建 |
| cancelled | cancelled | 不创建 |

Agent ready 不是 SSE itinerary.committed；后者只能在数据库提交成功后发出。后端同步传入最新 baseline 和授权范围，返回结果不允许由模型指定 revision_id/final_revision_id。

## 12. 可验证的不变量与实施边界

后续实现时优先验证：

- 全国地点经解析和范围检查，不存在仅允许苏州的分支；境外目的地明确拒绝，无法判定范围时询问。
- 城市、区县、景区、同名地点、模糊大区域和无供应商覆盖分别有可解释结果。
- 缺输入、无变化、不可行、工具失败和取消不能混成 ready。
- 草稿未知 place_ref、跨天越权修改、修改固定活动、时间冲突和已知费用超预算均被程序识别。
- 远期天气和未知价格不会补成事实；路径缺口影响硬约束时不能靠 warning 通过。
- 所有 retry/repair 共用预算，工具并发不突破上限，取消后不生成正式可提交结果。
- 两轮独立运行不共享可变 messages/evidence；输入和 baseline 不被原地修改。
- ready/unchanged 输出符合结果约束；先验证规则，再以真实工具联调评价质量。

当前交付到 State 和契约设计为止。建议下一步才把这些规格实现为 `backend/schemas/` 的输入/输出 Pydantic 模型和独立运行入口，再补工具替身及校验器，最后接真实 Planner；此时仍不需要 HTTP、数据库或 LangGraph 外层工作流。

## 13. 官方框架依据

本设计通过 Context7 核对 LangChain 官方文档，业务字段与全国范围是本项目的设计选择：

- [Agents](https://docs.langchain.com/oss/python/langchain/agents)：AgentState 管理循环消息与可扩展字段。
- [Short-term memory](https://docs.langchain.com/oss/python/langchain/short-term-memory)：自定义 AgentState 和 state_schema。
- [Tools](https://docs.langchain.com/oss/python/langchain/tools)：ToolRuntime 与独立运行上下文。
- [Structured output](https://docs.langchain.com/oss/python/langchain/structured-output)：结构化结果通过 structured_response 获取；结果仍需领域校验。
