# ADR-019 — Jev 技术选型（不接入主线 / 口径纠正 / 旁路试点边界）

- **状态**：Accepted（决策已由用户批准）
- **日期**：2026-09-23
- **决策人**：架构师（architect）
- **相关**：`deliverables/engineering-assurance/Jev-tech-selection-2026-09-23.md`（唯一事实源）；`deliverables/engineering-assurance/metrics-integrity-audit-2026-08-29.md`；`documents/大创真版证据链_2026-08-20.md`；ADR-011（三元评审权重）；ADR-017（评审单一真值源）
- **关联代码**：`py-server/engines/frugal_rag.py`（检索组件，本 ADR 未改动）；`py-server/engines/review_policy.py`（解析式判定，本 ADR 未改动）；旁路试点脚手架 `py-server/experiments/pilot_jev_judgment.py`（663 行）已于同日创建并经 QA 验证，属**旁路实验件**（不接入运行链路、不进交付链路）。**本 ADR 决策本身不含对业务主线的代码改动。**

## 背景

study-help-pro（分支 `career-literacy`，对外产品名「芒得很职」，技术底座代号 MARS-408）后端为 FastAPI + LangGraph 的 **11 节点**管线。有人提出：新出的 Jev（TypeSafe AI 的 System One 决策模型）很快又省 token，是否可替代或补充当初为「省」而选的检索组件 FrugalRAG。评估确认这是**类别错误**——Jev 不做检索、不生成任何文本，三原语仅输出类型化判断（Choice / Score / Noul），且**仅托管 API**；用 Jev 替换 FrugalRAG 等于取消检索层。

评估同时暴露一个更根本的叙事错误：**FrugalRAG 从未降本**。现行口径 token/查询 185.75 对全量检索 165.86，实为 **−11.99%（未降反增）**；延迟 574.36 ms 对 2.70 ms，约 **213×**。其真实收益在检索质量：Recall@5 **+7.14 pp**、Precision@5 **+15.71 pp**、MRR **+12.38 pp**。旧口径 token −0.14%（`benchmark_2026-08-17.json`）与现行不一致；`metrics-integrity-audit-2026-08-29.md` 已把申报书「检索成本降低 45%」列为 🔴 禁止使用。Jev 侧：$0.042/百万输入 token、输出免费、70–500 ms、官方自评 4-workflow ≈ 67.8%、独立 108-claim 测试 96.3%、ECE 0.07；试点一轮 30 题×3 = 90 次判断 ≈ 9 万 token ≈ **$0.0038**，成本不构成决策理由。

## 决策

1. **Jev 不接入业务主线。** 11 节点管线不引入 Jev。Jev 不是 RAG、不生成文本，既不能替代 FrugalRAG，也不能替代任何生成型节点（`generator_cluster` / `diagnostician` / `planner`）。
2. **叙事纠正（口径纪律）。** FrugalRAG 定位为**质量组件，不是成本组件**；对外材料**禁止**宣称「降本 / 提速」，依据 `metrics-integrity-audit-2026-08-29.md`（已列「检索成本降低 45%」为 🔴 禁止使用）与 `documents/大创真版证据链_2026-08-20.md`（明文「不应宣称降本/提速」）。
3. **已有更优解的环节不引入 Jev。** `quality_gate` 的权重决策已由解析式 `analytic_review_action` 承担（capture 100%、零训练零成本），`discipline_gate` 由确定性规则承担——这两处引入 Jev 为**负收益**，明确排除。
4. **「离线可复现」为硬约束。** Jev 仅托管 API、不可自托管、模型可能静默更新，与项目「口径先行 / 证据先行」纪律冲突。因此 **Jev 只允许停留在实验目录，永不进入交付链路，其输出永不参与任何对外数字。**
5. **P1 旁路试点的边界与前置。** 仅覆盖 4 个判断型节点：`triage` → Choice、`critic` → Noul、`evidence_check` → Noul、`assessor` → Score。前置条件：① TypeSafe API key；② 用户授权；③ 必须旁路（不修改 `py-server/` 任何源码、不接入运行链路、输出落盘独立 artifacts 目录）；题集来源为 `py-server/experiments/queries.json`（**28 条**，对应 benchmark 实验1 的 28 查询）；benchmark 实验2 的 30 题×3 属于**另一套题集**，两者不可混用；试点须显式声明所用题集与来源，**禁止以有放回重复采样冒充口径对齐**；seed 沿用 `20260719`。**当前状态：前置条件 ①② 未齐（本机未发现 API key），试点未执行。**

## 影响

- **变容易**：主线选型边界清晰——检索归检索、判断归判断、生成归生成，避免「拿判断模型优化生成成本」的类别错误复发；对外口径有了可审计的禁语依据。
- **变困难 / 需注意**：任何涉及 Jev 的实验必须留痕（调用时间戳、模型版本标识、原始响应落盘）作为**仅追加**工件；离线路线仍由本地链承担，不得因试点引入外部可用性依赖。
- **诚实边界**：Jev 的准确率 / 延迟 / ECE 均来自 TypeSafe 公开发布信息，**未在本项目独立复现**；P1 试点尚未执行。

## 备选方案（被否决）

- **用 Jev 替换 FrugalRAG**：类别错误——Jev 不检索、无索引无召回，替换等于取消检索层，并丢失 Recall@5 +7.14 pp 等质量收益，否决。
- **用 Jev 接管 `quality_gate` / `discipline_gate`**：两处已有更优解（解析式 capture 100% 零成本 / 确定性规则可审计），换用概率模型反增不确定性与不可解释性，为负收益，否决。
- **把 Jev 作为在线兜底通道接入主线**：托管 API 不可自托管、模型可能静默更新，破坏「离线可复现」硬约束与历史可复现性，否决。
- **先把 Jev 接进主线再观察**：违反「口径先行 / 证据先行」纪律——在无旁路对照证据前即改动交付链路，属以未验证组件污染生产，否决。
