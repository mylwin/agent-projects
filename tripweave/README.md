# TripWeave

旅行规划应用，当前优先把独立 Agent 调通，再接后端接口与前端。

前端已有旅行计划列表、每日行程、手动编辑、版本选择和浏览器保存，仍使用本地示例。
独立 Agent 已实现需求校验、地图地点查询、单次 LangChain 结构化规划、结果校验与 JSON 输出。
当前没有 HTTP 服务，前端没有连接真实 Agent。

## 运行独立 Agent

```bash
uv sync --offline
cp .env.example .env
# 在 .env 中填写模型和选定地图供应商凭据。
uv run --env-file .env python -m backend examples/trip-request.json
```

真实运行会向所选地图发送城市及搜索关键词，向所选模型发送旅行需求和候选地点，
可能消耗服务额度。输出是草稿，不保证路线、费用、预约或营业情况。
参数和结果见 [Agent 使用说明](docs/02-agent.md)。

## 运行前端

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

前端新建计划和助手仍为本地示例，不需要运行 Agent。

## 检查

```bash
uv run ruff check backend
uv run ruff format --check backend
uv run pytest backend/tests -q
```

前端检查：在 frontend/ 执行 `pnpm typecheck`、`pnpm lint`、`pnpm build`。
自动化测试使用地图与模型的 HTTP 协议替身，不消耗外部调用额度。

[文档入口](docs/README.md) · [开发约定](AGENTS.md)
