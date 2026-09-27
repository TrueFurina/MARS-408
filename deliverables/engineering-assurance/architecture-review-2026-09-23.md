# 系统架构审查报告

- **审查目标**：`E:\Program\MARL\study-help-pro`（全仓，后端 `py-server/` 为主）
- **审查范围**：全量静态审查（非 diff）；只读，未修改任何代码、未提交
- **分支 / HEAD**：`career-literacy` @ `7b6b3b0`
- **技术栈**：Vue 3 + TypeScript + Vite（前端）／ Python 3.13 + FastAPI + LangGraph + PyTorch(CPU) + SQLite/PostgreSQL + Milvus（后端）
- **总体评分**：**6.5 / 10**
- **结论**：⚠️ 可继续开发；**M-1 / M-2 / M-3 / M-5 已于 2026-09-27 修复**，M-4 的**第 1 条（main.py 拆分）已落地**、第 2/3 条（`user_store` 拆域、`seed_data` 归位）待处理

> 编号订正（2026-09-27）：上一轮维护结论行时误把「存储锁域三分裂」写成 M-4、「main.py 职责过载」写成 M-5，
> 与本报告正文编号相反。正文为准：**M-4 = 上帝文件集中**（含 main.py 拆分建议），**M-5 = 并发写保护只覆盖 2/3 存储域**。

---

## 一、架构全景

### 分层与规模（已排除 `crypto_platform` 副本）

| 层 | 目录 | 文件 | 行数 | 职责 |
|---|---|---|---|---|
| 前端 | `src/` | 45 views / 41 组件 | — | 54 路由，数据入口统一在 `src/composables/` |
| 接口 | `py-server/api/` | 44 | 20,870 | 237 个 HTTP 端点 |
| 编排 | `py-server/agents/` | 55 | 11,662 | LangGraph **11 节点** 多智能体 |
| 算法 | `py-server/engines/` | 44 | 17,439 | FrugalRAG / GOMARL / MAPPO / 复习调度 |
| 服务 | `py-server/services/` | 19 | 5,614 | 导入队列、记忆、TTS、视频 |
| 存储 | `py-server/db/` | 33 | 14,637 | SQLite / PG / Milvus / 讯飞 |
| 横切 | `py-server/shared/` | 34 | 3,247 | 限流、审计、DI、SSE 守卫、熔断 |
| 测试 | `py-server/tests/` | 128 | 26,861 | 测试/生产 ≈ 0.67 |

- 生产代码合计 **40,171 行**（不含 `experiments/`、`tools/`、`scripts/`）
- CI：`.github/workflows/` 3 个文件，`ci.yml` 含 **10 个 job**（secret-scan、pip-audit、design-token-drift、benchmark-evidence-gate 等）

### 主数据流

```
Vue 组件 → composables(useXxx) → /api/* (44 模块, 237 端点)
   → [可选] services/* (导入队列/记忆)
   → agents/* (LangGraph 11 节点: triage→coordinator→diagnostician→planner→retriever
        →generator_cluster→assessor→critic→evidence_check→quality_gate→path_planner)
   → engines/* (FrugalRAG 检索 / GOMARL 共识 / 复习调度)
   → db/* (SQLite netlearn_users.db / PG(回落 SQLite) / Milvus 向量库)
```

---

## 二、风险摘要

最大风险不是单点 bug，而是**分层被逐步侵蚀**：API 层（20.9k 行）吞掉了本应属于 service 层的业务逻辑，其中 27/44 个模块直接访问 `db.*`，甚至有 1 个模块（`api/literacy_assessment.py`）在接口层自建 SQLite 连接与锁；同时下层 `db/`、`engines/` 反向 import 上层（6 处），靠函数内延迟导入规避循环依赖。这导致**存储锁域分裂为 3 个**、替换存储实现与做并发压测都缺乏统一入口。好消息是**未发现真实 SQL 注入、未发现真实凭据泄露**（脚本报的 45 条 Critical 经逐条核实为误报，见第五节），且前端零裸 `fetch`、`.env` 未入库。

---

## 三、关键问题（Major）

