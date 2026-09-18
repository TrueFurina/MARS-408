# ============================================================
# 讯飞开放平台能力 API
# 暴露控制台已开通的全部讯飞服务：图片理解/聚合搜索/PPT生成/
# 数字人视频/文本纠错/公文校对/文本合规 + 能力状态全景
# 赛题合规：深度使用科大讯飞相关工具
# ============================================================

import logging
import time
import uuid
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List

from db.xfyun_services import (
    understand_image, web_search, generate_ppt, generate_video,
    proofread_text, proofread_document, check_compliance, get_all_status,
    roleplay_interview, generate_resume,
)
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from shared.prompt_guard import sanitize_user_input  # F-015：覆盖直连讯飞 LLM 入口（绕过统一边界）
from shared.content_safety import audit_output  # P1-7：讯飞直连端点输出内容安全审核

logger = logging.getLogger("netlearn.xfyun_api")
# F-011：讯飞能力端点统一鉴权 + 每用户 LLM 配额（429）
router = APIRouter(
    prefix="/xfyun", tags=["xfyun"],
    dependencies=[Depends(require_llm_quota)],
)

# ── 异步任务存储（PPT/视频后台生成，避免阻塞 worker 与反向代理超时）──
# 约束：仅单 worker 部署下有效；多 worker 需迁 Redis（见部署 ADR）。
# 加 TTL + 上限，避免进程内内存泄漏与无限增长。
_ppt_tasks: dict[str, dict] = {}
_video_tasks: dict[str, dict] = {}

_TASK_TTL = 3600           # 任务结果保留 1 小时
_MAX_TASK_ENTRIES = 1024   # 单字典上限，超出按创建时间淘汰最旧


def _prune_tasks(store: dict):
    now = time.time()
    expired = [k for k, v in store.items() if now - v.get("created_at", 0) > _TASK_TTL]
    for k in expired:
        store.pop(k, None)
    if len(store) > _MAX_TASK_ENTRIES:
        overflow = len(store) - _MAX_TASK_ENTRIES
        oldest = sorted(store.items(), key=lambda kv: kv[1].get("created_at", 0))[:overflow]
        for k, _ in oldest:
            store.pop(k, None)


async def _run_ppt_task(task_id: str, query: str, is_figure: bool, ai_image: str, search: bool):
    try:
        r = await generate_ppt(query, is_figure, ai_image, "", search)
        if r.success:
            # P1-7：PPT 标题输出安全审核
            safe_title, _ = await audit_output(r.title or "", "xfyun/ppt/title")
            _ppt_tasks[task_id] = {"status": "done",
                                   "result": {"ppt_url": r.ppt_url, "title": safe_title},
                                   "error": None, "created_at": time.time()}
        else:
            _ppt_tasks[task_id] = {"status": "failed", "result": None, "error": r.error, "created_at": time.time()}
    except Exception as e:  # noqa: BLE001
        _ppt_tasks[task_id] = {"status": "failed", "result": None, "error": str(e), "created_at": time.time()}


async def _run_video_task(task_id: str, prompt: str, word_count: int):
    try:
        r = await generate_video(prompt, word_count)
        if r.success:
            # P1-7：视频播报文本输出安全审核
            safe_text, _ = await audit_output(r.text or "", "xfyun/video/text")
            _video_tasks[task_id] = {"status": "done",
                                     "result": {"video_url": r.video_url,
                                                "audio_url": r.audio_url,
                                                "text": safe_text,
                                                "task_id": r.task_id},
                                     "error": None, "created_at": time.time()}
        else:
            _video_tasks[task_id] = {"status": "failed", "result": None, "error": r.error, "created_at": time.time()}
    except Exception as e:  # noqa: BLE001
        _video_tasks[task_id] = {"status": "failed", "result": None, "error": str(e), "created_at": time.time()}



# ── 请求模型 ──

class ImageUnderstandReq(BaseModel):
    image_base64: str
    question: str = "这张图片讲了什么？"


class SearchReq(BaseModel):
    query: str
    limit: int = 5


