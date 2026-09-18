# ============================================================
# API — AI Skills 创作平台（/api/skills/*）
# 技能 CRUD / 市场查询 / 评价 / 使用日志 / 运行时
# ============================================================

import logging
import uuid
import json as json_mod
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import StreamingResponse
from shared.sse_guard import sse_disconnect_guard
from pydantic import BaseModel, Field

from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from db.skill_store import (
    create_skill, get_skill, update_skill, delete_skill,
    batch_delete_skills, export_skills_json, import_skills_json,
    list_skills, publish_skill, archive_skill,
    create_rating, list_ratings,
    log_usage, increment_skill_usage,
    get_creator_stats, get_templates, get_template, seed_official_skills,
    add_favorite, remove_favorite, is_favorited, list_favorites,
)
from schemas.skills import (
    Skill, SkillRating, SkillUsage, SkillStatus, SkillCategory,
)

logger = logging.getLogger("netlearn.skills")
# F-011：Skills 运行时（prompt-test / run）端点统一鉴权 + 每用户 LLM 配额（429）
router = APIRouter(prefix="/skills", tags=["skills"], dependencies=[Depends(require_llm_quota)])


# ── Pydantic 请求模型 ──


class CreateSkillRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="技能名称")
    description: str = Field("", max_length=500, description="技能描述")
    icon: str = Field("🤖", max_length=10, description="图标")
    system_prompt: str = Field("", max_length=10000, description="System Prompt")
    llm_channel: str = Field("auto", pattern="^(auto|deepseek|xfyun|qwen)$")
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(2048, ge=64, le=8192)
    category: str = Field("other", max_length=30)
    tags: str = Field("[]", max_length=500, description="JSON 数组")
    rag_enabled: bool = True


class UpdateSkillRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=10)
    system_prompt: Optional[str] = Field(None, max_length=10000)
    llm_channel: Optional[str] = Field(None, pattern="^(auto|deepseek|xfyun|qwen)$")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=64, le=8192)
    category: Optional[str] = Field(None, max_length=30)
    tags: Optional[str] = Field(None, max_length=500)
    rag_enabled: Optional[bool] = None


class RateSkillRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="评分 1-5 星")
    comment: str = Field("", max_length=500)


class RunSkillRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="用户输入")
    session_id: str = Field("", max_length=100)
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=64, le=8192)


class CreateFromTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    icon: str = Field("🤖", max_length=10)


class LogUsageRequest(BaseModel):
    skill_id: str = Field(..., max_length=50)
    session_id: str = Field("", max_length=100)
    input_text: str = Field("", max_length=5000)
    output_text: str = Field("", max_length=50000)
    tokens_used: int = Field(0, ge=0)
    latency_ms: int = Field(0, ge=0)


# ── 辅助函数 ──


def _user_id(user: dict) -> str:
    return user.get("user_id") or user.get("id") or user.get("sub", "")


def _user_name(user: dict) -> str:
    return user.get("display_name") or user.get("username", "用户")


# ── 技能 CRUD ──


@router.post("/create")
async def api_create_skill(
    body: CreateSkillRequest,
    user: dict = Depends(get_current_user),
):
    """创建新技能"""
    try:
        tag_list = json_mod.loads(body.tags) if isinstance(body.tags, str) else body.tags
    except (json_mod.JSONDecodeError, TypeError):
        tag_list = []

    valid_categories = {c.value for c in SkillCategory}
    if body.category not in valid_categories:
        raise HTTPException(status_code=422, detail=f"无效分类: {body.category}")

    skill = Skill(
        name=body.name,
        description=body.description,
        icon=body.icon,
        system_prompt=body.system_prompt,
        llm_channel=body.llm_channel,
        temperature=max(0.0, min(1.0, body.temperature)),
        max_tokens=max(64, min(8192, body.max_tokens)),
        category=body.category,
        tags=tag_list,
        rag_enabled=body.rag_enabled,
        creator_id=_user_id(user),
        creator_name=_user_name(user),
    )
    created = create_skill(skill)
    return {"status": "ok", "skill": created.to_dict()}


