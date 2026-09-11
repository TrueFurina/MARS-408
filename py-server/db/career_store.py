# ============================================================
# career_store — 芒得很职·对抗实训 数据访问层
#
# 自包含、幂等建表（不改动公共 pg_client.py 的 schema 初始化），
# 复用全局 pg_client 连接，自动适配 PostgreSQL / SQLite 回退。
# 所有业务表 career_* 前缀，与 408 表完全隔离。
# ============================================================

import json
import logging
import uuid
from typing import Optional

from db.pg_client import pg_client

logger = logging.getLogger("netlearn.career.store")

_TABLES_READY = False

# PG 建表脚本（JSONB）
_DDL_PG = """
CREATE TABLE IF NOT EXISTS career_classes (
    id VARCHAR(64) PRIMARY KEY,
    teacher_id VARCHAR(64) NOT NULL,
    class_name VARCHAR(128) NOT NULL,
    student_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS career_tasks (
    id VARCHAR(64) PRIMARY KEY,
    class_id VARCHAR(64),
    teacher_id VARCHAR(64) NOT NULL,
    scenario_id VARCHAR(64),
    scenario_type VARCHAR(32),
    scenario_subtype VARCHAR(64),
    difficulty VARCHAR(16),
    max_turns INTEGER DEFAULT 8,
    due_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS career_sessions (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    task_id VARCHAR(64),
    scenario_id VARCHAR(64),
    scenario_type VARCHAR(32),
    scenario_subtype VARCHAR(64),
    title VARCHAR(256) DEFAULT '',
    difficulty VARCHAR(16),
    max_turns INTEGER DEFAULT 8,
    state JSONB,
    status VARCHAR(16) DEFAULT 'ongoing',
    turn_count INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS career_dialogue_turns (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    turn_index INTEGER NOT NULL,
    adversary_mode VARCHAR(16) DEFAULT 'normal',
    probe_dimension VARCHAR(32) DEFAULT '',
    question TEXT,
    answer TEXT,
    evidence JSONB,
    ts TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_career_turns_session ON career_dialogue_turns(session_id);
CREATE TABLE IF NOT EXISTS career_assessments (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    task_id VARCHAR(64),
    dimension_scores JSONB,
    evidence_chain JSONB,
    consistency_score FLOAT,
    improvement_plan JSONB,
    report_md TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
"""

# SQLite 建表脚本（TEXT 代替 JSONB，AUTOINCREMENT）
_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS career_classes (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL,
    class_name TEXT NOT NULL,
    student_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS career_tasks (
    id TEXT PRIMARY KEY,
    class_id TEXT,
    teacher_id TEXT NOT NULL,
    scenario_id TEXT,
    scenario_type TEXT,
    scenario_subtype TEXT,
    difficulty TEXT,
    max_turns INTEGER DEFAULT 8,
    due_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS career_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_id TEXT,
    scenario_id TEXT,
    scenario_type TEXT,
    scenario_subtype TEXT,
    title TEXT DEFAULT '',
    difficulty TEXT,
    max_turns INTEGER DEFAULT 8,
    state TEXT,
    status TEXT DEFAULT 'ongoing',
    turn_count INTEGER DEFAULT 0,
    started_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS career_dialogue_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    adversary_mode TEXT DEFAULT 'normal',
    probe_dimension TEXT DEFAULT '',
    question TEXT,
    answer TEXT,
    evidence TEXT,
    ts TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_career_turns_session ON career_dialogue_turns(session_id);
CREATE TABLE IF NOT EXISTS career_assessments (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    task_id TEXT,
    dimension_scores TEXT,
    evidence_chain TEXT,
    consistency_score REAL,
    improvement_plan TEXT,
    report_md TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def ensure_tables(force: bool = False) -> bool:
    """幂等建表。返回是否就绪。"""
    global _TABLES_READY
    if _TABLES_READY and not force:
        return True
    try:
        if not pg_client.is_enabled:
            pg_client.connect()
        ddl = _DDL_SQLITE if pg_client.is_fallback else _DDL_PG
        pg_client.migrate_exec(ddl)
        _TABLES_READY = True
        logger.info("career_* 表已就绪（%s）", "SQLite" if pg_client.is_fallback else "PostgreSQL")
        return True
    except Exception as e:
        logger.warning(f"career 建表失败（非阻塞）: {e}")
        return False


def new_id(prefix: str = "cs") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _ph(seq: int = 1) -> str:
    """按数据库类型返回占位符（sqlite=?，pg=%s），seq 为参数个数"""
    mark = "?" if pg_client.is_fallback else "%s"
    return ", ".join([mark] * seq)


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False) if obj is not None else None


def _loads(raw, default=None):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


# ────────────────────────────────────────────────────────────
# 会话
# ────────────────────────────────────────────────────────────
def create_session(state: dict) -> str:
    ensure_tables()
    sid = state.get("session_id") or new_id("sess")
    state["session_id"] = sid
    sql = (
        "INSERT INTO career_sessions "
        "(id,user_id,task_id,scenario_id,scenario_type,scenario_subtype,title,difficulty,max_turns,state,status,turn_count) "
        f"VALUES ({_ph(12)})"
    )
    params = (
        sid, state.get("user_id"), state.get("task_id"),
        state.get("scenario_id", ""), state.get("scenario_type", ""),
        state.get("scenario_subtype", ""), state.get("title", ""),
        state.get("difficulty", "medium"), int(state.get("max_turns", 8)),
        _dumps(state), "ongoing", len(state.get("dialogue_turns", [])),
    )
    if pg_client.is_fallback:
        with pg_client._lock:
            pg_client._conn.execute(sql, params); pg_client._conn.commit()
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, params)
    return sid


def save_session_state(state: dict, status: Optional[str] = None):
    ensure_tables()
    sid = state["session_id"]
    turn_count = len(state.get("dialogue_turns", []))
    st = status or state.get("status", "ongoing")
    state["status"] = st
    q = "?" if pg_client.is_fallback else "%s"
    finished_clause = ""
    params = [_dumps(state), st, turn_count]
    if st in ("finished", "abandoned"):
        finished_clause = ", finished_at = NOW()" if not pg_client.is_fallback else ", finished_at = datetime('now')"
    sql = (f"UPDATE career_sessions SET state={q}, status={q}, turn_count={q}"
           f"{finished_clause} WHERE id={q}")
    params.append(sid)
    if pg_client.is_fallback:
        with pg_client._lock:
            pg_client._conn.execute(sql, params); pg_client._conn.commit()
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, params)


