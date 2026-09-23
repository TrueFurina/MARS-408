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


def get_conn() -> sqlite3.Connection:
    """返回全局唯一 SQLite 连接（延迟初始化 + WAL + row_factory=Row）。

    仅负责连接与 WAL；各 store 的建表由各自 ``_init_schema`` 在首次
    ``_get_conn`` 时幂等触发，避免本模块耦合具体表结构。
    """
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn
