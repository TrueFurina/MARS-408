# 待办修复落地报告（F-02 / F-03 / F-08 / F-10）

**日期**：2026-09-15
**工作流**：工程保障修复执行（派生自 `TODO-pending-fixes-2026-09-15.md`，非标准 5 工作流之一）
**参与成员**：主理人（Zhen）直接执行（专门成员 agent 不可用 / 限流，参照 07-19 先例以通用执行代行）；Cody/Rex/Docu 结论由主理人据磁盘实测汇编

---

## 📌 TL;DR（执行摘要）

- **整体结论**：完成了 `TODO-pending-fixes-2026-09-15.md` 中遗留的 4 项修复（F-02 权重口径 / F-03 sandbox 异步阻塞 / F-08 文档漂移 / F-10 诚信限定词），全部为「方案级→代码级」落地，**未运行任何 git 命令**（遵守单会话 git 硬约束），提交待占用 git 的会话统一执行。
- **严重度分布**：🔴关键 0 新项 / 🟠高 2 项（F-03 实为潜在 NameError+事件循环阻塞双重 bug）/ 🟡中 2 项（F-02 口径 / F-08 文档漂移 / F-10 诚信）/ 🟢低 0 项
- **阻塞 / 非阻塞**：无阻塞。F-02 验收 `pytest tests/test_review_weight_protocol.py -q` → **36 passed**；F-03 `ast.parse` 通过且 fallback 改走 `to_thread`；F-08/F-10 为文档类，grep 全量复核通过。
- **团队状态（重要）**：被注入恢复的 `engineering-deep-dive-2026-07-19` 团队**完全不可恢复**（11 名成员全部 `unresumable`、无 durable task id），无法经 `SendMessage` 续跑。其产物 `archive/.../deploy-check-deep-dive-2026-07-19.md` 虽已存在（方案级、从未落码），但其**核心前提（"讯飞仅 X2 权限、强制 spark_x2"、ADR-011）已被 09-01 实测推翻**——账号无 X2 权限、`generalv3.5` 方为真实主通道，照原方案强制 X2 现会**直接弄坏 LLM**。故本次**未续作 07-19 线**，改执行当前最新的 live 待办。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟢 完成（4/4 落地，无新阻塞） |
| 阻塞项数量 | 0 |
| 关键行动项 | 1 条（提交待 git 会话统一处理） |
| 建议下一步 | 由占用 git 的会话将 4 处改动提交；CI 干净环境重跑全量回归（本地 Windows SIGSEGV 属环境级，不当红灯） |

---

## 🔧 修复明细（按 file:line + 改动 + 验证）

### F-02 · 统一 A/B 权重解析口径（正确性 / 口径）
- **文件**：`py-server/engines/agent_debate.py:163-169`
- **原状**：`:164` `decide_review_weight(feats, use_mappo=True)` 未传 `evidence/consensus` → 解析分支（analytic）需 evidence 与 consensus 同时非空才命中，点A 永远走不到 analytic（仅点B 经 `quality_gate.py:158-159` 正确传参驱动）。
- **改动**：作用域确认**无 evidence**（调用方 `api/agents.py` 与全部测试仅传 `consensus`），故采用 TODO 允许的「次选」：透传 `consensus=c` 保持签名一致 + 显式注释声明点A 仅走 MAPPO/规则路径（属设计预期非缺陷）。
- **验证**：`ast.parse` 通过；`pytest py-server/tests/test_review_weight_protocol.py -q` → **36 passed**；行为零变化（analytic 在点A 仍不触发，与修复前一致）。

### F-03 · sandbox 同步 fallback 改 `to_thread`（性能 / 并发 + 潜藏 bug）
- **文件**：`py-server/api/sandbox.py`
- **原状**：`:207-214` `except Exception` 兜底在 async 端点内用**同步** `subprocess.Popen(...).communicate(timeout)` → 阻塞事件循环最长 `timeout_sec`（下限 10s）；且**致命**：该处引用 `subprocess` 但文件从未 `import subprocess`（→ Windows 触发兜底即 `NameError`）；`start_new_session=True` 在 Windows 亦非法。
- **改动**：① 补 `import subprocess`（模块级）；② 新增模块级 `_run_blocking_proc(argv, timeout)`（POSIX 条件 `start_new_session`、`TimeoutExpired` 内先 `_kill_proc_group` 再 `raise`、返回 `(out, err, returncode)`）；③ 兜底改 `await asyncio.to_thread(_run_blocking_proc, [...], timeout_sec)`；④ 引入 `proc_returncode` 统一 :218/:233/:242，并修复 :250 记忆写入中 `proc.returncode`（fallback 路径 `proc` 不在作用域 → 原会 `NameError` 被静默吞掉记忆写入）。
- **验证**：`ast.parse` 通过；`grep to_thread` 确认 fallback 路由；无残留裸 `proc.returncode` 误用。