### [M-1] API 层自建 SQLite 存储，绕过 db 层 — 🟠 Major

- **位置**：`py-server/api/literacy_assessment.py:10, 123-147`
- **问题**：接口层直接 `import sqlite3`、`sqlite3.connect(db_path)`、自建 `_conn` 单例与 `_lock = threading.Lock()`。这使 `data/literacy.db` 成为**第三个独立锁域**，与 `db/core.py` 的统一连接+RLock 体系完全隔离；一旦该库与其它库同文件/跨 store 协作，将重演 `db/core.py` 头部注释记录的「两连接 + 两把不互斥的锁写同文件 → database is locked / WAL 损坏」。同时存储实现无法统一替换（换 PG 时需改接口层）。
- **修复建议**：下沉为 `db/literacy_store.py`，复用 `db/core.py` 的连接与锁：

```python
# db/literacy_store.py
from db.core import get_conn as _core_get_conn, LOCK as _lock

def _get_conn() -> sqlite3.Connection:
    conn = _core_get_conn()
    _ensure_schema(conn)   # 幂等建表
    return conn
```
接口层只调用 `db.literacy_store.*`，删除 `api/literacy_assessment.py` 中的 `sqlite3`/`threading`/`_conn`/`_lock`。

### [M-2] services 层被架空，业务逻辑沉积在 API 层 — ✅ 已修复（2026-09-27，🟢 收敛）

- **位置**：`py-server/api/*.py`（44 个模块）
- **问题（评审时）**：44 个 api 模块中 **27 个直接 `import db.*`**（其中 `db.user_store` 被 import **35 次**），仅 14 个走 `services.*`。API 层 20,870 行 vs services 层 5,614 行——比例失衡是「业务逻辑下沉失败」的量化证据。后果：同一业务规则在多端点重复实现；无法对业务做单测（必须起 HTTP）；替换存储/加缓存要改 27 个文件。
- **修复建议**：按领域收敛，先抽最高频的两个：
  1. 用户域 → `services/user_service.py`（收敛 `db.user_store` 的 35 处直连）
  2. 职业素养域 → 已有 `services/career_service.py`，把 `api/career_training.py`、`api/literacy_assessment.py` 中的存储调用迁入
接口层只做：参数校验 → 调 service → 组装响应。

**✅ 修复记录（2026-09-27）**：新建 `py-server/services/user_service.py` 作为用户域 service 入口，显式重导出 `db.user_store` 全部公共函数（配 `__all__`）；API 层 35 处 `from db.user_store import ...` 全部改挂 `services.user_service`（含 `main.py` / `seed_demo_data.py`）。3 处越级拿原始锁/连接的站点改用合规访问器——`daily_plan.reset_plan` 改调 `db.user_store.reset_daily_plan(pid, user_id)`，`wrong_questions` 两处所有权校验改调 `get_wrong_question_owner(qid)`（在 `_lock` 内完成，消除 `_get_conn/_lock/_now` 越级）。`db/user_store.py` 仅新增 2 个函数，未删任何既有符号，tests 仍直连 `db.user_store` 不受影响。

### [M-3] 反向依赖（下层 import 上层），循环依赖仅被"绕过"未消除 — 🟠 Major

- **位置**：
  - `py-server/db/user_store.py:822, 959, 989, 1014` → `engines.review_scheduler`
  - `py-server/db/graph_db.py:75, 281` → `agents.kg_dag`
  - `py-server/engines/review_policy.py:494` → `agents.quality_gate`（注释原文：`# 延迟导入，避免与 agents 循环`）
  - 另有 `engines/career_policy.py:512`、`engines/frugal_rag.py:288` 同类延迟导入
