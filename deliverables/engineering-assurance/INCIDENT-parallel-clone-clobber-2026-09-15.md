# 事故报告 — 并行会话 `git clone` 覆盖仓库，抹掉 2 个未推送提交

**日期**：2026-09-15
**工作流**：工作流 3（事故响应，SEV 评级 + 5 Why）
**严重度**：🔴 **SEV-1（数据丢失风险）** — 已被遏制，无实质内容丢失
**值班**：工程保障主理人（甄宇航 Zhen）
**状态**：✅ **已闭环**（2026-09-15 01:33 — 仓库已修复、被抹提交已重建，见文末「处置结果」）

---

## 📌 TL;DR

- 一个**并行 AI 会话**（git 身份「糖露星霜•暖霞拾光 `<2468001320@qq.com>`」）于 **~01:21:30** 对本仓库执行了 `git clone from https://github.com/TrueFurina/MARS-408.git` **覆盖 `.git`**，随后 `git reset`。
- 后果：修复波中**未推送**的两个提交 **`91fdaf4`（Tessa：判据A进CI + career_nodes 兜底单测 + p0_regression）**、**`e31128b`（Archi：ADR-007 归位 docs/adr）** 从分支历史中消失。
- **文件内容零丢失**：这两个提交的全部改动**仍在工作树**（逐项核验在位，见下）。
- 已推送的 4 个修复波提交（`76af69e`/`3a12734`/`9ee2603`/`844eed4`）安全——它们含在 `origin/career-literacy`（`56709f3`）的祖先链中。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 事件性质 | 并行会话对**含未推送提交**的仓库执行 clone 覆盖，非历史损坏 |
| 内容损失 | **0**（改动均在磁盘） |
| 提交历史损失 | 2 个（`91fdaf4`、`e31128b`），可从工作树重建 |
| 当前仓库 | ⚠️ 手术中（`.git` 被替换/重建，`refs/` 一度缺失，git 命令间歇失败） |
| 遏制措施 | 已快照 `.git` + 工作树；暂停写操作 |

---

## 🕒 事故时间线

| 时间 | 事件 |
|------|------|
| ~01:12 | 仓库正常；`git log` 顶部 = `e31128b`（含全部修复波提交） |
| ~01:15 | `.git/FETCH_HEAD` 被写（有进程 fetch） |
| ~01:16 | `git commit-graph write` 报 `not a git repository`（首次异常） |
| ~01:17 | `git rev-parse HEAD` = `366fb02`（"糖露星霜"线，**非**我们的线） |
| ~01:18 | 快照 `.git`（此时已丢失我们的对象，HEAD=366fb02） |
| ~01:21:30 | **并行会话 `git clone origin` 覆盖 `.git`** + `reset`（`.git/logs/HEAD` 铁证） |
| ~01:22 | `git log` 顶部 = `56709f3`（我们的前 4 提交在，`91fdaf4`/`e31128b` 消失） |
| ~01:23–01:25 | `.git` 反复重建（`refs/` 缺失→01:25 再现）；`.git_partial_012506` 中间产物；git 命令间歇失败 |

---

## 🔬 根因（5 Why）

1. **为什么 git 命令间歇报 `not a git repository`？** → `.git` 正被整体重建（clone 会创建全新 `.git`）。
2. **为什么 `.git` 被重建？** → 并行会话执行了 `git clone origin`。
3. **为什么 clone 会丢提交？** → `clone` 只含远端对象；本地**未推送**的 `91fdaf4`/`e31128b` 不在远端 → 被排除。
4. **为什么并行会话要 clone？** → 推测：仓库对象库此前已现缺失（`pack-873f9bc…pack` 丢失、`refs/heads/main` 指向丢失对象），其选择"重新 clone 覆盖"来"修复"。
5. **为什么会出现对象缺失？** → 疑与后台 `git maintenance`/`repack`（`geometric-repack` 报 `unable to read`）及多会话并发 git 操作叠加有关（**待并行会话收尾后复核**）。

