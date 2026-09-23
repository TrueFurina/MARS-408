# D2 共享 SQLite 统一连接与锁（P1 · 技术债 Priority=27）

**日期**：2026-09-23
**分支**：career-literacy
**类别**：🔴 严重并发缺陷（非交付阻塞，但真并发写会损坏）

---

## 一、根因（证据先行）

`user_store.py` 与 `skill_store.py` **共享同一个 `netlearn_users.db` 文件**，但各自持有独立状态：

| 维度 | user_store | skill_store |
|------|-----------|-------------|
| 连接 | 模块级 `_conn` 单例（L26/39） | 模块级 `_conn` 单例（L30/43） |
| 锁 | 独立 `_lock = threading.RLock()`（L29） | 独立 `_lock = threading.RLock()`（L31） |
| 路径 | `_DB_PATH`（支持 `NETLEARN_USER_DB` env） | `_DB_PATH`（无 env，直接拼路径） |

结论：跨 store 是**两个独立连接 + 两把不互斥的锁** 写同一文件。并发写时：
- 两把 RLock 不交叉保护 → 两个线程可同时进入各自的写临界区；
- 且底层是两个不同连接对象写同一文件；
- SQLite 即使 WAL 模式，并发写仍会抛 `database is locked` 或造成 WAL 损坏。

---

## 二、修复（行为零改动，仅统一连接与锁）

### 新增 `py-server/db/core.py`
提供**唯一连接单例** + **唯一全局 RLock**：
- `DB_PATH`：沿用 user_store 的 env 覆盖逻辑（`NETLEARN_USER_DB`），skill_store 借此也获得 env 隔离能力（行为增强、无破坏）。
- `LOCK = threading.RLock()`：全局唯一，两 store 共用。
- `get_conn()`：懒初始化单例，连接参数（`check_same_thread=False`）、`row_factory=Row`、`PRAGMA journal_mode=WAL` 与原 store 完全一致。

### 改动 `user_store.py` / `skill_store.py`
- 删除各自 `_DB_PATH`/`_conn`/`_lock` 定义，改为 `from db.core import get_conn as _core_get_conn, LOCK as _lock, DB_PATH as _DB_PATH`。
- 重写 `_get_conn()`：取 core 单例连接，首次调用时在本模块 `_lock` 内**幂等触发各自 `_init_schema`**（double-checked locking，避免重复建表与竞态）。
- `get_db_conn()` 公开别名保持不变（main.py L799 依赖）。

> 设计要点：core 只管连接与锁，不耦合任何表结构；各 store 的 `_init_schema` 仍由各自负责（确保建表职责不漂移）。两 store 现共用**同一连接对象 + 同一把锁**，从根上消除并发写冲突。

---

## 三、验证

- **单元/并发测试** `tests/test_db_core_d2.py`（2 passed）：
  1. `test_d2_shared_connection_and_lock`：断言 `us._get_conn() is ss._get_conn()` 且 `us._lock is ss._lock`（D2 核心不变量）。
  2. `test_d2_concurrent_cross_store_writes_no_locked`：30 线程交替通过两 store 并发写同一库，**无 `database is locked` / WAL 损坏**。
- `py_compile` 三个 db 模块 + 测试文件全部通过。
- 全量默认套件回归：运行确认无破坏（见提交前 CI）。

---

## 四、影响面

- `main.py`：仅用 `user_store.get_db_conn()` / `ensure_admin` / `authenticate` —— 接口不变，行为不变。
- 测试目录：无直接 import 两 store 模块的测试，回归风险低。
- 副作用：skill_store 现在也支持 `NETLEARN_USER_DB` env 覆盖（与 user_store 一致），测试隔离更统一。

**结论**：D2 收口。共享 SQLite 的跨 store 并发写不再依赖两把不互斥的锁，单一全局锁 + 单一连接单例确保互斥与一致性。
