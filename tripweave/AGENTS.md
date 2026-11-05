# TripWeave 开发约定

适用于本目录和所有子目录，命令默认在 `tripweave/` 执行。

## 当前阶段

参考 [Hello-Agents 第十三章](https://hello-agents.datawhale.cc/#/./chapter13/第十三章%20智能旅行助手)，按数据流逐层实现。
当前只开发和验证独立旅行规划 Agent。**先调通 Agent，再接 FastAPI，再接前端。**
本轮不实现 HTTP 接口、多 Agent、MCP、数据库、任务队列或 SSE。
前端保持已有页面与本地保存；不得将本地规则描述为真实模型功能。
实际状态和开发顺序见 [docs/README.md](docs/README.md)。

## 目录与命名

- `backend/__main__.py`：命令行入口，只做文件读取、配置装配和错误提示。
- `backend/schemas/trip.py`：需求、地点、模型草稿、前端展示结果。
- `backend/services/planning.py`：顺序编排、业务校验与结果装配。
- `backend/agents/planner.py`：提示词和一次结构化模型调用。
- `backend/integrations/`：模型和现有地图供应商适配。
- `backend/config/`：环境变量配置。
- `backend/tests/`：自动化测试；`examples/`：可直接执行的输入样例。
- `frontend/src/`：沿用 pages、components、api、hooks、types、utils、styles；
  `data/` 保存前端样例，不从 docs 导入运行数据。
- `docs/`：唯一入口 README，加少量按阅读顺序编号的正式说明，不多层嵌套。
- `tmp/`：忽略的日志、结果、截图和重构备份，不作为运行依赖。

不保留空占位目录，不为后续阶段提前创建模块。
Python 使用 snake_case，TypeScript 函数和变量 camelCase，组件 PascalCase。
文件名说清用途；禁止为单个调用点创建 manager、base、工厂体系或注册表。
现有地图协议由高德和百度两处真实实现共同使用，不扩展为插件平台。

## 简单优先

- 主要流程必须能从一个函数自上而下读完，辅助逻辑紧邻调用点。
- 默认只查有限地点、调用一次模型；不让模型控制查询循环。
- 第二处真实重复出现后再抽象，不为未来添加参数、开关、基类或接口。
- 单个功能尽量修改 1–3 个文件；跨 5 个及以上文件说明原因。
- 重命名必须同步导入、调用、样例、测试与文档。纯整理与功能变更分开提交。
- 注释、文档字符串和文档用简体中文，公共函数有简短且有意义的文档字符串。
- 文档描述实际代码和下一步，不能把设计写成已实现功能。

## 数据和外部调用

输入在调用供应商前校验；输出检查完整日期、时间顺序和真实地点引用。
模型只引用候选地点 ID；坐标、来源、查询时间由地图返回并由程序装配。
未知费用使用 null，未知距离写“待核实”，不得以 0 冒充查得价格。
`point` 是现有 SVG 像素坐标，不能直接塞入经纬度。
当前输出为首次生成草稿，不宣称完成预算、天气、酒店、路线或预约核验。
模型单次请求与整轮规划均有超时，整轮超时必须覆盖地图查询。
密钥仅从环境变量读取，不写源码、文档、日志或前端；只提交 `.env.example`。
自动测试使用替身；真实服务联调需明确授权并确认供应商、输入和调用范围。

## 环境与验证

Python 使用 uv，根目录保留 pyproject.toml、uv.lock、.python-version，
保持 `[tool.uv] package = false`。依赖通过 uv add/remove 管理并同步锁文件。
前端使用 pnpm，锁文件随依赖变更更新。

```bash
uv sync --offline
uv run ruff check backend
uv run ruff format --check backend
uv run pytest backend/tests -q
uv run --env-file .env python -m backend examples/trip-request.json
```

最后一条会调用真实地图和模型，不属于离线测试。标准输出只写结果 JSON，进度写标准错误。
前端在 frontend/ 执行 `pnpm typecheck`、`pnpm lint`、`pnpm build`。
交付如实区分协议替身测试、真实服务验证和仍未完成的阶段，不自动提交 Git。
Git 提交和 PR 使用简体中文及 Conventional Commits，scope 为 tripweave，type 按真实变更选择。
