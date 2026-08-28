# ============================================================
# PostgreSQL 关系数据库客户端（带 SQLite 本地回退）
# 存储：Agent 表现、用户画像、答题记录、会话历史
#
# 无 PostgreSQL 时自动降级到本地 `data/pg_fallback.db`，
# 使 GOMARL 动态权重等特性在开发环境也可真实运行。
# ============================================================

import json
import logging
import os
import sqlite3
import struct
import threading
from typing import Optional

from config import get_pg_config

logger = logging.getLogger("netlearn.pg")

try:
    import psycopg2
    import psycopg2.extras
    PG_AVAILABLE = True
except ImportError:
    logger.info("psycopg2 未安装，使用 SQLite 本地回退")
    PG_AVAILABLE = False

_FALLBACK_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_FALLBACK_DB = os.path.join(_FALLBACK_DIR, "pg_fallback.db")


def _coerce_scores(raw: list) -> list[float]:
    """将原始评分列表（可能为 float/int/str/bytes(BLOB)）统一转为 float。

    处理旧版写入的 IEEE-754 小端编码 BLOB：
      - 4 字节 → struct.unpack('<f', v)  (float32)
      - 8 字节 → struct.unpack('<d', v)  (float64)
    其余 bytes 尝试按 utf-8 文本解析；任何无法解析的值直接跳过，
    绝不抛出 TypeError。
    """
    out: list[float] = []
    for v in raw:
        if v is None:
            continue
        if isinstance(v, bytes):
            if len(v) == 4:
                try:
                    out.append(float(struct.unpack("<f", v)[0]))
                    continue
                except Exception:
                    pass
            elif len(v) == 8:
                try:
                    out.append(float(struct.unpack("<d", v)[0]))
                    continue
                except Exception:
                    pass
            try:
                v = v.decode("utf-8", "ignore")
            except Exception:
                continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


