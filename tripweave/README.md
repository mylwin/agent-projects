# TripWeave

旅行规划应用，当前已建立 uv 环境配置、架构文档与前后端目录骨架，尚未实现应用。

- `frontend/`：计划采用 TypeScript + React + Vite。
- `backend/`：计划采用 Python + FastAPI，代码直接按技术职责分层。
- [项目目录与系统架构](docs/architecture.md#10-项目目录与部署)
- [文档索引](docs/README.md)
- [开发与提交约定](AGENTS.md)

在本目录执行 `uv sync` 同步 Python 环境；已有缓存时可使用 `uv sync --offline`。
当前没有应用启动命令、前端依赖配置或可运行的 Compose 配置。

空目录通过 `.gitkeep` 跟踪，添加实际文件后可删除对应占位文件。
