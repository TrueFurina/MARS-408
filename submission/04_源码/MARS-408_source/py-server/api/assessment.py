# ============================================================
# API — 学习效果评估
# 从 learning.py 拆分 (D-05)
# ============================================================

import asyncio
import json
import logging
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends
from db.llm_provider import LLMProvider
from models import AssessmentRequest, AssessmentResponse
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from db.user_store import save_profile, get_profile

logger = logging.getLogger("netlearn.assessment")

router = APIRouter(prefix="", tags=["assessment"])

# 内存缓存：缓存评估结果，避免重复 LLM 调用
_assessment_cache: dict = {}
_CACHE_TTL = 60  # 缓存有效期 60 秒
_MAX_ASSESSMENT_CACHE = 200  # 缓存条目上限（超出时 LRU 驱逐最旧条目）


@router.post("/assessment", response_model=AssessmentResponse)
async def assessment_evaluate(req: AssessmentRequest, user: dict = Depends(require_llm_quota)):
    """学习效果评估。评估完成后自动将薄弱点反馈回写学生画像（赛题功能5：动态调整）"""
    from prompts import ASSESSMENT_PROMPT
    import time

    # 基于用户ID + 请求内容生成缓存 key
    user_id = user.get("id") or user.get("user_id")
    cache_key = f"{user_id}:{hashlib.sha256(json.dumps(req.quiz_history, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}"
    now = time.time()
    cached = _assessment_cache.get(cache_key)
    if cached and (now - cached["ts"]) < _CACHE_TTL:
        logger.info(f"评估缓存命中: user={user_id}")
        return cached["data"]

    total = len(req.quiz_history)
    correct = sum(1 for q in req.quiz_history if q.get("correct"))
    overall_acc = correct / max(total, 1)

    mastery, by_subject = {}, {}
    for q in req.quiz_history:
        subj = q.get("subject", "unknown")
        if subj not in by_subject:
            by_subject[subj] = {"total": 0, "correct": 0}
        by_subject[subj]["total"] += 1
        if q.get("correct"):
            by_subject[subj]["correct"] += 1

    for k, v in by_subject.items():
        v["accuracy"] = round(v["correct"] / max(v["total"], 1), 2)
        mastery[k] = v["accuracy"]

    activity = "高活跃" if total > 10 else "中等活跃" if total > 3 else "低活跃"
    trend = "上升" if overall_acc > 0.7 else "稳定" if overall_acc > 0.4 else "下降"

    weak_focus_list = [k for k, v in mastery.items() if v < 0.5]
    adjustment = "建议加强基础概念复习" if overall_acc < 0.5 else "建议适当提升难度" if overall_acc > 0.8 else "保持当前学习节奏"

    llm_assessed = False
    try:
        profile_str = "无"
        if req.profile:
            p = req.profile
            profile_str = f"基础:{p.get('knowledge_base','未知')} 薄弱点:{p.get('weak_points','无')} 目标:{p.get('goal','未知')}"
        user_in = f"学生画像: {profile_str}\n总题数: {total}\n正确率: {overall_acc:.2f}\n薄弱科目: {weak_focus_list}\n科目详情: {json.dumps(by_subject, ensure_ascii=False)}"
        llm = LLMProvider()
        # 添加超时控制，防止 LLM 卡死导致整个页面无响应
        result = await asyncio.wait_for(
            llm.text_completion(ASSESSMENT_PROMPT, user_in),
            timeout=5.0
        )
        if result:
            llm_assessed = True
    except asyncio.TimeoutError:
        logger.warning("LLM 评估超时（5s），返回降级评估结果")
    except Exception as e:
        logger.warning(f"LLM 评估失败: {e}")

    # 评估结果自动回写画像（赛题功能5：动态调整学习策略）
    try:
        existing = get_profile(user["user_id"]) or {}
        existing["weak_points"] = ",".join(weak_focus_list) if weak_focus_list else existing.get("weak_points", "")
        existing["recent_assessment"] = {
            "overall_accuracy": overall_acc,
            "trend": trend,
            "adjustment": adjustment,
            "activity": activity,
            "weak_focus": weak_focus_list,
            "mastery": mastery,
        }
        save_profile(user["user_id"], existing)
    except Exception as e:
        logger.warning(f"评估结果回写画像失败（非阻塞）: {e}")

    # L1/L2/L3 三层学情记忆回写（低侵入：评估结果写入 L2 掌握度 + L3 情景事件）
    try:
        user_id = user["user_id"]
        from db import memory_store as _ms
        # L2：薄弱点登记（保留既有薄弱点并追加本次评估发现的）
        from db import memory_store as _mems
        if weak_focus_list:
            mem = _mems.get_semantic_memory(user_id)
            merged_weak = list(dict.fromkeys(mem.get("weak_points", []) + weak_focus_list))
            _mems.save_semantic_memory(user_id, weak_points=merged_weak)
        # L3：记录评估事件（供趋势/审计追溯）
        _mems.append_episode(user_id, "assessment", {
            "overall_accuracy": overall_acc,
            "trend": trend,
            "weak_focus": weak_focus_list,
            "total_questions": total,
        })
    except Exception as _me:
        logger.debug(f"评估结果记忆回写失败(忽略): {_me}")

    resp = AssessmentResponse(
        mastery=mastery, activity=activity, weak_focus=weak_focus_list,
        trend=trend, adjustment=adjustment, by_subject=by_subject,
        total_questions=total, overall_accuracy=overall_acc,
        llm_assessed=llm_assessed,
    )
    # 写入缓存（含 LRU 驱逐：超过上限时删除最旧的条目）
    if len(_assessment_cache) >= _MAX_ASSESSMENT_CACHE:
        oldest = min(_assessment_cache.keys(), key=lambda k: _assessment_cache[k].get("ts", 0))
        del _assessment_cache[oldest]
    _assessment_cache[cache_key] = {"ts": time.time(), "data": resp}
    return resp


