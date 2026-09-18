# ============================================================
# 成就系统 API — 学习成就追踪与展示
# 前端 Store (achievementStore.ts) 是运行时真相源，后端负责持久化
# ============================================================

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from shared.auth import get_current_user
from db.user_store import get_quiz_history, get_profile

logger = logging.getLogger("netlearn.achievement")
router = APIRouter(prefix="/achievement", tags=["achievement"])

# 与前端 achievementStore.ts 保持一致的成就定义
ACHIEVEMENTS = [
    {"id": "first_login", "name": "初次见面", "description": "首次登录 NetLearn 系统", "icon": "👋", "category": "milestone", "color": "#7c6af2"},
    {"id": "profile_built", "name": "画像大师", "description": "完成学生画像构建", "icon": "🧠", "category": "milestone", "color": "#8b5cf6"},
    {"id": "first_chat", "name": "初次对话", "description": "完成第一次 AI 对话", "icon": "💬", "category": "milestone", "color": "#3b82f6"},
    {"id": "first_resource", "name": "资源猎人", "description": "生成第一份学习资源", "icon": "📄", "category": "milestone", "color": "#06b6d4"},
    {"id": "first_path", "name": "路线规划", "description": "查看个性化学习路径", "icon": "🗺️", "category": "milestone", "color": "#22c55e"},
    {"id": "quiz_10", "name": "初出茅庐", "description": "完成 10 道练习题", "icon": "📝", "category": "practice", "color": "#f59e0b"},
    {"id": "quiz_50", "name": "题海战士", "description": "完成 50 道练习题", "icon": "⚔️", "category": "practice", "color": "#f97316"},
    {"id": "quiz_100", "name": "刷题狂人", "description": "完成 100 道练习题", "icon": "🏆", "category": "practice", "color": "#ef4444"},
    {"id": "quiz_300", "name": "题王之王", "description": "完成 300 道练习题", "icon": "👑", "category": "practice", "color": "#ec4899"},
    {"id": "accuracy_80", "name": "精准射手", "description": "答题正确率达到 80%", "icon": "🎯", "category": "practice", "color": "#22c55e"},
    {"id": "accuracy_90", "name": "学霸模式", "description": "答题正确率达到 90%", "icon": "🌟", "category": "practice", "color": "#14b8a6"},
    {"id": "perfect_10", "name": "十全十美", "description": "连续答对 10 题", "icon": "💎", "category": "practice", "color": "#8b5cf6"},
    {"id": "knowledge_10", "name": "知识学徒", "description": "浏览 10 个知识点", "icon": "📚", "category": "knowledge", "color": "#3b82f6"},
    {"id": "knowledge_50", "name": "知识探索者", "description": "浏览 50 个知识点", "icon": "🔍", "category": "knowledge", "color": "#6366f1"},
    {"id": "knowledge_all", "name": "博学家", "description": "覆盖全部 4 门课程", "icon": "🎓", "category": "knowledge", "color": "#7c6af2"},
    {"id": "kg_built", "name": "图谱构建者", "description": "生成知识图谱", "icon": "🕸️", "category": "knowledge", "color": "#06b6d4"},
    {"id": "mindmap_view", "name": "思维导图", "description": "查看思维导图", "icon": "🧩", "category": "knowledge", "color": "#f59e0b"},
    {"id": "streak_3", "name": "三天打鱼", "description": "连续学习 3 天", "icon": "🔥", "category": "streak", "color": "#f97316"},
    {"id": "streak_7", "name": "一周坚持", "description": "连续学习 7 天", "icon": "📅", "category": "streak", "color": "#ef4444"},
    {"id": "streak_14", "name": "半月长征", "description": "连续学习 14 天", "icon": "🚀", "category": "streak", "color": "#ec4899"},
    {"id": "streak_30", "name": "月度冠军", "description": "连续学习 30 天", "icon": "🏅", "category": "streak", "color": "#14b8a6"},
    {"id": "streak_60", "name": "学习铁人", "description": "连续学习 60 天", "icon": "🦾", "category": "streak", "color": "#8b5cf6"},
    {"id": "collector_5", "name": "收藏家", "description": "解锁 5 个成就", "icon": "🏅", "category": "master", "color": "#f59e0b"},
    {"id": "collector_10", "name": "成就猎人", "description": "解锁 10 个成就", "icon": "🎖️", "category": "master", "color": "#f97316"},
    {"id": "collector_20", "name": "成就大师", "description": "解锁 20 个成就", "icon": "👑", "category": "master", "color": "#ec4899"},
    {"id": "four_in_one", "name": "全科通关", "description": "四门课程都有练习记录", "icon": "🌈", "category": "master", "color": "#7c6af2"},
    {"id": "speed_learner", "name": "速学者", "description": "单日完成 20+ 题", "icon": "⚡", "category": "master", "color": "#06b6d4"},
]


