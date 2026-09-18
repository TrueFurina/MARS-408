# NetLearn 后端 · career-literacy 分支 · 综合审计报告

**日期**：2026-09-15
**工作流**：工作流 1（综合代码审查）为主，合并架构 / 可运维 / 测试 / 文档四职能审计
**参与成员**：Cody（代码审查师）· Archi（系统架构师）· Rex（SRE 工程师）· Tessa（测试专家）· Docu（技术文档师）
**审计基线**：分支 `career-literacy`；各成员取证时点 HEAD ≈ `3a12734`（已含修复波 `76af69e`/`844e*`/`9ee2603`/`91fdaf4`/`255809f`）
**方法**：**只读**审计，逐项给 file:line 证据；本轮不修改任何项目文件

> ⚠️ 路径校正（成员独立复核发现简报笔误）：`quality_gate` 实为 `py-server/agents/quality_gate.py`；`agent_debate` 实为 `py-server/engines/agent_debate.py`；`api/teacher.py` **不是** career 端点，career 路由实为 `py-server/api/career_training.py`。

---

## 📌 TL;DR（执行摘要）

- **整体结论**：核心功能性构件（MAPPO/review 权重层、ADR-007 单写者、career 零侵入边界）**全部为真、无造假**；地图正确，但地面有若干需要消化的工程缺口，且**发布门禁当前为 🔴**。
- **严重度分布**：🔴 严重 **1** 项 / 🟠 高 **4** 项 / 🟡 中 **8** 项 / 🟢 合规 **7** 项
- **阻塞 / 非阻塞**：**1 项发布阻塞**（工作树未收敛 + 未跟踪新模块 → 打出镜像即可丢功能）；其余为演示后 / 规模化前须消化项。
- **最高置信度信号**：Cody 与 Archi **各自独立**命中同一偏差——**点 A / 点 B 的权重解析语义不对称**（`RULE_MODE="analytic"` 生产默认只真正驱动点 B，点 A 永远走不到解析式）。两名成员交叉印证 ⇒ 可信度高。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟡 **有条件通过**（可安全上线演示；规模化前须消化 🟠/🟡） |
| 阻塞项数量 | **1**（发布卫生：工作树未收敛） |
| 关键行动项 | **8** 条 |
| 建议下一步 | 收敛工作树 → 修点A/B口径 → 修 sandbox 残留阻塞 → 补文档订正 → 再打发布包 |

---

## 🔍 审查发现（按严重度排序，已跨成员去重）

