# ============================================================
# 三层学情记忆服务层（对标 HKU-DeepTutor 记忆解耦）
#
# 作用：
#   1. 为智能体（agent）提供统一的记忆读写入口，解耦智能体内部
#      直接操作 SQLite 的耦合
#   2. 提供「记忆上下文组装」：将 L1/L2/L3 组装为 LLM 可用的
#      上下文提示块（低侵入，不触碰 GOMARL/FrugalRAG/辩论/规则引擎）
#   3. 提供「答题后记忆回写」：答题事件 → L2 掌握度更新 + L3 情景记录
# ============================================================

import json
import logging
import time
from typing import Optional

from db import memory_store as ms

logger = logging.getLogger("netlearn.memory_service")

# 章节级 key → 中文名映射（循环5-P2：薄弱点/掌握点英文 key 统一映射，
# 一次修复 18 处前端页面显示。与 api/review.py SUBJECT_NAMES 保持一致）
SUBJECT_NAMES = {
    "computer_network": "计算机网络",
    "data_structures": "数据结构",
    "computer_organization": "计算机组成原理",
    "operating_system": "操作系统",
    # 章节级科目映射
    "overview": "计网-概述", "physical": "计网-物理层", "datalink": "计网-数据链路层",
    "network": "计网-网络层", "transport": "计网-运输层", "application": "计网-应用层", "security": "计网-网络安全",
    "ds_linear": "数据结构-线性表", "ds_stack": "数据结构-栈和队列", "ds_string": "数据结构-串",
    "ds_tree": "数据结构-树与二叉树", "ds_graph": "数据结构-图", "ds_search": "数据结构-查找", "ds_sort": "数据结构-排序",
    "co_overview": "计组-概述", "co_data": "计组-数据表示", "co_memory": "计组-存储系统",
    "co_isa": "计组-指令系统", "co_cpu": "计组-CPU", "co_bus": "计组-总线", "co_io": "计组-输入输出",
    "os_overview": "OS-概述", "os_process": "OS-进程管理", "os_memory": "OS-内存管理",
    "os_file": "OS-文件管理", "os_io": "OS-输入输出",
}


def _cn_names(items: list) -> list:
    """将章节级 key 列表映射为中文名，映射失败保留原值"""
    return [SUBJECT_NAMES.get(i, i) for i in items]


# ────────────────────────────────────────────────────────────
# 记忆健康度总览 TTL 缓存（P1① 并发优化）
#   高并发读 /api/memory/overview 时避免重复查库组装；
#   记忆写入（答题/行为/L1 更新）时事件驱动失效，保证一致性。
#   缓存读写均 try/except 降级：缓存故障不影响主流程。
# ────────────────────────────────────────────────────────────
_OVERVIEW_TTL = 5.0  # 秒；答题/行为后 5s 内 overview 可短暂滞后，换取并发性能
_OVERVIEW_CACHE: dict[str, tuple[float, dict]] = {}

# ── build_memory_context 组装 TTL 缓存（新P1：27 文件消费，避免高并发重复组装）──
_CONTEXT_TTL = 5.0
_CONTEXT_CACHE: dict[str, tuple[float, str]] = {}  # key: f"{user_id}:{session_id or ''}:{max_episodes}"


def _invalidate_overview(user_id: str) -> None:
    """记忆写入后失效该用户 overview + context 缓存（事件驱动失效）"""
    try:
        _OVERVIEW_CACHE.pop(user_id, None)
        # context 缓存键含 user_id 前缀（不同 session/max_episodes 多条），遍历删除该用户条目
        prefix = f"{user_id}:"
        for k in [k for k in _CONTEXT_CACHE if k.startswith(prefix)]:
            _CONTEXT_CACHE.pop(k, None)
    except Exception:
        pass


def _overview_cache_get(user_id: str) -> Optional[dict]:
    """读缓存：命中且未过期返回浅拷贝，否则 None（降级）"""
    try:
        hit = _OVERVIEW_CACHE.get(user_id)
        if hit and time.time() - hit[0] < _OVERVIEW_TTL:
            return dict(hit[1])
    except Exception:
        pass
    return None


def _overview_cache_set(user_id: str, data: dict) -> None:
    """写缓存：失败静默降级（不阻断 overview 计算）"""
    try:
        _OVERVIEW_CACHE[user_id] = (time.time(), dict(data))
        if len(_OVERVIEW_CACHE) > 2048:  # 防无限增长
            _OVERVIEW_CACHE.clear()
    except Exception:
        pass


def _context_cache_get(key: str) -> Optional[str]:
    """读 context 组装缓存：命中且未过期返回，否则 None（降级）"""
    try:
        hit = _CONTEXT_CACHE.get(key)
        if hit and time.time() - hit[0] < _CONTEXT_TTL:
            return hit[1]
    except Exception:
        pass
    return None


