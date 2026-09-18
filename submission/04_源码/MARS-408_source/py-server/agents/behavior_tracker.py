# ============================================================
# 行为驱动画像更新（P1-4）
#
# 从前端/聊天/资源生成中收集行为事件（dwell/reattempt/resource_click），
# 轻量规则映射到画像的 behavior_signals 子字段，不影响既有 8 维 completed 判定。
#
# 设计约束：
#   - 纯 Python + 既有 pg_client（不引入 Redis）
#   - 轻量规则，无 LLM 依赖
#   - fire-and-forget 调用，绝不阻塞主链路
# ============================================================

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from db.pg_client import pg_client

logger = logging.getLogger("netlearn.behavior_tracker")

# ── 阈值常量（与 config.json 的 behavior_tracking 节同步，此处为代码兜底默认值）──
_DEFAULT_DWELL_THRESHOLD_MS = 60_000   # 停留 > 60s → 薄弱点
_DEFAULT_REATTEMPT_THRESHOLD = 2       # 重答 ≥ 2 次 → 薄弱点置顶
_DEFAULT_HOT_TOPIC_TOPN = 5            # 高频点击 Top-N


@dataclass
class BehaviorEvent:
    """单条行为事件。

    Attributes:
        user_id: 用户/画像 ID
        event_type: 事件类型 dwell(停留) / reattempt(重答) / resource_click(资源点击)
        topic: 关联知识点/主题
        duration_ms: 停留时长（dwell 专用），单位毫秒
        resource_type: 资源类型（resource_click 专用）teacher/quiz/ppt/...
        timestamp: ISO8601 时间戳，空则自动填充当前时间
    """
    user_id: str
    event_type: Literal["dwell", "reattempt", "resource_click"]
    topic: str
    duration_ms: int = 0
    resource_type: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ── 规则提取（纯函数，可单测）──

def _dwell_to_weak(
    events: list[BehaviorEvent],
    dwell_threshold_ms: int = _DEFAULT_DWELL_THRESHOLD_MS,
) -> list[str]:
    """dwell 事件中平均停留时长超过阈值的 topic → 薄弱点列表。

    Returns:
        按 avg_duration_ms 降序排列的 topic 列表。
    """
    topic_durations: dict[str, list[int]] = {}
    for ev in events:
        if ev.event_type != "dwell" or not ev.topic:
            continue
        topic_durations.setdefault(ev.topic, []).append(ev.duration_ms)

    avg_list: list[tuple[str, float]] = []
    for topic, durations in topic_durations.items():
        avg_ms = sum(durations) / len(durations)
        if avg_ms > dwell_threshold_ms:
            avg_list.append((topic, avg_ms))

    avg_list.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in avg_list]


def _reattempt_to_priority(events: list[BehaviorEvent]) -> list[str]:
    """reattempt 事件中重答次数 ≥ 阈值的 topic → 置顶薄弱点列表。

    Returns:
        按重答次数降序排列的 topic 列表。
    """
    topic_counts: dict[str, int] = {}
    for ev in events:
        if ev.event_type != "reattempt" or not ev.topic:
            continue
        topic_counts[ev.topic] = topic_counts.get(ev.topic, 0) + 1

    priority = [
        (topic, cnt) for topic, cnt in topic_counts.items()
        if cnt >= _DEFAULT_REATTEMPT_THRESHOLD
    ]
    priority.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in priority]


def _click_to_interest(
    events: list[BehaviorEvent],
    topn: int = _DEFAULT_HOT_TOPIC_TOPN,
) -> list[str]:
    """resource_click 事件中频次最高的 topic → 兴趣领域列表（Top-N）。"""
    topic_counts: dict[str, int] = {}
    for ev in events:
        if ev.event_type != "resource_click" or not ev.topic:
            continue
        topic_counts[ev.topic] = topic_counts.get(ev.topic, 0) + 1

    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    return [t for t, _ in sorted_topics[:topn]]


def _load_config() -> dict:
    """从 config.json 读取 behavior_tracking 配置节，失败时返回空 dict（用代码默认值）。"""
    try:
        from config import load_config
        return load_config().get("behavior_tracking", {})
    except Exception:
        return {}


