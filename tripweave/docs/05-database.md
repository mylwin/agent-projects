# 数据库设计

状态：已提供可选的 MySQL 连接配置，用户注册和登录已接入，计划业务读写尚未实现；前端计划仍保存在 localStorage。

在项目根目录 `.env` 中设置 `DB_NAME`、`DB_USER`、`DB_PASSWORD`，并按需设置 `DB_HOST` 和 `DB_PORT`（默认分别为 `127.0.0.1` 和 `3306`）。先创建 MySQL 8.0.16+ 数据库并执行初始化脚本。引擎在首次使用时才连接，应用关闭时释放连接池；认证接口使用数据库；启动成功不代表连接验证成功。未设置 `DB_NAME` 时不启用连接。

初始化脚本见 [resource/schema.sql](../resource/schema.sql)。接口请求/响应契约见 [06-api-schema.md](06-api-schema.md)。

目标：

- 用户名和密码登录，不引入 token/session 表。
- 保存每次生成的计划结果，支持同一计划的多个版本。
- 保留研究摘要、工具原文和供应商公开返回的推理，方便后续回看。

不包含：服务端对话、待处理调整清单、分享协作、登录会话撤销。这些等出现真实需求再增加。

## 总体关系

所有表名统一以 `tb_` 开头。

```text
tb_user 1 ── n tb_project
tb_user 1 ── n tb_generation_run

tb_project 1 ── n tb_plan_revision
tb_project 1 ── n tb_generation_run

tb_plan_revision n ── 1 tb_generation_run
tb_generation_run 1 ── n tb_research_report
tb_research_report 1 ── n tb_tool_evidence
tb_generation_run 1 ── n tb_model_call
```

初始化脚本和当前模型使用 MySQL；下列字段描述保留了早期设计的 PostgreSQL 类型，具体以初始化脚本为准。

## 1. tb_user

```text
id             bigserial primary key
username       text unique not null
password_hash  text not null
created_at     timestamptz not null default now()
last_login_at  timestamptz
```

- 只做用户名和密码登录；密码使用带随机盐的 scrypt 哈希，禁止明文。
- 不建 `tb_auth_session`、refresh token、JWT 黑名单等表。
- 登录态由接口层处理，可以使用签名 Cookie 或 HTTP Basic；数据库只负责用户身份。
- `username` 建议加 `lower(username)` 唯一索引，避免大小写重复。

## 2. tb_project

```text
id                 bigserial primary key
user_id            bigint not null references tb_user(id) on delete cascade
name               text not null
destination        text not null
final_revision_id  bigint
created_at         timestamptz not null default now()
updated_at         timestamptz not null default now()
```

- 对应前端“旅行计划文件夹”。
- `destination` 冗余一列，方便列表搜索，不必解析 JSON。
- `final_revision_id` 指向选定版本；它与 `tb_plan_revision.project_id` 形成循环引用，可以不加外键、用延迟约束，或在业务层校验。

## 3. tb_plan_revision

```text
id                 bigserial primary key
project_id         bigint not null references tb_project(id) on delete cascade
number             int not null
title              text not null
schema_version     int not null default 1
trip               jsonb not null
places             jsonb not null default '[]'
warnings           jsonb not null default '[]'
reply              text
generation_run_id  bigint references tb_generation_run(id)
created_at         timestamptz not null default now()
unique(project_id, number)
```

- 每次生成或手动保存的行程版本存一行。
- 不拆 `days`、`activities` 表；版本是不可变快照，整份 `Trip` 存 JSONB 更适合当前阶段。
- `places` 保存地点事实及其坐标、坐标系、来源和接收时间，不重新推导。
- `generation_run_id` 对 AI 生成版本有值；手动编辑版本可以为空。

## 4. tb_generation_run

```text
id             bigserial primary key
project_id     bigint references tb_project(id) on delete set null
user_id        bigint not null references tb_user(id) on delete cascade
request        jsonb not null
status         text not null check (status in ('running', 'succeeded', 'failed'))
error_stage    text
error_code     text
error_message  text
model_name     text not null
map_provider   text not null
started_at     timestamptz not null default now()
finished_at    timestamptz
duration_ms    int
```

