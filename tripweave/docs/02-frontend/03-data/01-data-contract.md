# 前端数据与后端接入约定

## 1. 数据来源

当前唯一初始样本为 [02-trip-fixture.json](02-trip-fixture.json)。前端通过模块导入读取，不复制一份到 `src`。Vite 将 JSON 编入前端模块，生产运行不需要临时读取项目之外的文件。

样本包含完整三天活动与初始对话，不包含真实用户信息或密钥。价格、时间、路线和推荐内容未经过实时服务验证，不可据此保证开放时间、预约或出行成本。

## 2. 字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `schemaVersion` | number | 初始结构版本，目前为 1 |
| `id` | string | 行程标识 |
| `destination` | string | 目的地 |
| `travelers` | number | 人数 |
| `budget` / `currency` | number / string | 人民币全团预算，不含往返大交通 |
| `days` | TripDay[] | 按日期排序的旅行日 |
| `messages` | Message[] | 初始演示对话；后续消息由页面独立维护 |

`TripDay`：`id`、`date`（ISO 日期）、`label`（页签副标题）、`title`、`description`、`distance`（当日距离估计文本）及 `activities`。

`Activity`：`id`、`time`（展示字符串）、`title`、`description`、`location`、`kind`、`cost`、`point`。

- `kind` 用于选择图标，包含 breakfast / garden / food / museum / walk / lotus / hotel；未知类型回退为地点图标。
- `cost` 是全团该项估计费用，当前只用于出行信息展示，不代表完整预算。
- `point` 为 SVG 坐标系 `400 × 280` 内的 `[x,y]` 或 `null`，**不是经纬度**。地图高亮使用活动 ID 关联。
- 当前 `time` 只用于页面展示和直接编辑。真正做路线可行性校验时，应由后端返回结构化开始/结束时间，不能直接按任意字符串计算。

`Message`：`id`、`role`（assistant / user）、`content`（纯文本）、`time`（展示时间）。前端不执行消息中的 HTML，不依赖模型输出拼接 DOM。

TypeScript 类型位于 `frontend/src/types/trip.ts`。JSON 与类型通过 `pnpm typecheck` 校验；恢复浏览器存储时另外检查基本结构和数据版本。

## 3. 项目存储与结果归档

当前使用 `tripweave:workspace:v2`，按计划分别维护行程、对话、待处理要求、结果快照与未完成指令。旧单行程键 `tripweave:journal:v1` 会迁移，旧内容保留。

保存结构、恢复规则、处理动效和本地规则边界见 [01-plan-projects.md](../04-features/01-plan-projects.md)。本地记录不是服务端正式数据；接入后应由服务端版本与身份归属成为事实来源。

## 4. 后端对接顺序

1. 用 `GET /api/v1/trips/{id}` 返回的数据替换初始行程样本；在 `frontend/src/api/` 完成字段适配。
2. 为用户消息提交 `POST /api/v1/trips/{id}/runs:stream`，携带 `client_request_id`、`base_revision`、操作类型与指令。
3. 解析 SSE，按运行 ID 与事件序号合并进度和对话；显示失败、取消和待补信息状态。
4. 收到 `itinerary.committed` 后重新读取正式行程；流式说明和未校验草稿不覆盖已保存行程。
5. 保存、取消、版本历史与身份归属以架构文档中的服务端协议为准。

样本使用前端 camelCase，现有接口约定中运行字段采用 snake_case。接入时在 API 适配层转换，不能为方便页面擅自改变已约定的对外字段。

后端地图返回应使用 `poi_id`、经纬度、坐标系、来源与获取时间等字段，替换现在的 SVG `point`。组件联动继续使用稳定 ID。模型和高德 Web 服务密钥只在后端保存；当前页面不要求任何密钥。

## 5. 错误与数据保留

| 情况 | 当前处理 / 后续要求 |
| --- | --- |
| 空白输入 | 不提交，发送按钮禁用 |
| 超长输入 | 最多 500 字，显示计数，长文本自然换行 |
| 本地保存失败 | 保留页面内容，允许重新保存 |
| 本地草稿损坏 | 使用初始行程，不阻止页面打开 |
| 后端运行失败 | 后续显示错误并保留输入及旧行程，不伪造成功 |
| 版本冲突 | 后续提示刷新与合并，不静默覆盖 |
