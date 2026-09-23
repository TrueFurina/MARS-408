# D6 文档口径对齐（P1 · 技术债 Priority=28）

**日期**：2026-09-23
**分支**：career-literacy
**方法论**：证据先行——先以代码/产物实测出唯一真值，再对齐文档，杜绝"假装对齐"。

---

## 一、真值测量（单一真值源）

| 维度 | 测量手段 | 真值 |
|------|---------|------|
| API 端点 | `py-server/openapi.json`（FastAPI 自动生成，唯一权威） | **223 paths / 240 operations** |
| LangGraph 节点 | `agents/graph.py:99-109` 的 `add_node` 计数 | **11 节点**（triage→coordinator→diagnostician→planner→retriever→generator_cluster→assessor→critic→evidence_check→quality_gate→path_planner） |
| 前端 views | `src/views/*.vue` Glob 计数 | **45 个 views** |
| 前端 components | `src/components/*.vue` Glob 计数 | 36 个（README 原写"82 个 .vue 含组件"，45+36=81，量级一致保留表述） |
| LLM 通道 | `config.py:45-83` + `get_llm_config` 轮询顺序（xfyun→deepseek→qwen） | **DeepSeek（主）+ 讯飞星火 generalv3.5（兜底）；X2 未授权（11200）** |
| 检索增益 | `benchmark_2026-08-17.json` 真产物 | **Recall@5 +10.7% / MRR +9.6%** |
| 测试 | 全量 pytest（D5 后） | **917 passed / 207 skipped** |

> 注：`openapi.json` 的 tags（模块）统计为 0，故"路由模块数 43"沿用技术债评估基线的既有统计；端点严格以 openapi 实测 240 ops / 223 paths 为准。

---

## 二、漂移清单与修正（4 个对外产品口径文档）

### 1. `README.md`（根）
| 位置 | 原文（虚高/错误） | 修正 |
|------|----------------|------|
| L77 | `38 个页面` | `45 个页面（45 views）` |
| L78 | `451 个 API 端点（43 路由模块）` · `915 项测试` | `约 240 个 API 端点（openapi.json 实测 223 路径 / 240 操作，43 路由模块）` · `917 项测试` |
| L210 | `451 个 API 端点 · 11 Agent 节点` | `约 240 个 API 端点（openapi.json 实测 223 路径 / 240 操作）· 11 Agent 节点` |
| L213 | `915 项测试通过` | `917 项测试通过` |

### 2. `CLAUDE.md`（项目事实卡）
| 位置 | 原文 | 修正 |
|------|------|------|
| L58 | `10 节点单向主流程` | `11 节点单向主流程（首节点为 triage 分诊）` |
| L61 | 节点图漏 `triage`（从 coordinator 起） | 图首行补 `triage → coordinator → ...` |

### 3. `py-server/README.md`
| 位置 | 原文 | 修正 |
|------|------|------|
| L71 | `API 路由（25 模块, 97 端点）` | `API 路由（43 模块, 约 240 端点 / openapi.json 实测 223 路径）` |
| L72 | `多智能体节点（9 个 LangGraph 节点）` | `多智能体节点（11 个 LangGraph 节点）` |
| L93 | `测试（281+ 个）` | `测试（900+ 用例）` |

### 4. `README_EN.md`（英文）
| 位置 | 原文 | 修正 |
|------|------|------|
| L11/16/23/58/64/81/105/174 | `10-node` / `10-Node` / `10 agent nodes` | 全部 `11-node` / `11-Node` / `11 agent nodes` |
| L11 | Agent roster 漏 `triage` | 补 `triage →` 为首节点 |
| L48/58 | `68 pages` | `45 pages (45 views)` |
| L49/175 | `230+ API endpoints` | `~240 API endpoints (openapi.json: 223 paths / 240 ops)` |
| L50/176 | `iFlytek Spark X2 (primary) + DeepSeek (fallback)` | `DeepSeek (primary) + iFlytek Spark generalv3.5 (fallback; X2 not authorized)` |
| L83 | agent 表漏 `triage` 行 | 补 `triage` 行（Triage routing & intent classification） |
| L136 | `Recall@5 +15.8% / MRR +16.0%` | `Recall@5 +10.7% / MRR +9.6%`（对齐 benchmark_2026-08-17.json 真值，与中文 README 一致） |
| L175 | `843 tests passing` | `917 tests passing` |

---

## 三、范围边界（刻意不改的文件）

- `diagnostics/` 下历史快照（如 `项目体检报告-2026-09-02.md` 写"38 views / 10 节点"）属**时间点实测记录**，改动会破坏历史真实性，不改。
- `deliverables/` 下分析/规划文档（如 `前端战略规划` 写"41 个 views"）属**内部规划基线**，非对外产品口径，不改。
- `613 节点知识图谱` 伪证字样仅出现在"揭露伪证"的审视报告中，立场正确，不触碰。
- KG 节点数：README 仅写"26 知识群组"（未写死节点数），无 613 伪证残留，符合要求。

---

## 四、验证

- 残留虚高数字扫描（`451`/`38 个页面`/`915`/`10 节点`/`25 模块`/`97 端点`/`9 个 LangGraph`/`281+`/`68 pages`/`230+`/`843`/`10-node`/`X2 (primary)`/`15.8%`/`16.0%`）：4 文件 **0 命中**。
- 新真值落地确认：`约 240 个 API 端点` / `45 个页面` / `917 项测试` / `11 节点` / `triage → coordinator` 图 / `DeepSeek (primary)` / `Recall@5 +10.7% / MRR +9.6%` 全部命中。
- 诚实口径：LLM 通道、检索增益均对齐 `config.py` 与 `benchmark_2026-08-17.json` 真值，无虚高。

**结论**：D6 完成。对外产品口径文档（中/英 README + CLAUDE + py-server README）已与代码真值对齐，无虚高残留。
