# ============================================================
# 遗忘曲线排程 —— 兼容别名（M-3 重构后）
# ------------------------------------------------------------
# 实现已下沉至 shared/review_scheduler.py：本模块的唯一消费方是 db 层
# （db/user_store 的错题本排程），留在 engines 会形成 db → engines 的反向依赖，
# 只能靠函数内延迟导入规避循环。下沉后依赖方向恢复单向。
#
# 本文件仅做**委托再导出**，不复制任何实现（单一真值源 = shared/review_scheduler）。
# 新代码请直接 `from shared.review_scheduler import ...`。
# ============================================================

from shared.review_scheduler import (  # noqa: F401
    MAX_STAGE,
    REVIEW_INTERVALS_DAYS,
    _coerce_dt,
    advance_stage,
    compute_initial_review,
    graduate_if_done,
    is_due,
    next_review_after,
    schedule_after_review,
)

__all__ = [
    "MAX_STAGE",
    "REVIEW_INTERVALS_DAYS",
    "_coerce_dt",
    "advance_stage",
    "compute_initial_review",
    "graduate_if_done",
    "is_due",
    "next_review_after",
    "schedule_after_review",
]
