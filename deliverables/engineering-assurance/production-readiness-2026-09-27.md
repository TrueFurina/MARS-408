# 产品级就绪度评估 — 2026-09-27

- **分支 / HEAD**：`career-literacy @ 71f55bf`，工作树干净（WIP=0）
- **方式**：全部结论来自本次真跑的实测命令，未修改任何代码

---

## 结论：分场景 GO / NO-GO

| 场景 | 判定 | 理由 |
|---|---|---|
| **演示 / 答辩 / 评审**（单实例、可控路径、可复现） | ✅ **GO** | 前端构建绿、设计系统三门禁绿、部署件齐备（非 root + 健康检查 + 运维三文档）、安全红线 42 passed |
| **真实生产上线**（多用户并发、长期演进、团队协作） | ❌ **NO-GO** | 架构分层 M-1/M-2/M-3/M-5 已修、**M-4 第 1 条（main.py 拆分）已落地**（2026-09-27），但 M-4 ②③（user_store 拆域、seed_data 归位）未做、覆盖率 52% < 54% 门禁、测试存在顺序依赖污染 |

---

## 一、实测数据

### 前端（全绿）

| 项 | 命令 | 结果 |
|---|---|---|
| 类型检查 | `npx vue-tsc --noEmit` | EXIT=0 |
| 生产构建 | `npx vite build` | EXIT=0，8.58s |
| SSOT 漂移 | `python design-system/check_tokens.py` | 零漂移 |
| 组件裸值 | `python design-system/check_raw_values.py` | 零裸值 |
| 文档色值 | `python design-system/check_doc_tokens.py` | DOC IN SYNC |

### 后端（928 passed / 2 failed / 221 skipped）

```bash
cd py-server
env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE \
  .venv/Scripts/python.exe -m pytest \
  -m "not system and not requires_milvus and not slow" \
  --timeout=60 -q --basetemp=.pytest_tmp \
  --ignore=tests/test_review_shadow_probe.py -p no:randomly
# → 2 failed, 928 passed, 221 skipped, 1 xfailed in 909.89s (15:09)
# → 覆盖率 52.32%（门禁 54.0%）→ FAIL
```

- 安全红线：`pytest tests/test_safety_redline.py` → **42 passed**

### 部署件（就绪度好于预期）

- `Dockerfile:77-91`：非 root（gosu 切换）+ `HEALTHCHECK curl /api/status` + `uvicorn --workers 1`（契合 ADR-007 单写者约束）
- `docker-compose.yml`：app / milvus / redis 三服务
- 运维文档：`py-server/DEMO_GONOGO.md`、`DEMO_OBSERVABILITY.md`、`DEMO_RUNBOOK.md`
- `main.py:703 /api/status` 为**真实降级检测**（非硬编码 ok）；`main.py:797 /api/status/competition`

---

## 二、阻塞项（真实生产 NO-GO 的三条）

| # | 问题 | 位置 | 后果 |
|---|---|---|---|
| M-1 | API 层自建 SQLite 连接 + 独立 Lock | `api/literacy_assessment.py:10,123-147` | 第三个独立锁域；存储实现无法统一替换 |
| M-2 | ✅ **已修复** 运行中的 `api/*.py` 直连 `db.user_store` = 0（35 处改挂 `services/user_service.py`）；`db.*` 直连降至仅 `db/memory_store.py` 内部共享连接 | `api/*.py`→`services/user_service.py` | 业务规则重复实现风险收窄；替换存储现只需改 1 个 service 层 |
| M-3 | 下层反向依赖上层 6 处，靠函数内延迟导入规避 | `db/user_store.py:822,959,989,1014`；`db/graph_db.py:75,281`；`engines/review_policy.py:494` | 依赖环仍在，import 顺序一变即启动期 ImportError |
| M-5 | ✅ **已修复**（2026-09-27）SQLite 连接与锁全部由 `db/core.py` 按文件发放，`pg_fallback.db` 回退路径不再自建连接 | `py-server/db/pg_client.py:112-113`、`db/core.py`（新增 `close_conn_for`） | `connect()` 重复调用不再产生多连接 + 多把互不知情的锁写同一文件 |

