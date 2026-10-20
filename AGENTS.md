# AGENTS.md — study-help-pro 项目事实源

> 权威真值详见 CLAUDE.md（双分支双身份说明）与 .agents/skills/ 四件套；本文件是每会话最小事实卡。

## 这是什么
双分支双身份共用底座：`main` 分支 = 芒得很职（408 考研学习平台）；`career-literacy` 分支（当前）= 芒得很职（软素养对抗实训平台），新代码一律 `career_*` 前缀零侵入 408。

## 命令
- 后端: `cd py-server && pip install -e . && python main.py`（:8002）
- 测试: `cd py-server && env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE .venv/Scripts/python.exe -m pytest tests/ -q --basetemp=.pytest_tmp --no-cov -p no:cacheprovider --continue-on-collection-errors`
  - 2026-10-20 CI 权威真值（run `39467891052`，head `22a7469`，Backend Test Linux 默认档）：**1693 passed / 38 skipped / 1 xfailed / 0 failed**（约 1741 collected = 1693+38+1+9，`addopts` deselect 9，384.74s；旧「1654/38/1（10-18 run 39101268904 @ 3bae4b9）」「1524/38/1（10-17）」「1389/38/1（10-09）」作废——1654→1693 增量来自教师端看板口径 + 错误文案分类（M01）+ 四组运行时契约测试）。注：本机 Windows 因 torch `c10.dll` SIGSEGV 会丢失部分用例，CI/Linux 全量为准；10-06 快照「1178 passed / 208 skipped」为标记剖面错位，非当前真值。
  - 前两个 `env -u` 是必需的：WorkBuddy shell 的注入会污染 pytest 子进程；`--continue-on-collection-errors` 用于跳过 torch c10.dll 的本机环境错误。
- E5 模型恢复: `python scripts/fetch_e5_model.py`（模型不入库，会话重置后执行）
- 机验（改动结构后跑）: `py-server/scripts/verify_{app_wiring,auth_coverage,core_lock_unification,kb_coverage,seed_data_split,user_store_split}.py`（轻量，CI 由 `.github/workflows/verify-structural.yml` 自动跑）；`verify_{gold_candidates,retrieval}.py` 依赖 Milvus+KB，仅手动 dispatch 触发；品牌/口径扫描 `scripts/brand_scan.py` + `scripts/scan_stale_calibration.py` 亦由该 workflow 接管。

## 禁区
- 分支同步方向唯一：main → career-literacy，禁止反向
- 竞赛口径数字必须对齐代码真值；E5 模型文件不入库
- 永禁 `git add -A`（junction 会导致把未删文件误记为删除）；永禁 `git stash/merge/pull/gc/prune`
- ~~`*/crypto_platform/py-server/**`（188 文件嵌套副本）未经用户确认不得移动或删除~~ → **已于 2026-10-05 经用户授权全量删除**（10 处 / 189 文件，核实 0 被 git 跟踪、0 代码引用、内容已漂移）。如再发现同类嵌套副本，先跑引用检查再处置
- 品牌统一「芒得很职」：产品可见层（`src/`、`public/`、`index.html`、py-server 代码）禁出现旧品牌名与旧赛事名；机检 `npm run gate:brand`（历史文档/交付快照/冻结副本除外）
- 🔒 **品牌例外（已裁决·永久保留，勿再当作待办重提）**：① GitHub 仓 URL 里的 `MARS-408`（**真实仓库名**，改成别的会直接弄坏克隆命令）；② `vite.config.ts` 的 `base: '/MARS-408/app/'`（与 GitHub Pages 部署路径绑定）。二者以外的对外文案一律用「芒得很职」。
- 提交时必须逐文件显式 `git add`，且 add 后先看 `git status`（暂存为空时密钥扫描会退化成全仓扫描并误报）

## 当前状态（2026-09-27 架构评审收口，接手前先读）
- 架构评审 M-1~M-5 全部修复并机验；全项目结构已落定：
  `py-server/app/`（装配层，main.py 只剩 85 行组装）、`py-server/seed/`（408 四科语料包，`seed_data.py` 变 38 行委托层）、`db/profile_store.py`（画像域）。
