CREATE TABLE IF NOT EXISTS chat_threads (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL DEFAULT '新会话',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_threads_user_updated
    ON chat_threads(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS parent_chunks (
    id UUID PRIMARY KEY,
    product_id BIGINT NOT NULL,
    clause_name VARCHAR(300) NOT NULL,
    section_path TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parent_chunks_product
    ON parent_chunks(product_id);

COMMENT ON TABLE chat_threads IS '用户与智能客服的会话元数据，消息正文由 LangGraph Checkpointer 保存';
COMMENT ON COLUMN chat_threads.id IS '会话主键，同时作为 LangGraph thread_id';
COMMENT ON COLUMN chat_threads.user_id IS 'JWT 中解析出的业务用户主键';
COMMENT ON COLUMN chat_threads.title IS '会话列表展示标题';
COMMENT ON COLUMN chat_threads.created_at IS '会话创建时间';
COMMENT ON COLUMN chat_threads.updated_at IS '最后一次对话或修改标题的时间';

COMMENT ON TABLE parent_chunks IS '用于完整上下文和引用展示的父知识块';
COMMENT ON COLUMN parent_chunks.id IS '父块主键';
COMMENT ON COLUMN parent_chunks.product_id IS '关联的保险产品主键';
COMMENT ON COLUMN parent_chunks.clause_name IS '条款文件名，包含 .pdf 后缀';
COMMENT ON COLUMN parent_chunks.section_path IS 'Markdown 标题层级路径';
COMMENT ON COLUMN parent_chunks.content IS '父块完整正文';
COMMENT ON COLUMN parent_chunks.created_at IS '创建时间';