class PPTReq(BaseModel):
    query: str
    is_figure: bool = True
    ai_image: str = "normal"   # normal | advanced
    search: bool = True


class VideoReq(BaseModel):
    prompt: str
    word_count: int = 120


class ProofreadReq(BaseModel):
    text: str


class ComplianceReq(BaseModel):
    text: str
    categories: Optional[List[str]] = None


class RoleplayReq(BaseModel):
    persona: str = "mock_interviewer"   # DEFAULT_PERSONAS 的 key 或自定义角色描述
    message: str
    topic: str = ""


class ResumeReq(BaseModel):
    info: str                           # 个人信息文本（姓名/教育/技能/项目等）


# ── 端点 ──

@router.get("/status")
async def xfyun_status(user: dict = Depends(get_current_user)):
    """讯飞全部能力可用状态（前端能力全景展示）"""
    return get_all_status()


@router.post("/image-understand")
async def api_image_understand(req: ImageUnderstandReq, user: dict = Depends(get_current_user)):
    """图片理解：上传图片+提问，返回图文回答"""
    # F-015：用户自由文本净化（直连讯飞图片理解 LLM 入口，绕过统一边界）
    safe_question = sanitize_user_input(req.question)
    r = await understand_image(req.image_base64, safe_question)
    if not r.success:
        raise HTTPException(status_code=502, detail=r.error or "图片理解失败")
    # P1-7：输出内容安全审核
    safe_text, _ = await audit_output(r.text, "xfyun/image-understand")

    # L1/L2/L3 三层学情记忆联动（低侵入：讯飞能力调用入 L3，供多模态轨迹追溯）
    try:
        uid = user.get("user_id") or user.get("id") or ""
        if uid:
            from db import memory_store as _ms
            _ms.append_episode(uid, "xfyun_image_understand", {"question_len": len(safe_question)})
    except Exception as _me:
        logger.debug(f"讯飞图片理解记忆写入失败(忽略): {_me}")

    return {"text": safe_text, "source": "xfyun-image-understanding"}


@router.post("/search")
async def api_search(req: SearchReq, user: dict = Depends(get_current_user)):
    """聚合搜索（万搜）：联网检索，用于 RAG 增强"""
    # F-015：用户自由文本净化（直连讯飞聚合搜索 LLM 入口）
    safe_query = sanitize_user_input(req.query)
    r = await web_search(safe_query, req.limit)
    if not r.success:
        raise HTTPException(status_code=502, detail=r.error or "搜索失败")
    return {"items": [{"title": i.title, "summary": i.summary, "url": i.url}
                      for i in r.items],
            "count": len(r.items), "source": "xfyun-one-search"}


@router.post("/ppt")
async def api_ppt(req: PPTReq, background_tasks: BackgroundTasks,
                  user: dict = Depends(get_current_user)):
    """智能 PPT 生成：异步提交，返回 task_id；轮询 /ppt/status/{task_id} 获取结果链接"""
    task_id = uuid.uuid4().hex
    _ppt_tasks[task_id] = {"status": "pending", "result": None, "error": None, "created_at": time.time()}
    # F-015：用户自由文本净化（直连讯飞智能 PPT 生成 LLM 入口）
    safe_query = sanitize_user_input(req.query)
    background_tasks.add_task(_run_ppt_task, task_id, safe_query,
                              req.is_figure, req.ai_image, req.search)
    return {"task_id": task_id, "status": "pending", "source": "xfyun-ppt"}


@router.get("/ppt/status/{task_id}")
async def api_ppt_status(task_id: str, user: dict = Depends(get_current_user)):
    """PPT 生成进度/结果查询"""
    _prune_tasks(_ppt_tasks)
    t = _ppt_tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {"task_id": task_id, **t}