- **兼容层是"动态委托"（PEP 562 `__getattr__`），不是静态重导出** —— 改成静态会让打桩监控失效。改前读文件头注释。
- **覆盖率门禁 = `--cov-fail-under=50`**（CI 真值，见 `ci.yml:191` / `p0-regression.yml:65`；旧「54 门禁」作废）。本机实测 **57.19%**（过 50 门禁，但属本机值非 CI 全量口径，对外引用前需重测；该值为 2026-10-16 qa-2 fresh 重测，较旧 53.31% 因新增测试推高覆盖）。补测加了 9 个测试文件
  （SSRF 守卫 / 页码对齐算法 / lifespan 守门 / 中间件矩阵 / 画像域契约 / DI 容器 / 内容安全 / SPA 挂载 / JWT 角色），
  并修复 1 个随 M-4 拆分失效的静态锚点测试。
- ⚠️ **改动 `src/` 或 `py-server/` 代码后必须补跑 `python scripts/verify_metrics.py`**（不一致时用脚本 sanctioned 的 `--update` 重生成，**禁止手改表格**）。它是 CI `.github/workflows/verify-structural.yml:89` 的**阻断性**检查，而**本地 pre-commit 七道门禁不跑它** ⇒「家里全绿、CI 红」是常态失效形态（2026-10-13 实测：`a711ed7`+`36f08ed` 后三项漂移未被察觉）。
- **当前无阻塞项**（须每轮实测重确认，**勿当恒定真值**）：全量 **1693 passed / 38 skipped / 1 xfailed / 0 failed**（约 1741 collected，`addopts` deselect 9；2026-10-20 CI 默认档 run 39467891052 @ 22a7469 权威值）；唯一 error 是本机 torch `c10.dll` 加载失败（环境，CI/Linux 无此问题）。
- ⚠️ **节点数两种口径（勿互相"修正"，改任一个都是错的）**：10 = Triage 之外的流水线本体；11 = 编译图业务节点数（10 + `triage` 节点）。对外述"图"用 11，述"Triage 之后的流水线"用 10。内部可视化组件 `LangGraphFlow.vue` 只画 10 个，**是对的，不要批量改 11**。
- 🔒 **`/api/agents/runtime` 判定为"不实现"（已裁决，勿再当缺口重提）**：本仓库**没有 per-agent 运行时状态源**（LangGraph 流事件是瞬时的、无持久化），造一个就等于编造数据，违反诚信红线；真实引擎/向量库/模型状态走 `GET /api/status`。前端 `DashboardView.vue` 已诚实降级（注释写明"待后端提供后再接入"），不渲染任何运行时状态。
- 详细交接见 `deliverables/engineering-assurance/交接说明-2026-09-27.md`（含红线、可复现命令、踩坑表）。

## 快照版本与合作纪律（2026-10-20，REA #89/#90/#91）

**本文件是快照，不是实时真值。** 下面每类数字/结论都标注了 as-of 日期，引用前按顺序
核对；对不上时以**命令输出**为准，改文档而不是改命令。

| 内容 | 权威来源 | 核对方式 |
|---|---|---|
| 测试通过数 / 覆盖率 | CI 最近一次默认档 run | `make doctor --full` 或 CI run 页 |
| 后端代码行数 / 路径数 | `scripts/verify_metrics.py` 实测 | `python scripts/verify_metrics.py`（不一致禁止手改，用 `--update`） |
| 安全机制是否在位 | 代码 + 独立审计报告 | `deliverables/engineering-assurance/security-claims-audit-2026-10-19.md` |
| 分支/工作区/端口状态 | `scripts/doctor.mjs` | `make doctor`（JSON：`node scripts/doctor.mjs --json`） |

**doctor 不是仪式**：它输出带 `head` 与 `ran_at`（执行基线），判据是**当时那个提交**的
状态。看到 `head` 与你要引用的版本不一致，等价于"没跑过"——重跑，不要沿用旧结论。

**多会话协作字段**（同日多会话并发改同一仓时，先在 `plans/current.md` 顶部登记一行）：

```
- [会话] <会话标识> | 分支 <branch> | 占用 <文件/目录列表> | 开始 <HH:MM> | 退出条件 <可判定的完成态>
```

三条硬规则：
1. **只提交自己占用的文件**——`git add` 逐文件显式列出，永不 `git add -A`。
2. **别人占用的文件不"顺手格式化"**：行尾/缩进改动会让对方的 diff 变成噪音，也会
   让 `git status` 常驻脏文件（本项目已因 `core.autocrlf` 踩过）。
3. **收尾必须撤销登记**；未撤销的占用视为仍在使用，后续会话不得抢占。

## 项目级 skill（触发时读）
- `.agents/skills/project-context/` `.agents/skills/arch-rules/` `.agents/skills/test-gate/` `.agents/skills/debug-playbook/`
- 计划外脑：`plans/current.md` + `plans/decisions.md`
