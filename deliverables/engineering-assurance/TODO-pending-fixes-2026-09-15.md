# 待完成任务派发清单 — NetLearn/study-help-pro @ career-literacy

**日期**：2026-09-15
**生成者**：工程保障团队主理人（team-lead）
**用途**：供后续安排其它 agent 逐一领取执行。**每项均含 file:line 证据 + 精确修法 + 验收标准**，可直接照做。
**硬约束（务必遵守）**：
1. **git 只能单会话占用** —— 执行者**禁止运行任何 git 命令**（add/commit/push 一律不做），只改文件 + 跑测试；提交由占用 git 的会话统一执行。
2. 改前先 `Read` 文件确认当前内容（仓库有并行会话反复改动，file:line 可能已漂移）。
3. 仓库根路径：`E:\Program\MARL\study-help-pro`；后端在 `py-server/`。

> 现状核对时点：HEAD = `274613f`（02:28）。F-06 已由并行会话完成（见文末「已完成」）；F-02 / F-03 / F-10 已由工程保障主理人于 2026-09-15 20:39 直接落地，**F-08 在 2026-09-15 后续核对时发现文档记录与工作树不符（编辑未落地），已于本次由主理人补正**。4 项均遵守「禁止 git」硬约束，**已改未提交**，提交由占用 git 的会话统一执行（见文末「📋 精简派发 prompt」）。

---

## 📝 改动索引（4 项均已落到工作树 · 待单会话提交）

> 以下 4 项**改动已写入文件**，仅因「git 单会话占用」约束未提交。本清单作为改动索引 + 验收锚点；最终动作 = 由独占 git 的会话提交（见文末派发 prompt）。

### 🔴 任务 1 · F-02 统一 A/B 权重解析口径（正确性/口径）
- **文件**：`py-server/engines/agent_debate.py`
- **现状证据**：`:154` import `decide_review_weight`；`:164` `d = decide_review_weight(feats, use_mappo=True)` —— **未传 evidence/consensus**。
- **问题**：`review_policy.py` 的解析式分支需要 evidence/consensus 才能命中，点A 永远走不到 analytic；而点B（`py-server/agents/quality_gate.py:158-159`）正确传了 evidence/consensus。⇒ `RULE_MODE="analytic"` 生产默认只真正驱动点B。
- **修法（二选一，先读代码判断哪个可行）**：
  - 优选：参照 `quality_gate.py:158-159` 的传参方式，在点A 调用处把 evidence/consensus 透传进 `decide_review_weight`，使两点口径一致。
  - 次选（若 debate 作用域确实拿不到 evidence/consensus）：在 `:164` 上方加显式注释声明「点A 仅走 MAPPO/规则路径，不做解析式（作用域无 evidence/consensus）」，并说明原因。
- **验收**：改后 `grep -n "decide_review_weight" agent_debate.py` 能看到 evidence/consensus 被传入，或有明确注释；运行 `pytest py-server/tests/test_review_single_source.py -q` 不新增失败。

### 🔴 任务 2 · F-03 sandbox 同步 fallback 阻塞事件循环（性能/并发）
- **文件**：`py-server/api/sandbox.py`
- **现状证据**：`:207-214`（`except Exception:` 块内）用**同步** `subprocess.Popen(...)` + `proc.communicate(timeout=timeout_sec)`，位于 async 端点内；触发时阻塞事件循环最长 `timeout_sec`（下限 10s）。
- **修法**：把这段同步调用抽成一个小函数（如 `_run_blocking_proc(argv, timeout)` 内部做 Popen+communicate），在 async 端点里改调 `await asyncio.to_thread(_run_blocking_proc, [sys.executable, tmpfile], timeout_sec)`，保持返回的 `(out, err)` 结构与现有 `except subprocess.TimeoutExpired` 逻辑兼容。注意 `except subprocess.TimeoutExpired` 分支也要相应调整（to_thread 会把 TimeoutExpired 作为线程内异常抛回）。
- **验收**：改后 `grep -n "to_thread\|Popen" sandbox.py` 确认 fallback 走 to_thread；`python -c "import ast; ast.parse(open('py-server/api/sandbox.py').read())"` 语法通过。

### 🟡 任务 3 · F-08 prompt_guard 声称与代码不符（文档漂移）
- **文件**：`CLAUDE.md`
- **现状证据**：`:188` 写「指令注入检测使用**单一 injection-verb-gated 正则**」；实际 `py-server/shared/prompt_guard.py:22-40` 是 **9 条** `_INJECTION_PATTERNS`（含无动词规则：developer mode / jail break / "you are now a" / 行首 "system:"）。
- **修法**：订正 `CLAUDE.md:188` 附近表述，如实写「9 条注入模式（含无动词规则：developer mode / jail break / "you are now a" / 行首 system: 等）」。
- **验收**：`grep -n "9 条\|injection" CLAUDE.md` 确认表述与 `prompt_guard.py` 一致。

### 🟡 任务 4 · F-10 三位一体 ③ 钩子缺「合成环境」限定词（文档诚信）
- **文件（4 处，口径须一致）**：
  - `docs/CTO-深度验收结论与三项派单令-2026-09-14.md:147`
  - `docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md:281-282`
  - `docs/验收记录-三元评审权重MAPPO-2026-09-14.md:70`
  - `docs/派单执行回执-2026-09-14.md:47`
- **现状证据**：各处 ③ 钩子含「真实增益 / 真实特征空间」但**未内联**「合成环境」；同文他处（如 CTO-深度验收:178、验收记录:83）已有正确限定。
- **修法**：在 ③ 末尾补括号限定：`（合成环境：真实特征提取管线 + 合成上下文采样，非真实 trace；真实增益待 P5 试点）`，四处保持一致。
- **验收**：`grep -rn "真实增益" docs/CTO-*.md docs/验收记录*.md docs/派单执行回执*.md` 每处 ③ 钩子都带「合成环境」限定词。

