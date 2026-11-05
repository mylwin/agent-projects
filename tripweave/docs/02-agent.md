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
| MODEL_ENABLE_THINKING / MODEL_THINKING_BUDGET | 可选供应商参数，不采集或展示思考链 |

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
密钥由工厂写入官方 URL 的 query，不发送给模型，不输出连接 URL 或 SDK 原始连接错误。
CLI 的 .env 只由 uv 明确加载，不在导入模块时自动读文件。

## Agent 分工与调用上限

- 景点 Agent：景点、美食和兴趣候选，缺坐标时使用详情查询。
- 天气 Agent：天气/预报及必要的地理编码工具，资料不覆盖出行日期时保留未知。
- 住宿 Agent：搜索酒店候选，不承诺实时房价、余房或可订状态。
- Planner：综合三份研究报告和候选地点，一次结构化调用安排每一天。

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

自动测试覆盖内存 MCP、Streamable HTTP ASGI 传输替身、真实模型 SDK 和多 Agent 工具循环；
它们不证明真实供应商的权限、在线工具名、回包形状或模型效果已验证。
按用户选择尚未进行真实服务联调，也没有实现 HTTP 后端接口或前端接入。