> **核心教训**：`git clone`/`reset --hard` **不是修复**含未推送提交仓库的合法手段——它会静默丢弃本地独有历史。修复前必须先 `git reflog` / 快照并确认无独有提交。

---

## 📊 影响范围

| 对象 | 状态 | 备注 |
|------|------|------|
| `origin/career-literacy` (`56709f3`) | ✅ 安全 | 远端 GitHub `TrueFurina/MARS-408` |
| 修复波 `76af69e`/`3a12734`/`9ee2603`/`844eed4` | ✅ 安全 | 在 `56709f3` 祖先链 |
| `91fdaf4`（Tessa） | ⚠️ 历史丢失 | 改动在工作树：`tests/test_career_nodes_fallback.py`(新)、`test_review_analytic.py`、`test_review_single_source.py`、`test_career_policy_baseline.py`、`pyproject.toml`、`ci.yml` |
| `e31128b`（Archi） | ⚠️ 历史丢失 | 改动在工作树：`docs/adr/ADR-007-import-queue-servitization.md`(新)、`docs/adr/INDEX.md` |
| 工作树（含设计系统 WIP ~109 项） | ✅ 磁盘在位 | `git status --short` = 109 项 |

**已逐项核验在位的修复成果**：`multimodal.py` run_in_executor(=2)、`tts_service.py` to_thread(=2)、`frugal_rag.py` scan_iter(=3)、`DEMO_RUNBOOK.md` 冒烟段(=1)、`ADR-011`/`ADR-007` 文件存在、`DiagnosticView.vue` role=button(=4)。

---

## 🛡️ 已采取遏制措施

1. **`.git` 快照** → `/e/Program/MARL/_git_snapshot_20260915T0120/.git`（01:18 时点）
2. **工作树快照** → 同目录 `worktree.tar.gz`（1.3 GB，01:21 时点）
3. **暂停一切 git 写操作**（本次仅只读诊断）

---

## ✅ 行动项

| # | 行动 | 负责 | 紧急度 |
|---|------|------|--------|
| 1 | **暂停并行会话的一切 git 手术**，等其 clone/reset 收尾 | 用户协调 | P0 |
| 2 | 收尾后 `git status`/`git fsck` 复核；确认 `career-literacy` 落在稳定提交 | 主理人 | P0 |
| 3 | 从工作树**重建**被抹的 2 个提交（内容在磁盘，按原内容重组 commit） | Cody/Archi/Tessa | P1 |
| 4 | 复核被抹提交是否与工作树其余 109 项 WIP（他会话）混合，**只提交自己文件** | 主理人 | P1 |
| 5 | 全仓统一纪律：**禁止**对含未推送提交的仓库跑 `clone`/`reset --hard`/`gc --prune` | 全体 | P1 |
| 6 | 收尾后清理本次诊断临时文件（`.cg_*`/`.state*`/`.fs.txt` 等） | 主理人 | P2 |

---

## ✅ 处置结果（2026-09-15 01:33 闭环）

| 步骤 | 动作 | 结果 |
|------|------|------|
| 1 | 判定并行会话是否停手 | ✅ 已停手（`.git` 内文件 mtime 全部停在 01:25，无变化） |
| 2 | 快照当前 `.git` | → `_git_snapshot_20260915T0120/.git_clone_0125` |
| 3 | **附加式修复**：重建缺失的 `refs/` | `mkdir -p .git/refs/{heads,tags}` + `refs/heads/career-literacy` = `56709f3` |
| 4 | 验证 | `rev-parse HEAD`=`56709f3`、`git log`/`status` 恢复、**`git fsck` 0 错误**、双远端正常 |
| 5 | **重建被抹提交** | 从工作树按路径精确 add 8 文件 → commit **`255809f`**（+438/−2） |

**根因（最终）**：并行会话对仓库执行 `git clone origin` **整体覆盖 `.git`**，留下**残缺 clone**——`.git` **缺整个 `refs/` 目录**（只剩 `packed-refs`），故 git 判定 `not a git repository`。对象包完整（`pack-02f3def9`，48MB）。

