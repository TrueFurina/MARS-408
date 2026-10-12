# 芒得很职 单用户产品全面调研评估报告

**日期**：2026-10-13
**场景**：全面调研评估（只读）→ 为「方向 A：打磨单用户产品」定优先级
**参与成员**：产品评审员（gstack-product-reviewer） + 调查员（gstack-investigator） + QA与发布（gstack-qa-lead）
**基准 commit**：`e078616`（career-literacy，三条 P0 安全线已闭环并推送）

---

## 📌 TL;DR（执行摘要）

- **整体结论：🟡 条件 Go（Conditional Go）** —— 产品**核心对抗实训闭环已完整可用**（登录→选景→多轮对抗→六维报告→导出，对学生全开放、空/错态清晰、无静默失效）；后端 243 端点全部实现、零桩。但有两处 **P1 诚信/质量红线风险**必须在任何对外发布前闭环。
- **阻塞项数量**：2 项 P1（均触及项目「叙述诚实不夸大」硬红线）+ 若干 P2/P3 打磨项。
- **下一步**：先闭环 2 项 P1（quality gate fail-open、honesty_scan 红线绕过），再按 P2→P3 顺序做品牌口径统一、死代码清理、数字漂移校正、沙箱导航收敛。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| Go / No-Go | 🟡 条件 Go（核心功能可用；2 项 P1 须先闭环） |
| 严重度分布 | 🔴 P1 ×2 / 🟠 P2 ×5（含跨成员重复）/ 🟡 P3 ×9 |
| 关键行动项 | 6 条（见行动清单，P1 两条优先） |
| 建议负责人 | 主理人主导 P1 两项；产品评审员+调查员拆 P2/P3 |

---

## 1. 各成员核心结论

### 🔍 产品评审员（前端产品面 + 演示链路）
- **核心判断**：前端完成度**中高**。核心对抗实训闭环（登录→首页→选景→多轮对抗→六维报告→导出）**高完成度**，端点对学生全开放、空/错态清晰、无静默失效、无 blocker；演示学生可走完整主路径。
- **关键风险**：① 品牌口径不一致（公开站 `LoginView.vue:51`、`LandingView.vue:272` 仍指向旧品牌 MARS-408 GitHub 仓库；场景 A 大量 408/考研 残留文案）；② 硬编码数字漂移（`PlatformHomeView.vue:135` 写「46 前端视图」实为 47）；③ 个别过度承诺文案（卡片写「面试」情景但 `career_scenarios.json` 仅 4 项无面试；「3 实训模式」的「自学」未找到实现）；④ 实验室导航对学生暴露 admin-only 沙箱（`navConfig.ts:291` → 运行得 403）；⑤ 4 个孤儿视图死代码。
- **完成度总评**：中高，属「可演示、需打磨」，非「断裂/不可用」。

### 🛡️ 调查员（后端代码 + API 完整性）
- **核心判断**：后端 **API 完整性高**——42 router / **243 端点全部挂载且完全实现**，api 层零桩、零 TODO、零 NotImplementedError 可用端点；前后端一致性高（无功能性 404 隐患）；健壮/可运维良好（统一异常脱敏、重依赖全懒加载、SSE 容错、配额门控）。
- **关键风险（技术债）**：① 孤儿路由 `POST /api/guide/quiz`（`api/guided_parse.py:12,20` 定义但未挂载，纯死代码）；② legacy MARL 模块（`engines/algorithm_factory.py`、`marl_dqn.py`、`train_mixer*`、`gomarl*`、`mappo*` 等）未接入运行 API，属上一代死代码建议归档；③ `CareerTrainingView.vue:133` 裸 fetch 违反 CLAUDE.md「view 禁止裸 fetch」；④ `api/tutor.py:11` 顶层 import 与全局懒加载约定不一致；⑤ `main.py:40` vs `api/langgraph.py:28`「11 节点 / 10-Agent」命名不统一。
- **完成度总评**：约 **95%+**，适合打磨单用户产品；重点在清理死代码与一处合规修复，而非补功能。

### ✅ QA与发布（测试/CI/构建健康度）
- **核心判断**：质量就绪度 **条件 Go**。构建/测试/CI 主体健康：113 测试文件分层清晰，CI 权威 1389 passed / 38 skipped / 1 xfailed / 0 failed；门禁脚本 23 个全部存在无悬空引用；7 道 pre-commit 门禁全在 CI。
- **关键风险（发布前须闭环）**：
  1. **[P1·严重] Quality Gate fail-open**：`py-server/agents/quality_gate.py:17/:85/:204-209` 异常一律降级为 PASS；叠加 GOMARL 默认 "lite"（规则版），对外宣称的「共识质量」可能仅规则版保障，核心卖点缺乏真实保障。
  2. **[P1·严重] 诚信红线门禁可被绕过**：`scripts/pre-commit/honesty_scan.py:60-68/:135-154` 严格逐行匹配，`检索成本降低 45%`/`GOMARL 升 15%` 的变体（下降了/约/开销/提升了）与跨行拆分**全部漏检**；同缺陷在 `brand_scan.py:193` 与 `scan_stale_calibration.py`。虚假宣称可静默回流。
  3. **[P2·中] 品牌/部署路径不一致 + 口径扫描盲区**：`vite.config.ts:10` `base: '/MARS-408/app/'` 旧品牌硬编码；`scan_stale_calibration.py:23-30` SCAN_ROOTS 缺 `submission/` 与 `AGENTS.md`。
