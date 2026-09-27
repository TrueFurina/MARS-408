# ============================================================
# db/profile_store.py — 用户画像与答题历史/会话/快照存储
#
# M-4 ② 拆分（2026-09-27）：自 db/user_store.py 搬出「画像域」，
# 让 user_store.py 不再同时承载账户、画像、作业、资源、错题、每日计划六个域。
#
# 边界：本模块只负责 user_profiles / user_quiz_history / user_conversations /
# profile_snapshots 四张表及其读写函数；账户、作业、资源、错题、每日计划仍在
# db/user_store.py。
#
# 兼容：db/user_store.py 通过 __getattr__ 动态委托本模块的 8 个公共符号，
# 既有 `from db.user_store import get_profile` 等 20+ 处 import 不受影响。
#
# ⚠️ 三条硬约束：
#   1) 连接与锁一律来自 db.core（与 user_store 同一连接、同一把锁），
#      不得自建 sqlite3.connect —— 见 db/core.py 的库文件边界约定（M-5）。
#   2) _init_schema 用 CREATE TABLE IF NOT EXISTS，幂等；user_store 的
#      _init_schema 也建这四张表，两边重复执行无副作用。
#   3) 本模块**不得** import db.user_store：user_store 会委托访问本模块，
#      反向顶层 import 会构成循环依赖（M-3 刚消除过同类问题）。
# ============================================================

import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

logger = logging.getLogger("netlearn.userstore")

# 与 user_store 同一连接 + 同一把锁（db.core 按 DB 文件统一发放）
from db.core import get_conn as _core_get_conn, LOCK as _lock

_initialized = False


def _now() -> str:
    """与 db.user_store._now 同格式（"%Y-%m-%d %H:%M:%S"）。

    刻意就地定义而非从 user_store 导入：user_store 会委托访问本模块，
    反向 import 就是循环依赖。db 层的时间工具应在后续统一收敛到 shared/。
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_conn() -> sqlite3.Connection:
    """共享连接（来自 db.core 单例）；首次调用时幂等建本域的表。"""
    conn = _core_get_conn()
    global _initialized
    if not _initialized:
        with _lock:
            if not _initialized:
                _init_schema(conn)
                _initialized = True
    return conn


def _init_schema(conn: sqlite3.Connection):
    """只建画像域的四张表与索引（幂等，与 user_store 的建表语句一致）。"""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        profile_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_quiz_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        subject TEXT NOT NULL DEFAULT '',
        correct INTEGER NOT NULL DEFAULT 0,
        difficulty TEXT NOT NULL DEFAULT 'medium',
        timestamp TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_conversations (
        user_id TEXT NOT NULL,
        conv_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        messages_json TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, conv_id)
    );
    CREATE TABLE IF NOT EXISTS profile_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        snapshot_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_snapshot_user ON profile_snapshots(user_id);
    CREATE INDEX IF NOT EXISTS idx_quiz_user ON user_quiz_history(user_id);
    CREATE INDEX IF NOT EXISTS idx_conv_user ON user_conversations(user_id);
    """)
    conn.commit()


def save_profile(user_id: str, profile: dict):
    conn = _get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO user_profiles (user_id, profile_json, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET profile_json=excluded.profile_json, updated_at=excluded.updated_at",
            (user_id, json.dumps(profile, ensure_ascii=False), _now()),
        )
        conn.commit()


def get_profile(user_id: str) -> Optional[dict]:
    with _lock:
        conn = _get_conn()
        row = conn.execute("SELECT profile_json FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["profile_json"])
        except Exception:
            return None


# ── 每用户答题历史 ──

def append_quiz_history(user_id: str, records: list[dict]):
    if not records:
        return
    conn = _get_conn()
    now = _now()
    rows = [
        (user_id, r.get("subject", ""), 1 if r.get("correct") else 0, r.get("difficulty", "medium"), r.get("timestamp") or now)
        for r in records
    ]
    with _lock:
        conn.executemany(
            "INSERT INTO user_quiz_history (user_id, subject, correct, difficulty, timestamp) VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()


def get_quiz_history(user_id: str) -> list[dict]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT subject, correct, difficulty, timestamp FROM user_quiz_history WHERE user_id=? ORDER BY id", (user_id,)
        ).fetchall()
        return [
            {"subject": r["subject"], "correct": bool(r["correct"]), "difficulty": r["difficulty"], "timestamp": r["timestamp"]}
            for r in rows
        ]


# ── 每用户对话 ──

def save_conversations(user_id: str, conversations: list[dict]):
    if not conversations:
        return
    conn = _get_conn()
    now = _now()
    with _lock:
        for c in conversations:
            conn.execute(
                "INSERT INTO user_conversations (user_id, conv_id, title, messages_json, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(user_id, conv_id) DO UPDATE SET title=excluded.title, messages_json=excluded.messages_json, updated_at=excluded.updated_at",
                (user_id, c.get("id"), c.get("title", ""), json.dumps(c.get("messages", []), ensure_ascii=False), now),
            )
        conn.commit()


def get_conversations(user_id: str) -> list[dict]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT conv_id, title, messages_json, updated_at FROM user_conversations WHERE user_id=?", (user_id,)
        ).fetchall()
        out = []
        for r in rows:
            try:
                msgs = json.loads(r["messages_json"])
            except Exception:
                msgs = []
            out.append({"id": r["conv_id"], "title": r["title"], "messages": msgs, "updated_at": r["updated_at"]})
        return out


# ── 管理员聚合 ──


def save_profile_snapshot(user_id: str, profile: dict) -> int:
    """保存当前画像快照"""
    import json
    with _lock:
        conn = _get_conn()
        now = _now()
        cursor = conn.execute(
            "INSERT INTO profile_snapshots (user_id, snapshot_json, created_at) VALUES (?, ?, ?)",
            (user_id, json.dumps(profile, ensure_ascii=False), now),
        )
        conn.commit()
        return cursor.lastrowid or 0


def get_profile_snapshots(user_id: str, limit: int = 10) -> list[dict]:
    """获取画像快照历史"""
    import json
    with _lock:
        rows = _get_conn().execute(
            "SELECT id, snapshot_json, created_at FROM profile_snapshots WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    results = []
    for r in rows:
        try:
            snapshot = json.loads(r["snapshot_json"])
        except (json.JSONDecodeError, TypeError):
            snapshot = {}
        results.append({
            "id": r["id"],
            "snapshot": snapshot,
            "created_at": r["created_at"],
        })
    return results


# ── 班级作业（快照 + 提交） ──