class RecordRequest(BaseModel):
    event: str  # 事件类型: quiz, streak, profile_built, first_chat, first_resource, first_path, knowledge_browse, kg_built, mindmap_view, knowledge_all
    subject: str = ""
    correct: bool = False


@router.get("/list")
async def get_achievements(user: dict = Depends(get_current_user)):
    """获取成就列表及用户解锁状态"""
    user_id = user.get("user_id")
    profile = get_profile(user_id) or {}
    quiz_history = get_quiz_history(user_id) or []

    total_quiz = len(quiz_history)
    correct_count = sum(1 for q in quiz_history if q.get("correct"))
    subjects = set(q.get("subject") for q in quiz_history if q.get("subject"))
    expected = {"computer_network", "data_structures", "computer_organization", "operating_system"}

    # 从 profile 读取持久化成就状态
    saved_achievements = profile.get("achievements", {})
    saved_stats = profile.get("ach_stats", {})

    # 构建成就列表
    result = []
    for ach in ACHIEVEMENTS:
        ach_id = ach["id"]
        # 已持久化解锁的成就
        if saved_achievements.get(ach_id, {}).get("unlocked"):
            result.append({
                "id": ach_id,
                "name": ach["name"],
                "description": ach["description"],
                "icon": ach["icon"],
                "category": ach["category"],
                "color": ach["color"],
                "unlocked": True,
                "unlockedAt": saved_achievements[ach_id].get("unlockedAt"),
                "progress": 100,
                "progressLabel": "已解锁",
            })
            continue

        # 计算进度
        progress = 0
        progress_label = "0%"

        if ach_id == "first_login":
            progress = 100
        elif ach_id == "profile_built":
            progress = 100 if profile.get("knowledge_base") else 0
        elif ach_id == "first_chat":
            progress = 100 if saved_stats.get("firstChat") else 0
        elif ach_id == "first_resource":
            progress = 100 if saved_stats.get("firstResource") else 0
        elif ach_id == "first_path":
            progress = 100 if saved_stats.get("firstPath") else 0
        elif ach_id == "quiz_10":
            progress = min(100, total_quiz / 10 * 100)
            progress_label = f"{total_quiz}/10 题"
        elif ach_id == "quiz_50":
            progress = min(100, total_quiz / 50 * 100)
            progress_label = f"{total_quiz}/50 题"
        elif ach_id == "quiz_100":
            progress = min(100, total_quiz / 100 * 100)
            progress_label = f"{total_quiz}/100 题"
        elif ach_id == "quiz_300":
            progress = min(100, total_quiz / 300 * 100)
            progress_label = f"{total_quiz}/300 题"
        elif ach_id == "accuracy_80":
            if total_quiz >= 10:
                acc = correct_count / max(total_quiz, 1)
                progress = min(100, acc / 0.8 * 100)
                progress_label = f"{acc*100:.0f}%"
        elif ach_id == "accuracy_90":
            if total_quiz >= 10:
                acc = correct_count / max(total_quiz, 1)
                progress = min(100, acc / 0.9 * 100)
                progress_label = f"{acc*100:.0f}%"
        elif ach_id == "perfect_10":
            progress = 100 if saved_stats.get("maxConsecutiveCorrect", 0) >= 10 else 0
        elif ach_id == "knowledge_10":
            kb = saved_stats.get("knowledgeBrowsed", 0)
            progress = min(100, kb / 10 * 100)
            progress_label = f"{kb}/10"
        elif ach_id == "knowledge_50":
            kb = saved_stats.get("knowledgeBrowsed", 0)
            progress = min(100, kb / 50 * 100)
            progress_label = f"{kb}/50"
        elif ach_id == "knowledge_all":
            progress = 100 if len(subjects & expected) >= 4 else 0
        elif ach_id == "kg_built":
            progress = 100 if saved_stats.get("kgBuilt") else 0
        elif ach_id == "mindmap_view":
            progress = 100 if saved_stats.get("mindmapView") else 0
        elif ach_id in ("streak_3", "streak_7", "streak_14", "streak_30", "streak_60"):
            streak = saved_stats.get("currentStreak", 0)
            target = {"streak_3": 3, "streak_7": 7, "streak_14": 14, "streak_30": 30, "streak_60": 60}[ach_id]
            progress = min(100, streak / target * 100)
            progress_label = f"{streak}/{target} 天"
        elif ach_id == "speed_learner":
            progress = 100 if saved_stats.get("todayQuestions", 0) >= 20 else 0
        elif ach_id == "four_in_one":
            progress = 100 if len(subjects & expected) >= 4 else 0

        if progress >= 100:
            progress = 100
            progress_label = "已解锁"

        result.append({
            "id": ach_id,
            "name": ach["name"],
            "description": ach["description"],
            "icon": ach["icon"],
            "category": ach["category"],
            "color": ach["color"],
            "unlocked": progress >= 100,
            "progress": round(progress, 1),
            "progressLabel": progress_label,
        })

    unlocked_count = sum(1 for a in result if a["unlocked"])

    # 补算 collector 成就（依赖总解锁数）
    for a in result:
        if a["id"] == "collector_5":
            a["progress"] = min(100, unlocked_count / 5 * 100)
            a["progressLabel"] = f"{unlocked_count}/5"
            a["unlocked"] = unlocked_count >= 5
        elif a["id"] == "collector_10":
            a["progress"] = min(100, unlocked_count / 10 * 100)
            a["progressLabel"] = f"{unlocked_count}/10"
            a["unlocked"] = unlocked_count >= 10
        elif a["id"] == "collector_20":
            a["progress"] = min(100, unlocked_count / 20 * 100)
            a["progressLabel"] = f"{unlocked_count}/20"
            a["unlocked"] = unlocked_count >= 20

    # 重新计算解锁数
    unlocked_count = sum(1 for a in result if a["unlocked"])

    return {
        "total": len(ACHIEVEMENTS),
        "unlocked_count": unlocked_count,
        "achievements": result,
        "stats": {
            "totalQuestions": total_quiz,
            "totalCorrect": correct_count,
            **saved_stats,
        },
    }


