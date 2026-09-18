# ============================================================
# L1/L2/L3 三层分级学情记忆存储层（对标 HKU-DeepTutor 记忆架构）
#
# 设计原则（低侵入拓展，不改动 GOMARL/FrugalRAG/辩论/规则引擎核心）：
#   L1 工作记忆（Working Memory）  — 当前会话上下文，短时有效，TTL 自动过期
#   L2 语义记忆（Semantic Memory） — 学生画像 + 知识点掌握度矩阵，长期稳定
#   L3 情景记忆（Episodic Memory） — 历史事件流（答题/行为/资源交互），可追溯
#
# 存储：复用 user_store 的 SQLite 连接（同一 DB 文件），独立建表，互不干扰。
# ============================================================

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("netlearn.memory_store")

# ── 记忆层级常量 ──
L1_WORKING = "l1_working"
L2_SEMANTIC = "l2_semantic"
L3_EPISODIC = "l3_episodic"

# L1 工作记忆默认 TTL（秒）：当前会话上下文 30 分钟
L1_DEFAULT_TTL = 30 * 60
# L3 情景记忆保留窗口：90 天
L3_RETENTION_DAYS = 90

_schema_lock = threading.Lock()
_schema_ready = False


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_conn():
    """复用 user_store 的 SQLite 连接（同一 DB 文件 netlearn_users.db）"""
    from db.user_store import get_db_conn
    conn = get_db_conn()
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn):
    """幂等建表（首次使用时执行）"""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS memory_l1_working (
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            context_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (user_id, session_id)
        );
        CREATE TABLE IF NOT EXISTS memory_l2_semantic (
            user_id TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL DEFAULT '{}',
            mastery_json TEXT NOT NULL DEFAULT '{}',
            weak_points_json TEXT NOT NULL DEFAULT '[]',
            mastered_points_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memory_l3_episodic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_l3_user_time ON memory_l3_episodic(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_l3_user_type ON memory_l3_episodic(user_id, event_type);
        """)
        conn.commit()
        _schema_ready = True


# ══════════════════════════════════════════════════════════
# L1 工作记忆（Working Memory）
# ══════════════════════════════════════════════════════════

def save_working_memory(user_id: str, session_id: str, context: dict,
                        ttl_seconds: int = L1_DEFAULT_TTL) -> None:
    """写入当前会话的工作记忆（覆盖同会话旧值）

    expires_at 存 epoch 秒（精确比较，避免秒级字符串 TTL=1s 边界误判）。
    """
    conn = _get_conn()
    import time as _time
    expires = _time.time() + ttl_seconds
    conn.execute(
        "INSERT INTO memory_l1_working (user_id, session_id, context_json, updated_at, expires_at) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(user_id, session_id) DO UPDATE SET "
        "context_json=excluded.context_json, updated_at=excluded.updated_at, expires_at=excluded.expires_at",
        (user_id, session_id, json.dumps(context, ensure_ascii=False), _now(), str(expires)),
    )
    conn.commit()


def get_working_memory(user_id: str, session_id: str) -> Optional[dict]:
    """读取工作记忆；已过期自动清理并返回 None"""
    import time as _time
    conn = _get_conn()
    row = conn.execute(
        "SELECT context_json, expires_at FROM memory_l1_working "
        "WHERE user_id=? AND session_id=?",
        (user_id, session_id),
    ).fetchone()
    if not row:
        return None
    # 过期检查（epoch 秒精确比较）
    try:
        expired = float(row["expires_at"]) < _time.time()
    except (TypeError, ValueError):
        expired = False
    if expired:
        conn.execute("DELETE FROM memory_l1_working WHERE user_id=? AND session_id=?",
                     (user_id, session_id))
        conn.commit()
        return None
    try:
        return json.loads(row["context_json"])
    except Exception:
        return None


def merge_working_memory(user_id: str, session_id: str, patch: dict,
                         ttl_seconds: int = L1_DEFAULT_TTL) -> dict:
    """增量合并工作记忆（保留未冲突字段），返回合并后完整上下文"""
    current = get_working_memory(user_id, session_id) or {}
    current.update(patch)
    save_working_memory(user_id, session_id, current, ttl_seconds)
    return current


def clear_working_memory(user_id: str, session_id: Optional[str] = None) -> None:
    """清空工作记忆；session_id 为空则清空该用户全部会话"""
    conn = _get_conn()
    if session_id:
        conn.execute("DELETE FROM memory_l1_working WHERE user_id=? AND session_id=?",
                     (user_id, session_id))
    else:
        conn.execute("DELETE FROM memory_l1_working WHERE user_id=?", (user_id,))
    conn.commit()


# ══════════════════════════════════════════════════════════
# L2 语义记忆（Semantic Memory）
# ══════════════════════════════════════════════════════════

def save_semantic_memory(user_id: str, profile: Optional[dict] = None,
                         mastery: Optional[dict] = None,
                         weak_points: Optional[list] = None,
                         mastered_points: Optional[list] = None) -> None:
    """写入/合并长期语义记忆（画像 + 掌握度矩阵 + 薄弱/已掌握点）"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT profile_json, mastery_json, weak_points_json, mastered_points_json "
        "FROM memory_l2_semantic WHERE user_id=?", (user_id,)
    ).fetchone()
    if row:
        cur_profile = json.loads(row["profile_json"]) if row["profile_json"] else {}
        cur_mastery = json.loads(row["mastery_json"]) if row["mastery_json"] else {}
        cur_weak = json.loads(row["weak_points_json"]) if row["weak_points_json"] else []
        cur_mastered = json.loads(row["mastered_points_json"]) if row["mastered_points_json"] else []
    else:
        cur_profile, cur_mastery, cur_weak, cur_mastered = {}, {}, [], []

    if profile:
        cur_profile.update(profile)
    if mastery:
        cur_mastery.update(mastery)
    if weak_points is not None:
        cur_weak = list(dict.fromkeys(cur_weak + weak_points))  # 去重保序
    if mastered_points is not None:
        cur_mastered = list(dict.fromkeys(cur_mastered + mastered_points))

    conn.execute(
        "INSERT INTO memory_l2_semantic (user_id, profile_json, mastery_json, weak_points_json, mastered_points_json, updated_at) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "profile_json=excluded.profile_json, mastery_json=excluded.mastery_json, "
        "weak_points_json=excluded.weak_points_json, mastered_points_json=excluded.mastered_points_json, "
        "updated_at=excluded.updated_at",
        (user_id, json.dumps(cur_profile, ensure_ascii=False),
         json.dumps(cur_mastery, ensure_ascii=False),
         json.dumps(cur_weak, ensure_ascii=False),
         json.dumps(cur_mastered, ensure_ascii=False), _now()),
    )
    conn.commit()


def get_semantic_memory(user_id: str) -> dict:
    """读取完整语义记忆：{profile, mastery, weak_points, mastered_points}"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT profile_json, mastery_json, weak_points_json, mastered_points_json, updated_at "
        "FROM memory_l2_semantic WHERE user_id=?", (user_id,)
    ).fetchone()
    if not row:
        return {"profile": {}, "mastery": {}, "weak_points": [], "mastered_points": [], "updated_at": None}
    return {
        "profile": json.loads(row["profile_json"]) if row["profile_json"] else {},
        "mastery": json.loads(row["mastery_json"]) if row["mastery_json"] else {},
        "weak_points": json.loads(row["weak_points_json"]) if row["weak_points_json"] else [],
        "mastered_points": json.loads(row["mastered_points_json"]) if row["mastered_points_json"] else [],
        "updated_at": row["updated_at"],
    }


def update_mastery(user_id: str, point_id: str, mastery_score: float) -> None:
    """更新单个知识点掌握度（0-1），用于答题后即时回写"""
    mem = get_semantic_memory(user_id)
    mastery = mem["mastery"]
    mastery[point_id] = max(0.0, min(1.0, mastery_score))
    save_semantic_memory(user_id, mastery=mastery)


# ══════════════════════════════════════════════════════════
# L3 情景记忆（Episodic Memory）
# ══════════════════════════════════════════════════════════

def append_episode(user_id: str, event_type: str, event: dict) -> None:
    """追加一条情景记忆事件（答题/行为/资源交互等）"""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO memory_l3_episodic (user_id, event_type, event_json, created_at) VALUES (?,?,?,?)",
        (user_id, event_type, json.dumps(event, ensure_ascii=False), _now()),
    )
    conn.commit()


def append_episodes_batch(user_id: str, event_type: str, events: list[dict]) -> None:
    """批量追加同类型情景事件（一次性 commit）"""
    if not events:
        return
    conn = _get_conn()
    conn.executemany(
        "INSERT INTO memory_l3_episodic (user_id, event_type, event_json, created_at) VALUES (?,?,?,?)",
        [(user_id, event_type, json.dumps(e, ensure_ascii=False), _now()) for e in events],
    )
    conn.commit()


def get_episodes(user_id: str, event_type: Optional[str] = None,
                 limit: int = 50, since: Optional[str] = None) -> list[dict]:
    """按时间倒序读取情景记忆"""
    conn = _get_conn()
    sql = "SELECT event_type, event_json, created_at FROM memory_l3_episodic WHERE user_id=?"
    params: list = [user_id]
    if event_type:
        sql += " AND event_type=?"
        params.append(event_type)
    if since:
        sql += " AND created_at>=?"
        params.append(since)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        try:
            ev = json.loads(r["event_json"])
        except Exception:
            ev = {}
        out.append({"event_type": r["event_type"], "event": ev, "created_at": r["created_at"]})
    return out


def prune_episodes(retention_days: int = L3_RETENTION_DAYS) -> int:
    """清理过期情景记忆，返回删除条数（可被定时任务调用）"""
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("DELETE FROM memory_l3_episodic WHERE created_at<?", (cutoff,))
    conn.commit()
    deleted = cur.rowcount
    if deleted:
        logger.info(f"情景记忆清理: 删除 {deleted} 条过期记录")
    return deleted


def count_episodes(user_id: str) -> int:
    """统计用户情景记忆条数（供记忆健康度展示）"""
    conn = _get_conn()
    return conn.execute("SELECT COUNT(*) AS c FROM memory_l3_episodic WHERE user_id=?", (user_id,)).fetchone()["c"]


# ══════════════════════════════════════════════════════════
# 聚合查询
# ══════════════════════════════════════════════════════════

def get_full_memory(user_id: str, session_id: Optional[str] = None) -> dict:
    """一次性聚合三层记忆，供智能体初始化上下文"""
    l2 = get_semantic_memory(user_id)
    l1 = get_working_memory(user_id, session_id) if session_id else None
    l3_count = count_episodes(user_id)
    return {
        "l1_working": l1 or {},
        "l2_semantic": l2,
        "l3_episodic_count": l3_count,
        "memory_profile": {
            "level": "L1+L2+L3" if l1 and l2.get("profile") else ("L2+L3" if l2.get("profile") else "L3"),
            "has_semantic_profile": bool(l2.get("profile")),
            "has_working_context": l1 is not None,
        },
    }
