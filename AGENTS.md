# AGENTS.md — study-help-pro 项目事实源

> 权威真值详见 CLAUDE.md（双分支双身份说明）与 .agents/skills/ 四件套；本文件是每会话最小事实卡。

## 这是什么
双分支双身份共用底座：`main` 分支 = MARS-408（软件杯 A3，408 考研学习平台）；`career-literacy` 分支（当前）= 芒得很职（三创赛，软素养实训平台），新代码一律 `career_*` 前缀零侵入 408。

## 命令
- 后端: `cd py-server && pip install -e . && python main.py`（:8002）
- 测试: `cd py-server && env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE .venv/Scripts/python.exe -m pytest tests/ -q --basetemp=.pytest_tmp --no-cov -p no:cacheprovider --continue-on-collection-errors`
  - 2026-09-27 实测全量 **923 passed / 221 skipped / 3 xfailed / 0 failed**（旧文档"全量全挂"的说法已过时）。
  - 前两个 `env -u` 是必需的：WorkBuddy shell 的注入会污染 pytest 子进程；`--continue-on-collection-errors` 用于跳过 torch c10.dll 的本机环境错误。
- E5 模型恢复: `python scripts/fetch_e5_model.py`（模型不入库，会话重置后执行）
- 机验（改动结构后跑）: `py-server/scripts/verify_{app_wiring,core_lock_unification,seed_data_split,user_store_split}.py`

## 禁区
- 分支同步方向唯一：main → career-literacy，禁止反向
- 竞赛口径数字必须对齐代码真值；E5 模型文件不入库
- 永禁 `git add -A`（junction 会导致把未删文件误记为删除）；永禁 `git stash/merge/pull/gc/prune`
- `*/crypto_platform/py-server/**`（188 文件嵌套副本）**未经用户确认不得移动或删除**
- 提交时必须逐文件显式 `git add`，且 add 后先看 `git status`（暂存为空时密钥扫描会退化成全仓扫描并误报）

## 当前状态（2026-09-27 架构评审收口，接手前先读）
- 架构评审 M-1~M-5 全部修复并机验；全项目结构已落定：
  `py-server/app/`（装配层，main.py 只剩 85 行组装）、`py-server/seed/`（408 四科语料包，`seed_data.py` 变 38 行委托层）、`db/profile_store.py`（画像域）。
- **兼容层是"动态委托"（PEP 562 `__getattr__`），不是静态重导出** —— 改成静态会让打桩监控失效。改前读文件头注释。
- **覆盖率已达标**：52.32% → **54.08%**（门禁 54%，2026-09-28 补测 commit `32cfffc`）。补测加了 9 个测试文件
  （SSRF 守卫 / 页码对齐算法 / lifespan 守门 / 中间件矩阵 / 画像域契约 / DI 容器 / 内容安全 / SPA 挂载 / JWT 角色），
  并修复 1 个随 M-4 拆分失效的静态锚点测试。
- **当前无阻塞项**：全量 `1139 passed / 0 failed`；唯一 error 是本机 torch `c10.dll` 加载失败（环境，CI/Linux 无此问题）。
- 详细交接见 `deliverables/engineering-assurance/交接说明-2026-09-27.md`（含红线、可复现命令、踩坑表）。

## 项目级 skill（触发时读）
- `.agents/skills/project-context/` `.agents/skills/arch-rules/` `.agents/skills/test-gate/` `.agents/skills/debug-playbook/`
- 计划外脑：`plans/current.md` + `plans/decisions.md`
