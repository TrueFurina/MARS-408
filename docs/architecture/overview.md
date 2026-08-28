# MARS-408 架构总览（权威）

> 文档类型：架构总览（Architecture Overview）｜维护者：架构师（architect）
> canonical 口径：多智能体流水线 **9 节点**；向量库 **Milvus 主 + InMemory dev 回退**；LLM **两通道**（讯飞 X2 主 + DeepSeek 降）。
> 本文件为「事实类」单一真相源，架构决策（ADR）见 `docs/adr/INDEX.md`，不在此重复。

---

## 1. 9 节点 LangGraph 图

`agents/graph.py` `create_agent_graph()` 构建 `StateGraph`，全局实例 `agent_graph`（`graph.py:135`）。

```mermaid
flowchart TD
    CO[coordinator · 全局协调]
    DI[diagnostician · 学情诊断]
    PL[planner · 任务规划]
    RE[retriever · 检索优化]
    GC[generator_cluster · 资源生成集群(7并行子Agent)]
    AS[assessor · 评估反馈]
    CR[critic · 质量校验·GOMARL共识]
    EC[evidence_check · 证据校验]
    PP[path_planner · 路径规划]
    CO --> DI --> PL --> RE
    RE -->|有结果| GC
    RE -.->|空·重试≤2| PL
    GC --> AS --> CR
    CR -->|通过| EC
    CR -.->|需改进·重试≤2| RE
    CR -->|重试耗尽·降级| PP
    EC --> PP
    PP --> E([END])
```

- **边来源**：`graph.py:102-128`；条件路由 `route_after_retriever`（`graph.py:42`）、`route_after_critic`（`graph.py:60`）。
- **节点清单（9）**：`coordinator` `diagnostician` `planner` `retriever` `generator_cluster` `assessor` `critic` `evidence_check` `path_planner`（`graph.py:88-96`）。
- **`evidence_check`（第 9 节点，INC-01 质量闸门）**：在 `critic` 通过之后、`path_planner` 之前插入（`graph.py:95,125`），对检索证据做跨群（chapter group 1–26）冲突检测。历史上「8 节点 = 7 角色 + 1 PathPlanner」，evidence_check 为后续插入，故旧文档「8 节点」口径已废弃。
- **`generator_cluster` 内含 7 个并行资源 Agent**：Teacher / QuizMaster / MindMap / Extension / CodePractice / PPT / VideoScript（Lite）。
- **独立 Agent（不在图中，API 层按需调用）**：`Tutor`（智能答疑）。

---

## 2. 主链路数据流

```
Vue 3 SPA (src/)
  → Vite 代理 (/api → :8002)
    → FastAPI /api (main.py:190-210, 25 routers / ~121 endpoints)
      → agents.agent_graph (全局 agent_graph, graph.py:135)
        → engines.frugal_rag  (FrugalRAG 检索: E5 + BM25 + 个性化重排)
        → engines.gomarl      (GOMARL 共识: NeuralMixer 神经网络加权融合)
          → db.milvus_client.vector_db   (Milvus 生产 / InMemory 开发回退)
          → db.llm_provider             (讯飞 X2 主 + DeepSeek 降)
          → db.xfyun_services           (讯飞 10 能力)
          → 可选 pg / redis
```

- **入口**：`main.py` 启动 lifespan 连接数据层 + `_seed_vector_db`（`main.py:50`，幂等）。
- **统一错误**：`shared/errors.py` 的 `DomainError` → 全局 handler 返回 4xx/5xx（不再吞错返回 200）。
- **认证**：`shared/auth.py` JWT HMAC-SHA256；审计 `shared/audit.py`。

---

## 3. 集成点 / 外部依赖

| 类别 | 组件 | 说明 / 鉴权 |
|------|------|------------|
| LLM | 讯飞星火 X2（主） | `db/xfyun_services.py`：10 能力；HMAC / APIPassword / MD5+SHA1 多鉴权 |
| LLM | DeepSeek（降） | OpenAI 兼容接口回退 |
| 向量库 | Milvus（生产） | `db/milvus_client.py`；不可达时自动回退 `InMemoryVectorStore` |
| 向量库 | InMemoryVectorStore（开发） | 检索规模受限，不影响证据校验功能 |
| 数据 | PostgreSQL / Redis | 可选；PG 缺失回退 SQLite，Redis 缺失降级本地缓存 |
| 嵌入 | E5-base-v2 (768 维) | 本地模型，离线加载（`HF_HUB_OFFLINE=1`） |

**写路径单写者约束（ADR-007）**：所有向量库写入经 `services/import_worker.store_lock` 串行化，避免多写者冲突；`uvicorn` 必须 `--workers 1`。详见 `docs/adr/INDEX.md`。

**DI 现状（架构债，待后续）**：`shared/container.py:19-23` 仅管理数据层；`engines` / `agents` / `services` 仍用模块级单例，与 DI 容器并存。

---

## 4. 双线（Lite / 大创真版）说明

- **Lite 版（v1，软件杯演示就绪）**：功能规格见 `docs/MARS-408_PRD_Lite_2026-07.md`；本总览描述的 9 节点图与两通道 LLM 即 Lite 交付基线。
- **大创真版（v2）**：范围/路线图见 `deliverables/product-strategy/*`；v2 工程化文档（扩展节点/能力）待立项后补充，不在此文件展开。

> 相关决策（向量库回退、LLM 通道）以 `docs/adr/` 中的 ADR-009 / ADR-010 为权威，本文件只陈述事实。
