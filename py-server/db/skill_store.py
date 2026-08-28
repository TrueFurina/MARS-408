# ============================================================
# AI Skills 持久化 — SQLite（与 user_store 共享同一数据库文件）
# 技能 CRUD / 市场查询 / 评价 / 使用日志
# ============================================================

import os
import json
import sqlite3
import threading
import uuid
import logging
from typing import Optional

from schemas.skills import (
    Skill,
    SkillTemplate,
    SkillRating,
    SkillUsage,
    SkillStatus,
    SkillCategory,
)

logger = logging.getLogger("netlearn.skillstore")

# 与 user_store 共享同一数据库目录
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DB_PATH = os.path.join(_DB_DIR, "netlearn_users.db")
os.makedirs(_DB_DIR, exist_ok=True)

_conn: Optional[sqlite3.Connection] = None
_lock = threading.RLock()


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（延迟初始化 + 自动建表）"""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection):
    """初始化技能相关表结构（幂等）"""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS skills (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        icon TEXT NOT NULL DEFAULT '🤖',
        system_prompt TEXT NOT NULL DEFAULT '',
        llm_channel TEXT NOT NULL DEFAULT 'auto',
        temperature REAL NOT NULL DEFAULT 0.7,
        max_tokens INTEGER NOT NULL DEFAULT 2048,
        kb_ids TEXT NOT NULL DEFAULT '[]',
        rag_enabled INTEGER NOT NULL DEFAULT 1,
        tags TEXT NOT NULL DEFAULT '[]',
        category TEXT NOT NULL DEFAULT 'other',
        version INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'draft',
        memory_access TEXT NOT NULL DEFAULT 'read_write',
        usage_count INTEGER NOT NULL DEFAULT 0,
        user_count INTEGER NOT NULL DEFAULT 0,
        avg_rating REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        published_at TEXT,
        creator_id TEXT NOT NULL DEFAULT '',
        creator_name TEXT NOT NULL DEFAULT '',
        is_official INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS skill_ratings (
        id TEXT PRIMARY KEY,
        skill_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL DEFAULT '',
        rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
        comment TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (skill_id) REFERENCES skills(id)
    );
    CREATE TABLE IF NOT EXISTS skill_usage_log (
        id TEXT PRIMARY KEY,
        skill_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        session_id TEXT NOT NULL DEFAULT '',
        input_text TEXT NOT NULL DEFAULT '',
        output_text TEXT NOT NULL DEFAULT '',
        tokens_used INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (skill_id) REFERENCES skills(id)
    );
    CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);
    CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
    CREATE INDEX IF NOT EXISTS idx_skills_creator ON skills(creator_id);
    CREATE INDEX IF NOT EXISTS idx_skills_usage ON skills(usage_count DESC);
    CREATE INDEX IF NOT EXISTS idx_skills_rating ON skills(avg_rating DESC);
    CREATE INDEX IF NOT EXISTS idx_ratings_skill ON skill_ratings(skill_id);
    CREATE INDEX IF NOT EXISTS idx_usage_skill ON skill_usage_log(skill_id);
    CREATE INDEX IF NOT EXISTS idx_usage_user ON skill_usage_log(user_id);
    CREATE TABLE IF NOT EXISTS skill_favorites (
        user_id TEXT NOT NULL,
        skill_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (user_id, skill_id),
        FOREIGN KEY (skill_id) REFERENCES skills(id)
    );
    CREATE INDEX IF NOT EXISTS idx_fav_user ON skill_favorites(user_id);
    """)
    # P2② 兼容迁移：老库 skills 表缺 memory_access 列（历史版本无权限字段）
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(skills)").fetchall()]
        if "memory_access" not in cols:
            conn.execute("ALTER TABLE skills ADD COLUMN memory_access TEXT NOT NULL DEFAULT 'read_write'")
            logger.info("skills 表新增 memory_access 列（兼容迁移）")
    except Exception as e:
        logger.debug(f"skills 表 memory_access 列迁移跳过(忽略): {e}")
    conn.commit()
    logger.info("技能表结构初始化完成")


# ── 技能 CRUD ──