> **备注（编号订正）**：M-4 的正题是**上帝文件集中**（`main.py` 882 行身兼 lifespan/限流/异常处理/路由注册等 4 职、`user_store.py` 1,281 行、 `seed_data.py` 1,527 行等），不是存储锁域；存储锁域是 **M-5**，已于本轮收敛。上一轮结论行把两者写反了，此处与 `architecture-review-2026-09-23.md` 一并订正。

**连带问题（已收敛）**：存储锁域曾分裂为 3 个——`netlearn_users.db` 走 `db/core.py` 单连接+RLock ✓；`pg_fallback.db` 走 `db/pg_client.py:103` 自建连接 ✗；`data/literacy.db` 走 API 层 ✗（M-1 已下沉）。
现在三者全部经 `db/core.py` 登记发放；「三库文件永不交叉、跨文件时互不互斥是正确行为」已写进 `db/core.py` 模块头，不再是未落代码的隐含约定。

---

## 三、质量缺口

### 🔴 测试存在顺序依赖污染（新发现）
`tests/test_video_feedback.py::TestVideoGeneration::test_generate_teaching_video` 与 `::test_generate_video_with_cache`：
- 全量跑 → **FAIL**
- 单独跑 → **9 passed + 2 xfailed**

符合「单跑 PASS、全量 FAIL = 模块顶层全局状态污染」特征。污染源**未定位**（复现一次需 15 分钟全量）。风险：CI 可能出现随机红。

### 🔴 本机全量回归跑不通（环境坑，非代码缺陷）
`tests/test_review_shadow_probe.py` 在 collection 阶段即崩：`OSError [WinError 1114] … torch/lib/c10.dll`（与既有 Windows torch SIGSEGV 同源），会让整轮 pytest `Interrupted: 1 error during collection`。
**必须 `--ignore` 该文件**；权威回归以 Linux/CI 为准。

### 🟠 覆盖率 52.32% < 54.0% 门禁
`shared/url_guard.py` 0%、`train_mixer*.py` 0%、`start_bg.py` 0% 拉低整体。

### 🟡 仓库卫生
未跟踪嵌套副本 `*/crypto_platform/py-server/**` = **188 文件 / 46,374 行**，无人引用，污染工具链信号（按红线未删，待确认后处置）。

---

## 四、已达标的项（不必再投入）

- 安全：无真实 SQL 注入（脚本 36 条告警经逐条核实为误报）、无凭据泄露、`.env` 未入库、PBKDF2-SHA256 600k、生产环境错误消息脱敏（`main.py:628-661`）、进程内滑动窗口限流
- 前端：零裸 `fetch`（数据入口统一在 `src/composables/`）
- 设计系统：三道自动化门禁 + 文档与令牌强同步
- CI：10 个 job，含 secret-scan、pip-audit、design-token-drift、benchmark-evidence-gate

---

## 五、最小修复包（建议顺序）

1. **M-1**（约 1h）：新建 `db/literacy_store.py`，复用 `db/core.py` 的连接与锁；删除 `api/literacy_assessment.py` 里的 `sqlite3`/`threading`/`_conn`/`_lock`。 — ✅ **已实施**
2. **M-3**（约 2h）：`review_scheduler` 四个纯函数下沉 `shared/`；`kg_dag` 下沉；删除全部延迟导入。 — ✅ **已实施**
3. **顺序依赖污染**（约 1h 定位）：先跑 `pytest tests/test_video_feedback.py <候选污染文件>` 二分，定位后加 fixture 隔离或 `autouse` 重置。 — ⏸ 未做
4. **M-2**（约 1 天）：抽 `services/user_service.py` 收敛 35 处 `db.user_store` 直连（可迭代推进，不必一次做完）。 — ✅ **已实施**

---

## 六、M-1 / M-3 实施记录（2026-09-27 同日晚）

