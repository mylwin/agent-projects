# TripWeave 前端

基于用户最终确认的暖白酒红旅行日笺设计，使用 React + TypeScript + Vite，图标来自 `lucide-react`。

## 启动

要求 Node.js 22.19+、pnpm 12.6.0。在本目录执行：

```bash
pnpm install --frozen-lockfile
pnpm dev
```

默认地址为 `http://127.0.0.1:5173/plans`，端口占用时以终端输出为准。

## 检查与构建

```bash
pnpm typecheck
pnpm lint
```

另提供 `pnpm build` 与 `pnpm preview`，本次交付未执行生产构建。

## 数据与能力

- 初始行程和对话来自 [02-trip-fixture.json](../docs/02-frontend/03-data/02-trip-fixture.json)，不维护重复数据文件。
- `/plans` 为我的旅行计划；支持新建计划、独立对话、结果版本、搜索与浏览器保存。
- 详情支持日期切换、活动编辑、路线高亮、侧栏收缩与悬停 1 秒展开。
- 手动编辑与有效助手调整自动记录版本；可从历史版本中选定最终方案，继续规划不会覆盖选择。
- 三个示例由本地规则演示处理和逐字回复；未知要求留在待处理清单。尚未接入真实模型。
- 图片为单独生成的园林意境配图；路线为可交互 SVG 概览，不提供真实导航。
- 完整字段与后端接入约定见 [01-data-contract.md](../docs/02-frontend/03-data/01-data-contract.md)。
- 项目应从父仓库整体使用；前端的初始样本在同级 `docs` 中，不要单独拷走 `frontend` 后遗漏样本。

项目文件夹、迁移和后端演进见 [01-plan-projects.md](../docs/02-frontend/04-features/01-plan-projects.md)。生产部署需为 `/plans` 等前端路径配置 SPA 回退。