def _row_to_skill(row: sqlite3.Row) -> Skill:
    """将 SQLite 行转换为 Skill 对象"""
    return Skill(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        icon=row["icon"],
        system_prompt=row["system_prompt"],
        llm_channel=row["llm_channel"],
        temperature=row["temperature"],
        max_tokens=row["max_tokens"],
        kb_ids=json.loads(row["kb_ids"]),
        rag_enabled=bool(row["rag_enabled"]),
        tags=json.loads(row["tags"]),
        category=row["category"],
        version=row["version"],
        status=row["status"],
        memory_access=row["memory_access"] if "memory_access" in row.keys() else "read_write",
        usage_count=row["usage_count"],
        user_count=row["user_count"],
        avg_rating=row["avg_rating"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        published_at=row["published_at"],
        creator_id=row["creator_id"],
        creator_name=row["creator_name"],
        is_official=bool(row["is_official"]),
    )


def create_skill(skill: Skill) -> Skill:
    """创建新技能"""
    with _lock:
        conn = _get_conn()
        now = _now()
        skill_id = skill.id or uuid.uuid4().hex[:12]
        conn.execute(
            """INSERT INTO skills (
                id, name, description, icon, system_prompt,
                llm_channel, temperature, max_tokens, kb_ids, rag_enabled,
                tags, category, version, status, memory_access, usage_count, user_count, avg_rating,
                created_at, updated_at, published_at,
                creator_id, creator_name, is_official
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                skill_id,
                skill.name,
                skill.description,
                skill.icon,
                skill.system_prompt,
                skill.llm_channel,
                skill.temperature,
                skill.max_tokens,
                json.dumps(skill.kb_ids),
                1 if skill.rag_enabled else 0,
                json.dumps(skill.tags),
                skill.category,
                skill.version,
                skill.status,
                skill.memory_access,
                0, 0, 0.0,
                now, now,
                now if skill.status == SkillStatus.PUBLISHED.value else None,
                skill.creator_id,
                skill.creator_name,
                1 if skill.is_official else 0,
            ),
        )
        conn.commit()
        skill.id = skill_id
        skill.created_at = now
        skill.updated_at = now
        logger.info("技能创建成功: %s (%s)", skill_id, skill.name)
        return skill


def get_skill(skill_id: str) -> Optional[Skill]:
    """按 ID 获取技能"""
    with _lock:
        row = _get_conn().execute(
            "SELECT * FROM skills WHERE id = ?", (skill_id,)
        ).fetchone()
    return _row_to_skill(row) if row else None


def update_skill(skill: Skill) -> bool:
    """更新技能信息"""
    with _lock:
        conn = _get_conn()
        now = _now()
        published_at = skill.published_at
        if skill.status == SkillStatus.PUBLISHED.value and not published_at:
            published_at = now
        cursor = conn.execute(
            """UPDATE skills SET
                name=?, description=?, icon=?, system_prompt=?,
                llm_channel=?, temperature=?, max_tokens=?, kb_ids=?, rag_enabled=?,
                tags=?, category=?, version=?, status=?, memory_access=?,
                published_at=?, creator_name=?, is_official=?
            WHERE id=?""",
            (
                skill.name, skill.description, skill.icon, skill.system_prompt,
                skill.llm_channel, skill.temperature, skill.max_tokens,
                json.dumps(skill.kb_ids), 1 if skill.rag_enabled else 0,
                json.dumps(skill.tags), skill.category, skill.version, skill.status,
                skill.memory_access,
                published_at, skill.creator_name, 1 if skill.is_official else 0,
                skill.id,
            ),
        )
        if cursor.rowcount > 0:
            conn.execute("UPDATE skills SET updated_at=? WHERE id=?", (now, skill.id))
            conn.commit()
            skill.updated_at = now
            if published_at:
                skill.published_at = published_at
            logger.info("技能更新成功: %s", skill.id)
            return True
        return False


def delete_skill(skill_id: str) -> bool:
    """删除技能（级联删除评价和日志）"""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM skill_ratings WHERE skill_id=?", (skill_id,))
        conn.execute("DELETE FROM skill_usage_log WHERE skill_id=?", (skill_id,))
        conn.execute("DELETE FROM skill_favorites WHERE skill_id=?", (skill_id,))
        cursor = conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("技能已删除: %s", skill_id)
        return deleted


def batch_delete_skills(skill_ids: list[str]) -> int:
    """批量删除技能"""
    if not skill_ids:
        return 0
    with _lock:
        conn = _get_conn()
        placeholders = ",".join("?" for _ in skill_ids)
        conn.execute(f"DELETE FROM skill_ratings WHERE skill_id IN ({placeholders})", skill_ids)
        conn.execute(f"DELETE FROM skill_usage_log WHERE skill_id IN ({placeholders})", skill_ids)
        conn.execute(f"DELETE FROM skill_favorites WHERE skill_id IN ({placeholders})", skill_ids)
        cursor = conn.execute(f"DELETE FROM skills WHERE id IN ({placeholders})", skill_ids)
        conn.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info("批量删除技能: %d 个", deleted)
        return deleted


def export_skills_json(creator_id: Optional[str] = None, skill_ids: Optional[list[str]] = None) -> str:
    """导出技能为 JSON 字符串"""
    with _lock:
        conn = _get_conn()
        if skill_ids:
            placeholders = ",".join("?" for _ in skill_ids)
            rows = conn.execute(
                f"SELECT * FROM skills WHERE id IN ({placeholders})", skill_ids
            ).fetchall()
        elif creator_id:
            rows = conn.execute(
                "SELECT * FROM skills WHERE creator_id=?", (creator_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM skills").fetchall()
    skills = [_row_to_skill(r) for r in rows]
    data = {
        "version": 1,
        "exported_at": _now(),
        "skills": [s.to_dict() for s in skills],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def import_skills_json(json_str: str, creator_id: str = "", creator_name: str = "") -> int:
    """从 JSON 字符串导入技能"""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error("导入技能 JSON 解析失败: %s", e)
        return 0
    imported = 0
    for item in data.get("skills", []):
        try:
            skill = Skill.from_dict(item)
            skill.creator_id = creator_id or skill.creator_id
            skill.creator_name = creator_name or skill.creator_name
            skill.status = SkillStatus.DRAFT.value
            skill.usage_count = 0
            skill.user_count = 0
            skill.avg_rating = 0.0
            skill.published_at = None
            # 重新生成 ID 避免冲突
            skill.id = uuid.uuid4().hex[:12]
            create_skill(skill)
            imported += 1
        except Exception as e:
            logger.warning("导入技能失败: %s", e)
            continue
    logger.info("导入技能完成: %d 个", imported)
    return imported


def list_skills(
    creator_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    is_official: Optional[bool] = None,
    sort_by: str = "updated_at",
    sort_desc: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Skill], int]:
    """查询技能列表（支持过滤/分页/搜索）"""
    where_clauses: list[str] = []
    params: list = []

    if creator_id:
        where_clauses.append("creator_id = ?")
        params.append(creator_id)
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if category:
        where_clauses.append("category = ?")
        params.append(category)
    if tag:
        where_clauses.append("tags LIKE ?")
        params.append(f'%"{tag}"%')
    if search:
        where_clauses.append("(name LIKE ? OR description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if is_official is not None:
        where_clauses.append("is_official = ?")
        params.append(1 if is_official else 0)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 合法的排序列
    allowed_sorts = {"updated_at", "created_at", "usage_count", "avg_rating", "name"}
    sort_col = sort_by if sort_by in allowed_sorts else "updated_at"
    order = "DESC" if sort_desc else "ASC"

    with _lock:
        conn = _get_conn()
        # 总数
        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM skills WHERE {where_sql}", params
        ).fetchone()
        total = total_row["cnt"] if total_row else 0
        # 分页数据
        rows = conn.execute(
            f"SELECT * FROM skills WHERE {where_sql} ORDER BY {sort_col} {order} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    skills = [_row_to_skill(r) for r in rows]
    return skills, total


def publish_skill(skill_id: str) -> bool:
    """发布技能（draft → published）"""
    with _lock:
        conn = _get_conn()
        now = _now()
        cursor = conn.execute(
            """UPDATE skills SET status=?, published_at=COALESCE(published_at, ?), updated_at=?
               WHERE id=? AND status=?""",
            (SkillStatus.PUBLISHED.value, now, now, skill_id, SkillStatus.DRAFT.value),
        )
        conn.commit()
        return cursor.rowcount > 0


def archive_skill(skill_id: str) -> bool:
    """归档技能（published → archived）"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "UPDATE skills SET status=?, updated_at=? WHERE id=? AND status=?",
            (SkillStatus.ARCHIVED.value, _now(), skill_id, SkillStatus.PUBLISHED.value),
        )
        conn.commit()
        return cursor.rowcount > 0


# ── 技能统计 ──


def increment_skill_usage(skill_id: str, user_id: str) -> None:
    """技能被调用一次，更新统计计数"""
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE skills SET usage_count = usage_count + 1 WHERE id = ?",
            (skill_id,),
        )
        # 如果这个用户是第一次使用，增加 user_count
        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM skill_usage_log WHERE skill_id=? AND user_id=?",
            (skill_id, user_id),
        ).fetchone()
        if existing and existing["cnt"] == 0:
            conn.execute(
                "UPDATE skills SET user_count = user_count + 1 WHERE id = ?",
                (skill_id,),
            )
        conn.commit()


