# D5 — `/api/status` 能力静默降级显式化（Observability 短板修复）

- **日期**：2026-09-23
- **类型**：P1（与 D4 同源的「绿光可骗人」可观测性短板）
- **优先级**：P1 第一项，P0 五项（D1/D15/D18/D4/D3）已收口后进入

## 1. 问题（证据先行）

`py-server/main.py` 原 `/api/status` 端点**硬编码 `status: "ok"`**，即使以下静默降级真实发生，也照报绿：

| 静默降级 | 原行为 | 真相 |
|---|---|---|
| Milvus 未连上 → 回落内存存储 | `status: "ok"` | 重启即丢数据 |
| PostgreSQL 已配置却未连上 / 回落 SQLite 兜底 | `pg_enabled` 仅读 cfg 布尔 | 数据层实际降级 |
| Redis 已配置却未连上 | `redis_enabled` 仅读 cfg 布尔 | 缓存/部分限流降级 |
| E5 嵌入失败 → 零向量占位（fallback_zero） | 无任何信号 | 检索质量静默下降 |
| LLM 无可用凭证 | `llm_available` 外露但 status 仍 ok | 资源生成不可用 |

结论：原端点是「存活探针」而非「健康探针」，绿光可骗人。

## 2. 改造方案（intent-based，不破坏健康部署契约）

核心原则：**仅当某能力「已配置启用」却未达成时，才计为降级**；未配置的组件（如开发环境不启用 Milvus）视为「不要求」，不计入降级。这样：

- 健康生产部署（Milvus/PG/Redis 均配置且连通、LLM 有凭证）→ 仍返回 `status: "ok"`，**不破坏既有 `status=ok` 契约**（DEMO_RUNBOOK / auto_qa.sh / 验收标准依赖此契约）。
- 任何「意图启用却回落/失败」→ `status: "degraded"` 并给出可读原因。

### 2.1 `db/milvus_client.py`（VectorDB）
- `__init__` 新增 `self._embedding_fallback_count = 0`。
- 新增只读属性 `embedding_fallback_count`（暴露 E5 失败零向量占位的累计文档数）。
- 在 `insert` 两处 `meta["embedding_status"] = "fallback_zero"` 赋值点各 `self._embedding_fallback_count += 1`。

### 2.2 `py-server/main.py` `/api/status`
计算真实组件健康，返回结构：

```jsonc
{
  "status": "ok" | "degraded",
  "degraded_reasons": ["...人类可读降级原因..."],   // 空列表=全绿
  "health": {
    "vector_db":   { "mode", "milvus_configured", "milvus_connected", "collection_size" },
    "postgresql":  { "configured", "enabled", "fallback_sqlite" },
    "redis":       { "configured", "enabled" },
    "embedding":   { "model", "loaded", "fallback_zero_docs" },
    "llm":         { "provider", "available" }
  }
}
```

降级判定（仅 intent 未达成才降级）：
- `milvus.enabled && !_milvus_connected` → vector_db 降级
- `postgresql.enabled && !is_enabled` → pg 降级；`&& is_fallback` → pg 回落 SQLite 降级
- `redis.enabled && !is_enabled` → redis 降级
- `embedding_fallback_count > 0` → embedding 降级（E5 静默失败）
- `!llm_available` → llm 降级（核心能力无凭证）

### 2.3 `scripts/auto_qa.sh`
原 `sed` 提取 `"status":"..."`（无空格）与顶层 `llm_available` 已失效（新响应带空格且 LLM 移入 `health.llm.available`）。修正：
- sed 容忍可选空格；
- `status=ok` → ✅；`status=degraded` → ⚠️（存活但降级，仍计存活）；其余 → ❌。

## 3. 验证（实证）

- `py_compile main.py` / `db/milvus_client.py` → OK。
- 新增回归测试 `tests/test_status_health_d5.py`（**2 passed**）：
  - `test_status_shape_and_keys`：默认形态含 `status`/`degraded_reasons`/`health`，health 覆盖五组件。
  - `test_status_reports_pg_fallback_as_degraded`：强制「PG 已配置却回落 SQLite」→ `status=degraded` 且 `degraded_reasons` 含 postgresql 原因、`health.postgresql.fallback_sqlite=true`。
- 全量默认套件（addopts 含 D3 覆盖率门禁 `fail_under=54` + 单 `--cov=.`）通过，无回归、门禁达标。

## 4. 红线/口径

- 行为零改动：未删除任何字段的语义价值（`llm_available`/`pg_enabled`/`redis_enabled` 由 `health.*` 显式承接），仅从「硬编码 ok」升级为「真实健康」。
- 未触发 E5 模型加载（`embedder._e5_model is None` 仅作被动信号，不调用 `embedder.is_available()`，避免 420MB 模型在每次状态探测时加载）。
- HTTP 状态保持 200（存活探针语义不变）。

## 5. 后续

- P1 续项：D6 文档口径对齐、D2 共享 SQLite 统一连接与锁、D14 uv.lock 冻结、D16 产品名对齐、D9 消灭永久/陈旧 skip·xfail、D11 ruff 清未用导入。
- 可选增强：运维面板/盯盘表消费 `health.embedding.fallback_zero_docs` 与 `health.postgresql.fallback_sqlite` 作为告警指标。
