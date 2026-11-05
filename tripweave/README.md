# TripWeave

旅行规划应用。当前独立运行多 Agent + 官方地图 MCP，验证通过后再接后端和前端。

景点、美食、天气、住宿分别由研究 Agent 查询，Planner 汇总并返回行程草稿。
高德和百度通过工厂切换官方 MCP 服务，不再维护手写地图 REST 客户端。
前端仍为本地示例，尚无 HTTP 接口或真实 Agent 接入。

## 运行

```bash
uv sync --offline
# 已有 .env 时直接核对配置，不要覆盖。
uv run --env-file .env python -m backend examples/trip-request.json
```

首次配置可复制 .env.example 为 .env，填写模型与选定地图供应商密钥。
`MAP_PROVIDER=amap` 使用 AMAP_API_KEY；`MAP_PROVIDER=baidu` 使用 BAIDU_MAP_API_KEY。
密钥必须具备官方地图 MCP 服务权限，旧 Web API 权限不保证可直接使用 MCP。

输出保存：

```bash
mkdir -p tmp/agent
uv run --env-file .env python -m backend examples/trip-request.json > tmp/agent/result.json
```

该命令会调用真实模型和地图，可能消耗额度。程序不自动执行真实联调。
进度写标准错误，JSON 写标准输出；失败以非零状态退出。

## 离线检查

```bash
uv run ruff check backend
uv run ruff format --check backend
uv run pyright
uv run pytest backend/tests -q
```

测试使用内存 MCP、Streamable HTTP 的 ASGI 替身及模型 HTTP 替身，不访问真实供应商。

前端在 frontend/ 执行 `pnpm dev`，检查为 `pnpm typecheck`、`pnpm lint`、`pnpm build`。
页面仍展示本地样例，不会自动读取 CLI 的生成结果。

[文档入口](docs/README.md) · [Agent 使用说明](docs/02-agent.md) · [开发约定](AGENTS.md)
