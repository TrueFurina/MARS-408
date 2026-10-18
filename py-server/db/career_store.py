# ============================================================
# career_store — 芒得很职·对抗实训 数据访问层
#
# 自包含、幂等建表（不改动公共 pg_client.py 的 schema 初始化），
# 复用全局 pg_client 连接，自动适配 PostgreSQL / SQLite 回退。
# 所有业务表 career_* 前缀，与专业能力场景表完全隔离。
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
    join_code VARCHAR(16),
    status VARCHAR(16) DEFAULT 'open',
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
    phase VARCHAR(16),
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
CREATE TABLE IF NOT EXISTS career_class_students (
    id VARCHAR(64) PRIMARY KEY,
    class_id VARCHAR(64) NOT NULL,
    student_no VARCHAR(32) DEFAULT '',
    name VARCHAR(128) NOT NULL,
    user_id VARCHAR(64),
    joined_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_career_students_class ON career_class_students(class_id);

-- F6: 知情同意留痕（试用伦理；一人一条，重复同意覆盖更新时间）
CREATE TABLE IF NOT EXISTS career_consents (
    user_id VARCHAR(64) PRIMARY KEY,
    agreed BOOLEAN NOT NULL DEFAULT FALSE,
    version VARCHAR(32) NOT NULL,
    agreed_at TIMESTAMP DEFAULT NOW()
);

-- F6: 课后简评（学生每场会话一条；rating 1-5 整数，comment 选填）
CREATE TABLE IF NOT EXISTS career_feedback (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_career_feedback_session ON career_feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_career_feedback_user ON career_feedback(user_id);

-- F8: 场景生成器产出的自定义场景（draft→人工审核→active 入库；黄金样本仍存 career_scenarios.json）
CREATE TABLE IF NOT EXISTS career_scenarios_custom (
    id VARCHAR(64) PRIMARY KEY,
    scenario_json JSONB,
    job_direction VARCHAR(32),
    scenario_type VARCHAR(32),
    difficulty VARCHAR(16),
    status VARCHAR(16) DEFAULT 'draft',
    created_by VARCHAR(64),
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
    join_code TEXT,
    status TEXT DEFAULT 'open',
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
    phase TEXT,
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
CREATE TABLE IF NOT EXISTS career_class_students (
    id TEXT PRIMARY KEY,
    class_id TEXT NOT NULL,
    student_no TEXT DEFAULT '',
    name TEXT NOT NULL,
    user_id TEXT,
    joined_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_career_students_class ON career_class_students(class_id);

-- F6: 知情同意留痕（试用伦理；一人一条，重复同意覆盖更新时间）
CREATE TABLE IF NOT EXISTS career_consents (
    user_id TEXT PRIMARY KEY,
    agreed INTEGER NOT NULL DEFAULT 0,
    version TEXT NOT NULL,
    agreed_at TEXT DEFAULT (datetime('now'))
);

-- F6: 课后简评（学生每场会话一条；rating 1-5 整数，comment 选填）
CREATE TABLE IF NOT EXISTS career_feedback (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_career_feedback_session ON career_feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_career_feedback_user ON career_feedback(user_id);

-- F8: 场景生成器产出的自定义场景（draft→人工审核→active 入库；黄金样本仍存 career_scenarios.json）
CREATE TABLE IF NOT EXISTS career_scenarios_custom (
    id TEXT PRIMARY KEY,
    scenario_json TEXT,
    job_direction TEXT,
    scenario_type TEXT,
    difficulty TEXT,
    status TEXT DEFAULT 'draft',
    created_by TEXT,
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
        # P4: career_tasks 补 join_code 列（旧库幂等迁移；新库 DDL 已含或迁移后含）
        try:
            pg_client.migrate_exec(
                "ALTER TABLE career_tasks ADD COLUMN join_code VARCHAR(16)" if not pg_client.is_fallback
                else "ALTER TABLE career_tasks ADD COLUMN join_code TEXT")
        except Exception:
            pass  # 列已存在
        # F2: career_tasks 补 status 列（open/closed；旧库幂等迁移，默认 open 即历史任务全部开放）
        try:
            pg_client.migrate_exec(
                "ALTER TABLE career_tasks ADD COLUMN status VARCHAR(16) DEFAULT 'open'" if not pg_client.is_fallback
                else "ALTER TABLE career_tasks ADD COLUMN status TEXT DEFAULT 'open'")
        except Exception:
            pass  # 列已存在
        # F5: career_sessions 补 phase 列（pre/post 前后测标记；旧库幂等迁移，默认 NULL=未标记）
        try:
            pg_client.migrate_exec(
                "ALTER TABLE career_sessions ADD COLUMN phase VARCHAR(16)" if not pg_client.is_fallback
                else "ALTER TABLE career_sessions ADD COLUMN phase TEXT")
        except Exception:
            pass  # 列已存在
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
        "(id,user_id,task_id,scenario_id,scenario_type,scenario_subtype,title,difficulty,max_turns,state,status,turn_count,phase) "
        f"VALUES ({_ph(13)})"
    )
    params = (
        sid, state.get("user_id"), state.get("task_id"),
        state.get("scenario_id", ""), state.get("scenario_type", ""),
        state.get("scenario_subtype", ""), state.get("title", ""),
        state.get("difficulty", "medium"), int(state.get("max_turns", 8)),
        _dumps(state), "ongoing", len(state.get("dialogue_turns", [])),
        state.get("phase"),
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
    sql = (f"SELECT id,scenario_type,scenario_subtype,title,status,turn_count,started_at,finished_at,phase "
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


def list_assessments_by_session(session_id: str) -> list[dict]:
    """返回该会话全部评估记录（按时间正序，最早在前），供回溯重评做新旧对比。"""
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    sql = f"SELECT * FROM career_assessments WHERE session_id={q} ORDER BY created_at ASC"
    if pg_client.is_fallback:
        with pg_client._lock:
            rows = pg_client._conn.execute(sql, (session_id,)).fetchall()
            results = [dict(r) for r in rows]
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, (session_id,))
            cols = [d[0] for d in cur.description]
            results = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in results:
        for k in ("dimension_scores", "evidence_chain", "improvement_plan"):
            r[k] = _loads(r.get(k))
    return results


# ────────────────────────────────────────────────────────────
# P4 教师端：班级 / 花名册 / 任务（任务码）/ 班级看板
# ────────────────────────────────────────────────────────────
def _exec(sql: str, params: tuple):
    if pg_client.is_fallback:
        with pg_client._lock:
            pg_client._conn.execute(sql, params); pg_client._conn.commit()
    else:
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, params)


def _query(sql: str, params: tuple) -> list[dict]:
    if pg_client.is_fallback:
        with pg_client._lock:
            rows = pg_client._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    with pg_client._conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def create_class(teacher_id: str, class_name: str) -> dict:
    ensure_tables()
    cid = new_id("cls")
    _exec(f"INSERT INTO career_classes (id,teacher_id,class_name) VALUES ({_ph(3)})",
          (cid, teacher_id, class_name))
    return {"class_id": cid, "class_name": class_name, "student_count": 0}


def get_class(cid: str, teacher_id: str) -> Optional[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(f"SELECT * FROM career_classes WHERE id={q} AND teacher_id={q}", (cid, teacher_id))
    return rows[0] if rows else None


def list_classes_by_teacher(teacher_id: str) -> list[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    return _query(
        f"SELECT c.id AS class_id, c.class_name, c.created_at, "
        f"(SELECT COUNT(*) FROM career_class_students s WHERE s.class_id=c.id) AS student_count "
        f"FROM career_classes c WHERE c.teacher_id={q} ORDER BY c.created_at DESC", (teacher_id,))


def add_students(cid: str, teacher_id: str, students: list[dict]) -> int:
    """students: [{student_no, name}]；批量插入花名册并同步 student_count"""
    ensure_tables()
    if not get_class(cid, teacher_id):
        raise KeyError("班级不存在或无权操作")
    n = 0
    for stu in students:
        name = (stu.get("name") or "").strip()
        if not name:
            continue
        _exec(f"INSERT INTO career_class_students (id,class_id,student_no,name) VALUES ({_ph(4)})",
              (new_id("stu"), cid, (stu.get("student_no") or "").strip(), name))
        n += 1
    q = "?" if pg_client.is_fallback else "%s"
    _exec(f"UPDATE career_classes SET student_count="
          f"(SELECT COUNT(*) FROM career_class_students WHERE class_id={q}) WHERE id={q}", (cid, cid))
    return n


def list_students(cid: str, teacher_id: str) -> list[dict]:
    ensure_tables()
    if not get_class(cid, teacher_id):
        raise KeyError("班级不存在或无权操作")
    q = "?" if pg_client.is_fallback else "%s"
    return _query(f"SELECT student_no,name,user_id,joined_at FROM career_class_students "
                  f"WHERE class_id={q} ORDER BY student_no ASC", (cid,))


def create_task(teacher_id: str, class_id: str, scenario_id: str,
                scenario_type: str = "", scenario_subtype: str = "",
                difficulty: str = "medium", max_turns: int = 8,
                due_at: Optional[str] = None) -> dict:
    ensure_tables()
    if not get_class(class_id, teacher_id):
        raise KeyError("班级不存在或无权操作")
    tid = new_id("task")
    code = uuid.uuid4().hex[:6].upper()  # 6 位任务码
    _exec("INSERT INTO career_tasks "
          "(id,class_id,teacher_id,scenario_id,scenario_type,scenario_subtype,difficulty,max_turns,due_at,join_code,status) "
          f"VALUES ({_ph(11)})",
          (tid, class_id, teacher_id, scenario_id, scenario_type, scenario_subtype,
           difficulty, int(max_turns), due_at, code, "open"))
    return {"task_id": tid, "join_code": code, "class_id": class_id,
            "scenario_id": scenario_id, "difficulty": difficulty,
            "max_turns": int(max_turns), "due_at": due_at}


def get_task_by_code(code: str) -> Optional[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(f"SELECT * FROM career_tasks WHERE join_code={q} ORDER BY created_at DESC LIMIT 1",
                  ((code or "").strip().upper(),))
    return rows[0] if rows else None


def get_task_by_id(tid: str) -> Optional[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(f"SELECT * FROM career_tasks WHERE id={q}", (tid,))
    return rows[0] if rows else None


def list_tasks_by_teacher(teacher_id: str, class_id: Optional[str] = None) -> list[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    if class_id:
        return _query(f"SELECT id AS task_id,class_id,scenario_id,scenario_type,difficulty,max_turns,due_at,join_code,status,created_at "
                      f"FROM career_tasks WHERE teacher_id={q} AND class_id={q} ORDER BY created_at DESC",
                      (teacher_id, class_id))
    return _query(f"SELECT id AS task_id,class_id,scenario_id,scenario_type,difficulty,max_turns,due_at,join_code,status,created_at "
                  f"FROM career_tasks WHERE teacher_id={q} ORDER BY created_at DESC", (teacher_id,))


def class_dashboard(cid: str, teacher_id: str) -> Optional[dict]:
    """班级学情看板：每生实训完成状态 + 六维均分 + overall（聚合 career_sessions/assessments）

    2026-10-14 新增**班级级聚合**（服务于"报告能回答教学问题"，见 plans/teacher-loop-gap-2026-10-14.md）：
      - ``summary``：参与/完成人数、完成率、全班各维均分、**最弱维度**
      - ``attention``：需关注学生清单，每条带 ``reason``（**结构性事实，可反查**）

    诚实约束（本函数不做主观打分）：
      * 最弱维度是**纯相对排序**（按全班均分升序），**不引入任何绝对阈值**——
        均分高低本身不代表"教学干预线"，教师自行判断。
      * attention 的判定只依据**可反查的结构性事实**（无会话 / 有会话但未完成 / 完成但无可评分结果 /
        得分相对靠后），不编造"学习困难"之类的结论，也不给心理健康或能力定性。
      * 只使用 career_sessions / career_assessments 里真实存在的数据，缺失即标注缺失（None），不插值。
    """
    cls = get_class(cid, teacher_id)
    if not cls:
        return None
    q = "?" if pg_client.is_fallback else "%s"
    roster = list_students(cid, teacher_id)
    # 单查询取本班任务关联的全部会话（替代逐生一查的 N+1：50 人班 = 51 次往返）。
    # 语义与旧逐生查询逐字对齐：LEFT JOIN 保留无评分会话；按 task_id 归属本班过滤；
    # Python 侧只保留花名册内学生的行——非花名册用户（未 join 直接带 task_id 开局）
    # 的会话在旧实现里同样不可见，此处不改变可见性。
    all_rows = _query(
        "SELECT s.user_id AS uid, s.id AS session_id, s.status, s.turn_count, "
        "a.dimension_scores, a.consistency_score "
        "FROM career_sessions s "
        "LEFT JOIN career_assessments a ON a.session_id = s.id "
        f"WHERE s.task_id IN (SELECT id FROM career_tasks WHERE class_id={q}) "
        "ORDER BY s.started_at DESC", (cid,))
    by_user: dict = {}
    for r in all_rows:
        by_user.setdefault(r.get("uid"), []).append(r)
    students = []
    class_dim_acc: dict = {}  # 维度 → [各生该维均分]（用于全班各维均分）
    for stu in roster:
        rows = by_user.get(stu.get("user_id") or "", [])
        sessions = []
        dim_acc: dict = {}
        overall_best = None
        for r in rows:
            # ⚠️ 库里 dimension_scores 存的是**完整 assessment**（形如
            # {"dimensions": {dim: {"score": …}}, "summary": …}），六维在 "dimensions" 之下。
            # 直接遍历顶层键会得到 "dimensions" 本身（其 .get("score") 为 None）⇒ 均分恒空。
            # 兼容早期的扁平形态（顶层即 {dim: {"score": …}}）。
            raw = _loads(r.get("dimension_scores"), {}) or {}
            dims = raw.get("dimensions") if isinstance(raw, dict) and isinstance(raw.get("dimensions"), dict) else raw
            scores = {d: v.get("score") for d, v in dims.items()
                      if isinstance(v, dict) and v.get("score") is not None}
            for d, v in scores.items():
                dim_acc.setdefault(d, []).append(float(v))
            ov = r.get("consistency_score")
            if ov is not None:
                overall_best = max(overall_best or 0, float(ov))
            sessions.append({"session_id": r.get("session_id"), "status": r.get("status"),
                             "turn_count": r.get("turn_count"), "overall": ov})
        dim_avg = {d: round(sum(v) / len(v), 2) for d, v in dim_acc.items() if v}
        for d, v in dim_avg.items():
            class_dim_acc.setdefault(d, []).append(float(v))
        students.append({
            "student_no": stu.get("student_no"), "name": stu.get("name"),
            "user_id": stu.get("user_id"), "bound": bool(stu.get("user_id")),
            "session_count": len(sessions),
            "finished_count": sum(1 for s in sessions if s.get("status") == "finished"),
            "dimension_avg": dim_avg, "overall_best": overall_best,
            "sessions": sessions[:5],
        })

    # ── 班级级聚合 ──
    total = len(students)
    started = [s for s in students if s["session_count"] > 0]
    finished = [s for s in students if s["finished_count"] > 0]
    scored = [s for s in students if s["overall_best"] is not None]
    dimension_avg = {d: round(sum(v) / len(v), 2)
                     for d, v in class_dim_acc.items() if v}
    # 相对排序，不设绝对阈值：均分由低到高，取前 3（不足则全取）
    weakest = sorted(dimension_avg.items(), key=lambda kv: kv[1])[:3]

    attention = []
    for s in students:
        if s["session_count"] == 0:
            attention.append({**s, "reason": "not_started",
                              "detail": "尚未开始任何一场实训（无会话记录）"})
        elif s["finished_count"] == 0:
            attention.append({**s, "reason": "unfinished",
                              "detail": f"已开始 {s['session_count']} 场但未完成任何一场，无有效评估"})
        elif s["overall_best"] is None:
            attention.append({**s, "reason": "no_score",
                              "detail": "已完成实训但没有可评分的维度结果"})
    # 得分相对靠后（后 30%，至少 1 人；仅在有人得分时给出）
    if scored:
        k = max(1, round(len(scored) * 0.3))
        for rank, s in enumerate(sorted(scored, key=lambda x: x["overall_best"])[:k], 1):
            attention.append({**s, "reason": "lowest_score",
                              "detail": f"综合得分在已完成学生中相对靠后（第 {rank}/{len(scored)}）"})

    return {"class_id": cid, "class_name": cls.get("class_name"),
            "student_count": total, "students": students,
            "summary": {
                "student_count": total,
                "started_count": len(started),
                "finished_count": len(finished),
                "assessed_count": len(scored),
                "completion_rate": round(len(finished) / total, 2) if total else 0.0,
                "dimension_avg": dimension_avg,
                "weakest_dimensions": [{"dimension": d, "avg": v} for d, v in weakest],
                "note": "最弱维度为全班均分的相对排序（升序），非绝对达标线；无数据维度不参与最弱排序（六维均分中显示为无数据）。",
            },
            "attention": attention}


def bind_student(class_id: str, user_id: str, name: str = "") -> Optional[dict]:
    """学生凭任务码加入时，把其 user_id 绑定到花名册中的某一行。

    匹配策略（**优先姓名，失败才退回旧行为**）：
      1. 若调用方传入 name，先在该班**未绑定**行中按姓名精确匹配（trim + 大小写不敏感）；
      2. 匹配不到（或未传 name），退回「第一个未绑定行」——保持历史行为，
         避免因姓名写法不一致导致完全无法绑定（宁可绑错位也不能绑不上）。

    Returns: 被绑定的花名册行 ``{"student_no", "name", "matched_by"}``；
             无可绑定行（花名册已满/为空）时返回 ``None``。
             ``matched_by`` ∈ ``{"name", "first_unbound"}``，供调用方如实回传给前端。

    注意：本函数**不自己去查用户姓名**（career_store 只依赖 pg_client，不做用户域查询）——
    姓名由调用方 ``api/career_training.join_task`` 传入。

    历史说明：本函数原 docstring 写作「按姓名匹配未绑定行」，但实现是直接取第一个未绑定行，
    名实不符。**2026-10-14 补上真实姓名匹配**（此前 30 人同时加入会张冠李戴）。
    """
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(
        f"SELECT id, student_no, name FROM career_class_students "
        f"WHERE class_id={q} AND user_id IS NULL", (class_id,))
    if not rows:
        return None
    target = (name or "").strip().lower()
    picked = None
    matched_by = "first_unbound"
    if target:
        picked = next(
            (r for r in rows if (r.get("name") or "").strip().lower() == target), None)
        if picked is not None:
            matched_by = "name"
    if picked is None:
        picked = rows[0]
    _exec(f"UPDATE career_class_students SET user_id={q} WHERE id={q}",
          (user_id, picked["id"]))
    return {"student_no": picked.get("student_no"), "name": picked.get("name"),
            "matched_by": matched_by}


# ────────────────────────────────────────────────────────────
# F1 学生个体下钻（2026-10-15）：教师查看班内单个学生的全部会话明细
# ────────────────────────────────────────────────────────────
def student_detail(cid: str, teacher_id: str, user_id: str) -> Optional[dict]:
    """班级内单个学生的实训明细（教师下钻用）。

    权限：班级必须属于该教师；学生必须在该班花名册内且已绑定账号。
    返回该生**本班任务下**的会话（不受看板 5 条截断限制）+ 每场六维分 /
    overall / 轮数 / 起止时间。

    口径边界（与 class_dashboard 一致）：只统计 ``task_id`` 归属本班任务的会话——
    学生的**自由练习**（无任务关联）不计入班级视角，故此处并非"该生全部会话"，
    个人全部会话见学生端 ``growth_profile``。

    诚实约束：只呈现真实落库数据；无评分会话的 dimension_scores 为 {}（不插值），
    overall_best 仅在有真实 consistency_score 时给出。
    """
    cls = get_class(cid, teacher_id)
    if not cls:
        return None
    roster = list_students(cid, teacher_id)
    stu = next((s for s in roster if s.get("user_id") == user_id), None)
    if not stu:
        raise KeyError("学生不在该班花名册或未绑定账号")
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(
        "SELECT s.id AS session_id, s.status, s.turn_count, s.started_at, s.finished_at, "
        "s.scenario_id, s.difficulty, a.dimension_scores, a.consistency_score "
        "FROM career_sessions s LEFT JOIN career_assessments a ON a.session_id = s.id "
        f"WHERE s.user_id={q} AND s.task_id IN (SELECT id FROM career_tasks WHERE class_id={q}) "
        "ORDER BY s.started_at DESC", (user_id, cid))
    sessions = []
    dim_acc: dict = {}
    for r in rows:
        # 与 class_dashboard 同口径：dimension_scores 存完整 assessment，六维在 "dimensions" 之下
        raw = _loads(r.get("dimension_scores"), {}) or {}
        dims = raw.get("dimensions") if isinstance(raw, dict) and isinstance(raw.get("dimensions"), dict) else raw
        scores = {d: v.get("score") for d, v in dims.items()
                  if isinstance(v, dict) and v.get("score") is not None}
        for d, v in scores.items():
            dim_acc.setdefault(d, []).append(float(v))
        finished_at = r.get("finished_at")
        sessions.append({
            "session_id": r.get("session_id"), "status": r.get("status"),
            "turn_count": r.get("turn_count"),
            "started_at": str(r.get("started_at") or ""),
            "finished_at": str(finished_at) if finished_at else None,
            "scenario_id": r.get("scenario_id"), "difficulty": r.get("difficulty"),
            "dimension_scores": scores, "overall": r.get("consistency_score"),
        })
    dim_avg = {d: round(sum(v) / len(v), 2) for d, v in dim_acc.items() if v}
    overalls = [s["overall"] for s in sessions if s["overall"] is not None]
    return {"student_no": stu.get("student_no"), "name": stu.get("name"),
            "user_id": user_id, "session_count": len(sessions),
            "finished_count": sum(1 for s in sessions if s.get("status") == "finished"),
            "dimension_avg": dim_avg,
            "overall_best": max(overalls) if overalls else None,
            "sessions": sessions}


# ────────────────────────────────────────────────────────────
# F2 任务管理中心（2026-10-15）：任务参与进度 + 关闭任务
# ────────────────────────────────────────────────────────────
def task_stats(tid: str, teacher_id: str) -> Optional[dict]:
    """任务参与进度：按该任务的**真实会话**计已开始/已完成**人数**。

    诚实口径：
    - 只有真的建了会话的学生才计入"已开始"——没有"加入但未开始"的
      Join 日志，就不虚构"已加入人数"这个数。
    - ``started_count`` / ``finished_count`` 均为**去重学生数**（数人不数场，
      与 ``class_dashboard.summary`` 同口径）；``session_count`` 是会话总数。
      一名学生重复开多场只计 1 人——前端标签是"人"，口径必须撑得起这个字。
    """
    task = get_task_by_id(tid)
    if not task or task.get("teacher_id") != teacher_id:
        return None
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(f"SELECT user_id, status FROM career_sessions WHERE task_id={q}", (tid,))
    started_users = {r.get("user_id") for r in rows if r.get("user_id")}
    finished_users = {r.get("user_id") for r in rows
                      if r.get("user_id") and r.get("status") == "finished"}
    return {"task_id": tid, "started_count": len(started_users),
            "finished_count": len(finished_users), "session_count": len(rows)}


def close_task(tid: str, teacher_id: str) -> Optional[dict]:
    """关闭任务：学生端"我的任务"不再出现；历史会话/评分数据保留不动（不删任何数据）。"""
    ensure_tables()
    task = get_task_by_id(tid)
    if not task or task.get("teacher_id") != teacher_id:
        return None
    q = "?" if pg_client.is_fallback else "%s"
    _exec(f"UPDATE career_tasks SET status='closed' WHERE id={q}", (tid,))
    return {"task_id": tid, "status": "closed"}


# ────────────────────────────────────────────────────────────
# F3 学生任务中心（2026-10-15）：我已绑定班级的开放任务（免手输任务码）
# ────────────────────────────────────────────────────────────
def my_tasks(user_id: str) -> list[dict]:
    """学生任务中心：该生已绑定班级的**开放**任务，按新到旧。

    只列 open —— 已关闭任务不出现（close_task 的语义）；已绑定由 join 时
    bind_student 落库。join_code 原样带回，前端一键加入走与手输相同的
    POST /career/task/join 路径（不开第二条信任链）。
    """
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    return _query(
        "SELECT t.id AS task_id, t.join_code, t.scenario_id, t.difficulty, t.max_turns, "
        "t.due_at, t.created_at, c.class_name "
        "FROM career_tasks t "
        "JOIN career_class_students s ON s.class_id = t.class_id "
        "JOIN career_classes c ON c.id = t.class_id "
        f"WHERE s.user_id={q} AND t.status='open' "
        "ORDER BY t.created_at DESC LIMIT 50", (user_id,))


# ────────────────────────────────────────────────────────────
# F4 个人成长页（2026-10-15）：学生全部会话的六维趋势 + 证据金句 + 前后测对比
# ────────────────────────────────────────────────────────────
def _extract_quotes(evidence_chain, limit: int = 6) -> list[dict]:
    """从真实 evidence_chain 提取学生原话金句（dimension/quote/turn/polarity）。

    只取评估真实引用过的原话：evidence_quotes 与 per_turn_evidence.answer_snippet，
    不编造、不改写。
    """
    out: list[dict] = []
    for item in (evidence_chain or []):
        if len(out) >= limit:
            break
        if not isinstance(item, dict):
            continue
        label = item.get("label", "") or item.get("dimension", "") or "维度"
        score = item.get("score")
        for q in (item.get("evidence_quotes") or []):
            if len(out) >= limit:
                break
            text = (q or "").strip() if isinstance(q, str) else ""
            if text:
                out.append({"dimension": label, "score": score, "quote": text,
                            "turn": None, "polarity": ""})
        for h in (item.get("per_turn_evidence") or []):
            if len(out) >= limit:
                break
            if not isinstance(h, dict):
                continue
            snippet = (h.get("answer_snippet", "") or "").strip()
            if snippet:
                out.append({"dimension": label, "score": score, "quote": snippet,
                            "turn": h.get("turn"), "polarity": h.get("polarity", "")})
    return out


def growth_profile(user_id: str) -> dict:
    """学生个人成长画像：全部会话（新→旧）+ 六维趋势 + 证据金句 + 前后测对比。

    诚信约束：
    - 只统计 status=finished 且真有评估记录的会话进入趋势/对比（未完成场次只在明细里如实呈现）；
    - phase_compare 仅当 pre 与 post **都有**已评分会话时给出该维度差值，缺一侧就不出这个数（不插值）；
    - 金句只从评估真实引用过的原话提取。
    """
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(
        "SELECT s.id AS session_id, s.title, s.scenario_id, s.status, s.phase, "
        "s.turn_count, s.started_at, s.finished_at, a.dimension_scores, a.evidence_chain, "
        "a.consistency_score "
        "FROM career_sessions s LEFT JOIN career_assessments a ON a.session_id = s.id "
        f"WHERE s.user_id={q} ORDER BY s.started_at DESC LIMIT 100", (user_id,))
    sessions: list[dict] = []
    trend: dict = {}          # dim -> [{"date","score","phase"}]（按时间正序，前端画趋势）
    phase_acc: dict = {}      # phase -> dim -> [scores]
    all_quotes: list[dict] = []
    for r in rows:
        raw = _loads(r.get("dimension_scores"), {}) or {}
        dims = raw.get("dimensions") if isinstance(raw, dict) and isinstance(raw.get("dimensions"), dict) else raw
        scores = {d: v.get("score") for d, v in dims.items()
                  if isinstance(v, dict) and v.get("score") is not None}
        started = str(r.get("started_at") or "")
        phase = r.get("phase") or None
        finished = r.get("status") == "finished"
        overall = r.get("consistency_score") if finished else None
        sessions.append({
            "session_id": r.get("session_id"), "title": r.get("title", ""),
            "scenario_id": r.get("scenario_id"), "status": r.get("status"),
            "phase": phase, "turn_count": r.get("turn_count"),
            "started_at": started,
            "finished_at": str(r["finished_at"]) if r.get("finished_at") else None,
            "dimension_scores": scores, "overall": overall,
        })
        if not finished:
            continue  # 未完成场次不进趋势/对比（无评估）
        for d, v in scores.items():
            trend.setdefault(d, []).append({"date": started[:10], "score": float(v), "phase": phase})
            if phase in ("pre", "post"):
                phase_acc.setdefault(phase, {}).setdefault(d, []).append(float(v))
        quotes = _extract_quotes(_loads(r.get("evidence_chain"), []))
        for item in quotes:
            item["session_id"] = r.get("session_id")
            item["started_at"] = started
        all_quotes.extend(quotes)
    # 趋势按时间正序（画图从左到右）
    for d in trend:
        trend[d].sort(key=lambda x: x["date"])
    dim_avg = {d: round(sum(x["score"] for x in pts) / len(pts), 2) for d, pts in trend.items() if pts}
    # 前后测对比：仅两侧都有的维度才给差值（探索性观察口径，不作显著性宣称）
    phase_compare = None
    if "pre" in phase_acc and "post" in phase_acc:
        pre_avg = {d: round(sum(v) / len(v), 2) for d, v in phase_acc["pre"].items() if v}
        post_avg = {d: round(sum(v) / len(v), 2) for d, v in phase_acc["post"].items() if v}
        delta = {d: round(post_avg[d] - pre_avg[d], 2)
                 for d in post_avg if d in pre_avg}
        if delta:
            phase_compare = {"pre": pre_avg, "post": post_avg, "delta": delta,
                             "note": "单组前后测·探索性观察：仅呈现同维度分值差，不排除练习/记忆效应，不作因果与显著性宣称"}
    return {"user_id": user_id, "session_count": len(sessions),
            "finished_count": sum(1 for s in sessions if s["status"] == "finished"),
            "sessions": sessions, "dimension_trend": trend, "dimension_avg": dim_avg,
            "phase_compare": phase_compare, "quotes": all_quotes[:30]}


# ────────────────────────────────────────────────────────────
# F6 知情同意与课后简评（2026-10-15）：试用伦理留痕 + 满意度数据
# ────────────────────────────────────────────────────────────
CONSENT_VERSION = "2026-10-15-v1"

CONSENT_TEXT = (
    "知情同意：本实训系统会记录你的作答、六维评分与改进建议，用于产品改进与"
    "汇总统计分析（报告中只呈现匿名汇总，不点名个人）。你的答题数据不会分享给"
    "无关第三方。如不同意，你仍可使用系统自由练习，但数据不会被纳入试用分析。"
)


def record_consent(user_id: str, agreed: bool, version: str = CONSENT_VERSION) -> dict:
    """记录/更新知情同意（一人一条；重复提交覆盖 agreed/version/时间）。"""
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    now_expr = "datetime('now')" if pg_client.is_fallback else "NOW()"
    sql = ("INSERT INTO career_consents (user_id, agreed, version, agreed_at) "
           f"VALUES ({q},{q},{q},{now_expr}) "
           f"ON CONFLICT(user_id) DO UPDATE SET agreed={q}, version={q}, agreed_at={now_expr}")
    _exec(sql, (user_id, 1 if agreed else 0, version, 1 if agreed else 0, version))
    return {"user_id": user_id, "agreed": bool(agreed), "version": version}


def get_consent(user_id: str) -> Optional[dict]:
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(f"SELECT user_id, agreed, version, agreed_at FROM career_consents WHERE user_id={q}",
                  (user_id,))
    if not rows:
        return None
    r = rows[0]
    return {"user_id": r.get("user_id"),
            "agreed": bool(r.get("agreed")),
            "version": r.get("version"),
            "agreed_at": str(r.get("agreed_at") or "")}


def save_feedback(session_id: str, user_id: str, rating: int, comment: str = "") -> dict:
    """保存课后简评（每场会话一条：重复提交更新原记录，不叠加）。"""
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    existing = _query(f"SELECT id FROM career_feedback WHERE session_id={q}", (session_id,))
    if existing:
        _exec(f"UPDATE career_feedback SET rating={q}, comment={q} WHERE session_id={q}",
              (rating, comment, session_id))
        return {"session_id": session_id, "rating": rating, "updated": True}
    fid = new_id("fb")
    _exec(f"INSERT INTO career_feedback (id, session_id, user_id, rating, comment) VALUES ({q},{q},{q},{q},{q})",
          (fid, session_id, user_id, rating, comment))
    return {"session_id": session_id, "rating": rating, "updated": False}


def list_feedback(teacher_id: str, class_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    """教师查看本人班级学生的课后简评（按班级归属隔离，看不到别班学生的评价）。

    归属路径走 反馈→会话→任务→班级（会话真实的班级），不按学生绑定关系 JOIN——
    否则一个学生在本人多个班有绑定行时，同一份简评会被重复放大。
    """
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    sql = (
        "SELECT DISTINCT f.id, f.session_id, f.user_id, f.rating, f.comment, f.created_at, "
        "s.name AS student_name, c.class_name "
        "FROM career_feedback f "
        "JOIN career_sessions sess ON sess.id = f.session_id "
        "JOIN career_tasks t ON t.id = sess.task_id "
        "JOIN career_classes c ON c.id = t.class_id "
        "LEFT JOIN career_class_students s ON s.user_id = f.user_id AND s.class_id = c.id "
        f"WHERE c.teacher_id={q}"
    )
    params: list = [teacher_id]
    if class_id:
        sql += f" AND c.id={q}"
        params.append(class_id)
    sql += f" ORDER BY f.created_at DESC LIMIT {int(limit)}"
    return _query(sql, tuple(params))


# ────────────────────────────────────────────────────────────
# F8 场景生成器（2026-10-18）：草稿 → 人工审核 → active 入库
# ────────────────────────────────────────────────────────────
def save_generated_scenario(scenario: dict, job_direction: str, scenario_type: str,
                            difficulty: str, created_by: str = "",
                            status: str = "draft") -> str:
    """保存生成器产出的自定义场景（默认 draft，人工审核后 active）。"""
    ensure_tables()
    sid = scenario.get("id") or new_id("gensc")
    _exec(
        "INSERT INTO career_scenarios_custom "
        "(id,scenario_json,job_direction,scenario_type,difficulty,status,created_by) "
        f"VALUES ({_ph(7)})",
        (sid, _dumps(scenario), job_direction, scenario_type, difficulty, status, created_by),
    )
    return sid


def list_generated_scenarios(status: Optional[str] = None) -> list[dict]:
    """列出生成场景（可过滤 status）；返回完整 scenario dict 列表。"""
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    sql = ("SELECT id, scenario_json, job_direction, scenario_type, difficulty, status, created_by, created_at "
           "FROM career_scenarios_custom")
    params: list = []
    if status:
        sql += f" WHERE status={q}"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    out = []
    for r in _query(sql, tuple(params)):
        sc = _loads(r.get("scenario_json"), {})
        if isinstance(sc, dict):
            out.append(sc)
    return out


def get_generated_scenario(scenario_id: str) -> Optional[dict]:
    """按 id 取单个生成场景（任意 status）。"""
    ensure_tables()
    q = "?" if pg_client.is_fallback else "%s"
    rows = _query(f"SELECT scenario_json FROM career_scenarios_custom WHERE id={q}", (scenario_id,))
    if not rows:
        return None
    sc = _loads(rows[0].get("scenario_json"), {})
    return sc if isinstance(sc, dict) else None


def activate_generated_scenario(scenario_id: str) -> Optional[dict]:
    """人工审核通过：draft → active。返回激活后的场景；不存在返回 None。"""
    ensure_tables()
    if get_generated_scenario(scenario_id) is None:
        return None
    q = "?" if pg_client.is_fallback else "%s"
    _exec(f"UPDATE career_scenarios_custom SET status='active' WHERE id={q}", (scenario_id,))
    return get_generated_scenario(scenario_id)
