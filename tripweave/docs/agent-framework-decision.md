# TripWeave 第一个 Agent 项目的框架选择与学习路线

记录日期：2026-11-03  
状态：选型建议，尚未安装依赖或实现项目  
背景：[此前的「分析 Agent 框架」对话](chatgpt-conversation://6ae927a2-faec-83e9-9da2-5980a4fc9ca8)

## 1. 我的推荐

**现在先用 LangChain 的 `create_agent` 做 TripWeave 首版；在独立练习中手写一个最小 Agent Loop；当项目确实需要明确的业务分支和恢复执行时，再显式使用 LangGraph。暂不以 Deep Agents 或 pi-agent-core 为主线，也不从零开发通用框架。**

这里的前提是：你希望既完成第一个能用的旅行规划项目，又理解 Agent 原理，并沿用此前讨论的 Python / FastAPI 方向。当前本地 `tripweave` 只有空的 `backend/`、`frontend/`、`docs/` 目录，没有已有技术栈需要迁移；Python 是基于对话的建议，不是本地代码已经确立的事实。

具体顺序是：

1. **理解原理**：用一次短练习手写模型—工具循环，能解释消息如何流转后就结束练习。
2. **完成项目**：LangChain `create_agent` + 单个旅行 Planner + 少量工具 + 确定性的行程校验。
3. **处理复杂流程**：遇到暂停恢复、明确分支或局部重算需求，再用 LangGraph 编排，复用原来的 Planner 和业务服务。
4. **研究框架**：积累真实问题后再读 pi-agent-core、比较不同运行时；是否自研由具体缺口决定。

**“先用成熟框架，以后再考虑自己写”是我推荐的方向，但“以后必须自研”不是学习终点。能解释框架的边界、定位失败原因、合理替换组件，比拥有一个自制框架更重要。**

## 2. 从之前的对话继承什么，调整什么

之前的对话围绕智旅云图展开，之后确定项目名为“途织 · TripWeave”。与本次选择直接相关的观点是：区分固定业务编排与自主工具循环；用成熟运行时承接通用能力；把旅行知识、地点约束、预算和校验逻辑写在业务层。

本次重新读取了参考项目的[依赖文件](https://github.com/tutu-zzz/zhilv-yuntu/blob/main/backend/requirements.txt)和[旅行服务代码](https://github.com/tutu-zzz/zhilv-yuntu/blob/main/backend/app/services/trip_service.py)。依赖仍声明 LangChain 0.2–0.3 范围，服务代码可见显式编排和候选 POI 校验。它可以提供业务工程参考，但新项目不应直接照搬这组旧依赖。本次不是对其整个仓库的重新审计。

此前回答倾向于“FastAPI + LangGraph + 独立 RAG/Memory”，那更接近项目扩展后的架构。**对你的第一个可运行版本，我把起点收缩为 LangChain `create_agent`；LangGraph 保留为有需求时才显式使用的下一层。** 这能让你先理解一个循环，而不是同时学习图状态、路由、持久化和整个旅行产品。

此前助手还提到你使用过 HelloAgents、Qdrant、Neo4j 等；这些不是本次可见用户消息充分确认的前提，因此不据此给首版增加依赖。

## 3. 这些方案分别解决什么问题

你提到的 `deepagengs`，这里按 LangChain 生态的 **Deep Agents（包名 `deepagents`）** 理解。它们并非五个同层级、必须互斥的选择。

| 方案 | 主要负责什么 | 你还需要做什么 | 对 TripWeave 的建议 |
| --- | --- | --- | --- |
| LangChain `create_agent` | 提供标准模型—工具循环、模型/工具抽象和可扩展入口 | 工具实现、业务状态、校验、预算控制和评估 | **首版主选** |
| LangGraph | 显式控制状态、节点、分支及执行恢复 | 设计状态与执行边界，接好持久化和业务服务 | **第二阶段按需引入** |
| Deep Agents | 在基础循环上提供上下文管理、文件系统、子 Agent 等能力 | 配置能力、工具、执行环境及领域规则 | 长任务和研究型产品再评估 |
| pi-agent-core | TypeScript 的轻量 Agent 内核，处理工具执行和事件流 | 组装应用服务、持久化和业务工作流 | 全 TypeScript 路线的备选 |
| 自己写最小 Loop | 让模型调用、工具结果和终止条件完全可见 | 自己处理协议、错误、限制和上下文 | 原理练习适合 |
| 自己写通用框架 | 为多个应用抽象统一运行机制 | 持续承担兼容、恢复、观测和维护成本 | 第一个项目不作为目标 |

当前官方定位是：Deep Agents 建立在 LangChain Agent 之上，LangChain Agent 运行于 LangGraph；LangGraph 也可以脱离 LangChain 使用。因此从 `create_agent` 起步，已经在使用其底层运行时，不需要先手写外层 `StateGraph`。参见 [LangChain 概览](https://docs.langchain.com/oss/python/langchain/overview)与 [LangGraph 概览](https://docs.langchain.com/oss/python/langgraph/overview)。

## 4. 为什么首版选 LangChain，而不直接铺开 LangGraph

这是针对你的学习顺序和首版范围作出的判断，不是所有 Agent 项目的通用排名。

TripWeave 首先要验证的问题是：用户给出目的地、日期、预算和偏好后，系统能否查询真实地点，生成结构正确、约束合理的行程，并根据补充要求修改。这个闭环并不要求一开始就有多个 Agent 或复杂图结构。

我建议先让一个 Planner 使用两类查询工具，例如 `search_places` 和 `get_weather`。路线查询随后接入。预算汇总、日期合法性、候选地点 ID 和行程版本保存，由普通业务函数处理；这些检查需要稳定执行，不交给模型决定是否调用。

模型负责选择需要补充的信息和组合方案，程序负责约束执行结果。这样你可以很清楚地观察：模型选了哪个工具、参数是否正确、工具结果如何改变后续答案、失败发生在模型还是业务服务。

官方 LangGraph 文档也建议刚开始学习 Agent 的开发者先了解模型和工具，并可从 LangChain 的预构建循环入手；LangGraph 的价值在需要精细控制混合工作流时更突出。[官方说明](https://docs.langchain.com/oss/python/langgraph/overview)

如果你确认首个里程碑就必须实现“等待用户确认后继续”和“服务重启后恢复”，则可以直接选 LangGraph。判断依据是首版验收条件，而不是框架名字是否更高级。

## 5. 为什么暂不以 Deep Agents 为起点

Deep Agents 面向复杂多步骤任务，提供上下文管理、虚拟文件系统、子 Agent，以及可配置的规划等能力。这里的文件系统也不等于自动拥有一个已配置好的业务知识库。[Deep Agents 官方概览](https://docs.langchain.com/oss/python/deepagents/overview)

我的判断是：TripWeave 首版的主要困难更可能在地点真实性、时间安排、路线和预算一致性。额外的任务分解与委派，会增加你需要理解的执行路径，却未必先改善这些问题。框架提供规划能力，也不能保证规划出来的旅行可行。

当产品变成“综合大量网页、文件及多个目的地，持续收集证据并产出长篇旅行研究报告”，再做一个独立的 Deep Agents 原型很合理。用相同请求比较结果质量、调用次数、耗时和成本，达标后才考虑接入主项目。

**不要按“LangChain → LangGraph → Deep Agents”的顺序机械升级。** 前两者侧重执行控制，后者提供更多预设能力，是否采用由工作负载决定。

## 6. pi-agent-core 值不值得整合

### 它是什么

pi-agent-core 是可嵌入的 Agent 内核，不局限于写代码。其官方 README 展示了有状态 Agent、工具执行、流式事件、取消及上下文转换等接口；它基于 pi-ai 处理模型交互。[Agent 包文档](https://github.com/earendil-works/pi/blob/main/packages/agent/README.md)

检索时旧地址 `badlogic/pi-mono` 已跳转至 `earendil-works/pi`，当前主分支的包名是 `@earendil-works/pi-agent-core`，以 TypeScript/ESM 发布。老教程可能仍使用 `@mariozechner/pi-agent-core`；正式实施时应按选定发布版本核验包名、接口和 Node 要求，而不是混用不同年代的示例。本次没有核验 npm 最新发布版本。[包定义](https://github.com/earendil-works/pi/blob/main/packages/agent/package.json)

### 轻量内核意味着什么

它能省掉基础循环和事件处理中的一部分实现，但不等于接入后自动获得旅行工作流的完整恢复机制。需要区分进程中的 Agent 状态、会话历史保存，以及业务步骤在故障后的恢复语义。

Pi 的上层 `pi-coding-agent` SDK 另外提供 `AgentSession`、持久会话和压缩等能力，不能把这些都算到 agent-core 本身。官方 SDK 文档明确区分了会话与其存储管理器。[Pi SDK 文档](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md)

### 放进 TripWeave 的成本

如果沿用 Python/FastAPI，通常要额外运行一个 Node Agent 服务，由它通过 HTTP 调用 Python 业务工具。这样会多出服务部署、消息格式、流式事件转发、取消传播和两侧错误关联等工作。这是基于跨语言集成方式的工程判断，并非 pi 强制要求微服务。

如果整个后端改用 TypeScript，则这些跨语言成本可以避免，pi-agent-core 会成为合理候选。此时你需要愿意自己组装更多应用能力，并且确实想掌握内核及上下文处理方式。

**所以我现在不建议“FastAPI + LangGraph + pi-agent-core 全部整合”。** 两套循环容易出现职责重复：谁拥有消息历史、谁决定下一轮、谁控制取消和重试？先选择一个主要执行入口。将来若比较 pi 与 LangChain，做同一组任务的独立原型即可。

## 7. 自己写什么，以及什么时候值得写框架

### 现在值得手写：最小循环

单独练习下面的过程，使用一个工具就够：

```text
用户消息 → 模型响应
             ├─ 普通回答 → 结束
             └─ 工具调用 → 校验名称与参数 → 执行工具
                                           ↓
                         回填与调用 ID 对应的工具结果 → 再次请求模型
```

练习必须有最大轮数、工具异常和超时的处理，并能打印每轮输入、工具参数和结果。特别留意 assistant 工具调用消息与 tool 结果的对应关系；只把结果拼进 Prompt，不等于正确实现工具调用协议。

练习完成的标准是：你能解释为什么工具结果要再次交给模型，为什么会出现无限循环，以及参数错误时下一轮能看到什么。无需为此先设计插件系统、通用记忆层或多 Agent 调度器。

### 项目里值得自己写：旅行能力

- 地点候选集及 POI ID 约束，防止输出不存在的地点。
- 路线耗时、每日活动数量、预算计算与校验。
- 用户需求合并和行程局部修改，避免一次修改破坏整个计划。
- 检索结果的来源、时间和适用范围，以及失败时的降级策略。
- 一组能持续比较版本质量的旅行请求和运行记录。

这些是产品能力；采用成熟运行时并不会让它们失去工程含量。

### 后来可能值得写：小范围可复用组件

当你在不同任务中反复碰到同一个真实缺口，例如特殊工具审计、上下文裁剪或事件协议，先把那个组件提取出来。只有当多个应用确实需要一套共同运行机制，且现成框架难以满足时，再考虑把范围扩大为框架。

在决定替换运行时之前，应能拿出一个具体失败案例和对照结果，说明自研改善了什么。学习深入后仍然使用现成框架，完全可以是正确选择。

## 8. 建议的首版边界与落地步骤

以下是开发建议，不代表这些功能已经实现。每阶段以验收结果推进，不以“学完某框架”为前置条件。

| 阶段 | 做什么 | 完成标准 |
| --- | --- | --- |
| A：原理练习 | 独立的最小 Loop，一个模拟查询工具 | 看得到一次完整的工具调用、结果回填和终止；错误或超限也能退出 |
| B：首个可用版本 | LangChain 单 Planner，接真实地点查询与天气工具，输出结构化行程 | 一次真实请求可以从 API 进入、查到数据、生成并通过业务校验 |
| C：完善旅行体验 | 追加偏好、局部修改、路线校验、行程保存、必要的检索 | 修改第二天时保持其他天的有效内容；未知信息明确标记 |
| D：按需编排 | 当需求触发时显式使用 LangGraph | 有实际分支或恢复场景的验证，业务服务可以继续复用 |
| E：比较内核 | 单独用 pi 或 Deep Agents 重做一个小场景 | 用相同输入和评价方式说明差异，再决定是否迁移 |

首版先限制为单城市、少量天数的旅行计划和修改。可以先通过 API 文档或简单页面验证，再扩展地图交互。RAG 在确实需要攻略知识时加入；首版不必同时引入向量库、图数据库、Redis 和复杂长期记忆。

建议准备约 10–20 条固定请求作为小规模回归集：正常行程、预算很低、日期缺失、地点重名、雨天替代、工具超时、候选地点不足、修改某一天等。这个数量只用于起步，不能证明生产可靠性。

验收重点应包括：

- 地点来自查询候选，标识能够追溯；估价与实时价格清晰区分。
- 日期、活动数量和预算计算由程序检查。
- 工具失败有可解释结果，修复次数和运行成本有上限。
- 运行记录能关联请求、模型调用、工具参数、工具结果及校验失败原因。
- 自然语言修改确实影响目标行程；至少一个场景可观察到“查询结果改变了后续方案”。

结构化输出只解决输出形状问题，并不能证明地点真实或时间安排可行。模型服务对工具调用和结构化输出的支持，也需要用你最终选择的服务实测。

## 9. 何时显式引入 LangGraph

只要出现下面某个已经确认的需求，就值得评估外层图编排：

- 用户补充必要信息之前，需要暂停，收到信息后继续。
- “预算超限”和“路线过长”需要进入不同修复分支。
- 请求中断或进程重启后，希望从保存的状态继续。
- 不同阶段需要分别追踪状态和重试，不能总是重跑整个任务。

届时可以将流程组织为：需求解析 → 数据查询 → Planner → 规则校验 → 有限修复或返回。Planner 可以复用已有 LangChain Agent，其余节点继续调用普通 Python 业务服务。

需要保存状态时，明确区分 checkpointer（当前会话的图状态）与 store（跨会话数据）。内存 checkpointer 适合练习，不能满足进程重启后的恢复要求；需要选择持久后端。用户保存的行程和版本仍应作为业务数据明确管理。[LangGraph 持久化文档](https://docs.langchain.com/oss/python/langgraph/persistence)

不要把“可恢复执行”理解为所有外部操作都自动保证只执行一次。引入有副作用的工具时，仍需设计重复执行的处理方式和业务一致性。

## 10. 保留演进空间，但不先造抽象平台

代码组织可以保持以下边界，无需先搭建完整目录树：

- `services/`：地图、天气、检索等领域服务，输入输出尽量使用普通数据结构。
- `schemas/`：请求、候选地点、行程及校验结果。
- `validators/`：预算、时间、地点与行程约束。
- `agents/`：模型、工具适配、Prompt 及 Planner 创建。
- `workflows/`：需求出现后再放显式 LangGraph 编排。

对 API 层提供一个清晰的旅行规划服务入口即可。更换运行时仍会涉及消息、流式输出和恢复语义的适配；这样的分层只是减少业务重写，不保证任意框架可以无成本切换。

最终选型是：**用 LangChain 跑通第一个 Agent，用业务代码保证旅行质量，用小型手写练习理解原理，用实际需求决定 LangGraph、pi、Deep Agents 和自研的出场时间。**

## 资料与核验边界

本文读取了引用对话，并通过 Context7 及官方文档/仓库核对上述框架定位。判断基于 2026-11-03 可访问的文档和主分支；没有运行这些框架做性能对比，没有安装依赖，也没有据此声称某方案更快或更省钱。实施时应选择兼容的发布版本、生成锁文件，再验证实际模型服务的支持情况。

- [LangChain 概览](https://docs.langchain.com/oss/python/langchain/overview)
- [LangGraph 概览](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Deep Agents 概览](https://docs.langchain.com/oss/python/deepagents/overview)
- [pi-agent-core README](https://github.com/earendil-works/pi/blob/main/packages/agent/README.md)
- [pi-agent-core 包定义](https://github.com/earendil-works/pi/blob/main/packages/agent/package.json)
- [Pi 上层 SDK](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md)
- [参考项目依赖](https://github.com/tutu-zzz/zhilv-yuntu/blob/main/backend/requirements.txt)
- [参考项目旅行服务](https://github.com/tutu-zzz/zhilv-yuntu/blob/main/backend/app/services/trip_service.py)