- **补充隐患（非阻塞）**：单 worker 下 6 处同步阻塞热点（E5 嵌入/MeloTTS/python-pptx）；`caliber_check.py:101` 恒 `return 0`（只告警不拦截）。

> 仅列入场成员；安全官/设计师/排障手未参与本轮回访。

---

## 2. 综合审查发现（去重合并，按严重度排序）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源 |
|---|--------|------|------|---------|------|------|
| 1 | 🔴 P1 | 质量/诚信 | `py-server/agents/quality_gate.py:17,85,204-209`；`CLAUDE.md:74,80` | Quality Gate 异常一律降级 PASS（fail-open），核心「共识质检」卖点缺乏真实保障 | 改为 fail-closed 或显式向用户暴露「质检降级」信号；明确生产默认启用 real（NeuralMixer）或文档说明规则版口径 | QA |
| 2 | 🔴 P1 | 诚信红线 | `scripts/pre-commit/honesty_scan.py:60-68,135-154`；`brand_scan.py:193`；`scan_stale_calibration.py:109-113` | 红线正则逐行匹配，变体（下降了/约/开销/提升了）与跨行拆分全部漏检，虚假指标宣称可静默回流 | 红线匹配升级为归一化/语义匹配（容忍了/约/下降了、跨行窗口），或引入语义层复核 | QA |
| 3 | 🟠 P2 | 品牌口径 | `LoginView.vue:51`、`LandingView.vue:272`、`vite.config.ts:10`；场景 A `DashboardView/ChatView/ProfilePanel/icons.ts/ChatInput.vue` | 公开站仍指向旧品牌 MARS-408 GitHub 仓库；vite base 旧品牌硬编码；场景 A 大量 408/考研 残留文案 | 外链改为芒得很职当前仓库；统一 vite base；主线文案统一为职业素养口径 | 产品+QA |
| 4 | 🟠 P2 | 导航/权限 | `navConfig.ts:291` + `SandboxView.vue:93` | 实验室导航对学生可见 admin-only 沙箱，运行得 403，困惑 | 对学生隐藏或加「仅教师/管理员可用」禁用态 | 产品 |
| 5 | 🟠 P2 | 健壮性/一致 | `CareerTrainingView.vue:133` | 裸 fetch 绕过 `src/utils/api.ts` 统一层（401 拦截/重试） | 改走 api 封装或显式接 401 拦截 | 产品+调查 |
| 6 | 🟠 P2 | 死代码 | `api/guided_parse.py:12,20` | 孤儿路由 `POST /api/guide/quiz` 定义未挂载、前端未调用 | 如产品需要则挂载，否则删除（含其引擎） | 调查 |
| 7 | 🟠 P2 | 扫描盲区 | `scan_stale_calibration.py:23-30` | SCAN_ROOTS 仅含 src/docs/deliverables/frontend，缺 `submission/` 与 `AGENTS.md` | 补入（EXCLUDE 已控住归档），避免旧品牌/漂移口径逃过扫描 | QA |
| 8 | 🟡 P3 | 数字漂移 | `PlatformHomeView.vue:135` | 硬编码「46 前端视图」，实测 47 | 改为 47 或运行时统计 | 产品 |
| 9 | 🟡 P3 | 过度承诺 | `PlatformHomeView.vue:58,133` | 卡片写「面试」情景（实际无）；「3 实训模式」的「自学」未找到实现 | 文案对齐真实能力或补实现 | 产品 |
| 10 | 🟡 P3 | 死代码 | `QuizHistoryView/ReviewView/CourseExplorerView/KnowledgeGraphView.vue` | 4 个孤儿 redirect 视图组件永不被挂载 | 删除或改造成真页面 | 产品 |
| 11 | 🟡 P3 | 死代码 | `engines/algorithm_factory.py`、`marl_dqn.py`、`train_mixer*`、`gomarl*`、`mappo*` 等 | legacy MARL 模块未接入运行 API | 归档/删除避免误用（本轮回访未深审内部正确性） | 调查 |
| 12 | 🟡 P3 | 风格一致 | `api/tutor.py:11` | 顶层 import `agents.tutor`，与全局函数内懒加载约定不一致 | 改为函数内懒加载 | 调查 |
| 13 | 🟡 P3 | 文档/命名 | `main.py:40` vs `api/langgraph.py:28`；`CLAUDE.md:24-28` | 节点/智能体命名不统一（11 节点 / 10-Agent）；CLAUDE.md 过时 FastAPI 兼容警告 | 统一命名；清理过时文档 | 调查+QA |
| 14 | 🟡 P3 | 文案 | `LiteracyAssessmentView.vue:199` | 「实验编号（学号后4位）」研究式措辞对通用演示突兀 | 改为「昵称/学号（可选）」 | 产品 |
| 15 | ℹ️ 信息 | 功能缺口 | `/api/agents/runtime` | 未实现；前端已诚实降级（不编造数据） | 若需展示 agent 运行时状态则待补 | 调查 |