def _context_cache_set(key: str, text: str) -> None:
    """写 context 组装缓存：失败静默降级"""
    try:
        _CONTEXT_CACHE[key] = (time.time(), text)
        if len(_CONTEXT_CACHE) > 2048:  # 防无限增长
            _CONTEXT_CACHE.clear()
    except Exception:
        pass


def init_student_memory(user_id: str, profile: Optional[dict] = None) -> dict:
    """初始化用户三层记忆（幂等）：画像入 L2，返回完整记忆骨架"""
    if profile:
        ms.save_semantic_memory(user_id, profile=profile)
    return ms.get_full_memory(user_id)


def build_memory_context(user_id: str, session_id: Optional[str] = None,
                         max_episodes: int = 10) -> str:
    """组装三层记忆为 LLM 上下文提示块（供智能体 prompt 使用）

    返回格式（Markdown）：
    【学生长期画像】... 【知识点掌握度】... 【近期学习事件】...
    无数据时返回简短占位，避免空提示块。

    新P1：TTL 缓存（键含 user_id/session_id/max_episodes），27 文件高并发
    消费时避免重复查库组装；记忆写入时事件驱动失效（_invalidate_overview）。
    """
    cache_key = f"{user_id}:{session_id or ''}:{max_episodes}"
    cached = _context_cache_get(cache_key)
    if cached is not None:
        return cached
    mem = ms.get_full_memory(user_id, session_id)
    l2 = mem.get("l2_semantic", {})
    blocks = []

    # L2 画像
    profile = l2.get("profile", {})
    if profile:
        lines = []
        for k, v in profile.items():
            if v not in (None, "", 0, "0", []):
                lines.append(f"- {k}: {v}")
        if lines:
            blocks.append("【学生长期画像】\n" + "\n".join(lines[:12]))

    # L2 掌握度
    mastery = l2.get("mastery", {})
    if mastery:
        weak = [(k, v) for k, v in mastery.items() if v < 0.5]
        strong = [(k, v) for k, v in mastery.items() if v >= 0.8]
        parts = []
        if weak:
            parts.append("薄弱: " + ", ".join(f"{k}({v:.0%})" for k, v in sorted(weak, key=lambda x: x[1])[:6]))
        if strong:
            parts.append("已掌握: " + ", ".join(f"{k}({v:.0%})" for k, v in sorted(strong, key=lambda x: -x[1])[:4]))
        if parts:
            blocks.append("【知识点掌握度】\n" + "\n".join(parts))

    # L1 工作记忆（会话上下文）
    l1 = mem.get("l1_working", {})
    if l1 and l1.get("current_topic"):
        blocks.append(f"【当前学习上下文】\n- 当前主题: {l1.get('current_topic')}")
        if l1.get("focus"):
            blocks.append(f"- 当前聚焦: {l1['focus']}")

    # L3 近期情景事件
    episodes = ms.get_episodes(user_id, limit=max_episodes)
    if episodes:
        lines = []
        for ep in episodes:
            ev = ep.get("event", {})
            if ep["event_type"] == "quiz":
                lines.append(f"- {ep['created_at'][5:16]} 答题: {ev.get('topic','')} {'✓' if ev.get('correct') else '✗'}")
            elif ep["event_type"] == "behavior":
                lines.append(f"- {ep['created_at'][5:16]} 行为: {ev.get('event_type','')} @ {ev.get('topic','')}")
        if lines:
            blocks.append("【近期学习事件】\n" + "\n".join(lines[:8]))

    if not blocks:
        result = "【学生记忆】暂无历史学习数据"
    else:
        result = "\n\n".join(blocks)
    _context_cache_set(cache_key, result)
    return result


def record_quiz_result(user_id: str, topic: str, correct: bool,
                       difficulty: str = "medium",
                       mastery_delta: float = 0.05) -> None:
    """答题后记忆回写：L2 掌握度更新 + L3 情景记录

    mastery_delta: 答对 +delta，答错 -delta（掌握度 0-1 钳位）
    """
    # L3 情景事件
    ms.append_episode(user_id, "quiz", {
        "topic": topic,
        "correct": correct,
        "difficulty": difficulty,
    })

    # L2 掌握度更新（简化：按知识点 id 直接调整）
    if topic:
        mem = ms.get_semantic_memory(user_id)
        current = mem["mastery"].get(topic, 0.5)
        new_val = current + mastery_delta if correct else current - mastery_delta * 1.5
        ms.update_mastery(user_id, topic, max(0.0, min(1.0, new_val)))

    # P1①：答题后记忆变化，失效 overview 缓存（事件驱动）
    _invalidate_overview(user_id)