def get_creator_stats(creator_id: str) -> dict:
    """创作者统计看板"""
    with _lock:
        conn = _get_conn()
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM skills WHERE creator_id=?", (creator_id,)
        ).fetchone()
        published = conn.execute(
            "SELECT COUNT(*) as cnt FROM skills WHERE creator_id=? AND status=?",
            (creator_id, SkillStatus.PUBLISHED.value),
        ).fetchone()
        usage = conn.execute(
            "SELECT COALESCE(SUM(usage_count), 0) as total FROM skills WHERE creator_id=?",
            (creator_id,),
        ).fetchone()
        # 最新 7 天调用趋势
        usage_trend = conn.execute(
            """SELECT DATE(created_at) as day, COUNT(*) as cnt
               FROM skill_usage_log
               WHERE skill_id IN (SELECT id FROM skills WHERE creator_id=?)
                 AND created_at >= DATE('now', '-7 days')
               GROUP BY DATE(created_at)
               ORDER BY day""",
            (creator_id,),
        ).fetchall()
    return {
        "total_skills": total["cnt"] if total else 0,
        "published_skills": published["cnt"] if published else 0,
        "total_usage": usage["total"] if usage else 0,
        "usage_trend": [
            {"day": r["day"], "count": r["cnt"]} for r in usage_trend
        ],
    }


# ── 收藏 ──


def add_favorite(user_id: str, skill_id: str) -> bool:
    """收藏技能"""
    with _lock:
        conn = _get_conn()
        existing = conn.execute(
            "SELECT 1 FROM skill_favorites WHERE user_id=? AND skill_id=?",
            (user_id, skill_id),
        ).fetchone()
        if existing:
            return True  # 已收藏，幂等
        conn.execute(
            "INSERT INTO skill_favorites (user_id, skill_id, created_at) VALUES (?, ?, ?)",
            (user_id, skill_id, _now()),
        )
        conn.commit()
        return True