| # | 严重度 | 类别 | 文件:行 | 问题描述 | 建议修复 | 来源 |
|---|--------|------|---------|---------|---------|------|
| F-01 | 🔴 严重 | 发布卫生 | `git status`（~77 tracked M + ~25 untracked） | 工作树未收敛：含 `M py-server/main.py`、`M py-server/api/__init__.py`；且新模块 `?? py-server/api/benchmark.py`、`?? tests/`、`?? src/composables/` **未跟踪** → 干净检出 / `git archive` / `Docker COPY` 会**漏带功能** | 发布前处置 main.py/`__init__.py` 的未提交改动；把新模块 `git add` 入库后再构建 | Rex |
| F-02 | 🟠 高 | 正确性/口径 | `engines/agent_debate.py:164`（调用方 `api/agents.py:154`） | 点A 调 `decide_review_weight(feats, use_mappo=True)` **未传 evidence/consensus** ⇒ `review_policy.py:893` 解析式条件不满足 ⇒ **点A 永远走不到 analytic**，`RULE_MODE="analytic"` 仅驱动点B → **点A/点B 行为不对称** | 二选一：①把 evidence/consensus 透传进 `decide_review_weight`，令 A/B 口径一致；②在 A 处显式注释声明"点A 仅用 MAPPO/规则" | **Cody + Archi（独立双命中）** |
| F-03 | 🟠 高 | 性能/并发 | `api/sandbox.py:207-214` | 主路径 `await create_subprocess_exec` 正确，但 `except Exception:` **fallback 用同步** `subprocess.Popen` + `communicate(timeout)`，位于 async 端点内 → 触发时**阻塞事件循环**最长 `timeout_sec`（下限 10s） | 把 fallback 包成 `await asyncio.to_thread(_run_blocking_proc, [sys.executable, tmpfile], timeout_sec)`，返回结构不变 | Cody |
| F-04 | 🟠 高 | 可运维性 | `db/pg_client.py:82-113`、`db/milvus_client.py:520-572`、`db/redis_client.py` | **静默降级不可观测**：PG→SQLite 失败仅 warning；Milvus count 超时降级 0 与"真空库"**不可区分** → 会误触 `collection_size=0 → 回滚` 红线；Redis 降级态也未暴露 | 把 pg/redis/milvus 降级态暴露到 `/api/status`（或 metric）；Milvus count 超时区分 "unreachable" 与 "empty" | Rex |
| F-05 | 🟠 高 | 安全/稳定性 | `api/career_training.py:90-253`（全端点） | **无限流**（main.py 无 slowapi/limiter 中间件）；LLM 型端点可被刷爆配额 | `session/start`、`answer` 等加简单限流或并发信号量 | Rex |
| F-06 | 🟡 中 | 可运维性 | `Dockerfile:85-87` | 仅注释声明"须 `--workers 1`"；**CMD 未带 `--workers 1`，无 `ENV WEB_CONCURRENCY=1`**，靠 uvicorn 默认 1 + 启动守卫兜底；且 GoNoGo 第19行"Dockerfile 已显式"表述**与实现漂移** | CMD/ENV 显式固化 `--workers 1` + `WEB_CONCURRENCY=1`；订正 GoNoGo 表述 | Rex |
| F-07 | 🟡 中 | 架构/耦合 | `engines/career_policy.py:60` | `from engines.mappo_policy import _build_networks` —— career 依赖 408 侧**下划线私有 API**，408 侧重构可**静默断线** | 提升为公开稳定契约（加 shim/别名），或 career 自带网络构造 | Archi |
| F-08 | 🟡 中 | 文档漂移 | `shared/prompt_guard.py:22-40` vs `CLAUDE.md` | CLAUDE.md 称注入防护为"single verb-gated regex"，实际为 **9 条** `_INJECTION_PATTERNS`（含无动词规则）→ 安全姿态实际更宽，但**声称与代码不符** | 订正 CLAUDE.md 表述（9 条模式 + 无动词规则） | Cody |
| F-09 | 🟡 中 | 测试 | `pyproject.toml`、CI | "843 passed"全量数字**未经 Linux CI 端到端核验**（Windows 本地只证 **58** 例真跑绿，全量受 torch/numpy SIGSEGV 遮蔽）；`experiments/accept_review.py` 本体不在 `testpaths` | 全量 843 与新增两条 CI 门禁须在 Linux CI 复核后再写入对外结论 | Tessa |
| F-10 | 🟡 中 | 文档诚信 | `docs/CTO-深度验收:147` 等 4 处 | 三位一体叙事 ③"career 线 RL 真实增益"钩子**缺内联"合成环境"限定词**（标题含"真实增益/真实特征空间"却未注明合成），脱离上下文易被读成真实增益 | ③ 后补括号限定"（合成环境：真实特征提取管线+合成上下文采样，非真实 trace；真实增益待 P5 试点）" | Docu |
| F-11 | 🟡 中 | 架构/扩展 | `services/import_worker.py` + ADR-008 | 单写者 `--workers 1` 现**绑死整个 API 进程** → 与水平扩展存在张力；ADR-008 已记原则，落地机制 ADR-012 未立 | 按 ADR-008 把 import 单写者收敛到专属 worker，解绑 API 扩展；立 ADR-012 | Archi |
| F-12 | 🟡 中 | 可运维性 | `services/career_service.py:84-139`、`agents/career_nodes.py` | career 每轮 await 取证/生成，**本层无显式超时**，依赖底层 LLM client → LLM 挂起则请求挂起 | await 外包 `asyncio.wait_for` 或显式设 client timeout | Rex |
| F-13 | 🟡 中 | 架构/卫生 | `py-server/experiments/*` | 实验诊断脚本混入生产目录；旧接线脚本曾用字符串锚点直接改源文件（**已归档** `archive/drifted-wire-scripts/*.disabled`） → 仍有回用风险 | 保持归档禁用状态；根目录零散 `_probe_*.txt` 清理或 gitignore | Archi / Rex |

---

## ✅ 已核验合规项（正面结论，🟢）