def get_session_state(sid: str) -> Optional[dict]:
    ensure_tables()
    sql = f"SELECT state FROM career_sessions WHERE id={'?' if pg_client.is_fallback else '%s'}"
    if pg_client.is_fallback:
        with pg_client._lock:
            row = pg_client._conn.execute(sql, (sid,)).fetchone()
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, (sid,)); row = cur.fetchone()
    if not row:
        return None
    raw = row["state"] if pg_client.is_fallback else row[0]
    return _loads(raw)


def list_my_sessions(user_id: str, limit: int = 20) -> list[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    sql = (f"SELECT id,scenario_type,scenario_subtype,title,status,turn_count,started_at,finished_at "
           f"FROM career_sessions WHERE user_id={q} ORDER BY started_at DESC LIMIT {int(limit)}")
    if pg_client.is_fallback:
        with pg_client._lock:
            rows = pg_client._conn.execute(sql, (user_id,)).fetchall()
            return [dict(r) for r in rows]
    with pg_client._conn.cursor() as cur:
        cur.execute(sql, (user_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# ────────────────────────────────────────────────────────────
# 对话轮次（证据单元）
# ────────────────────────────────────────────────────────────
def add_turn(sid: str, turn: dict):
    ensure_tables()
    sql = ("INSERT INTO career_dialogue_turns "
           "(session_id,turn_index,adversary_mode,probe_dimension,question,answer,evidence) "
           f"VALUES ({_ph(7)})")
    params = (
        sid, int(turn.get("turn_index", 0)), turn.get("mode", "normal"),
        turn.get("probe_dimension", ""), turn.get("question", ""),
        turn.get("answer", ""), _dumps(turn.get("evidence")),
    )
    if pg_client.is_fallback:
        with pg_client._lock:
            pg_client._conn.execute(sql, params); pg_client._conn.commit()
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, params)


def get_turns(sid: str) -> list[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    sql = (f"SELECT turn_index,adversary_mode,probe_dimension,question,answer,evidence,ts "
           f"FROM career_dialogue_turns WHERE session_id={q} ORDER BY turn_index ASC")
    if pg_client.is_fallback:
        with pg_client._lock:
            rows = pg_client._conn.execute(sql, (sid,)).fetchall()
            out = [dict(r) for r in rows]
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, (sid,))
            cols = [d[0] for d in cur.description]
            out = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in out:
        r["evidence"] = _loads(r.get("evidence"), {})
    return out


# ────────────────────────────────────────────────────────────
# 评估报告
# ────────────────────────────────────────────────────────────
def save_assessment(session_id: str, user_id: str, assessment: dict,
                    improvement: dict, evidence_chain=None,
                    consistency_score: Optional[float] = None,
                    task_id: Optional[str] = None) -> str:
    ensure_tables()
    aid = new_id("assess")
    report_md = assessment.get("summary", "")
    sql = ("INSERT INTO career_assessments "
           "(id,session_id,user_id,task_id,dimension_scores,evidence_chain,consistency_score,improvement_plan,report_md) "
           f"VALUES ({_ph(9)})")
    params = (aid, session_id, user_id, task_id, _dumps(assessment),
              _dumps(evidence_chain or []), consistency_score, _dumps(improvement), report_md)
    if pg_client.is_fallback:
        with pg_client._lock:
            pg_client._conn.execute(sql, params); pg_client._conn.commit()
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, params)
    return aid


def get_assessment_by_session(session_id: str) -> Optional[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    sql = f"SELECT * FROM career_assessments WHERE session_id={q} ORDER BY created_at DESC LIMIT 1"
    if pg_client.is_fallback:
        with pg_client._lock:
            row = pg_client._conn.execute(sql, (session_id,)).fetchone()
            result = dict(row) if row else None
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, (session_id,))
            cols = [d[0] for d in cur.description]
            r = cur.fetchone()
            result = dict(zip(cols, r)) if r else None
    if result:
        for k in ("dimension_scores", "evidence_chain", "improvement_plan"):
            result[k] = _loads(result.get(k))
    return result