- **问题**：存储层/算法层反向依赖编排层，方向违反分层；延迟导入只是把 import 时机推后，**依赖环仍然存在**。任何一次 import 顺序调整、或新增一条 `agents → engines` 的正向引用，都可能让环闭合而导致启动期 ImportError。
- **修复建议**：把被反向引用的纯函数下沉到中立层：
  - `review_scheduler` 的 `compute_initial_review / schedule_after_review / is_due / _coerce_dt` → 迁 `shared/review_time.py`（无状态、无依赖）
  - `quality_gate.review_signals / weighted_consistency_score` → 迁 `engines/review_policy.py` 内部或 `shared/review_signals.py`
  - `kg_dag.GROUP_PREREQS` 等常量 → 迁 `db/kg_prereqs.py` 或 `shared/kg_consts.py`
  迁移后删除全部函数内延迟导入。

### [M-4] 上帝文件集中，单点认知负荷过高 — ✅ 已修复（2026-09-27，三条建议全部落地）

- **位置**：
  - `py-server/seed_data.py` 1,527 行
  - `py-server/db/user_store.py` 1,281 行
  - `py-server/api/chat.py` 1,187 行
  - `py-server/db/skill_store.py` 1,148 行
  - `py-server/engines/review_policy.py` 1,001 行
  - `py-server/main.py` 880 行（同时承担 lifespan、限流中间件、4 类异常处理器、路由注册）
- **问题**：`main.py` 混合了 4 种职责，任何一处改动都触碰应用入口；`user_store.py` 单一文件同时负责用户、画像、答题历史、复习调度回调。
**✅ 修复记录（2026-09-27）：建议 ①（main.py 拆分）已落地，882 行 → 78 行组装层。**

| 新位置 | 职责 | 行数（实测） |
| --- | --- | --- |
| `app/env.py` | 进程级环境引导（HF 离线标记 / .env / 结构化日志）+ `is_production()` | 55 |
| `app/lifespan.py` | 启动关闭编排：密钥校验 → 向量库 → PG/Redis/Admin 并行 → 迁移 → demo seed → LLM 凭证 → worker 守卫 → 清理任务 | 338 |
| `app/middleware.py` | CORS / GZip / 指标 / 安全头 / 请求体限制 / 限流 | 261 |
| `app/status.py` | `/api/status`、`/api/status/competition`、`/metrics` | 158 |
| `app/routers.py` | 42 个业务 router 汇总到 `/api` 前缀 | 102 |
| `app/static_sites.py` | plots / media 挂载 + 前端 SPA 挂载 | 74 |
| `app/errors.py` | 4 类异常处理器注册 | 59 |
| `app/__init__.py` | 包说明（刻意无副作用导入） | 22 |
| `main.py` | 只做组装（7 步，顺序约束写进注释） | **85**（原 882） |

行数复现命令：`cd py-server && wc -l main.py app/*.py`（拆分后总量 1,154 行，多于原 882 ——
增量全部来自**职责说明注释与顺序约束注解**，非新业务逻辑；入口认知负荷从"读 882 行才能改一行中间件"
降到"读 85 行定位到对应职责模块"）。

- **公开契约不断**：`main.app` / `main.lifespan` / `main._seed_vector_db` / `main.competition_status` 全部委托重导出（35 处 `from main import ...` 的既有测试与脚本无需改动），由 `scripts/verify_app_wiring.py` 用 `is` 断言守护。
- **顺序约束显式化**：中间件 / 静态挂载 / 路由 / SPA 的注册顺序 = Starlette 包装顺序，已写进 `main.py` 与各模块头注释。
- **顺带修一处 M-2 遗留缺陷（重要）**：`services/user_service.py` 原先是**静态 `from db.user_store import x` 的重导出**，会在 service 层绑定一份快照 —— 任何对 `db.user_store` 的 monkeypatch / 打桩都**静默失效**（表现：patch 了 DB 故障，走的却是真实连接，降级分支永远测不到）。已改为 **PEP 562 动态委托门面**（`__getattr__` 穿透到真值源、`DELEGATED_NAMES` 显式白名单、私有符号仍拒绝）。实锤：`test_competition_status_warns_on_db_error` 由 FAIL 转 PASS（修前 `user_count=125` 而非 0）。
- **顺带修一处 CORS 静态复查**：`tests/test_wave_a_security.py::TestCORSStaticReview` 原先静态扫 `main.py` 文本，拆分后会失效；已改为扫 `app/middleware.py`（新真值源）并对 `main.py` 兼容回退，使两次提交各自的 CI 都是绿的。