---

## ✅ 已完成（勿重复，供知悉）

| # | 项 | 状态 | 证据 |
|---|----|------|------|
| F-06 | Dockerfile 固化单写者 | ✅ 已由并行会话完成 | 根 `Dockerfile:72` `ENV WEB_CONCURRENCY=1`；`:91` `CMD ... --workers 1`；`:88-90` 注释已订正 |
| — | wave-2 恢复（CI 门禁 + 判据A + career_nodes 兜底 + ADR-007 归位） | ✅ 已持久 | commit `3d40092` 是 `origin/career-literacy` 祖先（02:26 核查） |
| F-02 | 统一 A/B 权重解析口径 | ✅ 主理人 09-15 落地 | `py-server/engines/agent_debate.py:163-169` 透传 `consensus=c` + 显式注释点A 仅走 MAPPO/规则（evidence 不在作用域）；`pytest tests/test_review_weight_protocol.py -q` **36 passed** |
| F-03 | sandbox 同步 fallback 改 to_thread | ✅ 主理人 09-15 落地 | `py-server/api/sandbox.py` 新增 `_run_blocking_proc`（POSIX 条件 `start_new_session`）+ `await asyncio.to_thread`（:230）；补 `import subprocess`（原缺失会 NameError）；`proc_returncode` 统一 :218/:233/:242/:250；`ast.parse` 通过 |
| F-08 | 订正 CLAUDE.md prompt_guard 口径 | ✅ 主理人 09-15 落地 | `CLAUDE.md:198`「单一 injection-verb-gated 正则」→「9 条注入模式（含无动词规则：developer mode / jail break / "you are now a" / 行首 system:）」，与 `prompt_guard.py:_INJECTION_PATTERNS` 对齐 |
| F-10 | ③ 钩子补「合成环境」限定词 | ✅ 主理人 09-15 落地 | 4 处 docs ③ 钩子（CTO-深度验收:147 / 攻坚令:281-282 / 验收记录:70 / 派单回执:47）均追加「（合成环境：真实特征提取管线 + 合成上下文采样，非真实 trace；真实增益待 P5 试点）」 |

---

## ⏸️ 挂起原因（已消解）

- 原派发的 Cody/Rex/Docu 三成员于 02:2x **全部 429 限流**（`2026-09-15 21:26:55 UTC+8` 重置）。4 项待办已由主理人于 20:39 直接落地（专门 agent 不可用），遵守「禁止 git」硬约束，提交由占用 git 的会话统一执行。
- 相关审计报告（含全部 file:line 出处）见：`deliverables/engineering-assurance/deep-audit-career-literacy-2026-09-15.md`。

---

## 📋 精简派发 prompt（一段话版 · 可直接粘贴给其它 agent）

> NetLearn/study-help-pro @ `career-literacy`：4 项工程保障修复（F-02/F-03/F-08/F-10）已落到工作树但**未提交**（git 单会话约束）。请在一个**独占 git** 的会话里执行：(1) 核对 4 处改动确实在位 —— `py-server/engines/agent_debate.py:168` 的 `decide_review_weight(feats, use_mappo=True, consensus=c)` 及 `:165-167` 注释、`py-server/api/sandbox.py:42` `_run_blocking_proc` 与 `:230` `await asyncio.to_thread`、`CLAUDE.md:198` 现述「9 条注入模式」、`docs/` 下 4 文件（CTO-深度验收:147 / 攻坚令:282 / 验收记录:70 / 派单回执:47）③ 钩子的「合成环境：真实特征提取管线 + 合成上下文采样，非真实 trace；真实增益待 P5 试点」限定词；(2) 跑 `pytest py-server/tests/test_review_single_source.py py-server/tests/test_review_weight_protocol.py -q` 与 `python -c "import ast; ast.parse(open('py-server/api/sandbox.py').read())"` 验证；(3) 确认无其它会话占用 git 后，**单 commit** 提交这 4 个文件（建议 message 注明 F-02/F-03/F-08/F-10），报告 commit hash。**严禁并行 git 会话**，提交前先 `git status` 确认工作树只有这 4 处预期改动、无他人混入。

### 派发时附带的验收红线（给执行 agent）
- F-02：`grep -n "decide_review_weight" py-server/engines/agent_debate.py` 须见 `consensus=c` 或显式注释。
- F-03：`grep -n "to_thread\|_run_blocking_proc" py-server/api/sandbox.py` 须见 fallback 走 `to_thread`；`ast.parse` 通过。
- F-08：`grep -n "9 条" CLAUDE.md` 须命中，且全文不再出现「单一 injection-verb-gated 正则」。
- F-10：`grep -rn "合成环境：真实特征提取管线" docs/CTO-*.md docs/验收记录*.md docs/派单执行回执*.md` 须 4 处全中。

### ✅ 执行结果（2026-09-18 · 主理人直接收口）
- 用户授权"全权交给你，现在没有并行了" → 主理人独占 git 会话，核对 4 项改动确仅含目标 diff（无他人改动混入），跑 `test_review_single_source.py` + `test_review_weight_protocol.py` 全绿（85 passed），`ast.parse` 通过。
- **已提交**：commit **`465ae1f`**（`fix(engineering): 收口 4 项工程保障修复 F-02/F-03/F-08/F-10`，7 files, +47/-17）。仅暂存 7 个目标文件，工作树其余他人改动（Dockerfile / 其它 docs / 多个 py-server 文件）未纳入。
- 本派发 prompt 已执行完毕；后续如需 push 到 `origin/career-literacy` 由用户/主理人另行决定（取决于 VPN/凭据）。
