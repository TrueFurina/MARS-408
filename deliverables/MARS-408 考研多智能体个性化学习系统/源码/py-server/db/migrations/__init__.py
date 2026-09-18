# ============================================================
# DB 迁移框架（D6，最小实现，无 Alembic 依赖）
# 由 main.py 的 lifespan 幂等调用 run_migrations() 一次。
# 详见 runner.py 的设计说明。
# ============================================================

from .runner import run_migrations, _VERSIONS_DIR  # noqa: F401

__all__ = ["run_migrations", "_VERSIONS_DIR"]