**机验**：`cd py-server && python scripts/verify_app_wiring.py` → 30 项断言全 PASS。
覆盖：`ALL_ROUTERS` 与拆分前 `_all_routers` **逐项逐序一致**（AST 比对基线提交 `f36b83e`）、252 条路由、4 类异常处理器、7 个安全头（含 WASI 依赖的 COOP/COEP）、请求体超限 413、限流器 429 + Retry-After、4 个公开符号的 `is` 同一性。
**变异验证**：仅注释 `middleware.install(app)` 一行，9 项断言立即 FAIL（安全头全丢、413 变 405、429 变 404）——证明这组检查真能抓住「少装一个中间件」这一最危险的静默失败。

**✅ 修复记录（2026-09-27）：建议 ①②③ 全部落地。**

**① main.py 拆分已落地（详见上文表格）。**

**③ seed_data.py（1,527 行）已按科目拆域，但落点不是 `scripts/` —— 原建议的前提经实测不成立。**

- **订正**：评审写的是「归入 `scripts/`（非运行时依赖）」。实测它有 **7 个运行时消费方**：
  `api/knowledge.py`（2 处）、`api/learning_path.py`、`api/rag.py`、`api/subjects.py`、`api/teacher.py`、
  `engines/frugal_rag_sft.py`、`app/lifespan.py`（启动期写种子语料），另加 4 个实验/脚本与 3 个测试。
  它既不是「非运行时」，也含**必须留存的派生逻辑**（408 四科 group 偏移对齐）。硬塞进一次性脚本目录
  会迫使运行时依赖去 hack `sys.path`，是净劣化。
- **实际拆法**：新建 `py-server/seed/` 包，按科目切分（数据段**二进制原样搬运**，杜绝手抄）：

| 位置 | 内容 | 行数 |
| --- | --- | --- |
| `seed/net.py` | 计网语料 + `SEED_SUBJECTS` + NET 基础 `KNOWLEDGE_GRAPH` / `LEARNING_PATH_DAG` | 593 |
| `seed/ds.py` | 数据结构段 | 226 |
| `seed/co.py` | 计组段 | 147 |
| `seed/os.py` | 操作系统段 | 143 |
| `seed/__init__.py` | 各科 EXTRA 试题 `.extend(...)` + `seed_data_expanded` import + group 偏移与自动 KG 派生 | 501 |
| `seed_data.py` | 只剩兼容委托层（38 行，原 1,527） | 38 |

- **两个必须写下来的坑**：
  1. 原文件的 `extras` 段（1098-1249）**不是纯数据**，而是 `SEED_KNOWLEDGE_CHUNKS.extend(...)` 这类
     **执行语句**，一旦拆成独立子模块就 `NameError` —— 该段只能留在 `__init__`。
  2. 文件内存在**同名重复定义**（`CO_SEED_KNOWLEDGE_CHUNKS` / `OS_SEED_KNOWLEDGE_CHUNKS` 各有两版、
     后者覆盖前者），因此 `net → ds → co → os` 的 import 顺序是硬约束，已写进模块头注释。
- **兼容层用动态委托**（PEP 562 `__getattr__`）：沿用 M-2 的教训，静态星号导入会绑定对象快照，
  令对 `seed` 包内符号的替换静默失效；现在 `seed_data.X is seed.X` 恒成立。

**机验**：`cd py-server && python scripts/verify_seed_data_split.py` → 12 项全 PASS。
覆盖：33 个公共符号与**拆分前冻结的基线快照**逐一对账（repr sha256 + 类型 + 长度）、委托层同一性、
KG 643 节点/639 边、group 覆盖 1-26、chunks 1892 / questions 230 / 27 个方向、未登记符号按 AttributeError 拒绝。
**变异验证（静默型）**：把 `from seed.co import *` 提前到 `net` 之前（让 v1 残留覆盖最终版）→
`CO_SEED_KNOWLEDGE_CHUNKS` 27→20、语料 1892→1885，**但 KG 节点数、group 覆盖、试题数全部不变** ——
粗粒度断言完全发现不了，只有逐符号差分能抓到。这正是本次必须冻结基线快照的原因。

