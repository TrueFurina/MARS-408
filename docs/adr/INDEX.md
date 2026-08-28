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
| ADR-007 | 导入队列服务化（进程内单写者） | `deliverables/engineering-assurance/ADR-007-import-queue-servitization.md` |

## 新增 ADR（docs/adr/，由本索引管理）

| ADR | 主题 | 状态 | 文件 |
|-----|------|------|------|
| ADR-008 | 并发与水平扩展模型 | Proposed | `docs/adr/ADR-008-concurrency-scaling.md` |
| ADR-009 | LLM 通道策略（两通道：讯飞 X2 主 + DeepSeek 降） | Accepted | `docs/adr/ADR-009-llm-channel-strategy.md` |
| ADR-010 | 向量库选型与回退策略（Milvus 主 + InMemory dev 回退 + prod fail-fast） | Proposed | `docs/adr/ADR-010-vector-db-strategy.md` |

> 注：ADR-008 并发与水平扩展模型（Proposed，定"为什么单 worker + 扩展原则"，机制细节见 ADR-012）；ADR-009 记录**现有已实现**两通道（Accepted）；ADR-010 的 prod fail-fast 尚未在代码中实现（`config.py:91`、`milvus_client.py:403` 仍为静默回退），属**待实现目标**（Proposed，纠正架构债 #8）。
> 状态约定：Proposed（提议，待评审）/ Accepted（已采纳）/ Superseded（被替代，须标注替代者）。
