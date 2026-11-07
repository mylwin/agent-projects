-- TripWeave 初始数据库结构（MySQL 8.0.16+）
-- 说明：
--   1. 字符串列按用途改为 VARCHAR，便于索引；长文本用 TEXT。
--   2. jsonb -> JSON；timestamptz -> DATETIME(6)（存 UTC）。
--   3. 索引、外键、CHECK 全部内联在 CREATE TABLE 中，保证脚本可重复执行。
--   4. MySQL DDL 隐式提交，事务无法回滚建表，因此不写 START TRANSACTION。
--   5. 用户名唯一性依赖 utf8mb4_0900_ai_ci（大小写不敏感），已显式指定排序规则。

SET NAMES utf8mb4;

-- 用户表
CREATE TABLE IF NOT EXISTS tb_user (
    id            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    username      VARCHAR(255) NOT NULL                COMMENT '用户名，默认排序规则下大小写不敏感唯一',
    password_hash VARCHAR(255) NOT NULL                COMMENT '密码哈希，不存明文',
    created_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    last_login_at DATETIME(6)  NULL                    COMMENT '最近登录时间，可为空',
    PRIMARY KEY (id),
    UNIQUE KEY tb_user_username_idx (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='用户表，仅保存用户名和密码哈希，登录态不落库';

-- 旅行计划文件夹
CREATE TABLE IF NOT EXISTS tb_project (
    id                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id           BIGINT       NOT NULL                COMMENT '所属用户，用户删除时级联删除',
    name              VARCHAR(255) NOT NULL                COMMENT '项目名称',
    destination       VARCHAR(255) NOT NULL                COMMENT '目的地',
    final_revision_id BIGINT       NULL                    COMMENT '最终版本修订 ID，逻辑关联 tb_plan_revision.id，由业务层校验；不建外键以避免循环引用',
    created_at        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    updated_at        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY tb_project_user_updated_idx (user_id, updated_at DESC),
    CONSTRAINT fk_project_user FOREIGN KEY (user_id)
        REFERENCES tb_user (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='旅行计划文件夹/项目表';

-- 每次生成尝试（成功与失败均保留）
CREATE TABLE IF NOT EXISTS tb_generation_run (
    id            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    project_id    BIGINT       NULL                    COMMENT '关联项目；项目删除时置空，以保留历史运行记录',
    user_id       BIGINT       NOT NULL                COMMENT '所属用户，用户删除时级联删除',
    request       JSON         NOT NULL                COMMENT '本次生成请求 JSON',
    status        VARCHAR(20)  NOT NULL                COMMENT '运行状态：running / succeeded / failed',
    error_stage   VARCHAR(100) NULL                    COMMENT '失败阶段，可为空',
    error_code    VARCHAR(100) NULL                    COMMENT '失败错误码，可为空',
    error_message TEXT         NULL                    COMMENT '失败错误信息，可为空',
    model_name    VARCHAR(255) NOT NULL                COMMENT '使用的模型名称',
    map_provider  VARCHAR(100) NOT NULL                COMMENT '地图服务提供方',
    started_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '开始时间',
    finished_at   DATETIME(6)  NULL                    COMMENT '结束时间，可为空',
    duration_ms   INT          NULL                    COMMENT '耗时（毫秒），可为空',
    PRIMARY KEY (id),
    KEY tb_generation_run_project_idx (project_id, started_at DESC),
    CONSTRAINT fk_run_project FOREIGN KEY (project_id)
        REFERENCES tb_project (id) ON DELETE SET NULL,
    CONSTRAINT fk_run_user FOREIGN KEY (user_id)
        REFERENCES tb_user (id) ON DELETE CASCADE,
    CONSTRAINT chk_run_status CHECK (status IN ('running', 'succeeded', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='每次行程生成尝试记录，成功与失败均保留';

-- 行程版本快照
CREATE TABLE IF NOT EXISTS tb_plan_revision (
    id                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    project_id        BIGINT       NOT NULL                COMMENT '所属项目，项目删除时级联删除',
    number            INT          NOT NULL                COMMENT '项目内版本号，与 project_id 组合唯一',
    title             VARCHAR(255) NOT NULL                COMMENT '版本标题',
    schema_version    INT          NOT NULL DEFAULT 1      COMMENT '行程 JSON 结构版本，默认 1',
    trip              JSON         NOT NULL                COMMENT '完整行程数据 JSON',
    places            JSON         NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '地点数据 JSON 数组，默认空数组',
    warnings          JSON         NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '警告信息 JSON 数组，默认空数组',
    reply             TEXT         NULL                    COMMENT '回复文本，可为空',
    generation_run_id BIGINT       NULL                    COMMENT '关联生成运行；运行记录删除时置空',
    created_at        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY tb_plan_revision_project_number_idx (project_id, number),
    CONSTRAINT fk_revision_project FOREIGN KEY (project_id)
        REFERENCES tb_project (id) ON DELETE CASCADE,
    CONSTRAINT fk_revision_run FOREIGN KEY (generation_run_id)
        REFERENCES tb_generation_run (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='行程版本快照，行程主体以 JSON 保存，不拆每日活动和地点表';

-- 每个研究主题的摘要与警告
CREATE TABLE IF NOT EXISTS tb_research_report (
    id         BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    run_id     BIGINT      NOT NULL                COMMENT '关联生成运行，运行删除时级联删除',
    topic      VARCHAR(50) NOT NULL                COMMENT '研究主题：attractions / weather / hotels',
    summary    TEXT        NOT NULL                COMMENT '该主题摘要',
    warnings   JSON        NOT NULL DEFAULT (JSON_ARRAY()) COMMENT '警告信息 JSON 数组，默认空数组',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY tb_research_report_run_topic_idx (run_id, topic),
    CONSTRAINT fk_report_run FOREIGN KEY (run_id)
        REFERENCES tb_generation_run (id) ON DELETE CASCADE,
    CONSTRAINT chk_report_topic CHECK (topic IN ('attractions', 'weather', 'hotels'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='每次生成运行中每个研究主题的摘要与警告';

-- 地图工具原文证据
CREATE TABLE IF NOT EXISTS tb_tool_evidence (
    id                 BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    report_id          BIGINT       NOT NULL                COMMENT '关联研究报告，报告删除时级联删除',
    sequence           INT          NOT NULL                COMMENT '同一报告内的证据顺序',
    tool               VARCHAR(100) NOT NULL                COMMENT '工具名称',
    tool_call_id       VARCHAR(255) NULL                    COMMENT '工具调用 ID，可为空',
    content            TEXT         NOT NULL                COMMENT '工具返回原文',
    structured_content JSON         NULL                    COMMENT '结构化内容 JSON，可为空',
    fetched_at         DATETIME(6)  NOT NULL                COMMENT '接收/抓取时间',
    PRIMARY KEY (id),
    KEY tb_tool_evidence_report_idx (report_id, sequence),
    CONSTRAINT fk_evidence_report FOREIGN KEY (report_id)
        REFERENCES tb_research_report (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='地图工具返回原文及结构化内容，作为研究证据';

-- 每轮模型调用记录
CREATE TABLE IF NOT EXISTS tb_model_call (
    id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    run_id      BIGINT       NOT NULL                COMMENT '关联生成运行，运行删除时级联删除',
    agent       VARCHAR(50)  NOT NULL                COMMENT '调用代理：attractions / weather / hotels / planner',
    call_index  INT          NOT NULL                COMMENT '同一代理下的调用序号',
    model_name  VARCHAR(255) NOT NULL                COMMENT '模型名称',
    provider    VARCHAR(100) NULL                    COMMENT '模型供应商，可为空',
    reasoning   TEXT         NULL                    COMMENT '推理内容，仅存供应商公开返回的部分',
    content     TEXT         NULL                    COMMENT '模型输出内容',
    tool_calls  JSON         NULL                    COMMENT '工具调用信息 JSON',
    started_at  DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '开始时间',
    finished_at DATETIME(6)  NULL                    COMMENT '结束时间，可为空',
    duration_ms INT          NULL                    COMMENT '耗时（毫秒），可为空',
    PRIMARY KEY (id),
    UNIQUE KEY tb_model_call_run_agent_call_idx (run_id, agent, call_index),
    CONSTRAINT fk_model_call_run FOREIGN KEY (run_id)
        REFERENCES tb_generation_run (id) ON DELETE CASCADE,
    CONSTRAINT chk_model_call_agent CHECK (agent IN ('attractions', 'weather', 'hotels', 'planner'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='每轮模型调用记录';

-- 为既有 MySQL 部署新增项目对话表；可重复执行，不修改原有行程数据。
CREATE TABLE IF NOT EXISTS tb_conversation_turn (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    base_revision_id BIGINT NOT NULL,
    result_revision_id BIGINT NULL,
    day_id INT NOT NULL,
    generate BOOLEAN NOT NULL DEFAULT FALSE,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    error_code VARCHAR(100) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deadline_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    KEY tb_conversation_project_id_idx (project_id, id),
    KEY tb_conversation_project_status_idx (project_id, status),
    CONSTRAINT chk_conversation_status CHECK (status IN ('running', 'succeeded', 'failed', 'cancelled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='项目内公开对话、运行状态与依据版本；应用负责归属及关联清理';
