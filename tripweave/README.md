# TripWeave

旅行规划应用。当前多 Agent + 官方地图 MCP 已可通过薄 FastAPI 入口调用；真实服务联调与前端接入仍待完成。

景点、美食、天气、住宿分别由研究 Agent 查询，Planner 汇总并返回行程草稿。
高德和百度通过工厂切换官方 MCP 服务，不再维护手写地图 REST 客户端。
前端仍为本地示例，尚未接入 HTTP 接口；后端已有薄 FastAPI 入口，真实服务联调未执行。

## 运行

```bash
uv sync --offline
# 已有 .env 时直接核对配置，不要覆盖。
uv run python -m backend examples/trip-request.json
```

首次配置可复制 .env.example 为 .env，填写模型与选定地图供应商密钥。
进程启动时会自动读取项目根目录 `.env`；已存在的同名环境变量优先。
`MAP_PROVIDER=amap` 使用 AMAP_API_KEY；`MAP_PROVIDER=baidu` 使用 BAIDU_MAP_API_KEY。
密钥必须具备官方地图 MCP 服务权限，旧 Web API 权限不保证可直接使用 MCP。

输出保存：

```bash
mkdir -p tmp/agent
uv run python -m backend examples/trip-request.json > tmp/agent/result.json
```

该命令会调用真实模型和地图，可能消耗额度。程序不自动执行真实联调。
进度写标准错误，JSON 写标准输出；失败以非零状态退出。

终端现在会即时显示各 Agent 的正文分片和工具开始、完成或失败信息。
模型客户端统一使用 ChatOpenAI，服务地址和模型名称仍由 .env 配置。
`MODEL_ENABLE_THINKING=true` 只请求供应商启用思考；终端仅显示 SDK 实际透传的推理块，
不保证第三方 reasoning_content 字段可见。正文与工具进度不受该开关影响。

默认不展开工具 JSON 参数。调试 Planner 的结构化生成过程时执行：

```bash
uv run python -m backend examples/trip-request.json --debug-tools
```

失败会显示阶段、底层异常类型及脱敏原因，便于区分模型拒绝与 MCP 故障；
研究 Agent 达到调用上限时结束该主题并保留已有证据，不使整轮规划失败。

## HTTP 入口

在 `tripweave/` 根目录执行：

```bash
# 直接运行模块文件，开发热重载
uv run python backend/api/app.py

# 或使用 uvicorn
uv run uvicorn backend.api.app:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend
```

`app.py` 的 `if __name__ == "__main__"` 会启动 uvicorn 并开启热重载；
直接执行文件时，文件顶部会把项目根目录加入导入路径，保证 `backend` 包可导入。

`GET /api/health` 检查配置；`POST /api/plans/generate` 接收 `TripRequest`，
成功返回 `{success: true, data}`，失败返回 `{success: false, error}`。
错误码包括 `invalid_request`、`planning_rejected`、`upstream_failed`、
`planning_timeout`、`busy`、`configuration_error`、`internal_error`、`not_found` 和 `http_error`。
认证接口使用 MySQL 和签名 Cookie；行程生成接口尚未加鉴权或异步任务，默认只绑定回环地址。

## 离线检查

```bash
uv run ruff check backend
uv run ruff format --check backend
uv run pyright
uv run pytest backend/tests -q
```

测试使用内存 MCP、Streamable HTTP 的 ASGI 替身、模型 HTTP 替身及 FastAPI TestClient，不访问真实供应商。

前端在 frontend/ 执行 `pnpm dev`，检查为 `pnpm typecheck`、`pnpm lint`、`pnpm build`。
页面仍展示本地样例，不会自动读取 CLI 的生成结果。

[文档入口](docs/README.md) · [Agent 使用说明](docs/02-agent.md) · [数据库设计](docs/05-database.md) · [接口 Schema](docs/06-api-schema.md) · [接口文档](docs/07-api-reference.md) · [开发约定](AGENTS.md)