| # | 结论 | 关键证据 | 来源 |
|---|------|---------|------|
| P-01 | **MAPPO/review 权重层真实、无造假** | `engines/review_policy.py:477-495` 真解析式（循环 argmax，非查表/硬编码），恒等式与 `agents/quality_gate.py:130-132` 打分函数**数学一致**；`review_policy.py:474` `RULE_MODE="analytic"`；`career_policy.py:32` `EVIDENCE_DENSITY_DEFAULT=0.3`（0.5→0.3 已落实） | Cody |
| P-02 | **单一真值源已收敛** | `review_policy.py:498-513` `review_precision`、`:516-537` `discipline_gate` 为唯一实现（3 份复制体已清）；Tessa 用**同一性断言 `x is y`** 守护（漂移无法发生） | Cody + Tessa |
| P-03 | **ADR-007 单写者双保险真落实** | `main.py:263-277` 启动守卫（env/CLI `--workers N >1` → fail-fast）+ `import_worker.py:112-133` filelock `acquire(blocking=True,timeout=2)` 真阻塞（原 no-op 已修） | Rex + Archi |
| P-04 | **career 零侵入边界成立** | 全 `career_*` 沙箱；独立 `db.career_store`，**不写** 408 的 `vectordb`/`netlearn_kb`；`agents/career_nodes.py` 对 review_weights/consensus/quality_gate/gomarl **零匹配** | Archi |
| P-05 | **异步阻塞多数已修** | 6 处中：E5 嵌入(`api/agents.py:63/226`)、PDF(`knowledge.py:227`)、Redis、pptx(`multimodal.py:113` run_in_executor) 已包裹；MeloTTS(`tts_service.py:238/244`) 与 pptx 原裸阻塞已由 `76af69e` 修复 | Cody |
| P-06 | **文档诚信红线未违反** | CTO 派单令四条红线（a/b/c/d）全无对外违规；capture 100%/99.8% 如实且带诚实边界（≠真实教学增益）；三位一体叙事核心文档一致 | Docu |
| P-07 | **关键测试守护力强** | 单一真值源用同一性断言；CTO 基线门 §6.1 a/b/c 齐全；行为双侧锚；`test_review_single_source.py`(49) + `test_career_policy_baseline.py`(9) **58 例真跑绿** | Tessa |

---

## 🏗️ 架构影响评估（合并 Archi 结论）

- **新权重层性质**：`🟢 干净下游插入` —— `agents/quality_gate.py:200-218` 仅替换判定**输入** `consistency_score`，PASS/FIX/REJECT 门 `:220+` 逐字未动；`gomarl*.py` 对 `review_policy`/`career` **零引用** ⇒ 无反向依赖。
- **灰度安全**：`config.py:302-304` `use_review_mappo()` 默认 **False** ⇒ 关闭时全链路权重=均匀、行为逐字等于现状。解析器与合成函数对 `None/空/均匀` 权重均**零偏移**，异常 **fail-open**。
- **总评级 🟡**：核心耦合层实为 🟢，拉低到 🟡 的是**治理/耦合债**（F-07 私有 API、F-11 扩展张力、F-13 实验脚本），非功能性缺陷。
- **三大架构债闭合进度**：① drift 接线脚本已归档 ✅ ② ADR 缺口（011/015/017 + ADR-007 归位）已闭合 ✅ ③ 单写者/扩展张力**待 ADR-012** ⏳。

---

## 🧪 测试覆盖评估（合并 Tessa 结论）

- **回归基线口径订正**：任务单写"既有 46"**有误**，实际 `test_review_single_source.py` 参数化展开为 **49** 例 ⇒ 49+9=**58**（非 55/46）。**843 全量数字未经本地/我端到端复跑核验**，须 Linux CI 背书。
- **守护力判定**：核心测试**无"测了但没效"**——均为语义/同一性断言，有明确变异体对照（discipline_gate 同一对象、差一回归、阈值等号、量纲 [0,1]、reward 分项记账等）。
- **唯一"测了但没进 CI"**：判据A（`experiments/accept_review.py`）本体不在 `testpaths` → 已由修复波镜像入 CI（`test_review_analytic.py` + `ci.yml` `pytest -m review_capture`）。
- **健康度 🟢**：3 处 🟡 缺口（判据A 无 CI 守护 / career_nodes 兜底无单测 / 基线未打 P0 标记）已在 commit `91fdaf4` 关闭。

