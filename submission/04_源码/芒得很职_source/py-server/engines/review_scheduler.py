# ============================================================
# 遗忘曲线排程引擎（review_scheduler）
# ------------------------------------------------------------
# 基于艾宾浩斯遗忘曲线的间隔复习（spaced repetition）排程。
# 纯规则、离线可复现，不依赖任何外部服务。
#
# 设计：
#   - 每道错题维护一个复习阶段 review_stage（0..MAX_STAGE）
#   - 阶段越高，下次复习间隔越长（对抗遗忘）
#   - 复习「答对」→ 阶段+1（间隔拉长）；「答错 / 忘记」→ 回到阶段 0（重新巩固）
#   - 达到最高阶段且仍答对 → 标记可毕业（建议移除错题本）
#
# 间隔天数取自经典记忆曲线经验值（天）：1, 2, 4, 7, 15, 30
# ============================================================

from datetime import datetime, timedelta
from typing import Optional

# 复习间隔天数表：索引 = 当前阶段，值 = 该阶段完成后「距今天数」触发下次复习
REVIEW_INTERVALS_DAYS = [1, 2, 4, 7, 15, 30]
MAX_STAGE = len(REVIEW_INTERVALS_DAYS) - 1


def _coerce_dt(value) -> Optional[datetime]:
    """把 int/float(时间戳) / str(ISO) / datetime 统一成 datetime。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # 兼容 "2026-08-29 12:00:00" 与 ISO "2026-08-29T12:00:00"
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        # 最后尝试 fromisoformat（容忍尾部 Z）
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def next_review_after(stage: int, base: Optional[datetime] = None) -> datetime:
    """给定当前阶段，返回「下一次应复习的日期」（base 默认 now）。"""
    stage = max(0, min(int(stage), MAX_STAGE))
    base = base or datetime.now()
    return base + timedelta(days=REVIEW_INTERVALS_DAYS[stage])


def advance_stage(stage: int, recalled_correct: bool) -> int:
    """根据本次回忆结果推进阶段。答对进阶，答错归零。"""
    stage = max(0, min(int(stage), MAX_STAGE))
    if recalled_correct:
        return min(stage + 1, MAX_STAGE)
    return 0


def is_due(next_review_at, now: Optional[datetime] = None) -> bool:
    """判断是否已到复习时间。"""
    nxt = _coerce_dt(next_review_at)
    if nxt is None:
        return True  # 无排程信息视为立即复习
    now = now or datetime.now()
    return nxt <= now


def compute_initial_review(first_wrong_at=None) -> dict:
    """新错题的初始排程：下一复习=首次错题 + 1 天，阶段 0。"""
    base = _coerce_dt(first_wrong_at) or datetime.now()
    nxt = next_review_after(0, base)
    return {
        "review_stage": 0,
        "next_review_at": nxt.isoformat(sep=" "),
    }


def graduate_if_done(stage: int, recalled_correct: bool) -> bool:
    """达到最高阶段且本次答对 → 可毕业（建议移出错题本）。"""
    return stage >= MAX_STAGE and bool(recalled_correct)


def schedule_after_review(
    prev_stage: int,
    prev_next_review_at,
    recalled_correct: bool,
    now: Optional[datetime] = None,
) -> dict:
    """复习后计算新排程。返回 {review_stage, next_review_at, graduated}。"""
    now = now or datetime.now()
    new_stage = advance_stage(prev_stage, recalled_correct)
    new_next = next_review_after(new_stage, now)
    graduated = graduate_if_done(prev_stage, recalled_correct)
    return {
        "review_stage": new_stage,
        "next_review_at": new_next.isoformat(sep=" "),
        "graduated": graduated,
    }
