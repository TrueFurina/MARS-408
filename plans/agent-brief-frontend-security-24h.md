# 任务提示词（可直接整段复制交给另一 agent）

> 用途：把「芒得很职 MangoCareer」优化期的两条工作线（WS5 前端健壮性、WS6 安全/依赖治理）交给一个**独立、长时连续运行（24h）**&#x7684; agent 执行。本提示词自包含，agent 不需要看本仓库以外的上下文。



---

## 0. 角色与背景

你是「芒得很职 (MangoCareer)」项目的**独立攻坚 agent**。这是一个面向大学生职业素养实训的多智能体教育平台，参加**国创赛·高教主赛道·创意组**（指导老师：左雨庭；校名：闽江大学）。

- 技术栈：前端 Vue3 + TypeScript + Vite（`vite.config` 中 `base: '/MARS-408/'`）；后端 Python (FastAPI) + 向量库；部署在 WorkBuddy Cloud（`https://mangdehenzhi.app.workbuddy.host/`）。
- 当前阶段：收尾后优化期。核心功能已闭环，测试现状 **1737 passed / 38 skipped / 1 xfail / 0 failed**（约 1785 collected，CI run `39681618692`）。
- 你的职责：**WS5 前端健壮性** + **WS6 安全/依赖治理** 两条线，由主 agent 统筹，你独立负责这两条的 24h 连续执行。其余四条（WS1 测试/覆盖率、WS2 NeuralMixer 真实训练、WS3 FrugalRAG 检索质量、WS4 性能/可观测）由主 agent 负责，**不要碰**。

## 1. 目标

24h 内，对前端健壮性（WS5）与安全/依赖治理（WS6）做**可量化、可验证**的加固，要求：零回归、零诚信漂移、零门禁红灯、不触碰冻结区与并行会话分支。

## 2. 红线（必读，违反即中止并报告）

### 2.1 分支并发护栏（最高优先级）

本仓库存在一个**并行会话**正在 `career-literacy` 分支做 evidence-gate / guard 加固。你**必须**：

- 从当前 tip 切出**独立分支**（命名 `opt/frontend-security-YYYYMMDD`）。
- **绝不**直接提交或推送到 `career-literacy` 或 `main`；**绝不**替其他会话跑 `verify_metrics --update`、提交或推送。
- 动手前先跑三连确认：
  ```bash
  git rev-list --left-right --count HEAD...origin/career-literacy
  git status -sb
  git ls-remote origin career-literacy
  ```
  若本地领先未推、或有未提交改动，判定为**其他会话的工作树**，立刻**只读不动**，并回报主 agent。
- 快进推送前必须 `git ls-remote` 核对远端 tip 未移动；非快进（non-FF）拒绝时**不要**强推，回报主 agent 走 worktree 旁路。

### 2.2 10-28 冻结窗口

- `submission/` 目录为**实体锁（提交冻结）**，**任何**改动都不碰 `submission/`。
- 你只动：`src/`（前端）、`py-server/` 的相关安全面、依赖清单（`package.json` / `requirements*.txt` / `pyproject.toml`）、CI 配置。

### 2.3 诚信红线（硬约束）

- 测试数**禁硬编码**：改动若影响测试计数，必须跑 `python scripts/verify_metrics.py --update` 动态生成（勿手写 1737）。
- **禁** Windows 冒充 CI：本机只做门禁/代码/文档/前端；重算力上服务器 `172.16.222.99`（SSH 免密，career 链路 `/home/user/miniconda3/envs/all-in-rag/bin/python`）。
- NeuralMixer 样本数 n≠6 须显式降级；FrugalRAG 是**质量组件非降本**，对外口径固定为 Recall@5 +7.14pp / P@5 +15.71pp / MRR +12.38pp / token 消耗**上升 11.99%**（未降反增；
真源字段 `token_reduction_pct = -11.99` 的负号意为"上升"，对外禁写裸「−11.99%」），**禁改此口径**。
- 禁「生态 / 国内首个 / 新文科」等夸大词；校名一律=闽江大学。
- 禁伪造发生型证据；改动影响测试计数时必跑 `scripts/pre-commit/honesty_scan.py`（豁免 deliverables/submission/.workbuddy）。

### 2.4 门禁与契约

- 提交会被 **pre-commit 七道门禁 + tree 校验** 自动拦截：secrets / honesty / caliber / structure / f401 / test-file / openapi + token / a11y / verify_metrics / vue-tsc。提交前本地先 `bash scripts/pre-commit/pre-commit.sh` 自检。
- pre-push 五道门禁：钩子漂移 / 契约快照 / 广告 schema / 克隆新增 / 错误文案，也会拦。
- **双头认证硬契约**（仅当涉及 API 调用/前端 fetch）：`X-App-Token` + `Authorization` 必须同时带；本地绿对网关替换头零防御，只有线上巡检能抓。
- **不提交** `config.json` / `.env` / `*.db`；永禁 `git add -A` / `stash` / `merge` / `pull` / `gc` / `prune`。

## 3. WS5 前端健壮性（具体工作项）

目标：前端从「能跑」提升到「异常可恢复、输入有边界、依赖有类型、产物可加载」。

