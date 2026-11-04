# -*- coding: utf-8 -*-
"""career_* 表的索引守卫（2026-11-02 性能审计）。

背景：`career_store` 里多处查询是「等值列 + ORDER BY」形态
（`WHERE user_id=? ORDER BY started_at DESC`、`WHERE join_code=?` 等），
但只有 dialogue_turns / class_students / feedback 建了索引，其余全是全表扫描。
数据量一上来就线性劣化。

本测试锁两件事：
1. 两套 DDL（PG 与 SQLite）**都**包含同一组索引——否则本地与生产的性能特征会分叉；
2. SQLite 落库后索引**确实存在**（不是脚本里写了但没执行）。
"""
from db import career_store

EXPECTED = (
    "idx_career_classes_teacher",
    "idx_career_tasks_join_code",
    "idx_career_tasks_teacher",
    "idx_career_tasks_class",
    "idx_career_sessions_user",
    "idx_career_sessions_task",
    "idx_career_assessments_session",
    "idx_career_students_user",
)


def test_both_ddl_declare_same_indexes():
    """两套 DDL 必须同口径（只改一套是最容易犯的错）。"""
    for name, ddl in (("PG", career_store._DDL_PG), ("SQLITE", career_store._DDL_SQLITE)):
        for idx in EXPECTED:
            assert idx in ddl, f"{name} DDL 缺少索引 {idx}"


def test_indexes_exist_after_ensure_tables():
    career_store.ensure_tables(force=True)

    # 双 dialect 探测：SQLite 查 sqlite_master，PG 查 pg_indexes。
    # ⚠️ 不要用 `except Exception: pytest.skip()` 兜底——那会把「参数传错」这类真 bug
    # 伪装成「本环境不适用」（本文件首版就踩过：`_query` 漏传 params 被吞成 skip）。
    try:
        rows = career_store._query(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_career_%'", ()
        )
    except Exception:
        rows = career_store._query(
            "SELECT indexname AS name FROM pg_indexes WHERE indexname LIKE 'idx_career_%'", ()
        )
    names = {r["name"] for r in rows}
    missing = [i for i in EXPECTED if i not in names]
    assert not missing, f"索引未真正创建：{missing}（DDL 写了但没执行？）"
