# ============================================================
# ability_store — 统一能力画像聚合表（双场景集成 · M1）
#
# 一个账号、一份画像：把两个业务场景的产出聚合到一行，供
# GET /api/profile/ability 读取（profile.py 优先读本表，未命中则实时聚合后回写）。
#
# 自包含幂等建表；复用全局 pg_client（PostgreSQL / SQLite 自动回退）。
# 表名 ability_profiles —— 跨场景共享层（既非 career_* 、也不是 408 业务表）。
#
# 【纪律】只新增、不迁移旧数据；任何读写异常一律 fail-open（返回 None/False），
# 由调用方回退到各源实时聚合，绝不让画像接口 500。
# ============================================================

import json
import logging
from typing import Optional

from db.pg_client import pg_client

logger = logging.getLogger("netlearn.ability.store")

_TABLES_READY = False

_DDL_PG = """
CREATE TABLE IF NOT EXISTS ability_profiles (
    user_id      VARCHAR(64) PRIMARY KEY,
    professional JSONB,
    soft_skills  JSONB,
    kaoyan_score JSONB,
    career_score JSONB,
    updated_at   TIMESTAMP DEFAULT NOW()
);
"""

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS ability_profiles (
    user_id      TEXT PRIMARY KEY,
    professional TEXT,
    soft_skills  TEXT,
    kaoyan_score TEXT,
    career_score TEXT,
    updated_at   TEXT DEFAULT (datetime('now'))
);
"""


def ensure_tables(force: bool = False) -> bool:
    """幂等建表。失败不阻塞（返回 False）。"""
    global _TABLES_READY
    if _TABLES_READY and not force:
        return True
    try:
        if not pg_client.is_enabled:
            pg_client.connect()
        pg_client.migrate_exec(_DDL_SQLITE if pg_client.is_fallback else _DDL_PG)
        _TABLES_READY = True
        logger.info("ability_profiles 表已就绪（%s）", "SQLite" if pg_client.is_fallback else "PostgreSQL")
        return True
    except Exception as e:
        logger.warning(f"ability 建表失败（非阻塞）: {e}")
        return False


def _dumps(o) -> Optional[str]:
    return json.dumps(o, ensure_ascii=False) if o is not None else None


def _loads(raw, default=None):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _q() -> str:
    return "?" if pg_client.is_fallback else "%s"


def get_profile(user_id: str) -> Optional[dict]:
    """读取聚合画像；无记录或异常返回 None（fail-open）。"""
    if not user_id or not ensure_tables():
        return None
    sql = (
        "SELECT user_id,professional,soft_skills,kaoyan_score,career_score,updated_at "
        f"FROM ability_profiles WHERE user_id={_q()}"
    )
    try:
        if pg_client.is_fallback:
            with pg_client._lock:
                row = pg_client._conn.execute(sql, (user_id,)).fetchone()
            if not row:
                return None
            return {
                "user_id": row["user_id"],
                "professional": _loads(row["professional"], {}),
                "soft_skills": _loads(row["soft_skills"], {}),
                "kaoyan_score": _loads(row["kaoyan_score"], None),
                "career_score": _loads(row["career_score"], None),
                "updated_at": row["updated_at"],
            }
        with pg_client._conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            row = cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "professional": _loads(row[1], {}),
            "soft_skills": _loads(row[2], {}),
            "kaoyan_score": _loads(row[3], None),
            "career_score": _loads(row[4], None),
            "updated_at": row[5],
        }
    except Exception as e:
        logger.warning(f"ability 读取失败（fail-open）: {e}")
        return None


def upsert_profile(user_id: str, *, professional=None, soft_skills=None,
                   kaoyan_score=None, career_score=None) -> bool:
    """按字段增量 upsert（None = 不改该字段）。异常返回 False（fail-open）。"""
    if not user_id or not ensure_tables():
        return False
    cur = get_profile(user_id) or {}
    p = professional if professional is not None else cur.get("professional")
    s = soft_skills if soft_skills is not None else cur.get("soft_skills")
    k = kaoyan_score if kaoyan_score is not None else cur.get("kaoyan_score")
    c = career_score if career_score is not None else cur.get("career_score")
    try:
        if cur:
            now = "datetime('now')" if pg_client.is_fallback else "NOW()"
            q = _q()
            sql = (
                f"UPDATE ability_profiles SET professional={q},soft_skills={q},"
                f"kaoyan_score={q},career_score={q},updated_at={now} WHERE user_id={q}"
            )
            params = (_dumps(p), _dumps(s), _dumps(k), _dumps(c), user_id)
        else:
            ph = ", ".join([_q()] * 5)
            sql = (
                "INSERT INTO ability_profiles "
                f"(user_id,professional,soft_skills,kaoyan_score,career_score) VALUES ({ph})"
            )
            params = (user_id, _dumps(p), _dumps(s), _dumps(k), _dumps(c))
        if pg_client.is_fallback:
            with pg_client._lock:
                pg_client._conn.execute(sql, params)
                pg_client._conn.commit()
        else:
            with pg_client._conn.cursor() as cur2:
                cur2.execute(sql, params)
        return True
    except Exception as e:
        logger.warning(f"ability 写入失败（fail-open）: {e}")
        return False