# ── 增强版学习效果评估 + 路径调整闭环（赛题加分项⑤） ──


@router.post("/assessment/feedback")
async def assessment_feedback(
    quiz_history: list[dict],
    study_sessions: list[dict] = None,
    profile: dict = None,
    user: dict = Depends(require_llm_quota),
):
    """增强版学习效果评估：多维度评估 + 路径调整建议

    赛题加分项⑤：学习效果评估闭环
    评估结果自动回写画像，支持动态调整学习策略。
    """
    if study_sessions is None:
        study_sessions = []
    if profile is None:
        profile = {}
    from agents.feedback_agent import evaluate_learning, adjust_learning_path

    # 1. 多维度评估
    eval_report = await evaluate_learning(
        profile=profile,
        quiz_history=quiz_history,
        study_sessions=study_sessions,
    )

    # 2. 获取当前学习路径（简化版：从画像中获取）
    current_path = []
    if profile.get("learning_path"):
        current_path = profile["learning_path"]
    elif profile.get("progress"):
        current_path = [{"name": "current", "status": "in_progress", "progress": profile["progress"]}]

    # 3. 路径调整建议
    path_adjustment = await adjust_learning_path(
        current_path=current_path,
        eval_report=eval_report,
        profile=profile,
    )

    # 4. 回写画像
    try:
        existing = get_profile(user["user_id"]) or {}
        weak = [w["topic"] for w in eval_report.get("weak_points", [])]
        if weak:
            existing["weak_points"] = ",".join(weak)
        existing["recent_assessment"] = {
            "overall": eval_report.get("overall", {}),
            "weak_points": weak,
            "adjustment": path_adjustment.get("message", ""),
            "path_adjusted": path_adjustment.get("adjusted", False),
        }
        save_profile(user["user_id"], existing)
    except Exception as e:
        logger.warning(f"评估结果回写失败（非阻塞）: {e}")

    return {
        "status": "ok",
        "evaluation": eval_report,
        "path_adjustment": path_adjustment,
    }


# ── 画像驱动推荐 API ──


@router.post("/assessment/recommendations")
async def get_assessment_recommendations(
    body: dict = {},
    user: dict = Depends(require_llm_quota),
):
    """基于画像生成个性化学习推荐（兼容 /api/assessment/recommendations 路径）"""
    profile = body.get("profile", {})
    quiz_history = body.get("quiz_history", [])
    from db.llm_provider import LLMProvider
    from prompts import ASSESSMENT_PROMPT

    weak_topics = []
    for r in quiz_history:
        if not r.get("correct", True):
            topic = r.get("subject", "unknown")
            if topic not in weak_topics:
                weak_topics.append(topic)

    recs = []
    for topic in weak_topics[:5]:
        recs.append({
            "icon": "📝",
            "title": f"加强 {topic}",
            "text": f"最近在 {topic} 上出现错误，建议针对性练习",
            "action": "开始练习",
            "route": f"/practice?subject={topic}",
            "priority": "high",
        })

    if not recs:
        recs.append({
            "icon": "🎯",
            "title": "开始新的学习",
            "text": "还没有答题记录，试试做几道练习题吧",
            "action": "去练习",
            "route": "/practice",
            "priority": "normal",
        })

    return {"status": "ok", "recommendations": recs, "total": len(recs)}


