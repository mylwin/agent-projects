# TripWeave 文档导航

按主题分目录，每个目录内独立编号；本文作为唯一文档总入口，不加数字前缀，也不在子目录重复建立 README。

## 架构探索与系统方案

- [Agent 框架探索与学习路线](01-architecture/01-agent-framework-decision.md)：LangChain、LangGraph、Deep Agents 与自研的取舍。
- [技术选型与系统架构](01-architecture/02-system-architecture.md)：模块职责、运行协议、数据模型与实施阶段。
- [交互架构图](01-architecture/03-diagrams/01-system-architecture.html)与[图定义](01-architecture/03-diagrams/02-system-architecture.json)：目标架构的可视化与可编辑源文件。

## 前端实施计划

- [实施阶段与接入顺序](02-frontend/01-planning/01-implementation-plan.md)：当前原型、后端接入、真实助手与地图的实施边界。

## 前端设计

- [界面设计与实现边界](02-frontend/02-design/01-interface-design.md)：暖白酒红的旅行日笺布局、交互与响应式。
- [素材、图标与字体](02-frontend/02-design/02-assets-and-icons.md)：园林配图、路线、罗盘品牌标记与字体说明。

## 前端数据

- [数据契约与后端接入](02-frontend/03-data/01-data-contract.md)：字段、存储、接口接入与错误处理。
- [行程与初始对话样本](02-frontend/03-data/02-trip-fixture.json)：前端直接导入的完整三天行程。
- [助手示例数据](02-frontend/03-data/03-assistant-examples.json)：示例提示与本地规则分类。

## 前端功能

- [计划项目与助手](02-frontend/04-features/01-plan-projects.md)：多计划、独立对话、侧栏与本地规则范围。
- [版本与最终方案](02-frontend/04-features/02-final-selection.md)：自动记录、结果选择与旧数据兼容。
- [返回提醒与出行信息](02-frontend/04-features/03-return-and-trip-info.md)：离开选择流程与弹窗信息层级。

## 文档与临时产物约定

`docs/` 只保留正式说明、样本数据及架构图源文件。新增内容归入对应主题；目录和普通文件按各层阅读顺序编号，README 不编号。

校验报告、截图、日志与中间产物放在 `tmp/frontend/YYYY-MM-DD/<任务名>/`，架构图工具的校验回执放在 `tmp/architecture/`。`tmp/` 整体由 Git 忽略，不作为正式文档或运行依赖。

当前已实现可运行前端原型，真实 Agent、业务后端和地图服务尚未接入。
目录中的架构、实施计划和目标接口不代表对应能力已经完成。