def record_behavior(user_id: str, event_type: str, topic: str,
                    duration_ms: Optional[int] = None,
                    resource_type: Optional[str] = None) -> None:
    """行为事件入 L3 情景记忆"""
    ev = {"event_type": event_type, "topic": topic}
    if duration_ms is not None:
        ev["duration_ms"] = duration_ms
    if resource_type:
        ev["resource_type"] = resource_type
    ms.append_episode(user_id, "behavior", ev)

    # P1①：行为事件入记忆后失效 overview 缓存
    _invalidate_overview(user_id)


def update_working_topic(user_id: str, session_id: str, topic: str,
                         focus: Optional[str] = None) -> dict:
    """更新 L1 工作记忆的当前主题（会话级上下文）"""
    patch = {"current_topic": topic}
    if focus:
        patch["focus"] = focus
    result = ms.merge_working_memory(user_id, session_id, patch)
    # P1①：L1 工作记忆变化后失效 overview 缓存（working_context 字段依赖）
    _invalidate_overview(user_id)
    return result


def get_memory_overview(user_id: str) -> dict:
    """记忆健康度总览（供前端展示）—— P1①：TTL 缓存降低高并发重复查库"""
    cached = _overview_cache_get(user_id)
    if cached is not None:
        return cached
    full = ms.get_full_memory(user_id)
    l2 = full.get("l2_semantic", {})
    result = {
        "has_profile": bool(l2.get("profile")),
        "profile_dimensions": len([k for k, v in l2.get("profile", {}).items() if v not in (None, "", 0, "0", [])]),
        "mastery_points": len(l2.get("mastery", {})),
        "weak_points": _cn_names(l2.get("weak_points", [])),
        "mastered_points": _cn_names(l2.get("mastered_points", [])),
        "episodic_count": full.get("l3_episodic_count", 0),
        "working_context": bool(full.get("l1_working")),
        "memory_level": full.get("memory_profile", {}).get("level", "L3"),
    }
    _overview_cache_set(user_id, result)
    return result


# ────────────────────────────────────────────────────────────
# Skill 插件读写 L1/L2/L3 三层记忆标准化接口（P2①）
#   插件可结构化读取三层记忆（不只文本注入），并可写入
#   标准化行为事件（统一 schema）。全部 try/except 降级：
#   插件记忆读写失败不影响插件执行（记忆模块硬约束）。
# ────────────────────────────────────────────────────────────

def read_memory_for_plugin(user_id: str, session_id: Optional[str] = None,
                           layers: Optional[list[str]] = None) -> dict:
    """插件结构化读取 L1/L2/L3 三层记忆（P2① 标准化接口）

    layers: 指定读取层，如 ["L1", "L2", "L3"]；默认全部。
    返回: {"L1": {...}, "L2": {...}, "L3": {...}}
    失败降级：返回空结构（不抛异常，不阻塞插件）。
    """
    result: dict = {}
    try:
        full = ms.get_full_memory(user_id, session_id)
        l1 = full.get("l1_working") or {}
        l2 = full.get("l2_semantic") or {}
        want = layers or ["L1", "L2", "L3"]
        if "L1" in want:
            result["L1"] = {
                "working_context": bool(l1),
                "current_topic": (l1.get("current_topic") or "") if l1 else "",
                "focus": (l1.get("focus") or "") if l1 else "",
            }
        if "L2" in want:
            result["L2"] = {
                "profile": l2.get("profile", {}),
                "mastery": l2.get("mastery", {}),
                "weak_points": l2.get("weak_points", []),
                "mastered_points": l2.get("mastered_points", []),
            }
        if "L3" in want:
            result["L3"] = {
                "count": full.get("l3_episodic_count", 0),
                "recent_episodes": ms.get_episodes(user_id, limit=8),
            }
    except Exception as e:
        logger.debug(f"插件读记忆失败(降级为空): {e}")
    return result


def write_plugin_event(user_id: str, plugin_id: str, event_type: str,
                       topic: str = "", payload: Optional[dict] = None) -> None:
    """插件写入标准化行为事件到 L3 情景记忆（P2① 标准化接口）

    统一 schema：plugin_id / event_type / topic 在事件顶层（可追踪），
    payload 合并到顶层（保持既有事件字段兼容，如 skill_id/output_len）。
    外层事件类型 = 传入 event_type（与既有事件过滤兼容，如 skill_run）。
    失败降级：静默（不阻塞插件执行）。
    """
    try:
        ev: dict = {"plugin_id": plugin_id, "event_type": event_type}
        if topic:
            ev["topic"] = topic
        if payload:
            ev.update(payload)  # 合并到顶层（兼容既有消费者字段）
        ms.append_episode(user_id, event_type, ev)
        # 行为事件入记忆后失效 overview 缓存（P1① 缓存一致性）
        _invalidate_overview(user_id)
    except Exception as e:
        logger.debug(f"插件写记忆失败(忽略): {e}")
