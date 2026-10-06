# ============================================================
# 轻量版本化迁移运行器（D6，最小实现，不引入 Alembic）
#
# 设计：
#   - 迁移目录：本模块同级 ``versions/``，按文件名升序顺序执行。
#   - 支持两类迁移：
#       *.sql  — 直接以 pg_client.migrate_exec 执行。
#                   请使用 CREATE TABLE IF NOT EXISTS 等幂等写法。
#       *.py   — 要求定义 ``upgrade(conn)``（conn 透传 pg_client._conn，
#                   PG 下为 psycopg2 连接，SQLite 回退下为 sqlite3 连接）。
#   - 已应用版本记录在 ``versions/applied.json``（相对目录，便于回滚/跟踪）。
#   - 幂等：lifespan 每次启动调用一次 run_migrations()，已应用的版本会跳过。
#
# 注意：数据库未连接（pg_client 未 enabled）时，迁移不执行也不记录，
# 下次启动再尝试；不抛异常以保证启动成功。
# ============================================================

import importlib.util
import json
import logging
import os
import re

from db.pg_client import pg_client

logger = logging.getLogger("netlearn.migrations")

_VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "versions")
_APPLIED_FILE = os.path.join(_VERSIONS_DIR, "applied.json")

# 迁移文件名前缀必须是递增版本号，如 0001_init_metrics.sql
_NAME_RE = re.compile(r"^(?P<ver>\d{1,6})_.*\.(sql|py)$")


def _load_applied() -> dict:
    if not os.path.exists(_APPLIED_FILE):
        return {}
    try:
        with open(_APPLIED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("读取 applied.json 失败，视为空: %s", e)
        return {}


def _save_applied(applied: dict) -> None:
    os.makedirs(_VERSIONS_DIR, exist_ok=True)
    tmp = _APPLIED_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(applied, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, _APPLIED_FILE)  # 原子写，避免半截文件


def run_migrations() -> int:
    """顺序应用未执行的迁移，返回本次新应用的数量。"""
    if not pg_client.is_enabled:
        logger.warning("数据库未启用，跳过迁移（下次启动再试）")
        return 0
    if not os.path.isdir(_VERSIONS_DIR):
        logger.info("无迁移目录 %s，跳过", _VERSIONS_DIR)
        return 0

    files = []
    for fname in os.listdir(_VERSIONS_DIR):
        m = _NAME_RE.match(fname)
        if m:
            files.append((m.group("ver"), fname))
    files.sort(key=lambda x: x[0])

    applied = _load_applied()
    applied_versions = set(applied.get("versions", []))
    newly = 0

    for ver, fname in files:
        if ver in applied_versions:
            continue
        path = os.path.join(_VERSIONS_DIR, fname)
        logger.info("应用迁移 %s ...", fname)
        try:
            if fname.endswith(".sql"):
                with open(path, "r", encoding="utf-8") as f:
                    sql = f.read()
                pg_client.migrate_exec(sql)
            elif fname.endswith(".py"):
                spec = importlib.util.spec_from_file_location(f"_migration_{ver}", path)
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"无法加载迁移模块 {fname}")
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                upgrade = getattr(mod, "upgrade", None)
                if not callable(upgrade):
                    raise RuntimeError(f"迁移 {fname} 未定义 upgrade(conn)")
                upgrade(pg_client._conn)
            else:
                continue
            applied_versions.add(ver)
            newly += 1
            logger.info("迁移 %s 成功", fname)
        except Exception as e:  # noqa: BLE001
            logger.error("迁移 %s 失败: %s", fname, e)
            # 不记录该版本，下次启动重试；中断后续以免级联失败
            break

    if newly:
        applied["versions"] = sorted(applied_versions)
        _save_applied(applied)
    return newly