@router.get("/get/{skill_id}")
async def api_get_skill(skill_id: str, user: dict = Depends(get_current_user)):
    """获取技能详情"""
    skill = get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"status": "ok", "skill": skill.to_dict()}


@router.post("/update/{skill_id}")
async def api_update_skill(
    skill_id: str,
    body: UpdateSkillRequest,
    user: dict = Depends(get_current_user),
):
    """更新技能信息"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.creator_id != _user_id(user) and not user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="无权修改他人技能")

    if body.name is not None:
        existing.name = body.name
    if body.description is not None:
        existing.description = body.description
    if body.icon is not None:
        existing.icon = body.icon
    if body.system_prompt is not None:
        existing.system_prompt = body.system_prompt
    if body.llm_channel is not None:
        existing.llm_channel = body.llm_channel
    if body.temperature is not None:
        existing.temperature = max(0.0, min(1.0, body.temperature))
    if body.max_tokens is not None:
        existing.max_tokens = max(64, min(8192, body.max_tokens))
    if body.category is not None:
        valid_categories = {c.value for c in SkillCategory}
        if body.category not in valid_categories:
            raise HTTPException(status_code=422, detail=f"无效分类: {body.category}")
        existing.category = body.category
    if body.tags is not None:
        try:
            existing.tags = json_mod.loads(body.tags) if isinstance(body.tags, str) else body.tags
        except (json_mod.JSONDecodeError, TypeError):
            existing.tags = []
    if body.rag_enabled is not None:
        existing.rag_enabled = body.rag_enabled

    ok = update_skill(existing)
    if not ok:
        raise HTTPException(status_code=500, detail="更新失败")
    return {"status": "ok", "skill": existing.to_dict()}


@router.post("/delete/{skill_id}")
async def api_delete_skill(skill_id: str, user: dict = Depends(get_current_user)):
    """删除技能"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.creator_id != _user_id(user) and not user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="无权删除他人技能")

    ok = delete_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"status": "ok", "message": "技能已删除"}


# ── 批量操作 ──


class BatchDeleteRequest(BaseModel):
    skill_ids: list[str]


@router.post("/batch-delete")
async def api_batch_delete_skills(
    body: BatchDeleteRequest,
    user: dict = Depends(get_current_user),
):
    """批量删除技能（仅管理员或创建者）"""
    if user.get("role") != "admin":
        # 非管理员只能删除自己的
        allowed = []
        for sid in body.skill_ids:
            s = get_skill(sid)
            if s and s.creator_id == _user_id(user):
                allowed.append(sid)
        if not allowed:
            raise HTTPException(status_code=403, detail="无权删除他人的技能")
        body.skill_ids = allowed

    deleted = batch_delete_skills(body.skill_ids)
    return {"status": "ok", "deleted": deleted}


@router.get("/export")
async def api_export_skills(
    user: dict = Depends(get_current_user),
):
    """导出我的技能为 JSON"""
    json_str = export_skills_json(creator_id=_user_id(user))
    from fastapi.responses import Response
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=netlearn-skills-export.json"},
    )


@router.post("/import")
async def api_import_skills(
    body: dict,
    user: dict = Depends(get_current_user),
):
    """从 JSON 导入技能"""
    json_str = json_mod.dumps(body, ensure_ascii=False)
    imported = import_skills_json(
        json_str,
        creator_id=_user_id(user),
        creator_name=_user_name(user),
    )
    return {"status": "ok", "imported": imported}


# ── 技能状态管理 ──


@router.post("/publish/{skill_id}")
async def api_publish_skill(skill_id: str, user: dict = Depends(get_current_user)):
    """发布技能（draft → published）"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.creator_id != _user_id(user) and not user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="无权发布他人技能")

    ok = publish_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=400, detail="发布失败，请确认技能状态为草稿")
    return {"status": "ok", "message": "技能已发布"}


@router.post("/archive/{skill_id}")
async def api_archive_skill(skill_id: str, user: dict = Depends(get_current_user)):
    """归档技能（published → archived）"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.creator_id != _user_id(user) and not user.get("role") == "admin":
        raise HTTPException(status_code=403, detail="无权归档他人技能")

    ok = archive_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=400, detail="归档失败，请确认技能状态为已发布")
    return {"status": "ok", "message": "技能已归档"}


