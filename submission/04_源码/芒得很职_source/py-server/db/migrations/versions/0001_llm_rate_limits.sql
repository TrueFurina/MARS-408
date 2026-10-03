-- 0001_llm_rate_limits.sql
-- 创建每用户 LLM 配额计数表（F-011 落库可选项）。
-- 本版本仅建表，运行器仍在应用内用 Redis 做实时滑动窗口限流；
-- 此表用于审计/离线统计，幂等（IF NOT EXISTS）。
-- 兼容 PostgreSQL 与 SQLite 回退。

CREATE TABLE IF NOT EXISTS llm_rate_limits (
    key          TEXT PRIMARY KEY,
    count        INTEGER NOT NULL DEFAULT 0,
    window_start BIGINT  NOT NULL DEFAULT 0,
    updated_at   BIGINT NOT NULL DEFAULT 0
);