def remove_favorite(user_id: str, skill_id: str) -> bool:
    """取消收藏"""
    with _lock:
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM skill_favorites WHERE user_id=? AND skill_id=?",
            (user_id, skill_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def is_favorited(user_id: str, skill_id: str) -> bool:
    """检查是否已收藏"""
    with _lock:
        row = _get_conn().execute(
            "SELECT 1 FROM skill_favorites WHERE user_id=? AND skill_id=?",
            (user_id, skill_id),
        ).fetchone()
        return row is not None


def list_favorites(user_id: str) -> list[Skill]:
    """获取用户收藏的技能列表"""
    with _lock:
        rows = _get_conn().execute(
            """SELECT s.* FROM skills s
               INNER JOIN skill_favorites f ON s.id = f.skill_id
               WHERE f.user_id = ?
               ORDER BY f.created_at DESC""",
            (user_id,),
        ).fetchall()
    return [_row_to_skill(r) for r in rows]


# ── 评价 ──


def create_rating(rating: SkillRating) -> SkillRating:
    """添加评价，并更新技能的平均评分"""
    with _lock:
        conn = _get_conn()
        now = _now()
        rating_id = rating.id or uuid.uuid4().hex[:12]
        conn.execute(
            """INSERT INTO skill_ratings (id, skill_id, user_id, user_name, rating, comment, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rating_id, rating.skill_id, rating.user_id, rating.user_name,
             rating.rating, rating.comment, now),
        )
        # 重新计算平均评分
        avg = conn.execute(
            "SELECT AVG(rating) as avg FROM skill_ratings WHERE skill_id=?",
            (rating.skill_id,),
        ).fetchone()
        if avg and avg["avg"] is not None:
            conn.execute(
                "UPDATE skills SET avg_rating=? WHERE id=?",
                (round(avg["avg"], 2), rating.skill_id),
            )
        conn.commit()
        rating.id = rating_id
        rating.created_at = now
        logger.info("评价已添加: %s → %s (★%d)", rating.user_id, rating.skill_id, rating.rating)
        return rating


def list_ratings(skill_id: str, limit: int = 20, offset: int = 0) -> tuple[list[SkillRating], int]:
    """获取技能的评价列表"""
    with _lock:
        conn = _get_conn()
        total_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM skill_ratings WHERE skill_id=?", (skill_id,)
        ).fetchone()
        total = total_row["cnt"] if total_row else 0
        rows = conn.execute(
            "SELECT * FROM skill_ratings WHERE skill_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (skill_id, limit, offset),
        ).fetchall()
    ratings = [
        SkillRating(
            id=r["id"], skill_id=r["skill_id"], user_id=r["user_id"],
            user_name=r["user_name"], rating=r["rating"],
            comment=r["comment"], created_at=r["created_at"],
        )
        for r in rows
    ]
    return ratings, total


# ── 使用日志 ──


def log_usage(usage: SkillUsage) -> SkillUsage:
    """记录技能使用日志"""
    with _lock:
        conn = _get_conn()
        now = _now()
        usage_id = usage.id or uuid.uuid4().hex[:12]
        conn.execute(
            """INSERT INTO skill_usage_log
               (id, skill_id, user_id, session_id, input_text, output_text, tokens_used, latency_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (usage_id, usage.skill_id, usage.user_id, usage.session_id,
             usage.input_text[:500], usage.output_text[:500],
             usage.tokens_used, usage.latency_ms, now),
        )
        conn.commit()
        usage.id = usage_id
        usage.created_at = now
        return usage


def list_usage_logs(
    skill_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SkillUsage], int]:
    """查询使用日志"""
    where_clauses: list[str] = []
    params: list = []
    if skill_id:
        where_clauses.append("skill_id = ?")
        params.append(skill_id)
    if user_id:
        where_clauses.append("user_id = ?")
        params.append(user_id)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    with _lock:
        conn = _get_conn()
        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM skill_usage_log WHERE {where_sql}", params
        ).fetchone()
        total = total_row["cnt"] if total_row else 0
        rows = conn.execute(
            f"SELECT * FROM skill_usage_log WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    logs = [
        SkillUsage(
            id=r["id"], skill_id=r["skill_id"], user_id=r["user_id"],
            session_id=r["session_id"], input_text=r["input_text"],
            output_text=r["output_text"], tokens_used=r["tokens_used"],
            latency_ms=r["latency_ms"], created_at=r["created_at"],
        )
        for r in rows
    ]
    return logs, total


# ── 预设模板（硬编码，后续可改为 JSON 配置） ──