- 记录每次生成尝试，包括失败尝试。
- `project_id` 可空，允许在项目创建前记录一次失败生成。
- `error_message` 必须是脱敏后的说明；不保存密钥、MCP 连接 URL 或认证参数。

## 5. tb_research_report

```text
id          bigserial primary key
run_id      bigint not null references tb_generation_run(id) on delete cascade
topic       text not null check (topic in ('attractions', 'weather', 'hotels'))
summary     text not null
warnings    jsonb not null default '[]'
created_at  timestamptz not null default now()
unique(run_id, topic)
```

对应 `PlanResult.research` 中每个研究主题的摘要和警告。一个生成运行最多三条记录。

## 6. tb_tool_evidence

```text
id                  bigserial primary key
report_id           bigint not null references tb_research_report(id) on delete cascade
sequence            int not null
tool                text not null
tool_call_id        text
content             text not null
structured_content  jsonb
fetched_at          timestamptz not null
```

- 保存地图工具原文，方便追溯地点、天气和酒店信息的来源。
- `content` 可能很大，当前阶段用 `TEXT` 保存；数据量变大后再考虑对象存储和摘要字段。
- 工具返回中不得写入密钥或完整认证 URL。

## 7. tb_model_call

```text
id             bigserial primary key
run_id         bigint not null references tb_generation_run(id) on delete cascade
agent          text not null
call_index     int not null
model_name     text not null
provider       text
reasoning      text
content        text
tool_calls     jsonb
started_at     timestamptz not null default now()
finished_at    timestamptz
duration_ms    int
unique(run_id, agent, call_index)
```

- `agent` 取 `attractions`、`weather`、`hotels` 或 `planner`。
- `content` 保存该轮模型正文，`tool_calls` 保存工具名、参数和调用 ID。
- `reasoning` 只保存供应商公开返回的推理；没有返回就存 `null`，不伪造、不补写隐藏推理。
- 当前 `PlanResult` 不包含推理内容，后续需要增加一个轨迹记录回调，把公开推理和模型调用写入这张表。

## 索引

```sql
create unique index tb_user_username_idx
    on tb_user (lower(username));

create index tb_project_user_updated_idx
    on tb_project (user_id, updated_at desc);

create index tb_plan_revision_project_idx
    on tb_plan_revision (project_id, number);

create index tb_generation_run_project_idx
    on tb_generation_run (project_id, started_at desc);

create index tb_research_report_run_idx
    on tb_research_report (run_id);

create index tb_tool_evidence_report_idx
    on tb_tool_evidence (report_id, sequence);

create index tb_model_call_run_idx
    on tb_model_call (run_id, agent, call_index);
```

## 与现有结果结构的关系

| 现有结构 | 存储位置 |
| --- | --- |
| `PlanResult.trip` | `tb_plan_revision.trip` |
| `PlanResult.places` | `tb_plan_revision.places` |
| `PlanResult.warnings` | `tb_plan_revision.warnings` |
| `PlanResult.reply` | `tb_plan_revision.reply` |
| `PlanResult.research[].summary` | `tb_research_report.summary` |
| `PlanResult.research[].evidence` | `tb_tool_evidence` |
| 模型公开推理 | `tb_model_call.reasoning`，当前尚未采集 |
| 模型正文与工具调用 | `tb_model_call.content` / `tool_calls`，当前尚未写入数据库 |

## 当前不建的表

- `tb_auth_session`：没有 token 撤销、刷新或持久登录需求时不需要。
- `tb_message`：服务端对话尚未实现，前端继续用本地消息。
- `tb_revision_request`：待处理调整清单仍由前端管理。
- `tb_project_member`：没有分享协作需求。

出现对应需求时再增加，不提前预留空表。

## 后续实现顺序

1. 确定数据库迁移工具并接入版本管理。
2. 用户注册/登录已实现，后续可根据需求增加登录态撤销。
3. 增加项目、版本和生成结果的保存接口。
4. 增加生成轨迹记录：研究摘要、工具证据、公开推理。
5. 前端从 localStorage 迁移到服务端前，先确定多端同步和冲突策略。