@router.post("/video")
async def api_video(req: VideoReq, background_tasks: BackgroundTasks,
                   user: dict = Depends(get_current_user)):
    """数字人视频生成：异步提交，返回 task_id；轮询 /video/status/{task_id} 获取结果链接"""
    task_id = uuid.uuid4().hex
    _video_tasks[task_id] = {"status": "pending", "result": None, "error": None, "created_at": time.time()}
    # F-015：用户自由文本净化（直连讯飞数字人视频 LLM 入口）
    safe_prompt = sanitize_user_input(req.prompt)
    background_tasks.add_task(_run_video_task, task_id, safe_prompt, req.word_count)
    return {"task_id": task_id, "status": "pending", "source": "xfyun-digital-human"}


@router.get("/video/status/{task_id}")
async def api_video_status(task_id: str, user: dict = Depends(get_current_user)):
    """视频生成进度/结果查询"""
    _prune_tasks(_video_tasks)
    t = _video_tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {"task_id": task_id, **t}


@router.post("/proofread")
async def api_proofread(req: ProofreadReq, user: dict = Depends(get_current_user)):
    """文本纠错：拼写/语法/搭配/成语等纠错"""
    # F-015：用户自由文本净化（直连讯飞文本纠错 LLM 入口）
    safe_text = sanitize_user_input(req.text)
    r = await proofread_text(safe_text)
    if not r.success:
        raise HTTPException(status_code=502, detail=r.error or "纠错失败")
    return {"corrections": r.corrections, "count": len(r.corrections),
            "source": "xfyun-text-correction"}


@router.post("/proofread-doc")
async def api_proofread_doc(req: ProofreadReq, user: dict = Depends(get_current_user)):
    """公文校对：政务/公文风格校对"""
    # F-015：用户自由文本净化（直连讯飞公文校对 LLM 入口）
    safe_text = sanitize_user_input(req.text)
    r = await proofread_document(safe_text)
    if not r.success:
        raise HTTPException(status_code=502, detail=r.error or "校对失败")
    return {"corrections": r.corrections, "count": len(r.corrections),
            "source": "xfyun-doc-proofread"}


@router.post("/compliance")
async def api_compliance(req: ComplianceReq, user: dict = Depends(get_current_user)):
    """文本合规：内容安全审核（防违规/防幻觉输出）"""
    # F-015：用户自由文本净化（直连讯飞文本合规 LLM 入口）
    safe_text = sanitize_user_input(req.text)
    r = await check_compliance(safe_text, req.categories)
    if not r.success:
        raise HTTPException(status_code=502, detail=r.error or "审核失败")
    return {"passed": r.passed, "suggest": r.suggest, "hits": r.hits,
            "source": "xfyun-text-moderation"}


@router.post("/roleplay")
async def api_roleplay(req: RoleplayReq, user: dict = Depends(get_current_user)):
    """星火角色模拟：模拟面试官/导师与用户多轮对话"""
    # F-015：用户自由文本净化（直连讯飞角色模拟 LLM 入口）
    safe_message = sanitize_user_input(req.message)
    safe_topic = sanitize_user_input(req.topic)
    safe_persona = sanitize_user_input(req.persona)
    # Cody #1/#6：user_id 必须用真实用户标识（不能传 topic），且 persona 需净化
    r = await roleplay_interview(safe_persona, safe_message,
                                 user_id=user["user_id"], topic=safe_topic)
    if not r.success:
        raise HTTPException(status_code=502, detail=r.error or "角色模拟失败")
    # P1-7：输出内容安全审核
    safe_reply, _ = await audit_output(r.reply, "xfyun/roleplay")
    return {"reply": safe_reply, "chat_id": r.chat_id,
            "source": "xfyun-character-simulation"}


@router.post("/resume")
async def api_resume(req: ResumeReq, user: dict = Depends(get_current_user)):
    """智能简历：生成可下载的考研复试/能力档案(word)"""
    # F-015：用户自由文本净化（直连讯飞智能简历 LLM 入口）
    safe_info = sanitize_user_input(req.info)
    r = await generate_resume(safe_info)
    if not r.success:
        raise HTTPException(status_code=502, detail=r.error or "简历生成失败")
    return {"word_url": r.word_url, "raw": r.raw, "source": "xfyun-resume"}