---

## ✅ 行动清单（按优先级排序）

| # | 行动 | 负责角色 | 紧急度 | 验收标准 |
|---|------|---------|--------|---------|
| 1 | **收敛工作树**：处置 `py-server/main.py`、`api/__init__.py` 未提交改动；`git add` 新模块 `benchmark.py`/`tests/`/`src/composables/` | Rex / 主理人 | **P0** | `git status` 无遗漏新模块；干净检出含全部功能 |
| 2 | **统一 A/B 权重解析口径**：`agent_debate.py:164` 透传 evidence/consensus，或注释声明点A 仅用 MAPPO | Cody / Archi | P1 | 两点行为一致（或偏差被显式文档化） |
| 3 | **修 sandbox 同步 fallback**：`api/sandbox.py:207-214` → `asyncio.to_thread` 包裹 | Cody | P1 | fallback 触发不再阻塞事件循环 |
| 4 | **暴露降级态**：PG/Redis/Milvus 降级写入 `/api/status` 或 metric；区分 Milvus count "unreachable/empty" | Rex | P1 | 静默降级可观测，防误触回滚 |
| 5 | **career 端点加限流/超时**：LLM 型端点限流 + await 外包 `asyncio.wait_for` | Rex / Cody | P1 | 端点可抗刷、请求不会无限挂起 |
| 6 | **Dockerfile 显式固化** `--workers 1` + `ENV WEB_CONCURRENCY=1`；订正 GoNoGo 漂移表述 | Rex | P2 | 镜像默认单写者，文档一致 |
| 7 | **文档订正两处**：`prompt_guard`（9 条模式）+ 三位一体③补"合成环境"限定词 | Docu | P2 | 声称与代码/边界一致 |
| 8 | **提升 career 私有 API 依赖为公开契约**；立 ADR-012（单写者 vs 扩展） | Archi | P2 | 408 侧重构不断 career；ADR-012 落盘 |

---

## ⚠️ 待完善 / 已知局限

- **本报告为时点快照**：仓库同树存在并行会话与修复波并发改动，工作树状态（F-01）随时变化；发布前须再取一次 `git status`/`fsck`。
- **全量回归数字未独立背书**：843 passed 未在 Linux CI 复核（Tessa 明确保留），对外引用前须 CI 背书。
- **审计未覆盖**：真实 trace 复评管线（`experiments/eval_review_mappo_real.py` 就绪但无真实输入、从未跑过）；Windows SIGSEGV 遮蔽的 4 个 segv_env 模块用例。
- **F-02 属"口径不一致"而非崩溃**：点A analytic 不可达是设计取舍问题，非功能缺陷；但两名成员独立标记 ⇒ 须明确处置。

---

## 📚 数据来源 & 成员产出索引

- **Cody（代码审查师）**：MAPPO 层真实性逐项核验（`review_policy.py:477-495`/`:474`/`career_policy.py:32`）；6 处异步阻塞核验（4 包裹 + 2 已修）；新发现 `api/sandbox.py:207-214` 残留阻塞（F-03）、`prompt_guard` 文档漂移（F-08）、点A analytic 不可达（F-02）。
- **Archi（系统架构师）**：插入点 A/B 耦合评估、双分支零侵入核验、架构债三路（F-07/F-11/F-13）、架构总评级 🟡。
- **Rex（SRE 工程师）**：career 端点可运维性（a1-a6）、ADR-007 硬约束逐项核验（b1-b6）、三降级容灾（c1-c5）、发布卫生（F-01 🔴/F-04/F-05/F-06/F-12）、Go with conditions。
- **Tessa（测试专家）**：58 例真跑绿、守护力变异体对照表、覆盖盲点（segv_env/CI 差异/requires_milvus）、基线口径订正（49 非 46）、F-09。
- **Docu（技术文档师）**：CTO 红线 a/b/c/d 逐条核查、三位一体一致性、F-10 唯一 🟡 加强建议、`9ee2603` 事实订正清单。
- 原始出处：各成员 SendMessage 回执（engineering-continue-opt 团队，2026-09-15 01:4x）。

---

> 本报告由工程保障团队 AI 协作生成，关键决策请由人类工程负责人复核。