**恢复手法（可复用）**：botched-clone 致 `.git` 缺 `refs/` 时，**手动重建 `refs/` + 分支指针文件**即可救活（务必先 `cp -r .git` 快照），随后 `git fsck` 复验至 0 错误。

**未触碰**：他会话 ~101 项未提交 WIP、`.git_partial_012506` 残留。

---

## 🔎 元凶会话指认（2026-09-15 01:41 取证）

在 `C:\Users\Lenovo\.workbuddy\projects\e-Program-MARL-study-help-pro\` 下对同项目全部活跃会话做 `git clone / MARS-408.git / .git_partial` 命中统计，**唯一元凶**：

| 会话 UUID | 最后写入 | `git clone` 命中 | `MARS-408.git` 命中 | `.git_partial` 命中 | cwd | 判定 |
|-----------|---------|-----------------|--------------------|--------------------|-----|------|
| **`cebf1414-6abe-405b-a2e6-c681ca9b6c14`** | **01:25:05** | **46** | **183** | **8** | `e:\Program\MARL\study-help-pro` | 🔴 **元凶**（与 `.git` 最终 mtime 01:25 精确吻合） |
| `d3b6c1b1-9313-464e-888c-35c4f9c0a8d5` | 01:33 | 0 | 0 | 0 | 同上 | 🟢 前端谋划线，无 clone（6×commit/2×stash） |
| `b999d405-6adc-4211-85aa-28b3ad09b0ba` | 01:28 | 0 | 0 | 0 | 同上 | 🟡 前端谋划线，**6×`git reset --hard`**（无 clone，但同为高危） |
| `0390d1f5-…`（本会话） | 01:41 | 0 | 0 | 0 | 同上 | 🟢 本团队（`teamName=engineering-continue-opt`） |

- **元凶会话身份**：**非本团队**（meta 无 `teamName`），是标准独立会话；其首个用户消息为「**分析本项目**」，对话摘要显示其主题为「**NetLearn 设计系统 v8 优化**」。其自身推理链明确写着"`git clone --no-checkout --quiet https://github.com/TrueFurina/MARS-408.git` … 获得一个完整健康的 `.git`" 并讨论了把克隆的 `.git` 换进来。
- **注入身份不可用于区分**：该机全局 `~/.gitconfig` = 「糖露星霜•暖霞拾光 `<2468001320@qq.com>`」，且**所有**并行会话（含元凶与本团队）注入的 `USER.md` 均为同一份（"张敏杰/信安"）——故"哪个会话"只能靠 **UUID + 主题** 定位，不能靠 git 作者名。
- **当前状态**：元凶会话最后写入 01:25，取证时 01:41（**16 分钟无写入**）→ 已停手/空闲，未再对本仓库动手。

---

## ⚠️ 待完善 / 已知局限

- 根因第 5 步（对象缺失的初始成因）**未最终坐实**——需待仓库稳定后查 `.git/logs`、`gc.log`、后台维护历史。
- 事件期间仓库 `.git` 仍被并行会话持续改动，本报告为**时点快照**，结论可能随后续操作变化。
- 该并行会话已定位（见上「元凶会话指认」）：UUID `cebf1414-…`，主题「分析本项目/设计系统 v8 优化」；非本团队，需用户在会话列表按此主题找到并约束它。

---

## 📚 数据来源

- `.git/logs/HEAD`（clone/reset 记录）、`.git/packed-refs`、`.git/objects/pack/*`
- `git fsck` / `git count-objects -v` / `git rev-parse` / `git status --short`（多时点）
- 诊断留痕：`.cg_fix.txt`、`.cg_diag.txt`、`.state2.txt`、`.state3.txt`、`.flap.txt`、`.who.txt`、`.fs.txt`、`.final_check.txt`、`.partial_check.txt`

---

> 本报告由工程保障团队 AI 协作生成，SEV-1 事件的关键处置请由人类工程负责人复核并协调并行会话。
