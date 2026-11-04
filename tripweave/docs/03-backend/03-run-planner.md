# 首次生成 Agent 的运行方式

## 1. 配置与启动

在 `tripweave/` 目录执行：

```bash
uv sync --locked
cp .env.example .env
```

已有 `.env` 时直接编辑原文件，避免覆盖。填写 `MODEL_API_KEY`，并通过
`MAP_PROVIDER=amap` 或 `MAP_PROVIDER=baidu` 选择地图供应商，分别填写
`AMAP_API_KEY` 或 `BAIDU_MAP_API_KEY`。未设置 `MAP_PROVIDER` 时默认使用高德。
前者属于支持工具调用的模型服务；默认地址与模型为百炼北京地域的兼容接口和
`qwen-plus`，也可以通过 `MODEL_BASE_URL`、`MODEL_NAME` 更换兼容服务。
首次模型请求包含系统提示、工具定义和完整需求，耗时波动较大，单次请求超时
由 `MODEL_TIMEOUT_SECONDS` 控制，未设置时默认 60 秒。
高德需要 Web 服务类型的 Key；百度需要 Web 服务 AK。真实凭证仅保留本地，不能提交到 Git。

运行示例：

```bash
uv run --env-file .env python -m backend.agents backend/agents/examples/generate.json
```

程序将 JSON 结果写到标准输出，错误写到标准错误并返回非零退出码。
需要保存结果时，先建立 `tmp/` 下的任务目录，再将标准输出重定向到该目录。

输入示例在 `backend/agents/examples/generate.json`，修改目的地、日期、天数、
人数、预算和偏好即可。输入仍采用现有 PlannerInput；本入口只处理 generate。
必要字段缺失时直接提示补齐，不启动多轮追问。

## 2. 一次运行做什么

1. 校验输入，并从起止日期或天数补齐确定的日期范围。
2. 通过选定供应商的行政区查询解析明确的国内城市或区县，不设苏州白名单。
3. 程序按固定三类关键词（游玩、餐饮、用户兴趣或特色街区）各查询一次，
   每次最多五个候选地点，合并去重后形成候选池。
4. 模型只调用一次：输入完整需求与候选地点清单，通过结构化工具返回每日活动。
5. 程序检查日期、地点引用及活动开始时间顺序，返回草稿与地点来源。

模型不参与"查什么、查几次"，因此不存在查询循环；失败只会来自查询为空、
模型未提交结构化结果或结果不满足约束。

下层分工：`backend/agents/` 只负责模型循环（`runtime.py`）和提示词（`prompts.py`），
不认识旅行规则；`backend/services/planning.py` 负责需求准备、区域解析、地点查询、
结果校验与装配。改业务流程不碰执行器，改执行器不影响业务规则。

同名地区、过大的区域或数据源不覆盖时提示无法唯一解析；请直接使用
`destination.query` 填写城市或区县。
景区可作为该城市内的查询目标，不直接将景区名称作为行政区解析输入。
百度行政区查询目前不覆盖港澳台；数据源不覆盖时会提示无法解析。

模型调用最多六次，地点工具最多八次，单轮总时长默认 300 秒（`PLANNER_TIMEOUT_SECONDS`
可调）；单个模型请求默认 60 秒（`MODEL_TIMEOUT_SECONDS` 可调），单个地图请求最多
15 秒。当前没有自动修复和业务级重试。

推理模型（Qwen3、DeepSeek-R1 等）默认会先输出较长的思考链，首字等待明显变长。
`MODEL_ENABLE_THINKING=false` 关闭思考，`MODEL_THINKING_BUDGET=<正整数>` 限制思考
token 数（Qwen3 系列达到预算即强制结束）。两者默认都不发送，因为部分供应商与
模型不支持这些参数；若接口报 400，请先设回 `auto`。

运行中把进度写到标准错误，标准输出保持纯 JSON，便于重定向保存：

```text
[规划] 解析目的地：成都（0.0s）
[规划] 目的地区域已确定：510100，开始规划 3 天行程（0.2s）
[规划] 已提交模型，等待首次响应（0.0s）
[规划] 第 1 次模型调用请求工具：search_places（18.4s）
[规划] 地点查询完成，累计 5 个候选地点，等待模型继续（1.1s）
[规划] 第 2 次模型调用返回结构化行程（12.7s）
[规划] 行程草稿已就绪，共 5 个候选地点（0.0s）
```

括号内是距离上一条进度的耗时，可用来判断慢在模型还是地图。进度只在终端
显示，不进入结果文件；`--quiet` 之类的开关尚未提供。

## 3. 输出与边界

输出包含：

- `requirements`：本轮需求及补齐的日期。
- `itinerary.days`：日期、主题、活动时间和地点 ID。
- `places`：实际引用的供应商地点、经纬度、坐标系与获取时间；
  `source` 标记 amap 或 baidu，百度请求返回 GCJ-02 坐标。
- `warnings`：路线、费用、天气、开放及预约尚未核验的说明。

这是供独立 Agent 验证使用的规划草稿，不是前端 API 的正式版本快照。
本轮尚未执行路线、预算可行性和营业时间校验；预算与偏好会传入模型，
不能据此声称全程费用已达标。地点存在不等于当前可访问。
局部修改、历史上下文、澄清、结构化硬约束暂不接受，明确返回错误；
未接入数据库、HTTP/SSE、前端或子 Agent 调度。

## 4. 本地验证

```bash
uv run --offline python -m unittest discover -s backend/tests -v
```

`tests/agents/` 使用真实 LangChain 循环、预设工具调用消息和 HTTP 替身，
验证模型—工具—结构化结果的执行链，不会付费调用真实模型或高德。
配置好密钥后，使用上面的启动命令单独进行真实服务联调。

## 5. 接口依据

- [LangChain 结构化输出](https://docs.langchain.com/oss/python/langchain/structured-output)
- [高德行政区查询](https://lbs.amap.com/api/webservice/guide/api/district)
- [高德地点查询](https://lbs.amap.com/api/webservice/guide/api-advanced/search)
- [百度行政区查询](https://lbsyun.baidu.com/docs/webapi?title=region_search%2Fdistrict-search%2Fbase)
- [百度地点检索](https://lbsyun.baidu.com/index.php?title=dev%2Fwebservice-placeapi)