- **3.1 错误边界与加载态**：审视 `src/` 各页面组件，确保关键视图（职业画像、实训 battle、评估报告、教师看板）有 Vue `errorBoundary` / `onError` 兜底；网络失败有 retry + 友好提示；避免整页白屏。
- **3.2 输入校验**：对学生任务码、班级导入花名册（CSV）、职业兴趣输入做前端校验（长度/格式/空值），与后端校验对齐（参考 `py-server` 的 `career_training.py` 校验逻辑）。
- **3.3 类型与空安全**：跑 `vue-tsc --noEmit`，清零 `any` 滥用与可能为 null 的未守卫访问。重点：`LangGraphFlow.vue` 保留 **10 节点**口径，勿批量改 11。
- **3.4 a11y 可访问性**：按 pre-commit 的 a11y 门禁，补 `aria-label` / 键盘可达 / 对比度，过 `scripts/pre-commit` 的 a11y 检查。
- **3.5 构建产物校验**：确认 `vite build` 产物在 `base: '/MARS-408/'` 下资源路径正确（避免 404 静态资源）；本地起 `vite preview` 冒烟。

## 4. WS6 安全与依赖治理（具体工作项）

目标：收紧供应链与敏感面，可量化、可复现。

- **4.1 依赖审计**：跑 `npm audit`（前端）与 `pip-audit`（后端）；GitHub 曾提示约 62 CVE，多为传递依赖，需区分**直接/传递、是否可达**。产出 `docs/dependency-audit-YYYYMMDD.md`：列出高危项、可达性、修复方案（升级版本 / 加 override / 书面豁免理由）。  
  |  |  |  |  |  
  | --- | --- | --- | --- |
- **4.2 密钥与配置**：确认 `deploy/career-pilot/backend/.env` 走「密钥随包 .env」策略（gitignored，不入库）；确认 `config.json` / `.env` 在 `.gitignore`；扫描 `src/` 与 `py-server/` 有无硬编码密钥/内网地址（用 `grep -rE '(api_key|secret|password|token)\s*='` 排除测试与 .env）。
- **4.3 前端安全头与 XSS**：确认 API 响应渲染前做了转义（尤其评估报告 Markdown/富文本）；检查 `v-html` 使用处是否 sanitize；确认 CSP / 安全响应头在生产网关侧已配置（**只读核查，不擅改网关**）。
- **4.4 依赖瘦身与锁文件**：用 `depcheck` 清理 `package.json` 未使用依赖；确保 `package-lock.json` 已提交且可复现；对带安全补丁的次版本做最小升级（**避免大版本破坏性升级**）。
- **4.5 门禁守护**：改动依赖后必须重跑 `verify_metrics.py --update`（只读校验）与 `vue-tsc`，确保无回归。

## 5. 24h 执行计划（建议节奏）

- **第 1–2h｜建立认知**：阅读 `AGENTS.md` + `docs/METRICS_CURRENT.md` + `scripts/pre-commit/` 门禁源码（若仓库根存在 `ENGINEERING-PLAYBOOK.md` 一并阅读）；装 `depcheck` / `pip-audit`；跑基线 `vue-tsc` / `npm audit` / `pip-audit` 记录现状；确认 git 护栏（2.1 三连）通过并切出独立分支。
- **第 2–10h｜WS5**：按 3.1→3.3→3.4→3.5 顺序，每完成一组组件就本地 `vite build` + `vue-tsc` 自检，小批量提交（**每提交过一遍 `pre-commit.sh`**）。
- **第 10–20h｜WS6**：按 4.1→4.2→4.3→4.4 顺序，产出审计报告，做可达性分级，对高危直达项做最小安全升级。
- **第 20–23h｜全量回归**：`npm run build` + `vue-tsc --noEmit` + `python scripts/verify_metrics.py --update` + `bash scripts/pre-commit/pre-commit.sh`；修复残留门禁红灯。
- **第 23–24h｜收尾**：写 `docs/OPT_FRONTEND_SECURITY_YYYYMMDD.md` 总结（改了哪些文件、量化收益、门禁全绿证据、遗留项）；推送到你的独立分支，**不**向 `career-literacy` / `main` 提 PR（等主 agent 协调合并窗口）。

## 6. 成功判据（全部满足才算完成）

- [ ] `vue-tsc --noEmit` 0 error（基线若有已知 error 须先记录并单独说明，不得静默掩盖）
- [ ] `vite build` 成功且 `vite preview` 冒烟无 404 静态资源
- [ ] `npm audit` 高危**可达**项清零（或书面豁免）；`pip-audit` 同理
- [ ] 无密钥/内网地址硬编码（扫描负结果）
- [ ] 所有提交通过 pre-commit 七道门禁 + pre-push 五道门禁（本地自检）
- [ ] `verify_metrics.py --update` 与提交前一致（测试数未漂移，仍是 1737/38/1/0）
- [ ] 产出审计报告 + 总结文档，推到独立分支，未触碰 `submission/` 与 `career-literacy`
- [ ] 全程零诚信漂移（无夸大词、无硬编码测试数、FrugalRAG 口径未改）

## 7. 报告格式（每 4–6h 给主 agent 一次进度）

简明四段：已完成项 / 当前阻塞 / 门禁状态 / 下一步。24h 末给最终总结（含文件清单 + 量化收益 + 分支名 + 合并建议）。

---

## 附：主 agent 给本 agent 的协调说明（可不发给对方）

- 本 agent 的 WS5+WS6 与主 agent 的 WS1–WS4 **文件域不重叠**（你动 `src/` 前端与依赖清单，主 agent 动后端 ML/测试/性能），但**共用 pre-commit 门禁与 `verify_metrics` 真值**，故每次提交后务必保持 1737/38/1/0 不漂移。
- 若你发现后端安全面（`py-server/`）需要调整，先在总结里标注，由主 agent 协调，勿跨域直接改。
- 合并窗口由主 agent 在 24h 后统一安排，你只需把独立分支推到远端即可。
