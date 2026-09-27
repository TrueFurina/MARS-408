# ============================================================
# 用户域服务层（services 层）
# ------------------------------------------------------------
# 架构评审 M-2 收敛点：API 层一律经本模块访问用户域能力，
# 不再直接 ``import db.user_store``（消除「API 越级访问存储」）。
#
# 本模块是 ``db.user_store`` 公共表面的**动态委托门面**（零行为变化）。
#
# ⚠️ 为什么用 PEP 562 的 ``__getattr__`` 而不是静态 ``from db.user_store import x``：
# 静态导入会在本模块命名空间绑定一份「快照」，之后对 ``db.user_store`` 的任何
# 重绑定（monkeypatch、打桩、热替换）都**不会**传导过来 —— 经本模块访问到的
# 仍是旧对象，故障不报错、直接表现为「测试 patch 无效」或「降级分支没走到」。
# 2026-09-27 实战踩坑：test_config_observability 的 DB 故障降级断言因此失败
# （patch 了 db.user_store.get_db_conn，但 service 层仍返回真实连接，user_count=125 而非 0）。
# 动态委托让每次属性访问都穿透到真值源，符合 M-2「委托而非复制」的原意。
#
# 私有符号（``_get_conn/_lock/_now``）**不**在此暴露——需要原始连接的场景
# 已改为调用合规访问器（``get_wrong_question_owner`` / ``reset_daily_plan``），
# 由 db 层在锁内完成。
#
# 后续可在此集中真正的业务规则（如所有权校验、计划重置编排），而不必让
# 27 个 api 模块各自直连存储。
# ============================================================

import db.user_store as _user_store

# 显式白名单：只有登记在此的公共符号才会被转发出去（私有符号一律不外泄）。
# 之所以用常量名而非直接写 ``__all__``：本模块的符号是运行时动态委托的，
# 若写成字面量 ``__all__`` 会命中 ruff F822（"未定义"的假报警）——这不是要靠
# noqa 压下去的问题，而是「显式登记」与「动态解析」本来就该分离：
# 登记看 DELEGATED_NAMES，解析看 __getattr__，供 ``import *`` 用的 __all__ 由前者生成。
DELEGATED_NAMES = (
    "get_db_conn",
    "create_user",
    "authenticate",
    "get_user_by_id",
    "get_user_by_username",
    "ensure_admin",
    "set_password",
    "save_profile",
    "get_profile",
    "append_quiz_history",
    "get_quiz_history",
    "save_conversations",
    "get_conversations",
    "list_all_users",
    "get_platform_stats",
    "save_profile_snapshot",
    "get_profile_snapshots",
    "create_assignment",
    "get_assignment",
    "list_assignments",
    "submit_assignment",
    "get_submission",
    "register_learning_resource",
    "get_learning_resource",
    "list_learning_resources",
    "delete_learning_resource",
    "add_wrong_question",
    "get_wrong_question",
    "get_error_profile",
    "record_review",
    "get_due_reviews",
    "list_wrong_questions",
    "mark_wrong_question_mastered",
    "delete_wrong_question",
    "get_wrong_question_stats",
    "get_or_create_daily_plan",
    "update_daily_plan_task",
    "list_daily_plans",
    # M-2 新增的合规访问器（替代 API 层越级访问 _get_conn/_lock/_now）
    "get_wrong_question_owner",
    "reset_daily_plan",
)

__all__ = list(DELEGATED_NAMES)
_DELEGATED = frozenset(__all__)


def __getattr__(name: str):
    """把属性访问动态委托到 ``db.user_store``（单一真值源）。

    仅转发 ``__all__`` 内登记的公共表面；其余名字按 Python 语义抛 AttributeError，
    避免把 db 层私有符号（``_conn`` 等）顺带透出去。
    """
    if name in _DELEGATED:
        return getattr(_user_store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """补全 IDE / dir() 的可发现性（ __getattr__ 模式下的常规补齐）。"""
    return sorted(set(list(globals().keys()) | _DELEGATED))