# ── 技能市场查询 ──


@router.get("/market")
async def api_market(
    category: Optional[str] = Query(None, description="分类过滤"),
    tag: Optional[str] = Query(None, description="标签过滤"),
    search: Optional[str] = Query(None, description="关键词搜索"),
    sort_by: str = Query("usage_count", description="排序: usage_count/avg_rating/updated_at/name"),
    sort_desc: bool = Query(True, description="是否降序"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """技能市场浏览（仅已发布技能）"""
    items, total = list_skills(
        status=SkillStatus.PUBLISHED.value,
        category=category,
        tag=tag,
        search=search,
        sort_by=sort_by,
        sort_desc=sort_desc,
        limit=limit,
        offset=offset,
    )
    return {
        "status": "ok",
        "total": total,
        "items": [s.to_dict() for s in items],
    }


@router.get("/my")
async def api_my_skills(
    status: Optional[str] = Query(None, description="过滤状态"),
    sort_by: str = Query("updated_at"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """获取我的技能列表"""
    items, total = list_skills(
        creator_id=_user_id(user),
        status=status,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )
    return {
        "status": "ok",
        "total": total,
        "items": [s.to_dict() for s in items],
    }


@router.get("/official")
async def api_official_skills(user: dict = Depends(get_current_user)):
    """获取官方技能列表"""
    items, total = list_skills(is_official=True, status=SkillStatus.PUBLISHED.value)
    return {
        "status": "ok",
        "total": total,
        "items": [s.to_dict() for s in items],
    }


# ── 评价 ──


@router.post("/rate/{skill_id}")
async def api_rate_skill(
    skill_id: str,
    body: RateSkillRequest,
    user: dict = Depends(get_current_user),
):
    """对技能进行评价"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if body.rating < 1 or body.rating > 5:
        raise HTTPException(status_code=422, detail="评分须在 1-5 之间")

    r = SkillRating(
        skill_id=skill_id,
        user_id=_user_id(user),
        user_name=_user_name(user),
        rating=body.rating,
        comment=body.comment,
    )
    created = create_rating(r)
    return {"status": "ok", "rating": created.to_dict()}


@router.get("/ratings/{skill_id}")
async def api_skill_ratings(
    skill_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """获取技能评价列表"""
    items, total = list_ratings(skill_id, limit=limit, offset=offset)
    return {
        "status": "ok",
        "total": total,
        "items": [r.to_dict() for r in items],
    }


# ── 收藏 ──


@router.post("/favorite/{skill_id}")
async def api_favorite_skill(skill_id: str, user: dict = Depends(get_current_user)):
    """收藏技能"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    add_favorite(_user_id(user), skill_id)
    return {"status": "ok", "favorited": True}


@router.post("/unfavorite/{skill_id}")
async def api_unfavorite_skill(skill_id: str, user: dict = Depends(get_current_user)):
    """取消收藏"""
    remove_favorite(_user_id(user), skill_id)
    return {"status": "ok", "favorited": False}


@router.get("/favorites")
async def api_favorites(user: dict = Depends(get_current_user)):
    """获取收藏列表"""
    items = list_favorites(_user_id(user))
    return {"status": "ok", "items": [s.to_dict() for s in items]}


@router.get("/favorited/{skill_id}")
async def api_is_favorited(skill_id: str, user: dict = Depends(get_current_user)):
    """检查是否已收藏"""
    fav = is_favorited(_user_id(user), skill_id)
    return {"status": "ok", "favorited": fav}


# ── 创作者统计 ──


@router.get("/stats")
async def api_creator_stats(user: dict = Depends(get_current_user)):
    """创作者统计看板"""
    stats = get_creator_stats(_user_id(user))
    return {"status": "ok", "stats": stats}


# ── 模板 ──


@router.get("/templates")
async def api_templates(user: dict = Depends(get_current_user)):
    """获取预设技能模板列表"""
    templates = get_templates()
    return {
        "status": "ok",
        "total": len(templates),
        "items": [t.to_dict() for t in templates],
    }


@router.get("/templates/{template_id}")
async def api_template_detail(template_id: str, user: dict = Depends(get_current_user)):
    """获取模板详情"""
    tmpl = get_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    return {"status": "ok", "template": tmpl.to_dict()}


@router.post("/from-template/{template_id}")
async def api_create_from_template(
    template_id: str,
    body: CreateFromTemplateRequest,
    user: dict = Depends(get_current_user),
):
    """基于模板创建技能"""
    tmpl = get_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="模板不存在")

    skill = Skill(
        name=body.name,
        description=body.description or tmpl.description,
        icon=body.icon or tmpl.icon,
        system_prompt=tmpl.system_prompt_template,
        llm_channel=tmpl.default_config.get("llm_channel", "auto"),
        temperature=tmpl.default_config.get("temperature", 0.7),
        max_tokens=tmpl.default_config.get("max_tokens", 2048),
        category=tmpl.category,
        tags=[tmpl.category],
        creator_id=_user_id(user),
        creator_name=_user_name(user),
    )
    created = create_skill(skill)
    return {"status": "ok", "skill": created.to_dict()}


# ── 种子数据（管理员） ──


@router.post("/seed-official")
async def api_seed_official(user: dict = Depends(get_current_user)):
    """初始化官方技能种子数据（管理员权限）"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    seed_official_skills()
    return {"status": "ok", "message": "官方技能种子数据已初始化"}


# ── 使用日志（内部） ──


@router.post("/log-usage")
async def api_log_usage(
    body: LogUsageRequest,
    user: dict = Depends(get_current_user),
):
    """记录技能使用日志（由 skill_agent 调用）"""
    existing = get_skill(body.skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")

    uid = _user_id(user)
    usage = SkillUsage(
        skill_id=body.skill_id,
        user_id=uid,
        session_id=body.session_id,
        input_text=body.input_text,
        output_text=body.output_text,
        tokens_used=body.tokens_used,
        latency_ms=body.latency_ms,
    )
    logged = log_usage(usage)
    increment_skill_usage(body.skill_id, uid)
    return {"status": "ok", "usage_id": logged.id}


# ── 技能运行时 ──


@router.post("/run/{skill_id}")
async def api_run_skill(
    skill_id: str,
    body: RunSkillRequest,
    user: dict = Depends(get_current_user),
):
    """执行技能（非流式，返回完整响应）"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.status != "published" and existing.creator_id != _user_id(user):
        raise HTTPException(status_code=403, detail="该技能未发布，仅创建者可调用")

    from agents.skill_agent import SkillAgent
    agent = SkillAgent(skill_id)
    try:
        response = await agent.execute(
            user_input=body.message,
            user_id=_user_id(user),
            session_id=body.session_id,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )

        # L1/L2/L3 三层学情记忆联动（低侵入：技能执行入 L3，供技能使用轨迹追溯）
        try:
            uid = _user_id(user)
            if uid:
                from db import memory_store as _ms
                _ms.append_episode(uid, "skill_run", {
                    "skill_id": skill_id,
                    "output_len": len(response or ""),
                })
        except Exception as _me:
            logger.debug(f"技能执行记忆写入失败(忽略): {_me}")

        return {"status": "ok", "response": response}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"技能执行异常: {e}")
        raise HTTPException(status_code=500, detail=f"技能执行失败: {e}")


class RunSkillWithMemoryRequest(RunSkillRequest):
    """带学情记忆的技能执行请求（优先级3b：插件独立读写学情记忆）"""
    use_memory: bool = True


@router.post("/run-with-memory/{skill_id}")
async def api_run_skill_with_memory(
    skill_id: str,
    body: RunSkillWithMemoryRequest,
    user: dict = Depends(get_current_user),
):
    """执行技能并注入 L1/L2/L3 学情记忆（插件生态增强）

    使用 SkillPluginRuntime：热加载配置 + 单技能故障熔断 + 记忆注入/写回。
    """
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.status != "published" and existing.creator_id != _user_id(user):
        raise HTTPException(status_code=403, detail="该技能未发布，仅创建者可调用")

    from engines.skill_plugin_runtime import SkillPluginRuntime, CircuitOpenError
    runtime = SkillPluginRuntime.get(skill_id)
    try:
        # P2②：记忆读权限校验——memory_access 含 read 才注入记忆（none/write 拒绝注入）
        effective_use_memory = body.use_memory and existing.memory_access in ("read", "read_write")
        response = await runtime.execute(
            user_input=body.message,
            user_id=_user_id(user),
            session_id=body.session_id,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            use_memory=effective_use_memory,
            memory_access=existing.memory_access,
        )
        return {"status": "ok", "response": response, "breaker": runtime.get_status()["breaker"],
                "memory_access": existing.memory_access,
                "memory_injected": effective_use_memory}
    except CircuitOpenError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"技能执行异常(带记忆): {e}")
        raise HTTPException(status_code=500, detail=f"技能执行失败: {e}")


@router.post("/breaker/reset/{skill_id}")
async def api_reset_skill_breaker(
    skill_id: str,
    user: dict = Depends(get_current_user),
):
    """手动重置指定技能的熔断器（管理员或技能创建者）"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if user.get("role") != "admin" and existing.creator_id != _user_id(user):
        raise HTTPException(status_code=403, detail="仅管理员或创建者可重置熔断器")
    from engines.skill_plugin_runtime import SkillPluginRuntime
    runtime = SkillPluginRuntime.get(skill_id)
    runtime.reset_breaker()
    return {"status": "ok", "breaker": runtime.get_status()["breaker"]}


@router.get("/breaker/status/{skill_id}")
async def api_skill_breaker_status(
    skill_id: str,
    user: dict = Depends(get_current_user),
):
    """查询技能熔断器状态"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    from engines.skill_plugin_runtime import SkillPluginRuntime
    runtime = SkillPluginRuntime.get(skill_id)
    return {"status": "ok", "breaker": runtime.get_status()["breaker"]}



@router.post("/run-stream/{skill_id}")
async def api_run_skill_stream(
    skill_id: str,
    body: RunSkillRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """执行技能（流式，SSE 格式）"""
    existing = get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.status != "published" and existing.creator_id != _user_id(user):
        raise HTTPException(status_code=403, detail="该技能未发布，仅创建者可调用")

    from agents.skill_agent import SkillAgent
    agent = SkillAgent(skill_id)

    async def event_stream():
        full_output = ""
        try:
            async for chunk in agent.stream_execute(
                user_input=body.message,
                user_id=_user_id(user),
                session_id=body.session_id,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            ):
                full_output += chunk
                safe_chunk = chunk.replace("\n", "\\n").replace("\r", "\\r")
                yield f"data: {json_mod.dumps({'type': 'content', 'content': safe_chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"data: {json_mod.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"技能流式执行异常: {e}")
            yield f"data: {json_mod.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(sse_disconnect_guard(request, event_stream()), media_type="text/event-stream")


# ── PromptStudio 测试端点（无需保存技能即可测试） ──


class PromptTestRequest(BaseModel):
    system_prompt: str
    message: str
    llm_channel: str = "auto"
    temperature: float = 0.7
    max_tokens: int = 1024


@router.post("/prompt-test")
async def api_prompt_test(
    body: PromptTestRequest,
    user: dict = Depends(get_current_user),
):
    """测试 Prompt 效果（不保存技能，直接调用 LLM）"""
    from db.llm_provider import LLMProvider

    provider_name = body.llm_channel if body.llm_channel != "auto" else None
    llm = LLMProvider(provider_name=provider_name)
    messages = [
        {"role": "system", "content": body.system_prompt},
        {"role": "user", "content": body.message},
    ]
    try:
        response = await llm.chat(
            messages=messages,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
        return {"status": "ok", "response": response or ""}
    except Exception as e:
        logger.error(f"Prompt 测试失败: {e}")
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}")