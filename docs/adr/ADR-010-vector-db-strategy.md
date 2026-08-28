# ADR-010 — 向量库选型与回退策略

- **状态**：Proposed（待架构师评审确认）
- **日期**：2026-07-15
- **决策人**：架构师（architect）
- **相关**：纠正文档债 #8「静默回退陷阱」；`db/milvus_client.py` 抽象层；`config.json` `milvus.enabled`

## 背景

向量库是检索增强（FrugalRAG）的核心依赖。系统支持 Milvus（生产）与 InMemoryVectorStore（开发），但旧文档与部分运行路径存在 **静默回退** 行为：Milvus 不可达时无声降级 InMemory，生产环境可能在不自知的情况下丢失规模能力与证据校验的跨群检索完整性保障。

## 决策

1. **生产（Milvus 优先）**：`milvus.enabled=true` 时，Milvus 不可达 → **fail-fast 启动失败**（不静默回退），由部署方保证 Milvus 可达（docker `--profile milvus`）。
2. **开发（InMemory 回退）**：`milvus.enabled=false` 或显式 dev 模式时，使用 `InMemoryVectorStore`；9 节点流水线（含 `evidence_check`）仍可完整运行，仅检索规模受限。
3. **抽象层**：所有向量操作经 `db/milvus_client.vector_db` 统一接口，调用方不感知后端。
4. **写单写者**：所有写入经 `services/import_worker.store_lock` 串行化（见 ADR-007），`uvicorn --workers 1`。

## 影响

- **部署**：生产必须显式拉起 Milvus（`docker compose --profile milvus up -d`），否则应用 fail-fast。README「Docker 部署」的 `production` profile 当前仅含 Redis，需与 Milvus profile 组合使用——已记入文档债 #11，待部署文档修正。
- **可观测性**：启动日志须明确打印当前向量库后端（Milvus / InMemory），避免静默。
- **数据**：Milvus 首次启动 `_seed_vector_db` 按 `kg_dag.chapter_to_group` 注入 `metadata.group`（1–26）供证据校验。

## 理由

- 静默回退会让生产在「看似正常」下丢失 Milvus 的规模与一致性保障，属隐性故障源。
- 显式 fail-fast 把「向量库可用性」上升为一等部署约束，符合生产就绪要求（`PRODUCTION_READINESS_2026-07-12.md`）。
- dev 回退保留，保证本地零依赖可跑通主链路，不牺牲开发体验。

## 备选方案（被否决）

- **始终静默回退 Milvus→InMemory**：掩盖生产配置缺陷，否决。
- **移除 InMemory 回退，强制 Milvus**：损害本地开发与 CI 轻量性，否决（dev 回退保留）。
