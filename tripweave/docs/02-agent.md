# Agent 与地图 MCP 运行

## 配置与命令

在项目根目录运行 `uv sync --offline`，缺缓存时执行 `uv sync`。
已有 .env 时保留并核对配置；首次运行才从 .env.example 复制。

| 变量 | 用途 |
| --- | --- |
| MODEL_API_KEY / MODEL_BASE_URL / MODEL_NAME | 支持工具调用的 OpenAI 兼容模型 |
| MAP_PROVIDER | amap 或 baidu |
| AMAP_API_KEY / BAIDU_MAP_API_KEY | 选中供应商具备 MCP 权限的密钥 |
| MODEL_TIMEOUT_SECONDS | 单次模型请求超时，默认 60 秒 |
| PLANNER_TIMEOUT_SECONDS | MCP 连接、研究、汇总的总超时，默认 300 秒 |
| MODEL_ENABLE_THINKING / MODEL_THINKING_BUDGET | 可选供应商参数；true 请求启用思考，显示取决于 SDK 透传 |

```bash
mkdir -p tmp/agent
uv run --env-file .env python -m backend examples/trip-request.json > tmp/agent/result.json
```

进度依次显示 attractions、weather、hotels 和生成/校验阶段，写标准错误。
成功 JSON 写标准输出，退出码 0；失败退出码 1。输入格式不变：目的地、日期、
1–5 天、1–12 人、全团人民币预算必填，节奏、兴趣和补充可选。
预算不含往返大交通，模型和地图的真实调用可能消耗额度。

## 连接官方 MCP