@router.post("/record")
async def record_event(req: RecordRequest, user: dict = Depends(get_current_user)):
    """记录成就事件，返回当前解锁状态"""
    user_id = user.get("user_id")
    profile = get_profile(user_id) or {}
    saved_stats = profile.get("ach_stats", {})
    saved_achievements = profile.get("achievements", {})

    # 更新统计
    event = req.event
    if event == "quiz":
        saved_stats["totalQuestions"] = saved_stats.get("totalQuestions", 0) + 1
        saved_stats["todayQuestions"] = saved_stats.get("todayQuestions", 0) + 1
        if req.correct:
            saved_stats["totalCorrect"] = saved_stats.get("totalCorrect", 0) + 1
            saved_stats["consecutiveCorrect"] = saved_stats.get("consecutiveCorrect", 0) + 1
            saved_stats["maxConsecutiveCorrect"] = max(
                saved_stats.get("maxConsecutiveCorrect", 0),
                saved_stats["consecutiveCorrect"],
            )
        else:
            saved_stats["consecutiveCorrect"] = 0
        if req.subject:
            sc = set(saved_stats.get("subjectsCovered", []))
            sc.add(req.subject)
            saved_stats["subjectsCovered"] = list(sc)
    elif event == "streak":
        saved_stats["currentStreak"] = saved_stats.get("currentStreak", 0) + 1
        saved_stats["maxStreak"] = max(saved_stats.get("maxStreak", 0), saved_stats["currentStreak"])
        saved_stats["todayQuestions"] = 0
    elif event == "profile_built":
        saved_stats["profileBuilt"] = True
    elif event == "first_chat":
        saved_stats["firstChat"] = True
    elif event == "first_resource":
        saved_stats["firstResource"] = True
    elif event == "first_path":
        saved_stats["firstPath"] = True
    elif event == "knowledge_browse":
        saved_stats["knowledgeBrowsed"] = saved_stats.get("knowledgeBrowsed", 0) + 1
    elif event == "kg_built":
        saved_stats["kgBuilt"] = True
    elif event == "mindmap_view":
        saved_stats["mindmapView"] = True

    # L1/L2/L3 三层学情记忆联动（低侵入：成就事件入 L3 情景记忆，供成长轨迹追溯）
    try:
        from db import memory_store as _ms
        _ms.append_episode(user_id, "achievement", {
            "event": event,
            "correct": bool(req.correct),
            "subject": req.subject or "",
        })
    except Exception as _me:
        logger.debug(f"成就事件记忆写入失败(忽略): {_me}")

    # 保存
    profile["ach_stats"] = saved_stats
    profile["achievements"] = saved_achievements
    from db.user_store import save_profile
    save_profile(user_id, profile)

    return {"status": "ok"}