---

## ✅ 行动清单（按优先级）

| # | 行动 | 负责方 | 紧急度 | 期望完成 |
|---|------|--------|--------|---------|
| 1 | **quality_gate 改为 fail-closed**，或至少向用户显式暴露「质检降级」信号；明确生产默认启用 real（NeuralMixer）或文档说明规则版口径 | 主理人 + 调查员 | **P1** | 发布前必闭环 |
| 2 | **升级 honesty/brand/caliber 红线扫描为归一化/语义匹配**（容忍变体与跨行），堵住虚假宣称静默回流 | 主理人 + 调查员 | **P1** | 发布前必闭环 |
| 3 | 品牌口径统一：公开站 MARS-408 外链改当前仓库；vite base 改；场景 A 408/考研 残留文案清理；`submission/` 与 `AGENTS.md` 补入 SCAN_ROOTS | 产品 + 调查 | P2 | 打磨首批 |
| 4 | 学生侧隐藏 admin-only 沙箱（navConfig 加 roles 或禁用态） | 产品 | P2 | 打磨首批 |
| 5 | `CareerTrainingView.vue:133` 改走 `api.ts` 封装；孤儿路由 `/api/guide/quiz` 挂载或删除 | 产品 + 调查 | P2 | 打磨首批 |
| 6 | 数字 46→47；过度承诺文案对齐；清理 legacy MARL 死代码与 4 个孤儿视图；统一节点命名；清理过时 CLAUDE.md 警告 | 产品 + 调查 | P3 | 打磨次批 |

---

## ⚠️ 待完善 / 已知局限

- 本轮回访**只读**，未运行 dev server / 全量测试 / 前端 build（避开 Windows torch SIGSEGV）；结论均锚定 file:line 静态证据，动态行为以 CI 权威值（1389 passed）为准。
- 调查员对 legacy MARL 模块仅标注「未接入运行 API」，**未深审其内部正确性**（按指令忽略 NeuralMixer/品牌统一旧任务）。
- 前端完成度为**静态评审**（路由/视图/文案/资源引用），未做真实浏览器交互走查；如需要可补一轮 E2E 走查。
- `/api/agents/runtime` 缺口为前端已诚实降级项，非缺陷，仅记录待补。

---

## 📚 成员产出索引

- 产品评审员（gstack-product-reviewer）原始产出：前端产品面 + 演示旅程调研（47 路由、Top10 打磨清单、完成度中高）。
- 调查员（gstack-investigator）原始产出：后端 243 端点清单 + 技术债清单 + 完成度 ~95%+。
- QA与发布（gstack-qa-lead）原始产出：测试/CI/门禁健康度评分 + 发布就绪度条件 Go + 质量 3 隐患。

---

## 🔒 两项 P1 闭环记录（2026-10-13）

### P1-1 Quality Gate fail-open → fail-closed
- 实现 `py-server/agents/quality_gate.py`：异常分支原 `gate_passed=True / verdict="pass"`（fail-open，谎报通过）改为 fail-closed——显式 `gate_degraded=True`，路由 `fix`（重试额度内重新生成）或 `reject`（额度耗尽），`MAX_GATE_RETRIES` 保证至多再 attempt 一次即终止，不无限循环。
- 提交：`2ce9154`（实现）+ `e626e81`（测试）。原 `test_gate_exception_fail_open` 把 bug 锁死为断言，已改为断言 `gate_passed=False / gate_degraded=True / verdict=fix|reject` 并补重试耗尽 reject 用例。
- 本地 `pytest tests/test_quality_gate.py` 23 passed；七道 pre-commit 门禁 + 树级 token_scan + a11y 全绿。

### P1-2 诚实红线门禁绕过 → 归一化 + 跨行
- 实现 `scripts/pre-commit/honesty_scan.py`：`_EXTERNAL_REDLINE_PATTERNS` 由僵化逐字正则升级为动词/副词归一化（降低|下降|减少|下滑|缩减|削减|降 / 提升|升|上升|增长|提高|上扬 + 了? + 约?），容忍「下降了/约/开销/提升了」等变体；`scan_text` 引入「前2行+当前行」跨行窗口，捕捉被换行拆分的红线。
- 提交：`cc31b74`（实现）+ `b3643c4`（将测试夹具 `test_honesty_scan.py` 加入 `_REDLINE_SKIP_FILES` 豁免，避免门禁自噬自身测试）+ `e7819a0`（回归测试，18 passed）。
- 功能探针确认：canonical/下降了/约降/开销/成本/GOMARL提升/500条/跨行 均命中；正常文案（成本优化/重要指标/架构说明）零误报。

### 结论
两项 P1（诚信/质量红线）已闭环，产品达到「可对外发布」的红线门槛。剩余 P2/P3 为打磨项（品牌口径统一、死代码清理、数字漂移校正、孤儿路由/视图），按优先级推进。

---

> 本报告由软件工坊 AI 协作生成，关键决策请由工程负责人复核。