async def update_profile_from_behavior(
    profile_id: str,
    events: list[BehaviorEvent],
) -> dict:
    """轻量规则：根据行为事件更新画像 behavior_signals 子字段。

    规则：
      - dwell_avg > 60s 的 topic → 加入 weak_points
      - reattempt ≥ 2 次 → weak_points 置顶
      - resource_click 频次 → interest_area

    不修改既有 8 维 completed 判定；仅深合并 behavior_signals。

    Args:
        profile_id: 用户/画像 ID
        events: 行为事件列表

    Returns:
        更新后的完整 profile dict；若 pg_client 不可用则返回空 dict。
    """
    if not events:
        return {}

    cfg = _load_config()
    dwell_threshold = cfg.get("dwell_threshold_ms", _DEFAULT_DWELL_THRESHOLD_MS)
    hot_topn = cfg.get("hot_topic_topn", _DEFAULT_HOT_TOPIC_TOPN)

    # 规则提取
    dwell_weak = _dwell_to_weak(events, dwell_threshold)
    reattempt_priority = _reattempt_to_priority(events)
    click_interest = _click_to_interest(events, hot_topn)

    # 合并薄弱点：reattempt 置顶 → dwell 补充（去重）
    merged_weak: list[str] = []
    seen: set[str] = set()
    for topic in reattempt_priority + dwell_weak:
        if topic not in seen:
            merged_weak.append(topic)
            seen.add(topic)

    # 构造 behavior_signals 增量
    behavior_signals: dict = {
        "dwell_topics": {ev.topic: ev.duration_ms for ev in events if ev.event_type == "dwell" and ev.topic},
        "reattempt_topics": reattempt_priority,
        "hot_topics": click_interest,
        "last_active": datetime.now(timezone.utc).isoformat(),
    }

    # 合并薄弱点到既有 weak_points（不覆盖，只追加新项）
    partial: dict = {"behavior_signals": behavior_signals}
    if merged_weak:
        # 读取既有 profile，合并 weak_points
        existing = pg_client.get_profile(profile_id) or {}
        existing_weak = existing.get("weak_points", "")
        if isinstance(existing_weak, str):
            existing_weak_list = [w.strip() for w in existing_weak.split(",") if w.strip()]
        elif isinstance(existing_weak, list):
            existing_weak_list = list(existing_weak)
        else:
            existing_weak_list = []

        # 追加新薄弱点（去重，保持既有顺序）
        for topic in merged_weak:
            if topic not in existing_weak_list:
                existing_weak_list.append(topic)

        partial["weak_points"] = ", ".join(existing_weak_list) if isinstance(existing_weak, str) else existing_weak_list

    # 追加兴趣领域
    if click_interest:
        existing = pg_client.get_profile(profile_id) or {}
        existing_interest = existing.get("interest_area", "")
        if isinstance(existing_interest, str):
            existing_interest_list = [i.strip() for i in existing_interest.split(",") if i.strip()]
        elif isinstance(existing_interest, list):
            existing_interest_list = list(existing_interest)
        else:
            existing_interest_list = []

        for topic in click_interest:
            if topic not in existing_interest_list:
                existing_interest_list.append(topic)

        partial["interest_area"] = ", ".join(existing_interest_list) if isinstance(existing_interest, str) else existing_interest_list

    # 逐条记录事件到 student_behavior_events 表
    for ev in events:
        try:
            pg_client.log_behavior_event(ev)
        except Exception as e:
            logger.warning(f"行为事件写入失败(user={ev.user_id}, topic={ev.topic}): {e}")

    # L1/L2/L3 三层学情记忆回写（低侵入：行为事件入 L3 情景记忆，支撑记忆驱动评估）
    try:
        from services.memory_service import record_behavior
        for ev in events:
            record_behavior(
                ev.user_id, ev.event_type, ev.topic,
                duration_ms=ev.duration_ms, resource_type=ev.resource_type,
            )
    except Exception as _me:
        logger.debug(f"行为事件记忆回写失败(忽略): {_me}")

    # 深合并到既有 profile
    try:
        updated = pg_client.update_profile_partial(profile_id, partial)
        logger.info(
            f"行为画像更新完成(user={profile_id}): "
            f"dwell_weak={len(dwell_weak)}, reattempt={len(reattempt_priority)}, "
            f"interest={len(click_interest)}"
        )
        return updated
    except Exception as e:
        logger.error(f"行为画像更新失败(user={profile_id}): {e}")
        return {}
