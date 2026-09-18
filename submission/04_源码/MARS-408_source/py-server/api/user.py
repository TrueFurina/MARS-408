# ============================================================
# API — 每用户数据（/api/user/*）— 需登录
# 画像 / 答题历史 / 对话 的持久化与读取（按 user_id 隔离）
# ============================================================

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from shared.auth import get_current_user
from db.user_store import (
    save_profile, get_profile,
    append_quiz_history, get_quiz_history,
    save_conversations, get_conversations,
)

logger = logging.getLogger("netlearn.user_api")
router = APIRouter(prefix="/user", tags=["user"])


class ProfilePayload(BaseModel):
    profile: dict


class QuizHistoryPayload(BaseModel):
    records: list[dict] = []


class ConversationsPayload(BaseModel):
    conversations: list[dict] = []


@router.get("/profile")
async def get_user_profile(user: dict = Depends(get_current_user)):
    return {"profile": get_profile(user["user_id"]) or {}}


@router.put("/profile")
async def put_user_profile(req: ProfilePayload, user: dict = Depends(get_current_user)):
    save_profile(user["user_id"], req.profile)
    return {"status": "ok"}


@router.get("/quiz-history")
async def get_user_quiz_history(user: dict = Depends(get_current_user)):
    return {"history": get_quiz_history(user["user_id"])}


@router.post("/quiz-history")
async def post_user_quiz_history(req: QuizHistoryPayload, user: dict = Depends(get_current_user)):
    if req.records:
        append_quiz_history(user["user_id"], req.records)
    return {"status": "ok", "count": len(req.records)}


@router.get("/conversations")
async def get_user_conversations(user: dict = Depends(get_current_user)):
    return {"conversations": get_conversations(user["user_id"])}


@router.post("/conversations")
async def post_user_conversations(req: ConversationsPayload, user: dict = Depends(get_current_user)):
    if req.conversations:
        save_conversations(user["user_id"], req.conversations)
    return {"status": "ok", "count": len(req.conversations)}


# ── PUT 别名：前端 studyStore 使用 PUT /user/conversations ──
@router.put("/conversations")
async def put_user_conversations(req: ConversationsPayload, user: dict = Depends(get_current_user)):
    if req.conversations:
        save_conversations(user["user_id"], req.conversations)
    return {"status": "ok", "count": len(req.conversations)}


# ── Dashboard 端点（前端 studyStore.fetchStats / fetchRecentSessions / fetchRecommendedTasks / fetchMasteryData 调用） ──

@router.get("/stats")
async def get_user_stats(user: dict = Depends(get_current_user)):
    """Dashboard 统计：学习时长、答题数、掌握度、连续学习天数"""
    history = get_quiz_history(user["user_id"]) or []
    profile = get_profile(user["user_id"]) or {}

    total_questions = len(history)
    correct = sum(1 for r in history if r.get("correct"))
    mastery = round(correct / max(total_questions, 1) * 100)

    # 连续学习天数（基于答题历史日期）
    import datetime
    dates = set()
    for r in history:
        ts = r.get("timestamp") or r.get("date")
        if ts:
            try:
                d = datetime.datetime.fromisoformat(str(ts)).date()
                dates.add(d)
            except Exception:
                logger.debug("streak calc: invalid timestamp %s", ts)
    today = datetime.date.today()
    streak = 0
    for i in range(30):
        d = today - datetime.timedelta(days=i)
        if d in dates:
            streak += 1
        else:
            break

    study_time = profile.get("total_study_minutes", total_questions * 3)

    return {
        "studyTime": study_time,
        "questionsDone": total_questions,
        "mastery": mastery,
        "streak": streak,
    }


