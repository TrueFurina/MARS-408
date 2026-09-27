# ============================================================
# 用户域服务层（services 层）
# ------------------------------------------------------------
# 架构评审 M-2 收敛点：API 层一律经本模块访问用户域能力，
# 不再直接 ``import db.user_store``（消除「API 越级访问存储」）。
#
# 当前本模块是 ``db.user_store`` 公共表面的**委托再导出**（零行为变化），
# 后续可在此集中重复的业务规则（如所有权校验、计划重置等），
# 而不必让 27 个 api 模块各自直连存储。
# 私有符号（``_get_conn/_lock/_now``）**不**在此暴露——需要原始连接的
# 场景已改为调用下文的合规访问器（``get_wrong_question_owner`` /
# ``reset_daily_plan``），由 db 层在锁内完成。
# ============================================================

from db.user_store import (
    get_db_conn,
    create_user,
    authenticate,
    get_user_by_id,
    get_user_by_username,
    ensure_admin,
    set_password,
    save_profile,
    get_profile,
    append_quiz_history,
    get_quiz_history,
    save_conversations,
    get_conversations,
    list_all_users,
    get_platform_stats,
    save_profile_snapshot,
    get_profile_snapshots,
    create_assignment,
    get_assignment,
    list_assignments,
    submit_assignment,
    get_submission,
    register_learning_resource,
    get_learning_resource,
    list_learning_resources,
    delete_learning_resource,
    add_wrong_question,
    get_wrong_question,
    get_error_profile,
    record_review,
    get_due_reviews,
    list_wrong_questions,
    mark_wrong_question_mastered,
    delete_wrong_question,
    get_wrong_question_stats,
    get_or_create_daily_plan,
    update_daily_plan_task,
    list_daily_plans,
    # M-2 新增的合规访问器（替代 API 层越级访问 _get_conn/_lock/_now）
    get_wrong_question_owner,
    reset_daily_plan,
)

__all__ = [
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
    "get_wrong_question_owner",
    "reset_daily_plan",
]