class PgClient:
    """PostgreSQL 关系数据库封装（自动 SQLite 回退）"""

    def __init__(self):
        self._conn = None
        self._enabled = False
        self._is_fallback = False
        self._lock = threading.Lock()

    def connect(self) -> bool:
        config = get_pg_config()
        # 优先尝试 PostgreSQL
        if PG_AVAILABLE and config.get("enabled", False):
            try:
                self._conn = psycopg2.connect(
                    host=config.get("host", "localhost"),
                    port=config.get("port", 5432),
                    dbname=config.get("database", "netlearn"),
                    user=config.get("user", "postgres"),
                    password=config.get("password", ""),
                )
                self._conn.autocommit = True
                self._enabled = True
                self._is_fallback = False
                self._init_schema_pg()
                logger.info("PostgreSQL 连接成功")
                return True
            except Exception as e:
                logger.warning(f"PostgreSQL 连接失败，降级到 SQLite: {e}")

        # SQLite 本地回退
        try:
            os.makedirs(_FALLBACK_DIR, exist_ok=True)
            self._conn = sqlite3.connect(_FALLBACK_DB, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._enabled = True
            self._is_fallback = True
            self._init_schema_sqlite()
            logger.info(f"SQLite 本地回退已启用: {_FALLBACK_DB}")
            return True
        except Exception as e:
            logger.error(f"SQLite 回退也失败: {e}")
            self._enabled = False
            return False

    def disconnect(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    # ── 迁移执行（D6 迁移框架使用） ──

    def migrate_exec(self, sql: str) -> None:
        """执行迁移 DDL/SQL（D6 迁移运行器调用）。

        兼容 PostgreSQL 与 SQLite 回退；幂等迁移请使用
        ``CREATE TABLE IF NOT EXISTS`` 等写法。
        数据库未连接时抛 RuntimeError，由运行器捕获并跳过后续。
        """
        if not self._enabled or self._conn is None:
            raise RuntimeError("数据库未连接，无法执行迁移")
        if self._is_fallback:
            with self._lock:
                self._conn.executescript(sql)
                self._conn.commit()
        else:
            with self._conn.cursor() as cur:
                cur.execute(sql)

    # ── Schema 初始化 ──

    def _init_schema_pg(self):
        with self._conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_profiles (
                    id VARCHAR(64) PRIMARY KEY,
                    profile JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_performance (
                    id SERIAL PRIMARY KEY,
                    agent_name VARCHAR(64) NOT NULL,
                    score FLOAT NOT NULL,
                    task_type VARCHAR(64),
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # P1-4: 行为事件表（行为驱动画像）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_behavior_events (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    event_type VARCHAR(32) NOT NULL,
                    topic VARCHAR(256) NOT NULL DEFAULT '',
                    duration_ms INTEGER DEFAULT 0,
                    resource_type VARCHAR(64) DEFAULT '',
                    ts TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_behavior_user ON student_behavior_events(user_id)
            """)

    def _init_schema_sqlite(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS agent_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    score REAL NOT NULL,
                    task_type TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_agent_name ON agent_performance(agent_name);
                CREATE TABLE IF NOT EXISTS student_profiles (
                    id TEXT PRIMARY KEY,
                    profile TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS student_behavior_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    topic TEXT NOT NULL DEFAULT '',
                    duration_ms INTEGER DEFAULT 0,
                    resource_type TEXT DEFAULT '',
                    ts TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_behavior_user ON student_behavior_events(user_id);
            """)
            self._conn.commit()

    # ── Agent 表现 ──

    def log_agent_score(self, agent_name: str, score: float, task_type: str = "", notes: str = ""):
        if not self._enabled:
            return
        if self._is_fallback:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO agent_performance (agent_name, score, task_type, notes) VALUES (?,?,?,?)",
                    (agent_name, score, task_type, notes),
                )
                self._conn.commit()
        else:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_performance (agent_name, score, task_type, notes) VALUES (%s,%s,%s,%s)",
                    (agent_name, score, task_type, notes),
                )

    def get_agent_history(self, agent_name: str, window: int = 5) -> list[float]:
        """获取 Agent 历史评分，用于 EWMA 动态权重计算。

        鲁棒性：历史库中可能存在旧版写入的 bytes/BLOB 形式分数
        （4/8 字节 IEEE-754 小端编码），直接 sum() 会触发
        TypeError: unsupported operand type(s) for +: 'int' and 'bytes'。
        此处统一还原为 float，跳过无法解析的非法值。
        """
        if not self._enabled:
            return []
        if self._is_fallback:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT score FROM agent_performance WHERE agent_name=? ORDER BY created_at DESC LIMIT ?",
                    (agent_name, window),
                ).fetchall()
                return _coerce_scores([row["score"] for row in rows])
        else:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT score FROM agent_performance WHERE agent_name = %s ORDER BY created_at DESC LIMIT %s",
                    (agent_name, window),
                )
                return _coerce_scores([row[0] for row in cur.fetchall()])

    # ── 画像操作 ──

    def get_profile(self, profile_id: str) -> Optional[dict]:
        if not self._enabled:
            return None
        if self._is_fallback:
            with self._lock:
                row = self._conn.execute(
                    "SELECT profile FROM student_profiles WHERE id=?", (profile_id,)
                ).fetchone()
                return json.loads(row["profile"]) if row else None
        else:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT profile FROM student_profiles WHERE id = %s", (profile_id,))
                row = cur.fetchone()
                return row["profile"] if row else None

    def save_profile(self, profile_id: str, profile: dict):
        if not self._enabled:
            return
        data = json.dumps(profile, ensure_ascii=False)
        if self._is_fallback:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO student_profiles (id, profile, updated_at) VALUES (?,?, datetime('now'))",
                    (profile_id, data),
                )
                self._conn.commit()
        else:
            with self._conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO student_profiles (id, profile, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (id) DO UPDATE SET profile = %s, updated_at = NOW()
                """, (profile_id, data, data))

    # ── 行为事件（P1-4）──

    def log_behavior_event(self, event) -> None:
        """记录单条行为事件到 student_behavior_events 表。

        Args:
            event: BehaviorEvent dataclass 实例（agents/behavior_tracker.py）
        """
        if not self._enabled:
            return
        if self._is_fallback:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO student_behavior_events (user_id, event_type, topic, duration_ms, resource_type) "
                    "VALUES (?,?,?,?,?)",
                    (event.user_id, event.event_type, event.topic,
                     event.duration_ms, event.resource_type),
                )
                self._conn.commit()
        else:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO student_behavior_events (user_id, event_type, topic, duration_ms, resource_type) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (event.user_id, event.event_type, event.topic,
                     event.duration_ms, event.resource_type),
                )

    def update_profile_partial(self, profile_id: str, partial: dict) -> dict:
        """合并 partial 到既有 profile（深合并 behavior_signals），写回 student_profiles。

        Args:
            profile_id: 用户/画像 ID
            partial: 增量字段 dict（如 {"weak_points": "...", "behavior_signals": {...}}）

        Returns:
            更新后的完整 profile dict。
        """
        if not self._enabled:
            return {}
        existing = self.get_profile(profile_id) or {}

        # 深合并：behavior_signals 子字段逐键合并
        if "behavior_signals" in partial and "behavior_signals" in existing:
            merged_signals = {**existing["behavior_signals"], **partial["behavior_signals"]}
            partial["behavior_signals"] = merged_signals

        # 浅合并其他字段
        existing.update(partial)

        # 写回
        self.save_profile(profile_id, existing)
        return existing


# 全局单例
pg_client = PgClient()