@router.post("/recommendations")
async def get_recommendations(
    profile: dict = {},
    quiz_history: list[dict] = [],
    user: dict = Depends(require_llm_quota),
):
    """基于画像生成个性化学习推荐

    画像驱动推荐：
    - 根据知识基础推荐学习路径
    - 根据薄弱点推荐专项练习
    - 根据学习风格推荐资源类型
    - 根据进度推荐下一步行动
    """
    recs = []

    # 1. 知识基础推荐
    kb = profile.get("knowledge_base", "beginner")
    if kb in ("none", "beginner"):
        recs.append({
            "icon": "📚", "priority": "high",
            "title": "基础入门",
            "text": "你的知识基础较薄弱，建议从核心概念开始系统学习",
            "action": "开始学习", "route": "/knowledge",
        })
    elif kb == "intermediate":
        recs.append({
            "icon": "📈", "priority": "medium",
            "title": "进阶提升",
            "text": "已有一定基础，建议通过做题巩固知识薄弱点",
            "action": "去练习", "route": "/practice",
        })
    elif kb == "advanced":
        recs.append({
            "icon": "🎯", "priority": "medium",
            "title": "冲刺拔高",
            "text": "基础扎实，建议挑战高难度题目和综合应用题",
            "action": "挑战难题", "route": "/practice?difficulty=hard",
        })

    # 2. 薄弱点推荐
    weak_points = profile.get("weak_points", "")
    if weak_points:
        weaks = [w.strip() for w in weak_points.replace("，", ",").split(",") if w.strip()]
        for w in weaks[:2]:
            recs.append({
                "icon": "🎯", "priority": "high",
                "title": f"攻克「{w}」",
                "text": f"薄弱点需要重点突破，建议生成专项练习",
                "action": "生成练习", "route": f"/practice?focus={w}",
            })

    # 3. 学习风格推荐
    style = profile.get("learning_style", "reading")
    style_recs = {
        "visual": {"icon": "👁️", "text": "视觉型学习者，推荐使用思维导图和视频脚本学习"},
        "auditory": {"icon": "👂", "text": "听觉型学习者，推荐使用TTS朗读和语音讲解"},
        "hands-on": {"icon": "🛠️", "text": "实操型学习者，推荐多做代码实操和练习题"},
        "reading": {"icon": "📖", "text": "阅读型学习者，推荐详细讲解文档和拓展阅读"},
    }
    if style in style_recs:
        s = style_recs[style]
        recs.append({
            "icon": s["icon"], "priority": "low",
            "title": "学习风格适配",
            "text": s["text"],
            "action": "查看资源", "route": "/resource",
        })

    # 4. 进度推荐
    progress = profile.get("progress", 0)
    if progress < 3:
        recs.append({
            "icon": "🗺️", "priority": "high",
            "title": "学习规划",
            "text": "学习进度较慢，建议制定每日学习计划",
            "action": "规划路径", "route": "/learning-path",
        })
    elif progress > 8:
        recs.append({
            "icon": "🏆", "priority": "low",
            "title": "接近目标",
            "text": "学习进度良好，保持节奏，冲刺高分",
            "action": "查看进度", "route": "/dashboard",
        })

    # 5. AI Skills 推荐
    recs.append({
        "icon": "🤖", "priority": "low",
        "title": "AI 技能推荐",
        "text": "试试 AI 技能市场，发现更多个性化学习工具",
        "action": "浏览技能", "route": "/skills",
    })

    return {
        "status": "ok",
        "recommendations": recs,
        "total": len(recs),
    }


# ── 画像快照历史（学习前后对比） ──


@router.post("/profile/snapshot")
async def save_profile_snapshot_api(
    profile: dict = {},
    user: dict = Depends(get_current_user),
):
    """保存当前画像快照（用于历史对比）

    每次调用保存当前画像的完整数据到快照表。
    可在学习前后各调用一次，通过对比快照查看学习效果。

    Args:
        profile: 当前画像数据（8 维）

    Returns:
        {"status": "ok", "snapshot_id": int}
    """
    from db.user_store import save_profile_snapshot
    snapshot_id = save_profile_snapshot(user["user_id"], profile)
    return {"status": "ok", "snapshot_id": snapshot_id}


@router.get("/profile/snapshots")
async def get_profile_snapshots_api(
    limit: int = 10,
    user: dict = Depends(get_current_user),
):
    """获取画像快照历史（按时间倒序）

    返回最近 N 次画像快照，包含创建时间和完整画像数据。
    前端可展示两张快照的对比雷达图，直观显示学习进步。

    Args:
        limit: 返回条数（默认 10，最大 50）

    Returns:
        {"status": "ok", "snapshots": [{id, snapshot, created_at}]}
    """
    from db.user_store import get_profile_snapshots
    limit = min(limit, 50)
    snapshots = get_profile_snapshots(user["user_id"], limit=limit)
    return {"status": "ok", "snapshots": snapshots}
