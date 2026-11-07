-- 停止旧应用后在目标数据库执行；历史记录不改写，旧 running 记录由新应用回收。
SET @deadline_exists = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'tb_generation_run'
      AND column_name = 'deadline_at'
);
SET @ddl = IF(
    @deadline_exists = 0,
    'ALTER TABLE tb_generation_run ADD COLUMN deadline_at DATETIME(6) NULL COMMENT ''最晚提交时间；旧运行可为空，按已中断处理'' AFTER started_at',
    'SELECT 1'
);
PREPARE deadline_migration FROM @ddl;
EXECUTE deadline_migration;
DEALLOCATE PREPARE deadline_migration;
