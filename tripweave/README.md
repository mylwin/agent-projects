# TripWeave

旅行规划应用。已实现暖白酒红的计划列表与旅行日笺前端，支持独立对话和结果归档；后端目前为目录骨架。

- `frontend/`：TypeScript + React + Vite，真实 Lucide 图标，支持行程编辑与浏览器保存。
- `backend/`：计划采用 Python + FastAPI，代码直接按技术职责分层。
- [项目目录与系统架构](docs/01-architecture/02-system-architecture.md#10-项目目录与部署)
- [文档索引](docs/README.md)
- [开发与提交约定](AGENTS.md)

在本目录执行 `uv sync` 同步 Python 环境；已有缓存时可使用 `uv sync --offline`。
前端启动：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

打开终端显示的本地地址（默认 `http://127.0.0.1:5173`）。在 `frontend/` 执行
`pnpm typecheck`、`pnpm lint` 检查代码。

当前使用 [前端样本数据](docs/02-frontend/03-data/02-trip-fixture.json)，没有接入真实模型、后端或地图服务。
提供三个本地示例调整及处理动效，未知要求保留为待处理项；各计划的行程、对话和版本保存仅限当前浏览器。
后端与 Compose 尚未实现。数据字段和接入步骤见 [前端数据约定](docs/02-frontend/03-data/01-data-contract.md)。

空目录通过 `.gitkeep` 跟踪，添加实际文件后可删除对应占位文件。