**② db/user_store.py（1,330 行）拆出 db/profile_store.py（画像域）— 已落地。**

| 位置 | 职责 | 行数 |
| --- | --- | --- |
| `db/user_store.py` | 账户 / 作业 / 学习资源 / 错题复习 / 每日计划 | 1,232（原 1,330） |
| `db/profile_store.py` | 画像 + 答题历史 + 会话 + 画像快照（4 张表、8 个函数） | 224 |

- **为什么用 `__getattr__` 动态委托而不是显式 import**：显式 `from db.profile_store import x`
  会①在本模块绑定对象快照，令对 profile_store 的 monkeypatch 静默失效（M-2 在
  `services/user_service` 踩过同款），②只用得到 `get_profile` 却要 import 8 个符号 → 命中
  ruff F401，而本项目明确不用 noqa 压制。动态转发同时解决两点，且既有 20+ 处
  `from db.user_store import get_profile` 照常可用。
- **无循环依赖**：`profile_store` 只依赖 `db.core`（同一连接、同一把锁，符合 M-5 的边界约定），
  **不** import `user_store`；机验断言 `import db.profile_store` 不会拉起 `db.user_store`。
- **建表幂等**：profile 域的 4 张表由 `profile_store._init_schema` 用 `CREATE TABLE IF NOT EXISTS`
  自建，`user_store._init_schema` 仍建全库表，两边重复执行无副作用 —— 机验覆盖了
  "profile_store 单独使用即可建表并读写"。

**机验**：`cd py-server && python scripts/verify_user_store_split.py` → 11 项全 PASS。
核心是**行为差分**：拆分前用 `scripts/user_store_behavior_probe.py` 在临时库上跑 42 步固定调用序列
（账户 / 画像 / 错题复习 / 每日计划 / 资源 / 作业全覆盖，含 `list_all_users` 内部回调 `get_profile`
这条最易断的链），冻结为 `scripts/user_store_baseline_probe.json`；拆分后重跑逐键对账，
**42 步零差异**。
**为什么不用符号 repr 快照**（seed/ 那次的做法）：user_store 的符号绝大多数是**函数**，
`repr(func)` 含内存地址，搬运后必然不同，会淹没真差异 —— 函数要证的是行为不变。
**变异验证（静默型）**：把 `get_profile` 的返回改成 `{}` → 差分立即 FAIL 于 `get_profile` 与
"独立建表读写"两项。
另查三项只看代码看不出来的：委托动态性（patch 后跟随）、无循环依赖、公共符号集合与拆分前一致。

至此 M-4 三条建议全部落地，`main.py` / `seed_data.py` / `user_store.py` 三个上帝文件均已收敛。
（清单里余下的 `api/chat.py` 1,187 行、`db/skill_store.py` 1,148 行、`engines/review_policy.py`
1,001 行不在 M-4 定义的修复建议内，属下一轮候选。）

### [M-5] 并发写保护只覆盖了 2/3 的存储域 — ✅ 已修复（2026-09-27，🟢 收敛）

- **位置**：`py-server/db/core.py:29-45`（正确做法）vs `db/pg_client.py:103`、`api/literacy_assessment.py:135`
- **问题（评审时）**：`db/core.py` 的 D2 修复把 `user_store` + `skill_store`（+ `memory_store` 复用连接）收编为**单连接 + 全局 RLock**，这是对的；但 `pg_fallback.db`（`db/pg_client.py:103`，独立连接 + `self._lock`）与 `data/literacy.db`（见 M-1）仍是旧模式。三个锁域互不知情。
- **修复建议**：统一由 `db/core.py` 发放连接与锁；`pg_client` 的 SQLite 回落路径改走 `db.core.get_conn()`（或显式声明 `pg_fallback.db` 与其它库**永不交叉**，并在 `db/core.py` 头部注释里写清这个边界约定）。

**✅ 修复记录（2026-09-27）**：两条建议都落地了。

