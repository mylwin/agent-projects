# TripWeave 文档

当前目标：真实 Agent + MCP 联调仍是前置验证；薄 FastAPI 入口已增加，之后连接前端。

1. [开发路线与目录](01-development.md)：角色分工、工厂职责、代码阅读顺序。
2. [Agent 与 MCP 运行](02-agent.md)：配置、调用上限、结果和验证边界。
3. [前端数据](03-frontend-data.md)：行程、研究证据、坐标和接入差异。
4. [Agent 执行函数流程图](04-flowcharts/01-agent-execution.html)：从 CLI、MCP 连接、三个研究 Agent 到 Planner 校验与结果输出，附研究内部步骤、回调与异常说明。
5. [数据库设计](05-database.md)：用户登录、计划版本、生成轨迹和模型推理的存储设计（尚未实现）。

流程图为独立 HTML，可直接在浏览器打开。它依据绘制时的工作区源码快照生成，
包含未提交修改；节点可查看对应源码路径和行范围。修改代码后需重新生成。
正式 HTML 放在 `docs/04-flowcharts/`，候选规格、源码快照和校验回执保留在忽略的 `.archify/`。

## 当前状态

- 前端：本地计划管理、编辑、版本、最终方案、样例助手和浏览器保存，尚未接入 Agent。
- Agent：LangChain 三个研究 Agent 顺序运行，Planner 汇总、校验和装配行程。
- 地图：工厂切换高德、百度官方 Streamable HTTP MCP，使用官方协议适配库发现工具。
- 自动验证：真实 MCP 初始化、工具发现/调用、多 Agent 工具循环与模型 SDK 均由离线替身覆盖。
- 真实联调：沿用用户暂不调用真实服务的选择，尚未验证在线服务权限与响应差异。
- 后端接口：薄 FastAPI 入口与统一成功/失败响应已实现，真实服务联调未执行。
- 数据库：设计见 [05-database.md](05-database.md)，尚未实现；当前前端继续使用 localStorage，服务端保存和前端接入未开始。

旧单 Agent 版本已作为 Git 基线提交；更早的资料备份仍在忽略的 tmp/refactor/2026-11-05/。
