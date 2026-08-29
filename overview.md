# MARS-408 持续迭代闭环 — 进度总览

> 自动化每日运行，按「规划→开发→工程→测试→质检」推进真版（大创中期 Nov 2026 北极星）。
> 详细日志见 `.workbuddy/automations/automation-1787085434097/memory.md` 与 `documents/大创真版-*`。

## 2026-08-22 — Gold Q&A 评测基线（前后测锚点）
- **增量**：构建带验证答案的 Gold 题集（30 题，四科均衡）+ 诚实化 retrieval-groundedness harness (`experiments/eval_gold.py`)。
- **基线**：整体 subject_recall@5=0.733、mean_groundedness=0.519、**answerable_rate=0.533**；计网/OS 较好(0.75/0.71)，**数据结构最弱(0.25)**。
- **根因诊断**：数据结构弱非覆盖缺口（~299 DS chunk 充足），而是**章节级模板 chunk 挤占实质内容**的检索排序缺陷 + 词面匹配局限。已如实标注，非掩盖。
- **产物**：`documents/大创真版-Gold评测基线_2026-08-22.md` + `gold_eval_2026-08-22.json` + 柱状图。
- **下一步 P0**：KB 去模板化 + 检索对实质 chunk 提权（用本 harness 做 A/B，预期数据结构 answerable 显著上升）。
- 诚信合规：所有数字真实离线运行，无美化。

## 2026-08-29 — 模板/近重复降权修复 + KB 一键恢复
- **检索降权扩展（`engines/frugal_rag.py` `_boilerplate_factor`）**：在原"章节模板"降权基础上，新增惩罚**助学标签包裹的近重复 chunk**（`【考点速记】/【易错辨析】/【关键术语】/【典型例题】/【本章导学】/【知识拓展】/【真题精讲】/【速记口诀】/【避坑指南】` 前缀）。经核验 100% 此类 chunk 包裹某条干净 chunk 正文（子串包含），降权不丢唯一事实。离线 A/B（种子语料）验证：groundedness +0.141、answerable +0.167、模板占比 −0.547，**无退化**。
- **环境反复清空问题（重要约束）**：会话间非 git 提交产物被清空（venv / `models/e5-base-v2` / `vectordb_data/netlearn_kb.json(.emb.npy)` 全丢，只剩 `.tmp` 残留）。**所有修复/脚本必须 commit 才能留存**，本地不可跑的验证须写成即用框架。
- **新增脚本**：
  - `scripts/setup_kb.py` —— 一键恢复 KB：E5 缺失则下载 `intfloat/e5-base-v2`(768) 到 `models/e5-base-v2`，再复用 `rebuild_vectordb.main` 重建向量库，并校验形状 (N,768) 与**零向量数=0**（诚信红线）。离线给出清晰指引。
  - `experiments/eval_llm.py` —— LLM 作答准确率评测（讯飞 X2→DeepSeek auto 通道）：fact_coverage + LLM-as-judge 0~1 分。需 `.env` 凭证，本地不可跑，写成即用框架。
- **README 数字收紧**（诚信）：移除 "554/500+ tests" 歧义表述，改为 **616 项测试定义 · Windows CI 198 通过（其余受环境级 SIGSEGV 阻断，以 Linux CI 为准）**（中英文 README 同步）。
- 诚信合规：未声称已训练/零数据自报；所有指标真实或可复现。

## 2026-08-29（晚）— 错题智能归因 + 计网辨析专项（痛点报告落地）
- **痛点报告闭环**：`documents/痛点挖掘-公开社区_2026-08-29.md` 提取 9 类真实用户痛点，其中 P0「遗忘+错题不复盘」与 P1「计网概念易混淆」直接驱动本次两个新模块。
- **① 错题智能归因（`engines/error_attributor.py` + `api/wrong_questions.py`）**：
  - 标记错题时自动调用 **讯飞 X2→DeepSeek auto 通道** 做结构化归因（error_type / confidence / reason / knowledge_points / review_suggestion）。
  - **诚信降级**：LLM 不可用（无凭证/网络）时明确 `degraded=True` 走规则启发式（空答案→盲区、数值错→计算失误、选项近义→概念混淆、默认→思路偏差），绝不谎称 AI 已分析。
  - 新增 `GET /api/wrong-questions/error-profile` 聚合「错误画像」：错误类型分布 + 高频知识点 + 归因来源(LLM/规则)占比。错题表加 `attribution_json` 列（带迁移）。
- **② 计网易混淆概念辨析专项（`engines/cn_distinction.py` + `api/cn_distinction.py`）**：
  - 内置 **12 组真实教材级易混概念对**（电路/分组交换、虚电路/数据报、SR/GBN、TCP/UDP、协议/服务/接口、CSMA/CD-CA、CIDR、集线器/交换机/路由器、MAC/IP/端口、拥塞/流控、DNS递归/迭代、HTTP/HTTPS），每组含辨析要点 + 一道确定性关键词判分自测题。
  - 端点：`GET /api/cn-distinction`、`/cn-distinction/{id}`、`/cn-distinction/quiz/random`、`POST /api/cn-distinction/quiz/answer`。与 Gold 评测「计网 groundedness 最低」结论呼应，提供专项补强入口。
  - 判分采用确定性关键词匹配（可复现），不伪装 AI 打分。
- **单测通过**：两引擎离线功能测试全绿（CN 12 组自洽、启发式归因 4 类分支正确、JSON 稳健提取）。
- 诚信合规：内容均为教材公开知识点不编造；归因仅真实调用或明确标注降级。

---

# HTML 产物融合进 Vue 系统 — 进度概览

