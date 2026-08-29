# ============================================================
# 用户数据持久化 — SQLite（零外部依赖）
# 每用户数据隔离：profile / quiz_history / conversations
# 管理员聚合：list_all_users / get_platform_stats
# ============================================================

import os
import json
import sqlite3
import threading
import hashlib
import hmac
import secrets
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger("netlearn.userstore")

# 支持 NETLEARN_USER_DB 环境变量覆盖 DB 路径（测试隔离用，低侵入）
_DB_PATH = os.environ.get("NETLEARN_USER_DB") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "netlearn_users.db"
)
os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)

_conn: Optional[sqlite3.Connection] = None
# RLock（可重入）：读路径与写路径共用同一把锁；list_all_users/get_platform_stats
# 内部会回调 get_profile 等读函数，非重入 Lock 会死锁，故用 RLock。
_lock = threading.RLock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _init_schema(_conn)
    return _conn


def get_db_conn() -> sqlite3.Connection:
    """公开别名：供 main.competition_status 等外部模块获取底层连接（私有 _get_conn 的公开出口）"""
    return _get_conn()


def _init_schema(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT 'student',
        created_at TEXT NOT NULL
    );
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
    CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        subject TEXT NOT NULL DEFAULT '',
        chapter TEXT NOT NULL DEFAULT '',
        quiz_snapshot_json TEXT NOT NULL DEFAULT '[]',
        knowledge_points_json TEXT NOT NULL DEFAULT '[]',
        deadline TEXT NOT NULL DEFAULT '',
        created_by TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS assignment_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        answers_json TEXT NOT NULL DEFAULT '[]',
        score REAL NOT NULL DEFAULT 0,
        submitted_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_wrong_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        question_id TEXT NOT NULL,
        question_json TEXT NOT NULL DEFAULT '{}',
        subject TEXT NOT NULL DEFAULT '',
        chapter TEXT NOT NULL DEFAULT '',
        knowledge_point TEXT NOT NULL DEFAULT '',
        wrong_answer TEXT NOT NULL DEFAULT '',
        correct_answer TEXT NOT NULL DEFAULT '',
        error_type TEXT NOT NULL DEFAULT 'concept',
        wrong_count INTEGER NOT NULL DEFAULT 1,
        mastered INTEGER NOT NULL DEFAULT 0,
        last_wrong_at TEXT NOT NULL,
        first_wrong_at TEXT NOT NULL,
        UNIQUE(user_id, question_id)
    );
    CREATE TABLE IF NOT EXISTS user_daily_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        plan_date TEXT NOT NULL,
        tasks_json TEXT NOT NULL DEFAULT '[]',
        total_tasks INTEGER NOT NULL DEFAULT 0,
        completed_tasks INTEGER NOT NULL DEFAULT 0,
        target_exam_date TEXT NOT NULL DEFAULT '',
        target_score INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, plan_date)
    );
    CREATE TABLE IF NOT EXISTS learning_resources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_user_id TEXT NOT NULL,
        resource_type TEXT NOT NULL DEFAULT 'reading_material',
        title TEXT NOT NULL DEFAULT '',
        content_hash TEXT NOT NULL DEFAULT '',
        content_json TEXT NOT NULL DEFAULT '{}',
        quality_score REAL,
        status TEXT NOT NULL DEFAULT 'active',
        visibility TEXT NOT NULL DEFAULT 'private',
        version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_resource_owner ON learning_resources(owner_user_id);
    CREATE INDEX IF NOT EXISTS idx_resource_type ON learning_resources(resource_type);
    CREATE INDEX IF NOT EXISTS idx_resource_hash ON learning_resources(content_hash);
    CREATE INDEX IF NOT EXISTS idx_snapshot_user ON profile_snapshots(user_id);
    CREATE INDEX IF NOT EXISTS idx_quiz_user ON user_quiz_history(user_id);
    CREATE INDEX IF NOT EXISTS idx_conv_user ON user_conversations(user_id);
    CREATE INDEX IF NOT EXISTS idx_assignment_owner ON assignments(created_by);
    CREATE INDEX IF NOT EXISTS idx_submission_assignment ON assignment_submissions(assignment_id);
    CREATE INDEX IF NOT EXISTS idx_submission_user ON assignment_submissions(user_id);
    CREATE INDEX IF NOT EXISTS idx_wrong_user ON user_wrong_questions(user_id);
    CREATE INDEX IF NOT EXISTS idx_wrong_subject ON user_wrong_questions(subject);
    CREATE INDEX IF NOT EXISTS idx_wrong_mastered ON user_wrong_questions(user_id, mastered);
    CREATE INDEX IF NOT EXISTS idx_plan_user_date ON user_daily_plans(user_id, plan_date);
    """)
    # 迁移：错题表增加 attribution_json 列（智能归因结果），已存在则跳过
    _cols = [r[1] for r in conn.execute("PRAGMA table_info(user_wrong_questions)")]
    if "attribution_json" not in _cols:
        conn.execute(
            "ALTER TABLE user_wrong_questions ADD COLUMN attribution_json TEXT NOT NULL DEFAULT '{}'"
        )
    conn.commit()


# ── 密码哈希（PBKDF2-HMAC-SHA256，加盐） ──
# OWASP 推荐 PBKDF2-HMAC-SHA256 ≥ 600_000 次迭代；存储串内嵌迭代次数，便于未来升级且不破坏旧账户
PBKDF2_ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 8


def _hash_password(password: str, salt: Optional[str] = None):
    """返回带迭代次数的存储串: pbkdf2$sha256$<iters>$<salt_hex>$<hash_hex>"""
    if salt is None:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2$sha256${PBKDF2_ITERATIONS}${salt}${pw_hash.hex()}", salt


def _verify_password(password: str, stored: str, salt: str) -> bool:
    """校验密码；兼容旧格式（纯 hex，默认 100_000 次）。使用常量时间比较防侧信道。"""
    if stored.count("$") == 4:
        try:
            _, _, iters_str, _, hash_hex = stored.split("$")
            iters = int(iters_str)
        except Exception:
            iters, hash_hex = 100_000, stored
    else:
        iters, hash_hex = 100_000, stored
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iters)
    return hmac.compare_digest(pw_hash.hex(), hash_hex)


# ── 用户账户 ──

def create_user(username: str, password: str, display_name: str = "", role: str = "student") -> dict:
    conn = _get_conn()
    username = (username or "").strip()
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码长度至少 {MIN_PASSWORD_LENGTH} 位")
    with _lock:
        existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            raise ValueError("用户名已存在")
        user_id = "u_" + secrets.token_hex(8)
        pw_hash, salt = _hash_password(password)
        created_at = _now()
        conn.execute(
            "INSERT INTO users (id, username, password_hash, salt, display_name, role, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, username, pw_hash, salt, display_name or username, role, created_at),
        )
        conn.commit()
    return {"id": user_id, "username": username, "display_name": display_name or username, "role": role, "created_at": created_at}


# 防用户名枚举：用户不存在时仍执行一轮 PBKDF2（固定常量），
# 使 verify 耗时与正常路径相近，消除时序侧信道差异。
_DUMMY_SALT = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"  # 32 hex = 16 bytes
_DUMMY_HASH = "pbkdf2$sha256$600000$_DUMMY_SALT$" + "0" * 64

def authenticate(username: str, password: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", ((username or "").strip(),)).fetchone()
    if not row:
        # 用户名不存在：仍执行 PBKDF2 防时序枚举（固定盐值，结果丢弃）
        _verify_password(password, _DUMMY_HASH, _DUMMY_SALT)
        return None
    if not _verify_password(password, row["password_hash"], row["salt"]):
        return None
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "role": row["role"], "created_at": row["created_at"]}


def get_user_by_id(user_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return None
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"], "role": row["role"], "created_at": row["created_at"]}


def ensure_admin(username: str, password: str, display_name: str = "系统管理员"):
    """幂等创建管理员账号（仅当该用户名不存在时）"""
    conn = _get_conn()
    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if row:
        return
    create_user(username, password, display_name, role="admin")
    logger.info(f"已创建管理员账号: {username}")


# ── 每用户画像 ──

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

def list_all_users() -> list[dict]:
    """返回所有用户及其画像/答题/对话统计（供管理员看板）— 批量查询优化"""
    with _lock:
        conn = _get_conn()
        users = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        uids = [u["id"] for u in users]
        if not uids:
            return []

        # 批量查询画像（一次取所有）
        profiles = {}
        profile_rows = conn.execute(
            "SELECT user_id, profile_json FROM user_profiles WHERE user_id IN ({})".format(
                ",".join(["?"] * len(uids))
            ), uids
        ).fetchall()
        for pr in profile_rows:
            try:
                profiles[pr["user_id"]] = json.loads(pr["profile_json"])
            except Exception:
                profiles[pr["user_id"]] = {}

        # 批量查询答题历史（一次取所有）
        all_quiz_rows = conn.execute(
            "SELECT user_id, subject, correct FROM user_quiz_history WHERE user_id IN ({})".format(
                ",".join(["?"] * len(uids))
            ), uids
        ).fetchall()

        # 批量查询对话统计（一次取所有）
        conv_counts = {}
        conv_rows = conn.execute(
            "SELECT user_id, COUNT(*) AS c FROM user_conversations WHERE user_id IN ({}) GROUP BY user_id".format(
                ",".join(["?"] * len(uids))
            ), uids
        ).fetchall()
        for cr in conv_rows:
            conv_counts[cr["user_id"]] = cr["c"]

        # 按 user_id 分组答题数据
        quiz_by_user: dict[str, list[dict]] = {}
        for q in all_quiz_rows:
            uid = q["user_id"]
            if uid not in quiz_by_user:
                quiz_by_user[uid] = []
            quiz_by_user[uid].append(q)

        result = []
        for u in users:
            uid = u["id"]
            profile = profiles.get(uid, {})
            quiz_rows = quiz_by_user.get(uid, [])
            total = len(quiz_rows)
            correct = sum(1 for q in quiz_rows if q["correct"])
            by_subject = {}
            for q in quiz_rows:
                s = q["subject"] or "unknown"
                by_subject.setdefault(s, {"total": 0, "correct": 0})
                by_subject[s]["total"] += 1
                if q["correct"]:
                    by_subject[s]["correct"] += 1
            for s in by_subject:
                by_subject[s]["accuracy"] = round(by_subject[s]["correct"] / max(by_subject[s]["total"], 1), 3)
            result.append({
                "id": uid,
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
                "created_at": u["created_at"],
                "profile": profile,
                "quiz_total": total,
                "quiz_correct": correct,
                "quiz_accuracy": round(correct / max(total, 1), 3),
                "by_subject": by_subject,
                "conversation_count": conv_counts.get(uid, 0),
            })
        return result


def get_platform_stats() -> dict:
    """平台级看板统计数据"""
    with _lock:
        conn = _get_conn()
        user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        student_count = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role='student'").fetchone()["c"]
        admin_count = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin'").fetchone()["c"]
        quiz_rows = conn.execute("SELECT user_id, subject, correct FROM user_quiz_history").fetchall()
        total_quiz = len(quiz_rows)
        correct_quiz = sum(1 for q in quiz_rows if q["correct"])
        active_row = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS c FROM (SELECT user_id FROM user_quiz_history UNION SELECT user_id FROM user_conversations)"
        ).fetchone()
        active_users = active_row["c"] if active_row else 0

        by_subject = {}
        for q in quiz_rows:
            s = q["subject"] or "unknown"
            by_subject.setdefault(s, {"total": 0, "correct": 0})
            by_subject[s]["total"] += 1
            if q["correct"]:
                by_subject[s]["correct"] += 1
        for s in by_subject:
            by_subject[s]["accuracy"] = round(by_subject[s]["correct"] / max(by_subject[s]["total"], 1), 3)

        today = datetime.now()
        daily = []
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            cnt = conn.execute("SELECT COUNT(*) AS c FROM user_quiz_history WHERE substr(timestamp,1,10)=?", (d,)).fetchone()["c"]
            daily.append({"date": d, "count": cnt})

        return {
            "user_count": user_count,
            "student_count": student_count,
            "admin_count": admin_count,
            "active_users": active_users,
            "total_quiz": total_quiz,
            "correct_quiz": correct_quiz,
            "overall_accuracy": round(correct_quiz / max(total_quiz, 1), 3),
            "by_subject": by_subject,
            "daily_quiz": daily,
        }


# ── 画像快照（历史对比） ──


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


def create_assignment(
    title: str,
    quiz_snapshot: list,
    *,
    subject: str = "",
    chapter: str = "",
    knowledge_points: list | None = None,
    deadline: str = "",
    created_by: str = "",
) -> dict:
    """发布作业：保存测验 JSON 快照（不受题库后续编辑影响）"""
    import json
    conn = _get_conn()
    now = _now()
    with _lock:
        cursor = conn.execute(
            "INSERT INTO assignments (title, subject, chapter, quiz_snapshot_json, knowledge_points_json, deadline, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                title.strip(),
                subject or "",
                chapter or "",
                json.dumps(quiz_snapshot or [], ensure_ascii=False),
                json.dumps(knowledge_points or [], ensure_ascii=False),
                deadline or "",
                created_by,
                now,
            ),
        )
        conn.commit()
        assignment_id = cursor.lastrowid or 0
    return get_assignment(assignment_id)


def get_assignment(assignment_id: int) -> Optional[dict]:
    """获取单个作业（含快照与提交统计）"""
    import json
    conn = _get_conn()
    with _lock:
        row = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
        if not row:
            return None
        submissions = conn.execute(
            "SELECT * FROM assignment_submissions WHERE assignment_id=?", (assignment_id,)
        ).fetchall()
    try:
        quiz_snapshot = json.loads(row["quiz_snapshot_json"])
    except Exception:
        quiz_snapshot = []
    try:
        knowledge_points = json.loads(row["knowledge_points_json"])
    except Exception:
        knowledge_points = []

    # 提交率：学生总数中已提交的人数
    student_count = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role='student'").fetchone()["c"]
    submitted_count = len(submissions)
    scores = [s["score"] for s in submissions]
    avg_score = round(sum(scores) / max(len(scores), 1), 1)
    correct_answers = sum(1 for s in submissions if s["score"] >= 60)
    pass_rate = round(correct_answers / max(len(scores), 1), 2)

    return {
        "id": row["id"],
        "title": row["title"],
        "subject": row["subject"],
        "chapter": row["chapter"],
        "quiz_snapshot": quiz_snapshot,
        "knowledge_points": knowledge_points,
        "deadline": row["deadline"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "stats": {
            "student_count": student_count,
            "submitted_count": submitted_count,
            "submission_rate": round(submitted_count / max(student_count, 1), 2),
            "avg_score": avg_score,
            "pass_rate": pass_rate,
        },
    }


def list_assignments(limit: int = 50) -> list[dict]:
    """列出全部作业（按发布时间倒序）"""
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT id FROM assignments ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [get_assignment(r["id"]) for r in rows if r["id"]]


def submit_assignment(
    assignment_id: int,
    user_id: str,
    answers: list,
    score: float,
) -> dict:
    """提交作业（同用户同作业只保留最新一次）"""
    import json
    conn = _get_conn()
    now = _now()
    with _lock:
        conn.execute(
            "DELETE FROM assignment_submissions WHERE assignment_id=? AND user_id=?",
            (assignment_id, user_id),
        )
        cursor = conn.execute(
            "INSERT INTO assignment_submissions (assignment_id, user_id, answers_json, score, submitted_at) "
            "VALUES (?,?,?,?,?)",
            (assignment_id, user_id, json.dumps(answers or [], ensure_ascii=False), score, now),
        )
        conn.commit()
    return {
        "id": cursor.lastrowid or 0,
        "assignment_id": assignment_id,
        "user_id": user_id,
        "score": score,
        "submitted_at": now,
    }


def get_submission(assignment_id: int, user_id: str) -> Optional[dict]:
    """获取用户在指定作业的提交（未提交返回 None）"""
    import json
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT * FROM assignment_submissions WHERE assignment_id=? AND user_id=?",
            (assignment_id, user_id),
        ).fetchone()
    if not row:
        return None
    try:
        answers = json.loads(row["answers_json"])
    except Exception:
        answers = []
    return {
        "id": row["id"],
        "assignment_id": row["assignment_id"],
        "user_id": row["user_id"],
        "answers": answers,
        "score": row["score"],
        "submitted_at": row["submitted_at"],
    }


# ── 可复用学习资源池（幂等登记 + 内容哈希去重） ──


def _resource_content_hash(resource_type: str, content: dict) -> str:
    """内容哈希：类型 + 规范化 JSON，用于跨资源去重"""
    import hashlib
    import json as _json
    normalized = _json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256()
    digest.update(resource_type.encode("utf-8"))
    digest.update(normalized.encode("utf-8"))
    return digest.hexdigest()


def register_learning_resource(
    owner_user_id: str,
    resource_type: str,
    title: str,
    content: dict,
    *,
    quality_score: Optional[float] = None,
) -> dict:
    """登记可复用学习资源；内容哈希相同则幂等返回已有资源（不重复登记）"""
    import json
    conn = _get_conn()
    now = _now()
    content_hash = _resource_content_hash(resource_type or "reading_material", content or {})
    with _lock:
        existing = conn.execute(
            "SELECT id FROM learning_resources WHERE owner_user_id=? AND content_hash=? AND status='active'",
            (owner_user_id, content_hash),
        ).fetchone()
        if existing:
            return get_learning_resource(existing["id"])
        cursor = conn.execute(
            "INSERT INTO learning_resources "
            "(owner_user_id, resource_type, title, content_hash, content_json, quality_score, status, visibility, version, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                owner_user_id,
                (resource_type or "reading_material"),
                (title or "").strip(),
                content_hash,
                json.dumps(content or {}, ensure_ascii=False),
                quality_score,
                "active",
                "private",
                1,
                now,
            ),
        )
        conn.commit()
        return get_learning_resource(cursor.lastrowid or 0)


def get_learning_resource(resource_id: int) -> Optional[dict]:
    """获取单个资源（含内容）"""
    import json
    conn = _get_conn()
    with _lock:
        row = conn.execute("SELECT * FROM learning_resources WHERE id=?", (resource_id,)).fetchone()
    if not row:
        return None
    try:
        content = json.loads(row["content_json"])
    except Exception:
        content = {}
    return {
        "id": row["id"],
        "owner_user_id": row["owner_user_id"],
        "resource_type": row["resource_type"],
        "title": row["title"],
        "content": content,
        "quality_score": row["quality_score"],
        "status": row["status"],
        "visibility": row["visibility"],
        "version": row["version"],
        "created_at": row["created_at"],
    }


def list_learning_resources(owner_user_id: str, limit: int = 50) -> list[dict]:
    """列出用户私有可复用资源（仅 active）"""
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT id FROM learning_resources "
            "WHERE owner_user_id=? AND status='active' AND visibility='private' "
            "ORDER BY id DESC LIMIT ?",
            (owner_user_id, limit),
        ).fetchall()
    resources = []
    for r in rows:
        item = get_learning_resource(r["id"])
        if item:
            resources.append(item)
    return resources


def delete_learning_resource(resource_id: int, owner_user_id: str) -> bool:
    """软删除用户私有资源"""
    conn = _get_conn()
    with _lock:
        cursor = conn.execute(
            "UPDATE learning_resources SET status='deleted' WHERE id=? AND owner_user_id=?",
            (resource_id, owner_user_id),
        )
        conn.commit()
    return cursor.rowcount > 0


# ── 错题本功能 ─────────────────────────────────────────────
def add_wrong_question(user_id: str, question: dict, wrong_answer: str, error_type: str = "concept", attribution: Optional[dict] = None) -> dict:
    """添加错题，已存在则错误次数+1。attribution 为智能归因结果（可空）。"""
    conn = _get_conn()
    now = _now()
    qid = question.get("id", str(hash(json.dumps(question, ensure_ascii=False))))
    subject = question.get("subject", "")
    chapter = question.get("chapter", "")
    knowledge_point = question.get("knowledge_point", question.get("kp", ""))
    correct_answer = question.get("answer", question.get("correct_answer", ""))
    attr_json = json.dumps(attribution, ensure_ascii=False) if attribution else "{}"

    with _lock:
        existing = conn.execute(
            "SELECT id, wrong_count FROM user_wrong_questions WHERE user_id=? AND question_id=?",
            (user_id, qid)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE user_wrong_questions SET wrong_count=wrong_count+1, last_wrong_at=?, wrong_answer=?, error_type=?, attribution_json=?, mastered=0 WHERE id=?",
                (now, wrong_answer, error_type, attr_json, existing["id"])
            )
            wid = existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO user_wrong_questions 
                (user_id, question_id, question_json, subject, chapter, knowledge_point, wrong_answer, correct_answer, error_type, attribution_json, wrong_count, last_wrong_at, first_wrong_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (user_id, qid, json.dumps(question, ensure_ascii=False), subject, chapter, knowledge_point, wrong_answer, correct_answer, error_type, attr_json, now, now)
            )
            wid = cursor.lastrowid
        conn.commit()

    return get_wrong_question(wid)


def get_wrong_question(qid: int) -> Optional[dict]:
    """获取单条错题详情"""
    conn = _get_conn()
    with _lock:
        row = conn.execute("SELECT * FROM user_wrong_questions WHERE id=?", (qid,)).fetchone()
    if not row:
        return None
    try:
        question = json.loads(row["question_json"])
    except Exception:
        question = {}
    return {
        "id": row["id"],
        "question_id": row["question_id"],
        "question": question,
        "subject": row["subject"],
        "chapter": row["chapter"],
        "knowledge_point": row["knowledge_point"],
        "wrong_answer": row["wrong_answer"],
        "correct_answer": row["correct_answer"],
        "error_type": row["error_type"],
        "attribution": _parse_attr(row["attribution_json"]),
        "wrong_count": row["wrong_count"],
        "mastered": bool(row["mastered"]),
        "last_wrong_at": row["last_wrong_at"],
        "first_wrong_at": row["first_wrong_at"],
    }


def _parse_attr(raw) -> Optional[dict]:
    """安全解析 attribution_json（容忍空/非法）。"""
    if not raw:
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def get_error_profile(user_id: str) -> dict:
    """聚合用户的错题『错误画像』：错误类型分布、知识点频次、LLM 归因占比。"""
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT error_type, attribution_json FROM user_wrong_questions WHERE user_id=?",
            (user_id,),
        ).fetchall()

    type_dist: dict = {}
    kp_freq: dict = {}
    llm_cnt = 0
    degraded_cnt = 0
    total = 0
    for r in rows:
        total += 1
        et = r["error_type"] or "concept"
        type_dist[et] = type_dist.get(et, 0) + 1
        attr = _parse_attr(r["attribution_json"])
        if attr:
            if attr.get("degraded"):
                degraded_cnt += 1
            else:
                llm_cnt += 1
            for kp in (attr.get("knowledge_points") or []):
                if kp:
                    kp_freq[kp] = kp_freq.get(kp, 0) + 1

    return {
        "total": total,
        "error_type_distribution": [
            {"type": k, "label": _ERROR_LABELS.get(k, k), "count": v}
            for k, v in sorted(type_dist.items(), key=lambda x: -x[1])
        ],
        "top_knowledge_points": [
            {"knowledge_point": k, "count": v}
            for k, v in sorted(kp_freq.items(), key=lambda x: -x[1])[:10]
        ],
        "attribution_source": {
            "llm": llm_cnt,
            "rule_fallback": degraded_cnt,
        },
    }


# error_type 中文标签（供画像展示）
_ERROR_LABELS = {
    "concept": "概念混淆",
    "misread": "审题错误",
    "calculation": "计算失误",
    "logic": "思路偏差",
    "memory": "记忆遗忘",
    "blindspot": "知识盲区",
}


def list_wrong_questions(user_id: str, subject: str = None, mastered: bool = None, page: int = 1, page_size: int = 20) -> dict:
    """获取用户错题列表"""
    conn = _get_conn()
    offset = (page - 1) * page_size
    query = "SELECT id FROM user_wrong_questions WHERE user_id=?"
    params = [user_id]
    
    if subject:
        query += " AND subject=?"
        params.append(subject)
    if mastered is not None:
        query += " AND mastered=?"
        params.append(1 if mastered else 0)
    
    count_query = query.replace("SELECT id", "SELECT COUNT(*) as total")
    query += " ORDER BY last_wrong_at DESC LIMIT ? OFFSET ?"
    params.extend([page_size, offset])
    
    with _lock:
        total = conn.execute(count_query, params[:-2]).fetchone()["total"]
        rows = conn.execute(query, params).fetchall()
    
    items = [get_wrong_question(r["id"]) for r in rows]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


def mark_wrong_question_mastered(qid: int, user_id: str, mastered: bool = True) -> bool:
    """标记错题已掌握/未掌握"""
    conn = _get_conn()
    with _lock:
        cursor = conn.execute(
            "UPDATE user_wrong_questions SET mastered=? WHERE id=? AND user_id=?",
            (1 if mastered else 0, qid, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_wrong_question(qid: int, user_id: str) -> bool:
    """删除错题"""
    conn = _get_conn()
    with _lock:
        cursor = conn.execute(
            "DELETE FROM user_wrong_questions WHERE id=? AND user_id=?",
            (qid, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_wrong_question_stats(user_id: str) -> dict:
    """获取错题统计信息"""
    conn = _get_conn()
    with _lock:
        total = conn.execute("SELECT COUNT(*) as cnt FROM user_wrong_questions WHERE user_id=?", (user_id,)).fetchone()["cnt"]
        mastered = conn.execute("SELECT COUNT(*) as cnt FROM user_wrong_questions WHERE user_id=? AND mastered=1", (user_id,)).fetchone()["cnt"]
        subject_stats = conn.execute(
            "SELECT subject, COUNT(*) as cnt, SUM(mastered) as mastered_cnt FROM user_wrong_questions WHERE user_id=? GROUP BY subject",
            (user_id,)
        ).fetchall()
        error_type_stats = conn.execute(
            "SELECT error_type, COUNT(*) as cnt FROM user_wrong_questions WHERE user_id=? GROUP BY error_type",
            (user_id,)
        ).fetchall()
    
    return {
        "total": total,
        "mastered": mastered,
        "unmastered": total - mastered,
        "mastery_rate": round(mastered / total * 100, 1) if total > 0 else 0,
        "subject_distribution": [{"subject": r["subject"], "count": r["cnt"], "mastered": r["mastered_cnt"]} for r in subject_stats],
        "error_type_distribution": [{"type": r["error_type"], "count": r["cnt"]} for r in error_type_stats],
    }


# ── 每日计划功能 ─────────────────────────────────────────────
def _generate_default_daily_tasks(user_id: str) -> list:
    """生成默认每日学习任务"""
    base_tasks = [
        {"id": "review_wrong", "type": "wrong_review", "title": "复习昨日错题", "subject": "综合", "chapter": "", "progress": 0, "completed": False, "estimated_minutes": 30},
        {"id": "ds_chapter", "type": "study", "title": "数据结构知识点学习", "subject": "数据结构", "chapter": "", "progress": 0, "completed": False, "estimated_minutes": 60},
        {"id": "co_chapter", "type": "study", "title": "计算机组成原理知识点学习", "subject": "计算机组成原理", "chapter": "", "progress": 0, "completed": False, "estimated_minutes": 60},
        {"id": "os_chapter", "type": "study", "title": "操作系统知识点学习", "subject": "操作系统", "chapter": "", "progress": 0, "completed": False, "estimated_minutes": 60},
        {"id": "cn_chapter", "type": "study", "title": "计算机网络知识点学习", "subject": "计算机网络", "chapter": "", "progress": 0, "completed": False, "estimated_minutes": 60},
        {"id": "practice", "type": "practice", "title": "对应章节习题练习", "subject": "综合", "chapter": "", "progress": 0, "completed": False, "estimated_minutes": 90},
        {"id": "summary", "type": "summary", "title": "今日知识点总结+笔记整理", "subject": "综合", "chapter": "", "progress": 0, "completed": False, "estimated_minutes": 30},
    ]
    return base_tasks


def get_or_create_daily_plan(user_id: str, plan_date: str = None, target_exam_date: str = None, target_score: int = None) -> dict:
    """获取或创建指定日期的学习计划"""
    from datetime import datetime
    conn = _get_conn()
    now = _now()
    if not plan_date:
        plan_date = datetime.now().strftime("%Y-%m-%d")
    
    with _lock:
        existing = conn.execute(
            "SELECT * FROM user_daily_plans WHERE user_id=? AND plan_date=?",
            (user_id, plan_date)
        ).fetchone()
        
        if existing:
            try:
                tasks = json.loads(existing["tasks_json"])
            except Exception:
                tasks = []
            return {
                "id": existing["id"],
                "plan_date": existing["plan_date"],
                "tasks": tasks,
                "total_tasks": existing["total_tasks"],
                "completed_tasks": existing["completed_tasks"],
                "completion_rate": round(existing["completed_tasks"] / existing["total_tasks"] * 100, 1) if existing["total_tasks"] > 0 else 0,
                "target_exam_date": existing["target_exam_date"],
                "target_score": existing["target_score"],
                "created_at": existing["created_at"],
                "updated_at": existing["updated_at"],
            }
        
        tasks = _generate_default_daily_tasks(user_id)
        total = len(tasks)
        completed = 0
        cursor = conn.execute(
            """INSERT INTO user_daily_plans 
            (user_id, plan_date, tasks_json, total_tasks, completed_tasks, target_exam_date, target_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, plan_date, json.dumps(tasks, ensure_ascii=False), total, completed, target_exam_date or "", target_score or 0, now, now)
        )
        conn.commit()
        pid = cursor.lastrowid
    
    row = conn.execute("SELECT * FROM user_daily_plans WHERE id=?", (pid,)).fetchone()
    try:
        tasks = json.loads(row["tasks_json"])
    except Exception:
        tasks = []
    return {
        "id": row["id"],
        "plan_date": row["plan_date"],
        "tasks": tasks,
        "total_tasks": row["total_tasks"],
        "completed_tasks": row["completed_tasks"],
        "completion_rate": round(row["completed_tasks"] / row["total_tasks"] * 100, 1) if row["total_tasks"] > 0 else 0,
        "target_exam_date": row["target_exam_date"],
        "target_score": row["target_score"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def update_daily_plan_task(pid: int, user_id: str, task_id: str, completed: bool = None, progress: int = None) -> Optional[dict]:
    """更新计划中任务状态"""
    conn = _get_conn()
    now = _now()
    with _lock:
        row = conn.execute("SELECT * FROM user_daily_plans WHERE id=? AND user_id=?", (pid, user_id)).fetchone()
        if not row:
            return None
        try:
            tasks = json.loads(row["tasks_json"])
        except Exception:
            tasks = []
        
        found = False
        completed_count = 0
        for task in tasks:
            if task["id"] == task_id:
                found = True
                if completed is not None:
                    task["completed"] = completed
                    task["progress"] = 100 if completed else progress or task.get("progress", 0)
                if progress is not None and completed is None:
                    task["progress"] = min(100, max(0, progress))
                    if task["progress"] >= 100:
                        task["completed"] = True
            if task.get("completed", False):
                completed_count += 1
        
        if not found:
            return None
        
        conn.execute(
            "UPDATE user_daily_plans SET tasks_json=?, completed_tasks=?, updated_at=? WHERE id=?",
            (json.dumps(tasks, ensure_ascii=False), completed_count, now, pid)
        )
        conn.commit()
    
    row = conn.execute("SELECT * FROM user_daily_plans WHERE id=?", (pid,)).fetchone()
    try:
        tasks = json.loads(row["tasks_json"])
    except Exception:
        tasks = []
    return {
        "id": row["id"],
        "plan_date": row["plan_date"],
        "tasks": tasks,
        "total_tasks": row["total_tasks"],
        "completed_tasks": row["completed_tasks"],
        "completion_rate": round(row["completed_tasks"] / row["total_tasks"] * 100, 1) if row["total_tasks"] > 0 else 0,
        "target_exam_date": row["target_exam_date"],
        "target_score": row["target_score"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_daily_plans(user_id: str, start_date: str = None, end_date: str = None, limit: int = 30) -> list:
    """获取用户一段时间的计划列表"""
    conn = _get_conn()
    query = "SELECT id FROM user_daily_plans WHERE user_id=?"
    params = [user_id]
    
    if start_date:
        query += " AND plan_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND plan_date <= ?"
        params.append(end_date)
    
    query += " ORDER BY plan_date DESC LIMIT ?"
    params.append(limit)
    
    with _lock:
        rows = conn.execute(query, params).fetchall()
    
    result = []
    for r in rows:
        row = conn.execute("SELECT * FROM user_daily_plans WHERE id=?", (r["id"],)).fetchone()
        try:
            tasks = json.loads(row["tasks_json"])
        except Exception:
            tasks = []
        result.append({
            "id": row["id"],
            "plan_date": row["plan_date"],
            "tasks": tasks,
            "total_tasks": row["total_tasks"],
            "completed_tasks": row["completed_tasks"],
            "completion_rate": round(row["completed_tasks"] / row["total_tasks"] * 100, 1) if row["total_tasks"] > 0 else 0,
            "target_exam_date": row["target_exam_date"],
            "target_score": row["target_score"],
        })
    return result
