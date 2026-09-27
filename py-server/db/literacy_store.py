# ============================================================
# db/literacy_store.py — 职业素养测评记录存储（data/literacy.db）
#
# 背景（M-1 修复）：原实现内联在 api/literacy_assessment.py —— 接口层直接
# import sqlite3、自建连接单例与 threading.Lock，既违反分层（存储实现无法统一
# 替换），又形成第三个独立锁域。此处下沉到 db 层。
#
# 设计约定：
# 1. 连接与锁改由 db.core 按「DB 文件路径」统一发放（get_conn_for / get_lock_for），
#    与 user_store / skill_store 共用同一套登记机制。
#    ⚠️ 锁按文件隔离：literacy.db 与 netlearn_users.db 是**两个文件**，仍是两把锁，
#    这是正确的（跨文件无需互斥）；被消除的是「同一文件被两个连接 + 两把锁同时写」。
# 2. DB 路径**每次调用**惰性解析 NETLEARN_LITERACY_DB：原实现注释已记录踩坑——
#    导入期固化 env 会让全量测试指向错位（测试间污染）。
# 3. 对外只暴露业务语义函数，接口层不再出现 SQL。
# ============================================================

import json
import os
import sqlite3

from db.core import get_conn_for, get_lock_for

_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "literacy.db")
os.makedirs(os.path.dirname(_DEFAULT_DB), exist_ok=True)


def _db_path() -> str:
    """惰性解析 DB 路径（每次调用读 env，避免导入期固化导致测试库错位）。"""
    return os.environ.get("NETLEARN_LITERACY_DB") or _DEFAULT_DB


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS literacy_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            class_name TEXT NOT NULL DEFAULT '',
            phase TEXT NOT NULL DEFAULT 'pre',          -- pre / post
            answers_json TEXT NOT NULL DEFAULT '[]',    -- [{qid, option_index}]
            dim_scores_json TEXT NOT NULL DEFAULT '{}', -- {维度: 分数}
            total_score REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_literacy_user_phase ON literacy_attempts(user_id, phase)")
    conn.commit()


def _get_conn() -> sqlite3.Connection:
    return get_conn_for(_db_path(), init=_init_schema)


def _lock():
    return get_lock_for(_db_path())


def save_attempt(
    user_id: str,
    user_name: str,
    class_name: str,
    phase: str,
    answers: list,
    dim_scores: dict,
    total_score: float,
) -> None:
    """写入一次作答。

    同一用户同 phase 仅保留最新一次：先删旧记录再插入（与原实现行为一致）。
    """
    conn = _get_conn()
    with _lock():
        conn.execute(
            "DELETE FROM literacy_attempts WHERE user_id=? AND phase=?", (user_id, phase))
        conn.execute(
            "INSERT INTO literacy_attempts"
            " (user_id, user_name, class_name, phase, answers_json, dim_scores_json, total_score)"
            " VALUES (?,?,?,?,?,?,?)",
            (user_id, user_name, class_name, phase,
             json.dumps(answers, ensure_ascii=False),
             json.dumps(dim_scores, ensure_ascii=False), total_score))
        conn.commit()


def get_user_attempts(user_id: str) -> list:
    """按用户取全部作答记录（按时间倒序）。"""
    conn = _get_conn()
    return conn.execute(
        "SELECT * FROM literacy_attempts WHERE user_id=? ORDER BY created_at DESC",
        (user_id,)).fetchall()


def get_class_attempts(class_name: str) -> list:
    """按班级取全部作答记录（按 user_id、时间倒序）。"""
    conn = _get_conn()
    return conn.execute(
        "SELECT * FROM literacy_attempts WHERE class_name=? ORDER BY user_id, created_at DESC",
        (class_name,)).fetchall()
