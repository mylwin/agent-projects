-- TripWeave 初始数据库结构（PostgreSQL）
-- 状态：设计稿，尚未接入应用；脚本可重复执行，不包含删除语句。

begin;

-- 用户只保留用户名和密码登录，不建 token/session 表。
create table if not exists tb_user (
    id            bigserial primary key,
    username      text not null,
    password_hash text not null,
    created_at    timestamptz not null default now(),
    last_login_at timestamptz
);

-- 旅行计划文件夹。
create table if not exists tb_project (
    id                bigserial primary key,
    user_id           bigint not null references tb_user(id) on delete cascade,
    name              text not null,
    destination       text not null,
    -- 业务层校验最终版本；不建循环外键。
    final_revision_id bigint,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

-- 每次生成尝试；失败记录也保留。
create table if not exists tb_generation_run (
    id            bigserial primary key,
    project_id    bigint references tb_project(id) on delete set null,
    user_id       bigint not null references tb_user(id) on delete cascade,
    request       jsonb not null,
    status        text not null check (status in ('running', 'succeeded', 'failed')),
    error_stage   text,
    error_code    text,
    error_message text,
    model_name    text not null,
    map_provider  text not null,
    started_at    timestamptz not null default now(),
    finished_at   timestamptz,
    duration_ms   int
);

-- 行程版本快照；不拆每日活动和地点表。
create table if not exists tb_plan_revision (
    id                bigserial primary key,
    project_id        bigint not null references tb_project(id) on delete cascade,
    number            int not null,
    title             text not null,
    schema_version    int not null default 1,
    trip              jsonb not null,
    places            jsonb not null default '[]'::jsonb,
    warnings          jsonb not null default '[]'::jsonb,
    reply             text,
    generation_run_id bigint references tb_generation_run(id) on delete set null,
    created_at        timestamptz not null default now()
);

-- 每个研究主题的摘要与警告。
create table if not exists tb_research_report (
    id         bigserial primary key,
    run_id     bigint not null references tb_generation_run(id) on delete cascade,
    topic      text not null check (topic in ('attractions', 'weather', 'hotels')),
    summary    text not null,
    warnings   jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

-- 地图工具原文；保留来源与接收时间。
create table if not exists tb_tool_evidence (
    id                 bigserial primary key,
    report_id          bigint not null references tb_research_report(id) on delete cascade,
    sequence           int not null,
    tool               text not null,
    tool_call_id       text,
    content            text not null,
    structured_content jsonb,
    fetched_at         timestamptz not null
);

-- 每轮模型调用；reasoning 只存供应商公开返回的内容。
create table if not exists tb_model_call (
    id          bigserial primary key,
    run_id      bigint not null references tb_generation_run(id) on delete cascade,
    agent       text not null check (agent in ('attractions', 'weather', 'hotels', 'planner')),
    call_index  int not null,
    model_name  text not null,
    provider    text,
    reasoning   text,
    content     text,
    tool_calls  jsonb,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    duration_ms int
);

create unique index if not exists tb_user_username_idx
    on tb_user (lower(username));

create index if not exists tb_project_user_updated_idx
    on tb_project (user_id, updated_at desc);

create unique index if not exists tb_plan_revision_project_number_idx
    on tb_plan_revision (project_id, number);

create index if not exists tb_generation_run_project_idx
    on tb_generation_run (project_id, started_at desc);

create unique index if not exists tb_research_report_run_topic_idx
    on tb_research_report (run_id, topic);

create index if not exists tb_tool_evidence_report_idx
    on tb_tool_evidence (report_id, sequence);

create unique index if not exists tb_model_call_run_agent_call_idx
    on tb_model_call (run_id, agent, call_index);

commit;
