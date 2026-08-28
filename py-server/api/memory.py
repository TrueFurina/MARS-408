# ============================================================
# API — 三层学情记忆（/api/memory/*）
#
# L1 工作记忆：当前会话上下文（TTL 过期）
# L2 语义记忆：学生画像 + 知识点掌握度矩阵
# L3 情景记忆：历史事件流（答题/行为/资源交互）
#
# 设计：低侵入新增路由，不改动 GOMARL/FrugalRAG/辩论/规则引擎核心。
# ============================================================

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from shared.auth import get_current_user
from services import memory_service as mem_svc
from db import memory_store as ms
from db.local_cache import LocalLRUCache

logger = logging.getLogger("netlearn.memory")
router = APIRouter(prefix="/memory", tags=["memory"])

# 记忆接口本地缓存（P1-2）：读接口命中缓存避免重复查询 SQLite；
# 写接口主动失效对应缓存。仅缓存确定性读结果，缓存失败不阻塞主流程。
_mem_cache = LocalLRUCache(max_size=512, ttl=30.0)
_MEM_CACHE_PREFIX = "mem:"


def _cache_get(key: str) -> Optional[dict]:
    try:
        return _mem_cache.get(_MEM_CACHE_PREFIX + key)
    except Exception:
        return None


def _cache_set(key: str, value: dict) -> None:
    try:
        _mem_cache.set(_MEM_CACHE_PREFIX + key, value)
    except Exception:
        pass


def _cache_invalidate(uid: str) -> None:
    """写接口后失效该用户全部记忆缓存（prefix 匹配删除）"""
    try:
        # 本地 LRU 无按前缀删除接口，用全清兜底（容量小、命中率损失可控）
        _mem_cache.clear()
    except Exception:
        pass


def _uid(user: dict) -> str:
    uid = user.get("user_id") or user.get("id") or user.get("username", "")
    if not uid:
        raise HTTPException(status_code=401, detail="用户未认证")
    return uid


# ── 请求模型 ──

class WorkingMemoryRequest(BaseModel):
    session_id: str = Field(..., max_length=128, description="会话 ID")
    context: dict = Field(default_factory=dict, description="工作记忆上下文")
    ttl_seconds: int = Field(1800, ge=60, le=86400, description="TTL（秒）")


class WorkingTopicRequest(BaseModel):
    session_id: str = Field(..., max_length=128)
    topic: str = Field(..., max_length=200, description="当前学习主题")
    focus: Optional[str] = Field(None, max_length=200, description="当前聚焦点")


class SemanticMemoryRequest(BaseModel):
    profile: Optional[dict] = Field(None, description="画像更新（合并）")
    mastery: Optional[dict] = Field(None, description="掌握度矩阵更新（合并）")
    weak_points: Optional[list[str]] = Field(None, max_length=100)
    mastered_points: Optional[list[str]] = Field(None, max_length=100)


class EpisodeRequest(BaseModel):
    event_type: str = Field(..., max_length=50)
    event: dict = Field(default_factory=dict)


class QuizResultRequest(BaseModel):
    topic: str = Field(..., max_length=200)
    correct: bool
    difficulty: str = Field("medium", max_length=20)
    mastery_delta: float = Field(0.05, ge=0.0, le=0.2)


class EpisodesQuery(BaseModel):
    event_type: Optional[str] = Field(None, max_length=50)
    limit: int = Field(50, ge=1, le=200)


# ── L1 工作记忆 ──

@router.get("/l1/{session_id}")
async def get_l1(session_id: str, user: dict = Depends(get_current_user)):
    """读取工作记忆（已过期自动清理）"""
    uid = _uid(user)
    cached = _cache_get(f"l1:{uid}:{session_id}")
    if cached is not None:
        return cached
    ctx = ms.get_working_memory(uid, session_id)
    resp = {"status": "ok", "session_id": session_id, "context": ctx or {}}
    _cache_set(f"l1:{uid}:{session_id}", resp)
    return resp


@router.post("/l1")
async def save_l1(req: WorkingMemoryRequest, user: dict = Depends(get_current_user)):
    """写入工作记忆（覆盖同会话）"""
    ms.save_working_memory(_uid(user), req.session_id, req.context, req.ttl_seconds)
    _cache_invalidate(_uid(user))
    return {"status": "ok"}


@router.post("/l1/merge")
async def merge_l1(req: WorkingMemoryRequest, user: dict = Depends(get_current_user)):
    """增量合并工作记忆，返回合并后完整上下文"""
    merged = ms.merge_working_memory(_uid(user), req.session_id, req.context, req.ttl_seconds)
    _cache_invalidate(_uid(user))
    return {"status": "ok", "context": merged}


@router.post("/l1/topic")
async def set_l1_topic(req: WorkingTopicRequest, user: dict = Depends(get_current_user)):
    """更新工作记忆当前主题（会话级上下文）"""
    ctx = mem_svc.update_working_topic(_uid(user), req.session_id, req.topic, req.focus)
    _cache_invalidate(_uid(user))
    return {"status": "ok", "context": ctx}


