# 前端数据与后续接入

## 当前页面

React + TypeScript + Vite，样式为现有暖白酒红旅行日笺，图标使用 lucide-react。
/plans 展示计划列表；/plans/:id 展示每日行程、对话、版本和最终方案。
支持手动编辑、日期切换、活动与 SVG 标记联动、侧栏展开和浏览器保存。
样例在 frontend/src/data/trip.json 与 assistant-examples.json，不从 docs 导入。

目前新建计划仍复制苏州样例，本地助手只处理轻松节奏、清淡午餐和餐费示例；
未知要求进入待处理清单。页面没有向模型或后端发请求，SVG 也不提供真实导航。
继续保留这些行为，直到独立 Agent 在线验证后再开展接入。

## 独立 Agent 的输入

TripRequest 保持扁平结构，字段 destination、start_date、day_count、travelers、budget
可直接来自新建计划表单。pace、interests、instruction 可选。
计划名称仅用于页面保存，不参与规划，不需要传给模型。
未来接入时需要把现在写死的苏州改成目的地输入；后端接口尚未定义。

## 独立 Agent 的输出

PlanResult 包含 trip、places、reply、warnings，新增 research。它是函数/CLI 的结果，不是已上线接口。

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

## 后续接入次序

Agent 真实联调通过后，再增加一个调用规划函数的薄后端入口，确定请求响应和失败状态。
前端随后提交需求、显示等待和错误，成功后用 result.trip 建立计划，用 reply 和 warnings
展示来源边界，继续沿用现有浏览器保存与版本机制。

真实地图展示另行决定：根据 places 中经纬度进行 SVG 投影，或者接地图 SDK。
高德默认 GCJ-02，百度默认 BD-09，必须按 coordinate_system 处理；当前未做坐标转换。
研究报告中的天气/住宿资料尚未适配成页面卡片，不将摘要当作已经核验的实时数据。
投影必须去掉当前示例街名并明确路线只是连线；没有路线查询时不能显示导航距离。
首轮先生成完整行程，真实局部修改不在当前阶段实现，不把首次生成硬当作局部修改。