### M-1：接口层不再持有存储实现
- 新增 `py-server/db/literacy_store.py`：对外只暴露 `save_attempt` / `get_user_attempts` / `get_class_attempts`，SQL 全部收归此处。
- `db/core.py` **加法改动**：新增 `get_conn_for(db_path, init=None)` 与 `get_lock_for(db_path)` 两张登记表（按 DB 文件维度），`get_conn()` 行为不变（仍走 `_conn` 单例 + WAL）。
  - 关键澄清：锁是**按文件隔离**的。`literacy.db` / `netlearn_users.db` / `pg_fallback.db` 本就是三个文件，跨文件无需互斥；被消除的是「同一文件被两个连接 + 两把锁同时写」的风险来源。
- `api/literacy_assessment.py`：删除 `sqlite3` / `threading` / `_conn` / `_lock` / `_init_schema`，保留 `NETLEARN_LITERACY_DB` 惰性解析。
- `tests/test_literacy_uid_resolution.py`：mock 目标从 `api.literacy_assessment._get_conn` 改为 `db.literacy_store._get_conn`（语义不变）。

### M-3：反向依赖清零（实测 `db → engines/agents` 与 `engines → agents` 均为 0）

| 被反向引用的实现 | 新位置 | 原路径 |
|---|---|---|
| `review_scheduler`（纯函数，唯一消费方 `db/user_store`） | `shared/review_scheduler.py` | `engines/review_scheduler.py` 转委托导出 |
| `review_signals` / `weighted_consistency_score` / `_normalize_review_weights` / `UNIFORM_REVIEW_W` | `engines/review_policy.py` | `agents/quality_gate.py` 转委托导出（解除 agents ↔ engines 双向循环） |
| `kg_dag`（纯数据表 + 纯函数，131 行仅依赖 typing） | `shared/kg_dag.py` | `agents/kg_dag.py` 转委托导出 |
| `search_kg_entities` + `_KG_DIR` | `shared/kg_search.py` | `agents/knowledge_graph.py` 转委托导出 |
| `CATFISH_MAX_CONTINUE` | `shared/career_consts.py` | `agents/career_state.py` 转委托导出 |

**委托（delegation）而非复制**：所有原路径保留同名再导出，20+ 实验/测试脚本的既有 import 不受影响；每次改动后用 `is` 断言验证同一性（如 `agents.quality_gate.review_signals is engines.review_policy.review_signals` → True）。这与项目既有的「单一真值源 + 其余位置只做委托」纪律一致（`test_review_single_source` 守护）。

### M-5：存储锁域统一（SQLite 连接/锁 100% 由 db/core.py 发放）

**为什么这是真 bug 而不是洁癖**：`pg_client.connect()` 的 SQLite 回退分支原本每次被调都新建一套连接与锁，而调用方不止一个——`db/__init__.py:13`、`db/ability_store.py:54`、`db/career_store.py:172`、`seed_demo_data.py:146`，其中后三者是「未连接就 connect」，实跑路径下会重复进入该分支。

- 修复：`connect()` 回退分支改用 `get_lock_for(_FALLBACK_DB)` + `get_conn_for(_FALLBACK_DB, init=self._init_schema_sqlite)`；`db/core.py` 新增 `close_conn_for(db_path)` 供 `disconnect()` 注销共享连接（否则注册表会把已关闭的连接继续发还）；`_init_schema_sqlite` 支持 `conn` 入参（init 回调执行时机早于 `self._conn` 赋值）。
- 边界约定入代码：`db/core.py` 模块头新增库文件归属表（netlearn_users.db / literacy.db / pg_fallback.db）+「任何 SQLite 连接必须经 `get_conn_for`」硬约束。
- 合规访问器：`pg_client.sqlite_query_one()` / `sqlite_execute()` 收口 `db/ability_store.py` 的 4 处 `pg_client._lock/_conn` 越级访问。

