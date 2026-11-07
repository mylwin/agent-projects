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
