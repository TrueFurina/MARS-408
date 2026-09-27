"""db/core.py — SQLite 共享连接与锁（D2 技术债修复）。

``user_store`` 与 ``skill_store`` 共享同一个 ``netlearn_users.db`` 文件，但原本各自持有
独立的模块级连接单例 + 独立的 RLock，导致跨 store 并发写时**两把锁不互斥**、
且是**两个连接写同一文件**，极易触发 ``database is locked`` / WAL 损坏。

本模块把**唯一连接单例**与**唯一全局可重入锁**收归一处，两个 store 复用，
从根上消除并发写冲突。

行为零改动：连接参数（``check_same_thread=False``）、``row_factory``、WAL pragma
与原 store 内定义完全一致；各 store 仍负责自己的 ``_init_schema``（幂等建表），
避免本模块耦合具体表结构。
"""
import os
import threading
from typing import Optional

import sqlite3

# 支持 NETLEARN_USER_DB 环境变量覆盖 DB 路径（测试隔离用，低侵入）。
# 与 user_store 原逻辑保持一致；skill_store 借此也获得 env 覆盖能力。
DB_PATH = os.environ.get("NETLEARN_USER_DB") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "netlearn_users.db"
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 唯一全局可重入锁：user_store 与 skill_store 共用同一把锁，跨 store 互斥。
# 读路径会回调读函数（如 list_all_users 内调 get_profile），非重入 Lock 会死锁，故用 RLock。
LOCK = threading.RLock()

_conn: Optional[sqlite3.Connection] = None

# 按「DB 文件」维度登记连接与锁：新增 store 一律复用本表，
# 不再各自 sqlite3.connect + 各自 threading.Lock（那会重现「两连接 + 两把
# 不互斥的锁写同一文件」）。注意锁是**按文件隔离**的：不同 DB 文件互不互斥，
# 这正是期望行为——需要互斥的是「写同一个文件」。
_conns: dict[str, sqlite3.Connection] = {}
_locks: dict[str, threading.RLock] = {}
# 用 RLock：init 回调里若再次调用 get_conn_for（幂等建表路径）不会自锁。
_REGISTRY_LOCK = threading.RLock()


def get_lock_for(db_path: str) -> threading.RLock:
    """返回该 DB 文件全局唯一的 RLock（可重入，读路径回调读函数不死锁）。"""
    with _REGISTRY_LOCK:
        lk = _locks.get(db_path)
        if lk is None:
            lk = threading.RLock()
            _locks[db_path] = lk
        return lk


def get_conn_for(db_path: str, init=None) -> sqlite3.Connection:
    """返回该 DB 文件全局唯一的 SQLite 连接（WAL + row_factory=Row）。

    ``init`` 为可选的一次性建表回调（``init(conn)``），仅在新建连接时执行，
    使各 store 的 ``_init_schema`` 仍由自己持有，本模块不耦合表结构。
    """
    with _REGISTRY_LOCK:
        conn = _conns.get(db_path)
        if conn is None:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            _conns[db_path] = conn
            if init is not None:
                init(conn)
        return conn


def get_conn() -> sqlite3.Connection:
    """返回默认库（netlearn_users.db）的唯一连接（延迟初始化 + WAL + Row）。

    仅负责连接与 WAL；各 store 的建表由各自 ``_init_schema`` 在首次
    ``_get_conn`` 时幂等触发，避免本模块耦合具体表结构。
    """
    global _conn
    if _conn is None:
        _conn = get_conn_for(DB_PATH)
    return _conn