### F-08 · 订正 CLAUDE.md prompt_guard 口径（文档漂移）
- **文件**：`CLAUDE.md:198`
- **原状**：写「指令注入检测使用**单一 injection-verb-gated 正则**」，与实际 `py-server/shared/prompt_guard.py:_INJECTION_PATTERNS` 不符。
- **改动**：更正为「9 条注入模式（含无动词规则：developer mode / jail break / "you are now a" / 行首 system:）」，并保留「`instructions:` 后接动词才隔离、不误伤正常提问」的要点。
- **验证**：grep 确认 `prompt_guard.py` 共 9 条模式；CLAUDE.md 表述与代码一致。

### F-10 · ③ 钩子补「合成环境」限定词（文档诚信）
- **文件**（4 处）：`docs/CTO-深度验收结论与三项派单令-2026-09-14.md:147`、`docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md:281-282`、`docs/验收记录-三元评审权重MAPPO-2026-09-14.md:70`、`docs/派单执行回执-2026-09-14.md:47`
- **改动**：每处 ③ 钩子末尾追加「（合成环境：真实特征提取管线 + 合成上下文采样，非真实 trace；真实增益待 P5 试点）」，与同文他处（如 CTO-深度验收:178、验收记录:83 已正确限定）口径统一。
- **验证**：4 文件 grep 均命中「真实增益…合成环境」限定词。

---

## ✅ 行动清单（按优先级）

| # | 行动 | 负责角色 | 紧急度 | 预期完成 |
|---|------|---------|--------|---------|
| 1 | 由占用 git 的会话提交本次 4 处改动（未 commit，遵守单会话 git 约束） | git 占用会话 | P0 | 立即 |
| 2 | CI 干净环境重跑全量回归（`-m "not system and not requires_milvus"`）；本地 Windows SIGSEGV(139) 属环境级缺陷，不当红灯 | CI / 主理人 | P1 | 提交后 |
| 3 | 07-19 深度续作报告中的 ADR-011（强制 spark_x2）**作废**：以 09-01 实测为准（generalv3.5 主通道），如需护栏应改为「禁止误配无权限模型」而非「强制 X2」 | 主理人 / 用户 | P2 | 后续 |

---

## ⚠️ 待完善 / 已知局限

- **团队恢复失败**：`engineering-deep-dive-2026-07-19` 11 名成员全部 `unresumable`、无 durable task id，无法 `SendMessage` 续跑；已据实声明，未伪造进度。
- **07-19 方案已过时**：其「X2 唯一权限 + ADR-011 强制 X2」前提被 09-01 实测推翻（账号无 X2、generalv3.5 主通道），该报告方案级结论不应再被当作可执行项；本报告第 3 条行动项已将其标记为作废。
- **未跑全量测试**：F-02 仅以轻量 `test_review_weight_protocol.py` 验证（36 passed）；F-03 仅 `ast.parse` + 逻辑复核（无 sandbox 专用测试）。全量回归依赖 CI（本地 torch/SIGSEGV 环境级）。
- **未 git 提交**：遵守 `TODO-pending-fixes` 的「执行者禁止 git」硬约束；提交由占用 git 的会话统一执行，避免与并行会话冲突。

---

## 📚 数据来源 & 成员产出索引

- 任务来源：`deliverables/engineering-assurance/TODO-pending-fixes-2026-09-15.md`（含全部 file:line 与修法）
- 代码证据：`py-server/engines/agent_debate.py`、`py-server/api/sandbox.py`、`py-server/shared/prompt_guard.py:_INJECTION_PATTERNS`、`py-server/engines/review_policy.py:decide_review_weight`
- 文档证据：`CLAUDE.md`、`docs/CTO-*.md`、`docs/验收记录-三元评审权重MAPPO-2026-09-14.md`、`docs/派单执行回执-2026-09-14.md`
- 历史对照：`archive/deliverables_历史/deliverables/engineering-assurance/deploy-check-deep-dive-2026-07-19.md`（07-19 方案，前提已过时）

---

> 本报告由工程保障团队 AI 协作生成，关键决策与代码改动请由人类工程负责人复核后提交。