1. **连接与锁统一发放**：`pg_client.connect()` 的 SQLite 回退路径改为 `get_lock_for(_FALLBACK_DB)` + `get_conn_for(_FALLBACK_DB, init=self._init_schema_sqlite)`。
   修复前该分支每次被调用都新建一套 `sqlite3.connect` + `threading.Lock`——而 `db/__init__.py:13`、`ability_store`、`career_store`、`seed_demo_data` 都会各自调用 `connect()`，
   即**同一份 pg_fallback.db 被多个连接 + 多把互不知情的锁同时写**，正是 db/core.py 当初为 user_store/skill_store 根除的同款缺陷。现在重复 `connect()` 返回同一连接、同一把锁。
   - 配套：`db/core.py` 新增 `close_conn_for(db_path)`（Shared→Registry 注销，否则注册表会发还已关闭的连接）；`pg_client.disconnect()` 在回退模式下改调它；`_init_schema_sqlite` 支持 `conn` 入参（init 回调在 `self._conn` 赋值之前执行）。
2. **边界约定写入代码**：`db/core.py` 模块头新增「库文件边界约定」表，列明三个库文件（`netlearn_users.db` / `literacy.db` / `pg_fallback.db`）的归属 store、按文件隔离的语义、以及「任何 SQLite 连接都必须经 `get_conn_for` 发放」的硬约束。
3. **合规访问器**：新增 `pg_client.sqlite_query_one()` / `sqlite_execute()`，`db/ability_store.py` 原先越级取 `pg_client._lock` / `pg_client._conn` 的 4 处私有访问已改用访问器（与 M-2 处理 user_store 同构）。

**机验**：`py-server/scripts/verify_core_lock_unification.py`（绕开 `db/__init__` 的 numpy 依赖，stub 后直测 core+pg_client）。
14 项断言全过：双 client `connect()` 后 `conn is conn`、`lock is lock` 且与 `db.core` 注册表同一对象；8 线程 × 50 次并发写零异常、400 行全部落库；`disconnect()` 正确注销且可重连写入。
**变异验证**：把回退路径改回 `sqlite3.connect` 后，前 5 项断言立即 FAIL 并最终抛 `OperationalError: no such table`，证明该组检查有真实辨别力而非空跑。

**残留（不阻塞）**：`db/career_store.py` 仍有 ~10 处 `pg_client._lock` / `pg_client._conn` 私有访问。因其持有的是 `self._lock`，而现在 `self._lock` 就是 `db.core` 的文件锁，故**并发正确性已随本次修复自动收敛**；剩余只是分层异味，归入下一轮（career_store 属并发会话职责域，需协调后再动）。

---

## 四、一般问题（Minor）

### [m-1] 未跟踪的嵌套副本 `crypto_platform`（188 文件 / 46,374 行）— 🟡 Minor
- **位置**：`py-server/{agents,api,db,engines,services,tools}/crypto_platform/py-server/**`
- **问题**：约等于生产代码的 **1.15 倍**，`git ls-files` = 0（未跟踪），全仓无任何模块 import 它。属复制残留。实际危害：① 本次静态扫描 2,573 条告警中 **1,672 条来自它**，淹没真实信号；② 编辑/搜索时极易误中副本文件。
- **修复建议**：确认无引用后整体移出工作区（**按项目红线，不擅自删除**——需你确认后再执行归档或删除）。

### [m-2] py-server 根目录临时脚本堆积 — 🟡 Minor
- **位置**：`py-server/_smoke_*.py`（6）、`_verify_*.py`（5）、`_probe_*.py`、`_p2_*.py`、`_diag_*.py`，以及 `*.log`（`_baseline.log`、`_regress*.log`、`backend_run.log`、`collect.log` 等）
- **问题**：根目录混杂一次性验证脚本与运行日志，且已有 1 个入库。
- **修复建议**：迁入 `py-server/_scratch/`（已存在该目录）并加 `.gitignore` 规则。