_BUILTIN_TEMPLATES: list[SkillTemplate] = [
    SkillTemplate(
        id="quiz-bot",
        name="智能出题机器人",
        description="按知识点和难度自动生成练习题，含答案解析和易错点标注",
        category=SkillCategory.QUIZ.value,
        icon="📝",
        system_prompt_template=(
            "你是一个 408 {{subject}} 出题专家。\n"
            "请根据以下要求生成一道练习题：\n"
            "- 知识点：{{knowledge_point}}\n"
            "- 难度：{{difficulty}}\n"
            "- 题型：{{question_type}}\n\n"
            "要求：\n"
            "1. 题目准确、无歧义\n"
            "2. 提供标准答案\n"
            "3. 给出详细解析\n"
            "4. 标注易错点"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.7, "max_tokens": 2048},
        sort_order=1,
    ),
    SkillTemplate(
        id="socratic-coach",
        name="苏格拉底式教练",
        description="不直接给答案，通过追问引导学习者自己推理出答案",
        category=SkillCategory.TEACHING.value,
        icon="🎓",
        system_prompt_template=(
            "你是一个苏格拉底式的教学教练。\n"
            "你的任务是引导 {{subject}} 的学习者自己找到答案，而不是直接告诉他们。\n\n"
            "规则：\n"
            "1. 不要直接给出答案\n"
            "2. 通过追问引导学习者一步步推理\n"
            "3. 当学习者卡住时，给提示而不是答案\n"
            "4. 当学习者答对时，给予肯定并追问更深的问题\n"
            "5. 保持耐心和鼓励的态度"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.8, "max_tokens": 1024},
        sort_order=2,
    ),
    SkillTemplate(
        id="code-reviewer",
        name="代码审查官",
        description="审查代码的正确性、效率和风格，给出改进建议",
        category=SkillCategory.CODE.value,
        icon="🔍",
        system_prompt_template=(
            "你是一个严格的代码审查官。\n"
            "请审查以下 {{language}} 代码，从以下维度给出反馈：\n\n"
            "1. 正确性：是否有 bug 或逻辑错误？\n"
            "2. 效率：时间复杂度和空间复杂度如何？能否优化？\n"
            "3. 风格：代码风格是否符合规范？\n"
            "4. 可读性：变量命名、注释、结构是否清晰？\n"
            "5. 改进建议：给出具体的改进代码\n\n"
            "请用友好但专业的态度给出反馈。"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=3,
    ),
    SkillTemplate(
        id="knowledge-explainer",
        name="知识点讲解师",
        description="按指定风格讲解知识点，包含概念、类比和例子",
        category=SkillCategory.TEACHING.value,
        icon="📊",
        system_prompt_template=(
            "你是一个 408 {{subject}} 的资深讲师。\n"
            "请用{{style}}的风格讲解{{knowledge_point}}。\n\n"
            "要求：\n"
            "1. 先给出核心概念\n"
            "2. 用生活化的类比帮助理解\n"
            "3. 给出具体的例子\n"
            "4. 标注重点和易错点\n"
            "5. 最后用一句话总结\n"
            "提示：字符串模式匹配计算可调用 kmp_match（text/pattern，输出 next 数组与匹配位置）；"
            "哈希冲突处理可调用 hash_conflict_resolve（keys/size/method，输出散列过程与 ASL）；"
            "CRC 校验可调用 calculate_crc（data/poly）；"
            "页表地址转换可调用 translate_page_address（logical/page_size_kb）；"
            "IP 校验和可调用 calculate_ip_checksum（hex 报文）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.7, "max_tokens": 2048},
        sort_order=4,
    ),
    SkillTemplate(
        id="mindmap-generator",
        name="思维导图生成器",
        description="将知识点整理为层级结构的思维导图",
        category=SkillCategory.MINDMAP.value,
        icon="🧩",
        system_prompt_template=(
            "请将以下 {{subject}} 的知识点整理为层级结构的思维导图。\n"
            "主题：{{topic}}\n\n"
            "格式要求：\n"
            "1. 根节点为总主题\n"
            "2. 第二层为核心子主题\n"
            "3. 第三层为具体知识点\n"
            "4. 第四层为关键细节\n\n"
            "请同时输出 Markdown 和 Mermaid 两种格式。"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.6, "max_tokens": 2048},
        sort_order=5,
    ),
    SkillTemplate(
        id="study-planner",
        name="学习计划制定者",
        description="根据剩余时间和目标制定个性化学习计划",
        category=SkillCategory.GUIDE.value,
        icon="📋",
        system_prompt_template=(
            "你是一个考研学习规划师。\n"
            "请根据以下信息制定一个可执行的学习计划：\n\n"
            "- 目标科目：{{subject}}\n"
            "- 当前掌握度：{{mastery}}\n"
            "- 剩余天数：{{days_remaining}}\n"
            "- 每日可用时间：{{daily_hours}}小时\n"
            "- 目标分数：{{target_score}}\n\n"
            "要求：\n"
            "1. 按阶段划分（基础→强化→冲刺）\n"
            "2. 每天具体任务\n"
            "3. 标注薄弱点重点投入\n"
            "4. 包含阶段性自测节点"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.7, "max_tokens": 2048},
        sort_order=6,
    ),
    SkillTemplate(
        id="exam-analyzer",
        name="真题解析师",
        description="深度解析历年真题，从考察知识点、解题思路、常见错误三个维度分析",
        category=SkillCategory.QUIZ.value,
        icon="📖",
        system_prompt_template=(
            "你是一个 408 真题解析专家。\n"
            "请从以下三个维度深度解析这道 {{subject}} 真题：\n\n"
            "题目：{{question}}\n\n"
            "1. 考察知识点：\n"
            "   - 涉及哪些知识点？\n"
            "   - 考纲中的要求等级？\n\n"
            "2. 解题思路：\n"
            "   - 分步解题过程\n"
            "   - 关键判断点\n"
            "   - 时间优化技巧\n\n"
            "3. 常见错误：\n"
            "   - 最常见的错误答案\n"
            "   - 错误原因分析\n"
            "   - 如何避免踩坑"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=7,
    ),
    SkillTemplate(
        id="analogy-master",
        name="概念类比大师",
        description="用生活化类比解释抽象概念，让零基础学生也能听懂",
        category=SkillCategory.TEACHING.value,
        icon="🗣️",
        system_prompt_template=(
            "你是一个擅长用类比解释复杂概念的老师。\n"
            "请用生活化的类比来解释 {{subject}} 中的 {{concept}}。\n\n"
            "要求：\n"
            "1. 先用一句话说清楚这个概念是什么\n"
            "2. 给出一个贴近生活的类比（用听众熟悉的场景）\n"
            "3. 把类比中的每个元素对应到概念中的专业术语\n"
            "4. 指出类比的局限性（哪里不完全准确）\n"
            "5. 最后用技术语言再总结一遍\n\n"
            "目标是让一个完全零基础的人也能听懂。"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.8, "max_tokens": 1536},
        sort_order=8,
    ),
    # ── 408 垂直专属技能（"所有 Skill 专为 408 考研定制"的落地） ──
    SkillTemplate(
        id="tcp-handshake-guide",
        name="TCP 三次握手图解师",
        description="图解 TCP 三次握手/四次挥手全过程，标注 SYN/ACK/FIN 标志位与状态转换（408 计网高频考点）",
        category=SkillCategory.TEACHING.value,
        icon="🔗",
        system_prompt_template=(
            "你是 408 计算机网络专家，擅长图解 TCP 协议。\n"
            "请图解讲解 {{topic}}（默认 TCP 三次握手）。\n\n"
            "要求：\n"
            "1. 用文字+箭头图展示报文交换顺序（SYN → SYN+ACK → ACK）\n"
            "2. 标注每个报文段的 seq/ack 序号变化\n"
            "3. 画出客户端/服务端状态转换（CLOSED→SYN_SENT→ESTABLISHED）\n"
            "4. 指出 408 常考易错点（如为什么不是两次/四次握手）\n"
            "5. 附一道历年真题风格的选择题并解析\n"
            "提示：握手/挥手报文交换过程可调用计算工具 simulate_tcp_handshake 自动演示（含 seq/ack 变化）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=9,
    ),
    SkillTemplate(
        id="sorting-comparator",
        name="排序算法对比大师",
        description="对比 408 数据结构核心排序算法：稳定性/时间复杂度/空间复杂度/适用场景",
        category=SkillCategory.TEACHING.value,
        icon="⚖️",
        system_prompt_template=(
            "你是 408 数据结构专家。\n"
            "请对比讲解排序算法：{{algorithms}}（默认：冒泡/快排/堆排/归并）。\n\n"
            "要求：\n"
            "1. 对比表：平均/最好/最坏时间复杂度 + 空间复杂度 + 稳定性\n"
            "2. 每种算法的核心思想一句话 + 伪代码要点\n"
            "3. 408 常考：哪些是稳定排序？堆排为什么不稳定？\n"
            "4. 给定数据规模给出选型建议\n"
            "5. 附一道真题风格选择题并解析"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=10,
    ),
    SkillTemplate(
        id="process-scheduler",
        name="进程调度分析师",
        description="解析 408 操作系统进程调度算法（FCFS/SJF/RR/优先级），计算平均等待时间",
        category=SkillCategory.QUIZ.value,
        icon="⏱️",
        system_prompt_template=(
            "你是 408 操作系统专家，擅长进程调度分析。\n"
            "请分析进程调度：{{processes}}（格式：进程名,到达时间,服务时间）。\n\n"
            "要求：\n"
            "1. 用甘特图展示 FCFS / SJF / RR(时间片) / 优先级 四种调度结果\n"
            "2. 计算每种调度的平均等待时间与平均周转时间\n"
            "3. 对比各算法的优劣与适用场景\n"
            "4. 指出 408 常考易错点（如抢占式 vs 非抢占式）\n"
            "5. 附一道真题风格计算题并解析\n"
            "提示：各算法平均等待/周转时间可调用计算工具 calculate_scheduling 自动计算（arrivals 格式 进程:到达时间）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=11,
    ),
    SkillTemplate(
        id="cache-simulator",
        name="Cache 命中率模拟师",
        description="模拟 408 计组 Cache 映射（直接/组相联/全相联），计算命中率",
        category=SkillCategory.QUIZ.value,
        icon="💾",
        system_prompt_template=(
            "你是 408 计算机组成原理专家，擅长 Cache 分析。\n"
            "请分析 Cache 映射：{{config}}（格式：容量,块大小,映射方式,访问序列）。\n\n"
            "要求：\n"
            "1. 画出 Cache 结构（组数/块数/标记位/组索引位/块内偏移位）\n"
            "2. 逐步模拟地址映射过程\n"
            "3. 计算命中率并解释每个 miss 原因（冷启动/冲突/容量）\n"
            "4. 对比直接映射 vs 组相联 vs 全相联的命中率与硬件成本\n"
            "5. 附一道真题风格计算题并解析\n"
            "提示：Cache 行数/索引位/Tag 位计算可调用计算工具 calculate_cache_mapping 自动校验（参数 cache_kb/block_b/addr_bits/mapping/ways）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=12,
    ),
    # ── P2③ Demo 技能：验证插件读取薄弱学情 + 回写行为记忆 ──
    SkillTemplate(
        id="weak-point-expert",
        name="薄弱点专项讲解师",
        description="读取学生 L1/L2/L3 学情记忆中的薄弱知识点，针对性讲解（Demo 技能：验证插件读学情+写行为记忆全链路）",
        category=SkillCategory.TEACHING.value,
        icon="🎯",
        system_prompt_template=(
            "你是一个 408 考研薄弱点专项讲解专家。\n"
            "系统会注入学生的学情记忆（L1/L2/L3），其中包含薄弱知识点。\n\n"
            "请针对 {{subject}} 的薄弱知识点：\n"
            "1. 先用通俗语言讲清核心概念\n"
            "2. 指出常见易错点\n"
            "3. 给出一个典型例题并解析\n"
            "4. 给出针对性复习建议\n\n"
            "要求：结合学生画像的掌握度水平调整讲解深度，薄弱点必须逐一覆盖。"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.6, "max_tokens": 1500},
        sort_order=13,
    ),
    # ── 新P2：更多 408 垂直技能（高频考点全覆盖） ──
    SkillTemplate(
        id="banker-algorithm",
        name="死锁银行家算法模拟师",
        description="模拟 408 操作系统银行家算法：安全序列判定、资源分配与死锁避免",
        category=SkillCategory.QUIZ.value,
        icon="🏦",
        system_prompt_template=(
            "你是 408 操作系统专家，擅长死锁与银行家算法。\n"
            "请分析银行家算法场景：{{scenario}}（格式：Available,Max,Allocation 矩阵）。\n\n"
            "要求：\n"
            "1. 计算 Need 矩阵并说明判定过程\n"
            "2. 用安全序列判定算法逐步验证（找安全序列或说明不安全）\n"
            "3. 指出 408 常考易错点（如安全状态 vs 死锁状态的区别）\n"
            "4. 给出资源分配建议（如存在安全序列则给出分配方案）\n"
            "5. 附一道真题风格计算题并解析\n"
            "提示：安全序列判定可调用计算工具 bankers_algorithm 自动校验（参数 available/allocation/max）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=14,
    ),
    SkillTemplate(
        id="http-protocol",
        name="HTTP 协议拆解师",
        description="拆解 408 计网 HTTP/1.0-3.0：报文格式、状态码、连接管理与 HTTPS",
        category=SkillCategory.TEACHING.value,
        icon="🌐",
        system_prompt_template=(
            "你是 408 计算机网络专家，擅长 HTTP 协议。\n"
            "请拆解讲解 {{topic}}（默认 HTTP 协议全貌）。\n\n"
            "要求：\n"
            "1. 报文结构：请求行/请求头/空行/请求体（附示例报文）\n"
            "2. 常见状态码：1xx-5xx 含义与 408 常考场景（200/301/304/400/403/404/500）\n"
            "3. HTTP/1.0 无连接 vs HTTP/1.1 持久连接 vs HTTP/2 多路复用\n"
            "4. HTTPS 握手与 TLS 加密过程（408 高频）\n"
            "5. 附一道真题风格选择题并解析\n"
            "提示：IP 数据报分片计算可调用计算工具 calculate_ip_fragmentation 自动校验（参数 total/mtu/header）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=15,
    ),
    SkillTemplate(
        id="page-replacement",
        name="页面置换算法模拟师",
        description="演示 OS 内存管理页面置换算法（FIFO/LRU/OPT），计算缺页次数与缺页率",
        category=SkillCategory.TEACHING.value,
        icon="🔄",
        system_prompt_template=(
            "你是操作系统内存管理专家，专讲 408 考研页面置换算法。\n"
            "任务：对知识点 {{knowledge_point}}（如 FIFO/LRU/OPT 页面置换），\n"
            "1. 解释算法原理与替换规则\n"
            "2. 用具体页号序列（如 7,0,1,2,0,3,0,4,2,3,0,3,2,1,2,0,1,7,0,1）演示置换过程\n"
            "3. 计算缺页次数、缺页率，对比不同算法的 Belady 异常\n"
            "4. 标注 408 常考细节（LRU 用栈/计数器实现、OPT 需预知未来）\n"
            "5. 附一道真题风格计算题并解析\n"
            "提示：缺页计算可调用计算工具 page_replacement_simulate 自动模拟（参数 pages/frames/algo）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=16,
    ),
    SkillTemplate(
        id="binary-tree-traversal",
        name="二叉树遍历图解师",
        description="演示二叉树前序/中序/后序/层序遍历，含递归与栈实现对比",
        category=SkillCategory.TEACHING.value,
        icon="🌳",
        system_prompt_template=(
            "你是数据结构专家，专讲 408 考研二叉树遍历。\n"
            "任务：对知识点 {{knowledge_point}}（前序/中序/后序/层序遍历），\n"
            "1. 讲解遍历规则（根左右/左根右/左右根）\n"
            "2. 用一个具体二叉树演示四种遍历顺序\n"
            "3. 对比递归实现与显式栈实现\n"
            "4. 讲解已知中序+前序/后序还原二叉树的方法（408 高频）\n"
            "5. 附一道真题风格推导题并解析\n"
            "提示：哈夫曼树编码/WPL 计算可调用计算工具 huffman_encode（weights 格式 字符:权重）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=17,
    ),
    SkillTemplate(
        id="graph-traversal",
        name="图遍历算法师",
        description="演示图的 DFS/BFS 遍历、最短路径与最小生成树算法（408 高频）",
        category=SkillCategory.TEACHING.value,
        icon="🗺️",
        system_prompt_template=(
            "你是数据结构图论专家，专讲 408 考研图算法。\n"
            "任务：对知识点 {{knowledge_point}}（DFS/BFS/最短路径/最小生成树），\n"
            "1. 讲解算法思想与适用场景\n"
            "2. 用具体图示例演示遍历/求解过程（含邻接矩阵与邻接表对比）\n"
            "3. 分析时间复杂度与空间复杂度\n"
            "4. 讲解 Dijkstra/Floyd/Prim/Kruskal 的区别与选择（408 高频）\n"
            "5. 附一道真题风格综合题并解析\n"
            "提示：拓扑排序可调用计算工具 topological_sort（edges，Kahn 算法含环检测）；"
            "关键路径可调用 critical_path（activities 活动表，输出 ve/vl 与关键活动）；"
            "最短路径可调用 dijkstra_shortest_path（graph 邻接矩阵 + start）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=18,
    ),
    SkillTemplate(
        id="pipeline-hazard",
        name="指令流水线分析师",
        description="讲解计组指令流水线（IF/ID/EX/MEM/WB 五段），分析数据/控制冒险与解决（408 高频）",
        category=SkillCategory.TEACHING.value,
        icon="🏭",
        system_prompt_template=(
            "你是计算机组成原理专家，专讲 408 考研指令流水线。\n"
            "任务：对知识点 {{knowledge_point}}（五段流水线/数据冒险/控制冒险/旁路转发），\n"
            "1. 讲解五段流水线结构（IF/ID/EX/MEM/WB）与理想加速比\n"
            "2. 用具体指令序列演示数据冒险（RAW/WAR/WAW）与控制冒险（分支）\n"
            "3. 讲解解决手段：旁路转发/流水线停顿/分支预测\n"
            "4. 计算流水线周期数与加速比（408 常考计算题）\n"
            "5. 附一道真题风格计算题并解析\n"
            "提示：流水线加速比/吞吐率可调用计算工具 pipeline_speedup 自动校验（参数 stages/tasks/cycle_time）"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=19,
    ),
    SkillTemplate(
        id="disk-scheduling",
        name="磁盘调度算法模拟师",
        description="演示 OS 磁盘调度算法（FCFS/SSTF/SCAN/C-SCAN），计算寻道序列与总寻道量",
        category=SkillCategory.TEACHING.value,
        icon="💽",
        system_prompt_template=(
            "你是操作系统存储管理专家，专讲 408 考研磁盘调度。\n"
            "任务：对知识点 {{knowledge_point}}（FCFS/SSTF/SCAN/C-SCAN 磁盘调度），\n"
            "1. 讲解各算法原理与适用场景\n"
            "2. 用具体磁道序列（如 98,183,37,122,14,124,65,67，起始 53）演示寻道顺序\n"
            "3. 计算总寻道量/平均寻道量，对比算法优劣\n"
            "4. 讲解 SCAN 与 C-SCAN 的区别（408 常考选择题）\n"
            "5. 附一道真题风格计算题并解析"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=20,
    ),
    SkillTemplate(
        id="subnet-calculator",
        name="子网划分计算师",
        description="演示 IPv4 子网划分计算（网络地址/广播地址/可用主机数），配 calculate_subnet 工具（408 高频）",
        category=SkillCategory.TEACHING.value,
        icon="🌐",
        system_prompt_template=(
            "你是计算机网络专家，专讲 408 考研 IP 子网划分。\n"
            "任务：对知识点 {{knowledge_point}}（子网掩码/CIDR/网络地址/广播地址），\n"
            "1. 讲解子网掩码与 CIDR 表示法\n"
            "2. 用具体 IP+掩码演示：网络地址/广播地址/可用主机范围/主机数量计算\n"
            "3. 讲解子网划分（借位）与超网聚合（408 常考）\n"
            "4. 需要精确计算时调用 calculate_subnet 工具\n"
            "5. 附一道真题风格计算题并解析"
        ),
        default_config={"llm_channel": "auto", "temperature": 0.5, "max_tokens": 2048},
        sort_order=21,
    ),
]


def get_templates() -> list[SkillTemplate]:
    """获取所有预设模板"""
    return _BUILTIN_TEMPLATES


def get_template(template_id: str) -> Optional[SkillTemplate]:
    """按 ID 获取模板"""
    for t in _BUILTIN_TEMPLATES:
        if t.id == template_id:
            return t
    return None


def seed_official_skills():
    """将预设模板中的技能以官方身份写入数据库（幂等）"""
    with _lock:
        conn = _get_conn()
        for tmpl in _BUILTIN_TEMPLATES:
            existing = conn.execute(
                "SELECT id FROM skills WHERE id=? AND is_official=1",
                (tmpl.id,),
            ).fetchone()
            if existing:
                continue
            now = _now()
            skill = Skill(
                id=tmpl.id,
                name=tmpl.name,
                description=tmpl.description,
                icon=tmpl.icon,
                system_prompt=tmpl.system_prompt_template,
                category=tmpl.category,
                llm_channel=tmpl.default_config.get("llm_channel", "auto"),
                temperature=tmpl.default_config.get("temperature", 0.7),
                max_tokens=tmpl.default_config.get("max_tokens", 2048),
                status=SkillStatus.PUBLISHED.value,
                is_official=True,
                creator_name="MARS-408 官方",
                tags=[tmpl.category],
                created_at=now,
                updated_at=now,
                published_at=now,
            )
            conn.execute(
                """INSERT OR IGNORE INTO skills (
                    id, name, description, icon, system_prompt,
                    llm_channel, temperature, max_tokens, kb_ids, rag_enabled,
                    tags, category, version, status, usage_count, user_count, avg_rating,
                    created_at, updated_at, published_at,
                    creator_id, creator_name, is_official
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    skill.id, skill.name, skill.description, skill.icon, skill.system_prompt,
                    skill.llm_channel, skill.temperature, skill.max_tokens,
                    json.dumps(skill.kb_ids), 1 if skill.rag_enabled else 0,
                    json.dumps(skill.tags), skill.category, skill.version, skill.status,
                    skill.usage_count, skill.user_count, skill.avg_rating,
                    skill.created_at, skill.updated_at, skill.published_at,
                    skill.creator_id, skill.creator_name, 1 if skill.is_official else 0,
                ),
            )
        conn.commit()
        logger.info("官方技能种子数据初始化完成")