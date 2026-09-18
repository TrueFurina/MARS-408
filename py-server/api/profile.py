# ============================================================
# API — 学习画像（/api/profile/*）
# 已迁移：deps → db.llm_provider + config
# ============================================================

import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db.llm_provider import LLMProvider, LLMUnavailable
from models import ProfileBuildRequest, ProfileBuildResponse, BehaviorReportRequest, BehaviorReportResponse
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota

logger = logging.getLogger("netlearn.profile")
router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/build", response_model=ProfileBuildResponse)
async def profile_build(req: ProfileBuildRequest, user: dict = Depends(require_llm_quota)):
    """画像构建对话接口。每次用户回复后，LLM 分析是否已收集到足够信息（双通道）。"""
    # 首次问候语不需要 LLM，先行返回（避免无 LLM 时连问候语都不可用）
    if not req.history:
        return ProfileBuildResponse(
            reply="你好！我是你的学习助手，想先了解一下你的情况，这样我可以给你推荐最合适的学习内容。你之前学过计算机网络吗？",
            profile=None,
            completed=False,
        )

    llm = LLMProvider()
    try:
        provider = llm._resolve()
    except LLMUnavailable:
        raise HTTPException(status_code=503, detail="LLM API 未配置")

    from prompts import PROFILE_PROMPT

    messages = [{"role": "system", "content": PROFILE_PROMPT}]

    for h in req.history:
        if "role" in h and "content" in h:
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": req.message})

    try:
        resp = await llm.chat(messages, temperature=0.7, max_tokens=1000)
        reply = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

        profile = None
        completed = False
        try:
            json_match = reply.split("{")[-1].split("}")[0] if "{" in reply and "}" in reply else None
            if json_match:
                profile = json.loads("{" + json_match + "}")
                # PROFILE_PROMPT 定义8个维度，赛题要求≥6
                _REQUIRED_DIMS = [
                    "knowledge_base", "learning_style", "goal",
                    "weak_points", "progress", "interest_area",
                    "study_time", "preferred_difficulty",
                ]
                filled = sum(1 for d in _REQUIRED_DIMS if profile.get(d) not in (None, "", 0, "0"))
                completed = filled >= 6
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        return ProfileBuildResponse(reply=reply, profile=profile, completed=completed)

    except Exception as e:
        logger.warning(f"画像构建异常: {e}")
        raise HTTPException(status_code=504, detail="LLM 响应超时，请稍后重试")


@router.post("/behavior", response_model=BehaviorReportResponse)
async def report_behavior(req: BehaviorReportRequest, user: dict = Depends(get_current_user)):
    """前端上报行为事件，fire-and-forget 更新画像。

    接收 dwell/reattempt/resource_click 行为事件，调用 behavior_tracker
    轻量规则更新画像的 behavior_signals 子字段（不影响 8 维 completed 判定）。
    """
    from agents.behavior_tracker import BehaviorEvent, update_profile_from_behavior

    user_id = user.get("user_id", "")
    events = [
        BehaviorEvent(
            user_id=user_id,
            event_type=ev.event_type,
            topic=ev.topic,
            duration_ms=ev.duration_ms,
            resource_type=ev.resource_type,
        )
        for ev in req.events
    ]

    try:
        updated = await update_profile_from_behavior(user_id, events)
        return BehaviorReportResponse(
            accepted=len(events),
            updated=bool(updated),
        )
    except Exception as e:
        logger.warning(f"行为上报处理失败: {e}")
        return BehaviorReportResponse(accepted=len(events), updated=False)


class ProfileUpdateRequest(BaseModel):
    target_score: int = 120
    target_school: str = ""
    study_time: str = "2-4h"
    subject_count: int = 4


@router.post("/update")
async def profile_update(req: ProfileUpdateRequest, user: dict = Depends(get_current_user)):
    """更新学生画像目标设置"""
    from db.user_store import get_profile, save_profile
    user_id = user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="用户未认证")
    try:
        profile = get_profile(user_id) or {}
        profile["target_score"] = req.target_score
        profile["target_school"] = req.target_school
        profile["study_time"] = req.study_time
        profile["subject_count"] = req.subject_count
        profile["profile_updated"] = True
        save_profile(user_id, profile)

        # L1/L2/L3 三层学情记忆联动（低侵入：画像更新同步 L2 语义记忆）
        try:
            from db import memory_store as _ms
            _ms.save_semantic_memory(user_id, profile={
                "target_score": req.target_score,
                "target_school": req.target_school,
                "study_time": req.study_time,
                "subject_count": req.subject_count,
            })
        except Exception as _me:
            logger.debug(f"画像记忆联动失败(忽略): {_me}")

        logger.info(f"画像更新成功: user={user_id}")
        return {"status": "ok", "profile": profile}
    except Exception as e:
        logger.warning(f"画像更新失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


@router.get("/ability")
async def get_ability_profile(user: dict = Depends(get_current_user)):
    """统一能力画像（双场景集成 · F4 + M1）—— 一个账号、一份画像。

    读路径（M1 聚合表优先，未命中实时聚合后回写）：
      1. db.ability_store.get_profile —— ability_profiles 聚合表命中即返回
      2. 未命中 → 实时聚合两源（下述）并回写聚合表，供下次命中
    两源：professional-场景A 考研408（db.memory_store）/ soft_skills-场景B 职业素养（db.career_store）。
    任一源失败一律 **fail-open**，绝不 500；前端 useAbilityProfile 另有本地缓存回退。
    """
    user_id = user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="用户未认证")

    # 1) 优先读 M1 聚合表
    try:
        from db import ability_store
        cached = ability_store.get_profile(user_id)
        if cached:
            cached.setdefault("user_id", user_id)
            cached["source"] = "table"
            return cached
    except Exception as e:
        logger.debug("ability: 聚合表读取失败（转实时聚合）: %s", e)

    # 2) 实时聚合两源
    professional: dict = {}
    soft_skills: dict = {}
    kaoyan_score = None
    career_score = None
    updated_at = None

    # 场景A：考研408 语义记忆（画像 + 掌握度）
    try:
        from db import memory_store
        sem = memory_store.get_semantic_memory(user_id) or {}
        professional = sem.get("profile") or {}
        mastery = sem.get("mastery") or {}
        if mastery:
            kaoyan_score = {"mastery": mastery, "weak_points": sem.get("weak_points") or []}
        updated_at = sem.get("updated_at")
    except Exception as e:
        logger.debug("ability: 场景A 画像读取失败（fail-open 忽略）: %s", e)

    # 场景B：职业素养实训最近一次评估
    try:
        from db import career_store
        sessions = career_store.list_my_sessions(user_id, limit=1) or []
        if sessions:
            sid = sessions[0].get("id")
            if sid:
                assessment = career_store.get_assessment_by_session(sid)
                if assessment:
                    soft_skills = assessment.get("dimensions") or assessment
                    career_score = assessment
    except Exception as e:
        logger.debug("ability: 场景B 评估读取失败（fail-open 忽略）: %s", e)

    result = {
        "user_id": user_id,
        "professional": professional,
        "soft_skills": soft_skills,
        "kaoyan_score": kaoyan_score,
        "career_score": career_score,
        "updated_at": updated_at,
        "source": "live",
    }

    # 3) 回写 M1 聚合表（供下次命中；失败不影响返回）
    try:
        from db import ability_store
        ability_store.upsert_profile(
            user_id,
            professional=professional,
            soft_skills=soft_skills,
            kaoyan_score=kaoyan_score,
            career_score=career_score,
        )
    except Exception as e:
        logger.debug("ability: 聚合表回写失败（忽略）: %s", e)

    return result