@router.get("/recent-sessions")
async def get_user_recent_sessions(user: dict = Depends(get_current_user)):
    """Dashboard 最近学习记录"""
    history = get_quiz_history(user["user_id"]) or []
    conversations = get_conversations(user["user_id"]) or []

    sessions = []
    # 从答题历史提取
    for i, r in enumerate(history[-5:]):
        sessions.append({
            "id": f"quiz_{i}",
            "subject": r.get("subject", "综合"),
            "title": f"{r.get('subject', '综合')}练习",
            "duration": f"{r.get('total', 0) * 2}分钟",
            "date": r.get("timestamp", r.get("date", "")),
            "score": round(r.get("accuracy", 0) * 100) if r.get("accuracy") else 0,
        })
    # 从对话历史补充
    for i, c in enumerate(conversations[-3:]):
        sessions.append({
            "id": f"conv_{i}",
            "subject": "AI对话",
            "title": c.get("title", f"对话 {i+1}"),
            "duration": "10分钟",
            "date": c.get("updated", ""),
            "score": 0,
        })

    return sessions[:8]


@router.get("/recommended-tasks")
async def get_user_recommended_tasks(user: dict = Depends(get_current_user)):
    """Dashboard 推荐任务（基于画像薄弱点 + L2 记忆薄弱点）"""
    profile = get_profile(user["user_id"]) or {}
    weak_points = profile.get("weak_points", "")

    # L1/L2/L3 三层学情记忆聚合（低侵入：L2 记忆薄弱点并入推荐）
    memory_weak = []
    try:
        from db.memory_store import get_semantic_memory
        mem = get_semantic_memory(user["user_id"])
        memory_weak = [w for w in mem.get("weak_points", []) if w and w not in ("无", "无薄弱点")]
    except Exception as _me:
        logger.debug(f"推荐任务记忆聚合失败(降级): {_me}")

    tasks = []
    # 画像薄弱点 + 记忆薄弱点（去重）
    all_weak = []
    seen: set[str] = set()
    for wp in list(weak_points.split(",")) + memory_weak:
        wp = wp.strip()
        if wp and wp not in seen and wp not in ("无", "无薄弱点"):
            all_weak.append(wp)
            seen.add(wp)

    if all_weak:
        for wp in all_weak[:3]:
            tasks.append({
                "id": f"task_{wp}",
                "icon": "warning",
                "title": f"复习{wp}",
                "desc": f"针对薄弱点「{wp}」进行专项练习（画像+学情记忆）",
                "time": "20分钟",
                "color": "#f59e0b",
            })

    # 默认推荐任务
    default_tasks = [
        {"id": "task_ds", "icon": "code", "title": "数据结构练习", "desc": "链表与树的基础题目", "time": "30分钟", "color": "#3b82f6"},
        {"id": "task_cn", "icon": "network", "title": "计算机网络复习", "desc": "TCP/IP协议栈核心概念", "time": "25分钟", "color": "#10b981"},
        {"id": "task_os", "icon": "server", "title": "操作系统概念", "desc": "进程调度与内存管理", "time": "20分钟", "color": "#8b5cf6"},
    ]

    if not tasks:
        tasks = default_tasks

    return tasks[:5]


@router.get("/mastery")
async def get_user_mastery(user: dict = Depends(get_current_user)):
    """Dashboard 掌握度数据（按科目）"""
    history = get_quiz_history(user["user_id"]) or []

    subject_map = {
        "数据结构": "数据结构",
        "计算机网络": "计算机网络",
        "计算机组成原理": "计组",
        "操作系统": "操作系统",
    }

    by_subject = {}
    for r in history:
        subj = r.get("subject", "unknown")
        label = subject_map.get(subj, subj)
        if label not in by_subject:
            by_subject[label] = {"total": 0, "correct": 0}
        by_subject[label]["total"] += 1
        if r.get("correct"):
            by_subject[label]["correct"] += 1

    items = []
    for label, counts in by_subject.items():
        pct = round(counts["correct"] / max(counts["total"], 1) * 100)
        items.append({"subject": label, "label": label, "pct": pct})

    # 如果没有答题历史，返回默认数据
    if not items:
        for subj, label in subject_map.items():
            items.append({"subject": label, "label": label, "pct": 0})

    return items