@router.delete("/l1/{session_id}")
async def delete_l1(session_id: str, user: dict = Depends(get_current_user)):
    """清空指定会话工作记忆"""
    ms.clear_working_memory(_uid(user), session_id)
    _cache_invalidate(_uid(user))
    return {"status": "ok"}


# ── L2 语义记忆 ──

@router.get("/l2")
async def get_l2(user: dict = Depends(get_current_user)):
    """读取完整语义记忆（画像+掌握度+薄弱/已掌握）"""
    uid = _uid(user)
    cached = _cache_get(f"l2:{uid}")
    if cached is not None:
        return cached
    mem = ms.get_semantic_memory(uid)
    resp = {"status": "ok", **mem}
    _cache_set(f"l2:{uid}", resp)
    return resp


@router.post("/l2")
async def save_l2(req: SemanticMemoryRequest, user: dict = Depends(get_current_user)):
    """合并更新语义记忆"""
    ms.save_semantic_memory(
        _uid(user),
        profile=req.profile,
        mastery=req.mastery,
        weak_points=req.weak_points,
        mastered_points=req.mastered_points,
    )
    _cache_invalidate(_uid(user))
    return {"status": "ok"}


# ── L3 情景记忆 ──

@router.get("/l3")
async def get_l3(limit: int = 50, event_type: Optional[str] = None,
                 user: dict = Depends(get_current_user)):
    """按时间倒序读取情景记忆"""
    uid = _uid(user)
    limit = min(limit, 200)
    cached = _cache_get(f"l3:{uid}:{event_type or 'all'}:{limit}")
    if cached is not None:
        return cached
    episodes = ms.get_episodes(uid, event_type=event_type, limit=limit)
    resp = {"status": "ok", "episodes": episodes, "total": len(episodes)}
    _cache_set(f"l3:{uid}:{event_type or 'all'}:{limit}", resp)
    return resp


@router.post("/l3")
async def append_l3(req: EpisodeRequest, user: dict = Depends(get_current_user)):
    """追加一条情景事件"""
    ms.append_episode(_uid(user), req.event_type, req.event)
    _cache_invalidate(_uid(user))
    return {"status": "ok"}


@router.post("/quiz-result")
async def record_quiz(req: QuizResultRequest, user: dict = Depends(get_current_user)):
    """答题结果记忆回写：L2 掌握度更新 + L3 情景记录"""
    mem_svc.record_quiz_result(
        _uid(user), req.topic, req.correct, req.difficulty, req.mastery_delta
    )
    _cache_invalidate(_uid(user))
    return {"status": "ok"}


# ── 聚合 ──

@router.get("/overview")
async def memory_overview(user: dict = Depends(get_current_user)):
    """记忆健康度总览（画像维度/掌握点数/情景条数/记忆层级）"""
    uid = _uid(user)
    cached = _cache_get(f"overview:{uid}")
    if cached is not None:
        return cached
    overview = mem_svc.get_memory_overview(uid)
    resp = {"status": "ok", **overview}
    _cache_set(f"overview:{uid}", resp)
    return resp


@router.get("/context")
async def memory_context(session_id: Optional[str] = None, max_episodes: int = 10,
                         user: dict = Depends(get_current_user)):
    """组装三层记忆为 LLM 上下文提示块（供智能体/前端调试使用）"""
    uid = _uid(user)
    cached = _cache_get(f"context:{uid}:{session_id or 'none'}:{max_episodes}")
    if cached is not None:
        return cached
    ctx = mem_svc.build_memory_context(uid, session_id, max_episodes)
    resp = {"status": "ok", "context": ctx}
    _cache_set(f"context:{uid}:{session_id or 'none'}:{max_episodes}", resp)
    return resp


# ── 记忆管理（清空/重置，供用户主动管理记忆生命周期） ──

@router.delete("/l2")
async def reset_l2(user: dict = Depends(get_current_user)):
    """清空 L2 长期语义记忆（画像/掌握度/薄弱点）"""
    from db import memory_store as _ms
    conn = _ms._get_conn()
    conn.execute("DELETE FROM memory_l2_semantic WHERE user_id=?", (_uid(user),))
    conn.commit()
    _cache_invalidate(_uid(user))
    logger.info("L2 语义记忆已清空 user=%s", _uid(user))
    return {"status": "ok", "cleared": "l2"}


@router.delete("/l3")
async def reset_l3(user: dict = Depends(get_current_user)):
    """清空 L3 情景记忆（答题/行为/资源事件流）"""
    from db import memory_store as _ms
    conn = _ms._get_conn()
    conn.execute("DELETE FROM memory_l3_episodic WHERE user_id=?", (_uid(user),))
    conn.commit()
    _cache_invalidate(_uid(user))
    logger.info("L3 情景记忆已清空 user=%s", _uid(user))
    return {"status": "ok", "cleared": "l3"}
