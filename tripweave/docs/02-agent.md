# 独立旅行规划 Agent

## 准备环境

在项目根目录执行 `uv sync --offline`，缓存不足时执行 `uv sync`。
复制 `.env.example` 为 `.env`，填写以下配置：

| 变量 | 用途 |
| --- | --- |
| MODEL_API_KEY、MODEL_BASE_URL、MODEL_NAME | 支持工具结构化输出的 OpenAI 兼容模型 |
| MAP_PROVIDER | amap 或 baidu，沿用已有适配器 |
| AMAP_API_KEY / BAIDU_MAP_API_KEY | 只填选定供应商的 Web 服务密钥 |
| MODEL_TIMEOUT_SECONDS | 单次请求超时，默认 60 秒 |
| PLANNER_TIMEOUT_SECONDS | 地图到结果装配的整轮超时，默认 300 秒 |
| MODEL_ENABLE_THINKING | auto / true / false；auto 不发送供应商扩展参数 |
| MODEL_THINKING_BUDGET | 可选，供应商支持时使用 |

不依赖模块导入时读取 `.env`，由 `uv run --env-file .env` 明确加载。
模型可内部思考，但程序不收集或展示思考链，不使用 SDK 私有方法补字段。

## 输入与执行

修改 examples/trip-request.json：目的地、出发日期、1–5 天、1–12 人、全团预算必填。
预算以人民币计，不含往返大交通。pace 为 relaxed/balanced/packed，兴趣和补充说明可选。
只支持一次一个国内城市或区县，目的地歧义时返回错误。

```bash
mkdir -p tmp/agent
uv run --env-file .env python -m backend examples/trip-request.json > tmp/agent/result.json
```

进度写标准错误，结果 JSON 写标准输出。成功退出码 0，输入、配置、供应商、模型、
校验或超时失败退出码 1；失败不会伪造成功结果。旧的 backend.agents.planner 启动入口已移除。

## 一次运行具体做什么

1. Pydantic 检查输入，确认日期区间可表示。
2. 地图解析城市/区县，查询景点和当地美食；有兴趣则追加第一种兴趣，最多三次检索。
3. 每类最多五个地点，按供应商 ID 去重；没有地点直接停止。
4. 将需求、候选地点名称、地址和 ID 交给模型一次，使用 LangChain 标准结构化输出。
5. 检查完整连续日期、时间递增且不重复、活动只引用本轮地点。
6. 程序装配前端需要的 Trip、地点来源、回复摘要及未核验说明。

不循环纠错，不自动重试模型，不让模型编造坐标。结果无效时直接显示失败原因，
调整需求或模型后人工重跑。总超时包住地图阶段，单次地图请求另限 15 秒。

## 能力边界

现阶段只生成首次行程。instruction 是首次生成的偏好补充，不是局部修改接口。
预算只是安排时的参考，没有费用数据就返回 null，不能验证预算是否满足。
地点真实存在不代表开放或可预约；未接入天气、住宿、路线、营业时间和票价查询。
没有 HTTP 接口、服务端保存、版本运行状态、用户系统或流式输出协议。

## 验证

```bash
uv run ruff check backend
uv run ruff format --check backend
uv run pytest backend/tests -q
```

测试经过真实 ChatOpenAI SDK、流式 HTTP 解析和结构化结果解析，使用合成响应替代外部网络；
覆盖两家地图、1/3/5 天、无地点、虚构地点、错位日期、重复时间、输入边界与整轮超时。
这能验证程序和协议路径，不证明真实服务权限、额度、模型工具输出质量或目的地覆盖。
用户当前选择暂不调用真实服务。后续恢复在线联调时，应单独检查阶段输出及结果，
确认后再开始后端接口。