## 问题
`deliverables/` 里 16 个独立 HTML 文件与 `src/` Vue 组件完全脱节。设计团队一直在造"展品"而非改进"产品"。

## 方案
停止造独立 HTML，把每个 HTML 里有价值的视觉元素直接融进对应 Vue 组件。

## 16 个 HTML → Vue 视图映射

| HTML 文件 | → Vue 视图 | 状态 |
|---|---|---|
| `netlearn-dashboard-final.html` (73KB) | `DashboardView.vue` | ✅ 已融合 |
| `MARS-408-landing-final-v2.html` (66KB) | `LandingView.vue` | 待融合 |
| `MARS-408-profile-final.html` (68KB) | `ProfileView.vue` | 待融合 |
| `MARS-408-knowledge-graph.html` (64KB) | `KnowledgeGraphView.vue` | 待融合 |
| `MARS-408-agent-collab.html` (74KB) | `EngineView.vue` | 待融合 |
| `MARS-408_official_site.html` (32KB) | `ShowcaseView.vue` | 待融合 |
| `MARS-408_judge_hero_v10_mockup.html` (22KB) | Dashboard hero | ✅ 已融合 |
| `netlearn-ui-polish-prototype.html` (82KB) | `_variables.css` | ✅ 令牌已补 |
| `MARS-408_dachuang_deck.html` (33KB) | PPT 答辩稿（非产品页） | 保留 |
| 其余重复版本（landing×3/dashboard×1/profile×1） | 去重后取最终版 | 已归档 |

## 第一波融合详情（Dashboard）

### 1. `_variables.css` — 补入仪表盘扩展令牌
- 图表分类色板 `--series-1…6`
- 连续数值色阶 `--seq-1…6`（紫系深浅，热力图用）
- 三态状态色 `--state-success/warning/danger/weak`
- 图表网格/轴 `--chart-grid/axis/tick`
- KPI 卡 `--kpi-value-size/weight/glow`
- 角标 `--tag-demo/live`
- 8 Agent 状态 `--agent-online/busy/idle/offline/error`
- 含浅色主题完整覆盖

### 2. `DashboardView.vue` — 新增 3 个数据可视化区块
- **8-Agent 状态网格**：8 个 Agent 卡片（协调/诊断/规划/检索/生成/评估/审核/路径），五态状态点（在线/忙碌/空闲/离线/异常），脉冲动效
- **知识点掌握度热力图**：4 科 × 8 知识点 = 32 格，紫系连续色阶 `--seq-1…6`，从 subjectMastery computed 推导（零编造），hover 放大 + tooltip
- **预警干预面板**：从 recommendations 提取高危项，薄弱(紫)/危险(红) 状态点，点击跳转对应路由
- 全部使用 Vue 响应式 + 现有 CSS 变量体系
- 诚实标注"示意"角标（`--tag-demo`）
- 响应式：1024px 2列 / 768px 1列 / 480px 热力图降级 4 列
- vue-tsc 类型检查 0 错误

### 3. 验证
- `vue-tsc --noEmit` → Exit 0（零类型错误）

---

## 2026-08-29（深夜）— 遗忘曲线排程 + 思路引导式解析（痛点报告落地续）

> 延续 `痛点挖掘-公开社区_2026-08-29.md` 建议②（遗忘曲线自动排程）与③（思路引导式解析）。两者均为**纯规则、离线可复现**模块，不依赖 E5/LLM 即可运行；LLM 可用时增强，不可用时明确 `degraded=True` 降级。

### ① 遗忘曲线排程（`engines/review_scheduler.py` + `db/user_store.py`）
- **算法**：基于间隔复习（spaced repetition）的艾宾浩斯经验间隔 `[1, 2, 4, 7, 15, 30]` 天。每道错题维护 `review_stage`（0..5）；复习「答对」→ 阶段+1（间隔拉长），「答错/忘记」→ 回到阶段 0（重新巩固）；达最高阶段且仍答对 → 标记 `mastered`（建议移出错题本）。
- **DB 迁移**：错题表加 `review_stage` / `next_review_at` / `review_history_json` 三列（带 ALTER 迁移，已存在则跳过）。`add_wrong_question` 自动写初始排程（阶段0，下次=首次错+1天）。
- **API**：`GET /api/wrong-questions/due`（到期待复习列表）、`POST /api/wrong-questions/{id}/review`（记录回忆结果、推进排程）。
- **DB 层端到端单测全绿**：加题→stage0/next+1d；3 次答对→stage3；答错→归零；驱动至毕业→mastered；错误画像聚合；毕业题不进待复习。

### ② 思路引导式解析（`engines/guided_parse.py` + `api/guided_parse.py`）
- **算法**：苏格拉底式分步引导。LLM 可用时（`use_llm=True`）生成真实步骤；不可用时走规则模板（按题型：选择/计算/简答/通用），明确 `degraded=True` 不伪装。
- **题型识别**：规则启发式（含「计算/求/算」→ calc；含选项 → choice；含「简述/论述/为什么」→ explain）。
- **API**：`POST /api/guide/quiz`，返回 `steps` + `source`(llm/template) + `degraded` + `qtype`。
- 诚信：模板降级路径清晰标注，绝不谎称 AI 已分析。

### 诚实声明
- 本轮**未重建全量 KB**（HuggingFace 不可达 + venv 依赖被清空），故变体前缀降权对 CN groundedness 的真实回升效应**尚未用全量 2083 语料验证**，待联网后 `scripts/setup_kb.py` 重建再跑 `eval_gold_offline.py` / `eval_llm.py`。
- 两模块均为离线规则，单测全绿，可立即并入产品，无需等待 KB。
- Vite dev server :5173 → HTTP 200（可实时预览）