### [m-3] DI 容器采用度不足 — 🟡 Minor
- **位置**：`py-server/shared/container.py`
- **问题**：仅 6 个模块使用容器/依赖注入，其余仍是模块级全局单例（`db/graph_db.py:17 _graph_db`、`db/embedder.py:60 _file_lock`、`engines/gomarl_mixer.py:28-29 _torch/_nn`）。可测试性受限。
- **修复建议**：新增模块一律走容器；存量按 M-2/M-4 重构时顺带接入，不做一次性大改。

### [m-4] 演示账号凭据硬编码，生产需显式关闭 — 🟡 Minor（发布风险）
- **位置**：`py-server/seed_demo_data.py:15` `DEMO_PASSWORD = "demo123456"`；另有 5 个脚本硬编码 `{"username":"demo","password":"demo123456"}`
- **问题**：设计上有意（登录页明示演示账号），风险在于**生产环境若执行 seed，将存在公开可登录账号**。
- **修复建议**：seed 脚本加环境闸门：

```python
if os.environ.get("NETLEARN_ENV") == "production":
    raise SystemExit("refuse to seed demo account in production")
```

---

## 五、安全性核查：脚本 Critical 告警逐条证伪

`analyze.py` 在核心区报出 **45 条 Critical**，逐条读源码核实后结论如下（避免后续重复排查）：

| 告警类型 | 条数 | 核实结论 |
|---|---|---|
| SQL 注入（字符串/变量拼接） | 36 | **全部误报** |
| 硬编码密钥/密码 | 9 | 8 条为演示账号常量（有意设计）；1 条为变量名误报 |

**误报依据（关键 3 类）**：

1. **占位符生成式拼接**——`db/skill_store.py:271`、`db/user_store.py:405/417/425`：
   ```python
   placeholders = ",".join("?" for _ in skill_ids)
   conn.execute(f"DELETE FROM skills WHERE id IN ({placeholders})", skill_ids)
   ```
   拼接内容只含 `?`，值走参数绑定 → 安全。

2. **排序字段有白名单**——`db/skill_store.py:373`：
   ```python
   allowed_sorts = {"updated_at", "created_at", "usage_count", "avg_rating", "name"}
   sort_col = sort_by if sort_by in allowed_sorts else "updated_at"
   ```
   `ORDER BY {sort_col}` 不可被注入 → 安全。

3. **`_DUMMY_SALT` 不是密钥**——`db/user_store.py:236`：
   ```python
   # 防用户名枚举：用户不存在时仍执行一轮 PBKDF2（固定常量），
   # 使 verify 耗时与正常路径相近，消除时序侧信道差异。
   _DUMMY_SALT = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
   ```
   这是**防时序侧信道的正确设计**，非漏洞。

**另已核实的安全基线**：
- `py-server/.env` **未入库** ✓
- 全仓跟踪文件未发现真实 API Key / APISecret 字面量 ✓
- 认证使用 PBKDF2-SHA256 600000 轮 ✓（记忆中 MD5→SHA256 整改已落地）
- 前端 `src/views`、`src/components` **零裸 `fetch`** ✓（数据入口统一在 `src/composables/`）

---

## 六、架构评估结论

- **模块边界**：目录划分（api / agents / engines / services / db / shared）语义清晰，但**边界执行不严**——API 层越级访问存储（M-1、M-2），下层反向依赖上层（M-3）。
- **依赖方向**：主方向 `api → (services) → agents/engines → db` 成立（无 `agents → api` 类反向），但存在 6 处 `db/engines → agents/engines` 的**逆向边**，靠延迟导入掩盖。
- **主要风险**：① 存储锁域分裂（3 个），并发写正确性依赖"各域不交叉"这一**未写进代码的隐含约定**；② 业务逻辑与 HTTP 层耦合，难以单测与替换实现；③ 46k 行未跟踪副本污染工具链。
- **做得好的地方**（本次确认）：LangGraph 11 节点编排边界清晰；前端数据入口单一、零裸 fetch；`.env` 未入库、PBKDF2 强度足够、无真实凭据泄露；CI 已有 10 个门禁含 secret-scan 与 pip-audit；防时序枚举（dummy hash）设计正确。
