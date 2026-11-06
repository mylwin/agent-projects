# 前端数据与后续接入

## 当前页面

React + TypeScript + Vite，样式为现有暖白酒红旅行日笺，图标使用 lucide-react。
/plans 展示服务端已保存计划与浏览器本地草稿；/saved-projects/:id 查看服务端版本和轨迹，
/plans/:id 展示可编辑的本地行程、对话、版本和最终方案。
支持手动编辑、日期切换、活动与 SVG 标记联动、侧栏展开和浏览器保存。
样例在 frontend/src/data/trip.json 与 assistant-examples.json，不从 docs 导入。

新建计划提交真实目的地和行程需求到 `/api/plans/generate`，成功后打开服务端保存的版本。
原有本地草稿及本地助手继续保存在浏览器；本地助手只处理轻松节奏、清淡午餐和餐费示例，
未知要求进入待处理清单。已保存计划通过 `/api/projects` 系列接口读取；SVG 不提供真实导航。

## 独立 Agent 的输入

TripRequest 保持扁平结构，字段 destination、start_date、day_count、travelers、budget
可直接来自新建计划表单。pace、interests、instruction 可选。
计划名称用于服务端创建项目，不参与规划。当前新建表单已提供目的地输入，并调用
`POST /api/plans/generate`；节奏固定为 `balanced`，兴趣暂为空数组，补充要求可输入。

## 独立 Agent 的输出

PlanResult 包含 trip、places、reply、warnings 和 research，也是已上线生成接口的结果。

| 路径 | 含义与来源 |
| --- | --- |
| trip.schemaVersion / id | 结构版本 1 / 本次结果 UUID，保存层可替换 ID |
| trip.destination / travelers / budget / currency | 输入目的地、人数、全团预算、CNY |
| trip.days[].id / date / label | 从 1 开始的日序、实际日期、“第 N 天” |
| trip.days[].title / description | 模型的当天主题与说明 |
| trip.days[].distance | 当前固定为“待核实” |
| activities[].id / time / title / description / kind | 程序活动 ID、模型安排及类型 |
| activities[].location / placeId | 地图名称与地址 / 供应商地点 ID |
| activities[].cost | null，费用尚未查询；前端类型和存储已支持未知 |
| activities[].point | null，不能把经纬度当作当前 SVG 的像素坐标 |
| places[] | 已引用地点的 ID、名称、地址、经纬度、供应商坐标系、来源、接收时间 |
| research[] | 景点、天气、住宿研究摘要；每份含成功工具原文、结构化内容和缺失说明 |
| reply | 程序生成的一句行程摘要，不是模型的思考过程 |
| warnings[] | 未核验费用、路线、天气预报日期覆盖、住宿价格与预约等说明 |

Trip 和 TripDay 的基础字段与现有前端相同，活动增加 placeId 便于关联真实地点。
前端遇到任何未知活动费用时将合计显示为“待核实”，不能把 null 相加当零。
原有已保存样例金额仍可读取。全部 point 为 null 时，当前 SVG 不显示地点标记。

## 后续工作

已接入生成请求、等待和错误显示；生成成功后跳转至服务端版本详情。
本地草稿与已保存计划目前是两个独立的数据来源，尚无草稿迁移功能。

真实地图展示另行决定：根据 places 中经纬度进行 SVG 投影，或者接地图 SDK。
高德默认 GCJ-02，百度默认 BD-09，必须按 coordinate_system 处理；当前未做坐标转换。
研究报告中的天气/住宿资料尚未适配成页面卡片，不将摘要当作已经核验的实时数据。
投影必须去掉当前示例街名并明确路线只是连线；没有路线查询时不能显示导航距离。
首轮先生成完整行程，真实局部修改不在当前阶段实现，不把首次生成硬当作局部修改。
