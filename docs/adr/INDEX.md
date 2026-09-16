# ADR Index — MARS-408 / study-help-pro

> 维护者：架构师（architect）｜本索引为架构决策记录（ADR）的唯一入口。
> 原则：**事实**（如 9 节点图、evidence_check 节点）进 `docs/architecture/overview.md`，**决策**（选型/约束/策略）才进 ADR，避免 ADR 膨胀。

## 既有 ADR（001–007，位于 `documents/系统架构设计文档.md` §5）

> 以下为历史 ADR 的指针，原文未整体迁移。编号与 Accepted/Proposed 状态以 `documents/系统架构设计文档.md` §5 为准。

| ADR | 主题 | 位置 |
|-----|------|------|
| ADR-001 | （见 §5） | `documents/系统架构设计文档.md` §5 |
| ADR-002 | （见 §5） | `documents/系统架构设计文档.md` §5 |
| ADR-003 | （见 §5） | `documents/系统架构设计文档.md` §5 |
| ADR-004 | （见 §5） | `documents/系统架构设计文档.md` §5 |
| ADR-005 | （见 §5） | `documents/系统架构设计文档.md` §5 |
| ADR-006 | （见 §5） | `documents/系统架构设计文档.md` §5 |
| ADR-007 | 导入队列服务化（进程内单写者）—— Accepted | `docs/adr/ADR-007-import-queue-servitization.md`（archive/ 下另有历史副本，保留不动） |

## 新增 ADR（docs/adr/，由本索引管理）

| ADR | 主题 | 状态 | 文件 |
|-----|------|------|------|
| ADR-008 | 并发与水平扩展模型 | Accepted（单写者约束已落地；扩展机制见 ADR-012，待立） | `docs/adr/ADR-008-concurrency-scaling.md` |
| ADR-009 | LLM 通道策略（两通道：讯飞 X2 主 + DeepSeek 降） | Accepted | `docs/adr/ADR-009-llm-channel-strategy.md` |
| ADR-010 | 向量库选型与回退策略（Milvus 主 + InMemory dev 回退 + prod fail-fast） | Proposed | `docs/adr/ADR-010-vector-db-strategy.md` |
| ADR-011 | 三元评审权重 MAPPO 化（解析式默认 + RL 兜底） | Accepted | `docs/adr/ADR-011-review-weight-mappo.md` |
| ADR-015 | career-literacy 分支治理（双分支双身份 / 零侵入 / `career_*` 公约） | Accepted | `docs/adr/ADR-015-career-branch-governance.md` |
| ADR-017 | 评审单一真值源（`discipline_gate` / `review_precision` 收敛） | Accepted | `docs/adr/ADR-017-review-single-source.md` |
| ADR-018 | 代码审查机制（标准/流程/PR模板/红线grep守护） | Accepted | `docs/adr/ADR-018-code-review-mechanism.md` |

> 注：ADR-007（导入队列单写者）与 ADR-008（并发模型）记**已生效现实**——`--workers 1` + import_worker filelock 真阻塞 + `pytest -m import_queue` 13 passed/1 xfailed；两者于 2026-09-14 由 Proposed 提升为 Accepted。ADR-008 的"水平扩展机制"部分仍待 ADR-012。
> ADR-009 记录**现有已实现**两通道（Accepted）；ADR-010 的 prod fail-fast 尚未在代码中实现（`config.py:91`、`milvus_client.py:403` 仍为静默回退），属**待实现目标**（Proposed，纠正架构债 #8）。
> ADR-011 记录三元评审权重 MAPPO 化的**三位一体**结论：解析式最优（生产默认）+ RL 兜底 + career 线真实 RL 增益；诚实边界=仅证 effective 口径下最优。ADR-015 记录双分支双身份零侵入公约。ADR-017 记录判定语义的单一真值源（49 例守护）。
> 状态约定：Proposed（提议，待评审）/ Accepted（已采纳）/ Superseded（被替代，须标注替代者）。
