# 开发路线与目录

## 按教程拆分任务

参考 [Hello-Agents 第十三章](https://hello-agents.datawhale.cc/#/./chapter13/第十三章%20智能旅行助手)，
采用研究资料后统一规划的分工。保留现有 React 前端，当前只实现独立 CLI。

```text
需求 JSON → TripRequest 校验 → 地图 MCP 工厂 → 建立会话并发现工具
                                              ↓
                            景点/美食 Agent → 天气 Agent → 住宿 Agent
                                              ↓
                           工具事实提取 + 研究资料 → Planner
                                              ↓
                                日期/时间/地点校验 → PlanResult JSON
```

三个研究 Agent 使用 LangChain create_agent，各有独立消息与调用上限；顺序运行便于定位问题。
Planner 使用结构化模型调用汇总。没有自研 Agent 框架、Supervisor、任务队列或自定义状态图。
LangChain 底层图运行机制由框架提供，不在业务代码重复实现。

## 工厂与 MCP

`create_map_mcp(settings)` 根据 MAP_PROVIDER 创建 MultiServerMCPClient：

| 供应商 | 官方入口 | 凭据参数 |
| --- | --- | --- |
| 高德 | https://mcp.amap.com/mcp | key |
| 百度 | https://mcp.map.baidu.com/mcp | ak |

工厂不连接服务、不查询行政区、不解析 REST 回包。会话由用例入口统一打开和关闭，
工具通过 load_mcp_tools 动态发现，不手写 MCP 握手、工具定义或地图请求。

研究 Agent 只获得已知的只读搜索、详情、地理编码或天气工具，不获得分享、打车等工具。
现阶段服务端更改工具名时会出现缺失说明，不能声称兼容所有未来版本。
没有候选地点 ID 与有效坐标时停止；不从 Agent 摘要捏造地点填补结果。

## 源码阅读顺序

| 文件 | 职责 |
| --- | --- |
| examples/trip-request.json | 可执行需求样例 |
| backend/__main__.py | 读取请求、加载配置、输出进度和 JSON |
| backend/api/app.py | FastAPI 应用装配、生命周期和路由注册 |
| backend/api/exception_handlers.py | 全局异常处理器 |
| backend/api/routes/ | health 与 plans 路由 |
| backend/errors/api.py | API 异常与规划失败映射 |
| backend/schemas/api.py | 通用成功与失败响应 |
| backend/services/planning.py | 顺序编排、校验与前端结果装配 |
| backend/integrations/map_mcp.py | 工厂选择官方 MCP 服务 |
| backend/agents/research.py | 三个研究角色、工具范围、框架调用限制 |
| backend/integrations/place_evidence.py | MCP JSON/structuredContent 到 Place 的最小字段映射 |
| backend/agents/planner.py | 用研究证据生成完整行程 |
| backend/schemas/trip.py | 请求、草稿、前端结构和研究证据 |

地点映射仍需兼容供应商的 id/uid、字符串/对象坐标；这是展示数据转换，
不再维护底层 HTTP、地图查询参数或供应商 REST 错误处理。

## 后续顺序

薄后端接口已增加，真实 MCP 工具清单、权限、回包形状及模型工具调用质量仍需验证。
前端随后提交需求并消费结果，保留原有编辑与浏览器保存。
天气日期覆盖、酒店价格、交通和预算核验逐项增强，不把查询到候选等同于完成预订或可出行保证。