**机验**：`cd py-server && python scripts/verify_core_lock_unification.py` → 14 项全 PASS（同连接/同锁、与 core 注册表同一对象、8×50 并发写零异常且 400 行全落库、disconnect 后可重连）。
**变异验证**：回退为 `sqlite3.connect` 后立即 5 项 FAIL + `OperationalError`，证明该检查非空跑。

### M-4 ①：main.py 从 882 行收敛到 78 行纯组装层（2026-09-27）

- 拆出 `app/` 包：`env.py`（环境引导）/ `lifespan.py`（生命周期，最大块 300 行）/ `middleware.py`（6 个中间件 + CORS）/ `errors.py`（4 类 handler）/ `routers.py`（42 个业务 router）/ `status.py`（3 个运维端点）/ `static_sites.py`（plots/media + SPA 挂载）。
- **公开契约零断裂**：`main.app` / `main.lifespan` / `main._seed_vector_db` / `main.competition_status` 委托重导出，35 处 `from main import ...` 无需改动。
- **机验 30 项全 PASS**：`python scripts/verify_app_wiring.py` —— 含 `ALL_ROUTERS` 与拆分前逐项逐序 AST 比对、252 条路由、4 类异常处理器、7 个安全头、413 / 429 行为。**变异验证**：注释掉 `middleware.install(app)` 一行即 9 项 FAIL（安全头全丢），证明能抓住「少装中间件」这一静默失败模式。
- **回归**：`test_wave_a_security` + `test_wave_b_security` + `test_wave_b_sre` + `test_api_contract_comprehensive` + `test_literacy_assessment` + `test_config_observability` + `test_api_consistency` = **184 passed**。

### M-4 附带修复：services/user_service 改为动态委托门面（修掉一处 M-2 埋下的雷）

M-2 收敛出的 `services/user_service.py` 原本用静态 `from db.user_store import x` 重导出 —— 这会在 service 层绑定一份**函数对象快照**，此后任何针对 `db.user_store` 的 monkeypatch / 打桩都**静默失效**：测试以为在验证降级路径，实际走的仍是真实连接。
实锤：`test_competition_status_warns_on_db_error` 在 M-2 后变为 FAIL（`user_count=125` 而非降级后的 0）。
已改为 PEP 562 `__getattr__` 动态穿透（`DELEGATED_NAMES` 显式白名单、私有符号照旧拒绝、`__all__` 由白名单生成以避免 ruff F822 假报警——**未使用 noqa 压制**）。修复后上述用例 PASS。

### M-2：API 层越级访问存储收敛到 services 层（实测 `api/*.py` 直连 `db.user_store` = 0）

- 新增 `py-server/services/user_service.py`：显式重导出 `db.user_store` 全部 38 个公共函数 + 2 个新增合规访问器，配 `__all__`（ruff F401 不误报）。这是 `API → services → db` 正确分层的用户域入口。
- API 层 35 处 `from db.user_store import ...`（含 `main.py` / `seed_demo_data.py`）全部改挂 `services.user_service`；运行中的 `api/*.py` 现已零 `db.user_store` 直连（仅 `db/memory_store.py` 保留内部共享连接调用，属 M-5 单连接设计）。
- 消除最严重越级：`daily_plan.reset_plan` 原 `from db.user_store import _get_conn, _lock, _now` + 裸 UPDATE → 改调 `db.user_store.reset_daily_plan(pid, user_id)`；`wrong_questions` 两处 `SELECT user_id` 所有权校验（裸 `_get_conn/_lock`）→ 改调 `get_wrong_question_owner(qid)`。两访问器在 `db` 层 `_lock` 内完成，API 不再触达存储锁。
- `db/user_store.py` 仅**加法**：新增 `get_wrong_question_owner` / `reset_daily_plan` 两个函数，未删任何既有符号；tests 仍直连 `db.user_store`，不受影响。
- 顺带修复本次纳入门禁扫描暴露的 4 个既有 F841 死变量（`assessment.py:profile` / `profile.py:provider` 保留 `_resolve()` 副作用 / `quiz.py:llm_updated` / `quiz.py:analysis` 保留 `error_analyzer.analyze` 调用）。