- [高德快速接入](https://lbs.amap.com/api/mcp-server/gettingstarted)：使用 Streamable HTTP；旧 SSE 已下线。
- [百度快速开始](https://lbsyun.baidu.com/docs/ai?title=mcpserver%2Fquickstart)：使用推荐的 Streamable HTTP。
- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters)：负责会话与工具适配。

无需安装 Node 地图进程，当前使用远程官方服务；代码不把 MCP 降级为旧 REST 请求。
密钥由工厂写入官方 URL 的 query，不发送给模型，终端对连接 URL、已知密钥和认证字段脱敏，不打印原始堆栈。
CLI 的 .env 只由 uv 明确加载，不在导入模块时自动读文件。

## 终端流式显示与错误定位

`ConsoleCallback` 是唯一的 LangChain 原生异步回调处理器。通过 agent 标签区分景点、天气、
住宿和 Planner，直接显示正文分片、模型开始、工具开始/完成/失败；没有事件总线或额外模型调用。
业务函数仍返回完整结果，流式内容写 stderr，最终通过校验的 JSON 写 stdout。
运行失败时不输出成功 JSON。

模型客户端统一使用 langchain-openai 的 ChatOpenAI，不按思考开关切换实现。
实际 MODEL_BASE_URL、MODEL_NAME 和密钥仍由配置决定，可连接支持当前协议的兼容服务。
`MODEL_ENABLE_THINKING=true` 只请求供应商启用思考，不保证推理内容可以显示。
回调显示 SDK 实际透传的标准推理块或兼容字段；第三方 reasoning_content 可能不会被 ChatOpenAI 保留。
项目不补写供应商适配器、不覆盖 SDK 私有方法，也不伪造缺失的推理内容。
正文分片、工具进度、异常脱敏和最终 JSON 输出均保留。

Planner 通常只返回 TravelDraft 工具参数，因此默认显示生成进度，完成后返回结构化行程。
需要看原始参数分片时加 `--debug-tools`，此时参数同样写 stderr。
“参数生成”表示模型正在生成参数，尚未执行；“执行参数”表示工具开始时使用的完整参数。
这两个阶段展示同一次调用，实际执行次数按“工具开始”计数：

```bash
uv run --env-file .env python -m backend examples/trip-request.json --debug-tools > tmp/agent/result.json
```

`PlanningError` 保留失败阶段和底层异常类型，展开 MCP 异常组后输出脱敏原因。
例如天气 Agent 超限会显示 `weather 研究失败 [ModelCallLimitExceededError]` 和 6 次上限说明；
模型返回 400/401/429 等错误时保留 SDK 的状态与说明；整轮超时仍单独提示。
异常组含多个失败时显示第一条底层原因，不输出完整堆栈或连接地址。

## Agent 分工与调用上限

- 景点 Agent：景点、美食和兴趣候选，缺坐标时使用详情查询。
- 天气 Agent：天气/预报及必要的地理编码工具，资料不覆盖出行日期时保留未知。
- 住宿 Agent：搜索酒店候选，不承诺实时房价、余房或可订状态。
- Planner：综合三份研究报告和候选地点，一次结构化调用安排每一天。

提示词集中在 backend/agents/prompts.py，按“共同调用纪律 + 当前角色 + 当前供应商 few-shot”组合。
各部分使用 Markdown 标题分层，区分任务、规则、调用示例、工具返回和结论；JSON 示例使用代码块及两空格缩进。
送入模型的旅行需求、候选地点与研究资料也使用独立标题和格式化 JSON。
景点提示不评价酒店或天气，天气提示不搜索景点或住宿，住宿提示不判断全程预算可行性；
Planner 使用独立的结构化输出示例，不重新研究或调用地图。

提示词要求先核对工具 schema，仅填写必要参数，同一无效参数不得重发，每个角色最多纠错一次。
景点通常两次搜索、最多一次详情补查；天气通常一次定位加一次天气查询；住宿通常一次搜索，
最多一次详情补查。通用提示要求工具调用不超过 4 次并预留总结响应。
百度天气 few-shot 特别区分字符串 "true" 与布尔值 true，location 使用 "经度,纬度" 字符串，
不把数组传给字符串参数；高德示例独立使用自己的工具名和字段。
工具 schema 与服务端校验冲突时应说明不兼容；预报不覆盖出行日期时停止查询并保留未知。
所有示例地点、ID、日期与工具结果都是虚构的格式示例，不能进入本轮地点证据。

上述次数与纠错规则是模型行为指引，本轮未增加参数自动转换或重复调用拦截器；
实际是否遵循仍需真实模型验证。程序继续通过以下框架硬限制兜底：

每个研究 Agent 最多 6 次模型调用、8 次工具调用，通过 LangChain 内置中间件限制。
因此整轮最多 19 次模型、24 次工具调用；这是上限，不是固定消费。总超时仍会提前结束运行。
每轮使用一个 MCP 会话，退出或超时后关闭。没有自动模型重试、后台任务或额外纠错循环。

缺少某类工具或工具返回错误时，该主题写入缺失说明；不会采用无工具证据的模型结论。
传输故障或框架预算耗尽会使本轮失败。不存在可用地点则停止，不调用最终 Planner。

## 结果与边界

PlanResult 包含 trip、places、reply、warnings，新增 research 保存每个主题的摘要与工具原文。
只有工具成功返回的地点 ID、名称、坐标才进入 places；模型只能引用这些 ID。
高德默认 GCJ-02，百度默认 BD-09，不把坐标写入当前 SVG 的 point 字段。
费用仍为 null，距离待核实。天气查询与酒店搜索不等于天气日期覆盖或价格核验。

自动测试覆盖内存 MCP、Streamable HTTP ASGI 传输替身、真实模型 SDK 和多 Agent 工具循环；新增分片到达即时显示、单一 OpenAI 客户端、标准推理块显示、输出不重复及异常脱敏验证。

新增 few-shot 参数通过合成 MCP 的 schema 校验，Planner 示例通过真实草稿模型和业务校验。
它们不证明真实供应商的权限、在线工具名、回包形状或模型遵循提示词的效果已验证。
按用户选择尚未进行真实服务联调，也没有实现 HTTP 后端接口或前端接入。
