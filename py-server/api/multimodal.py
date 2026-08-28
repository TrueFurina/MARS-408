# ============================================================
# 多模态内容生成 API
# 赛题要求：支持多种媒体类型（文本/图表/PPT/代码/视频脚本）
# ============================================================

import logging
import json as json_mod
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

from db.llm_provider import LLMProvider
from shared.sse_guard import sse_disconnect_guard
from db.xfyun_multimodal import (
    generate_image, generate_speech, generate_multimodal_resource,
    get_multimodal_status, is_tti_available, is_tts_available,
)
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from shared.prompt_guard import sanitize_user_input  # F-015：覆盖直连讯飞 TTI 图片生成入口（绕过统一边界）
from shared.content_safety import audit_output  # P1-7：统一输出内容安全审核

logger = logging.getLogger("netlearn.multimodal")
# F-011：多模态生成端点统一鉴权 + 每用户 LLM 配额（429）
router = APIRouter(
    prefix="/multimodal", tags=["multimodal"],
    dependencies=[Depends(require_llm_quota)],
)


class GenerationRequest(BaseModel):
    topic: str
    resource_type: str  # "ppt" | "code" | "video_script" | "infographic" | "mindmap"
    student_profile: Optional[dict] = None
    difficulty: str = "medium"


@router.post("/generate")
async def generate_multimodal(req: GenerationRequest, user: dict = Depends(get_current_user)):
    """生成多模态学习资源（注入 L1/L2/L3 学情记忆，低侵入个性化）"""
    resource_type = req.resource_type.lower()

    # L1/L2/L3 三层学情记忆注入（低侵入：多模态内容个性化，失败不影响主流程）
    memory_ctx = ""
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        if user_id:
            from services.memory_service import build_memory_context
            memory_ctx = build_memory_context(user_id, session_id=None, max_episodes=4)
            if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
                req.student_profile = {**(req.student_profile or {}), "_memory_context": memory_ctx}
    except Exception as _me:
        logger.debug(f"多模态记忆注入失败(降级): {_me}")

    if resource_type == "ppt":
        return await _generate_ppt(req)
    elif resource_type == "code":
        return await _generate_code(req)
    elif resource_type == "video_script":
        return await _generate_video_script(req)
    elif resource_type == "infographic":
        return await _generate_infographic(req)
    elif resource_type == "mindmap":
        return await _generate_mindmap(req)
    elif resource_type == "narrated_video":
        return await _generate_narrated_video(req)
    elif resource_type == "teaching_video":
        return await _generate_teaching_video(req)
    elif resource_type == "study_notes":
        return await _generate_study_notes(req)
    elif resource_type == "interactive_model":
        return await _generate_interactive_model(req)
    elif resource_type == "video_recommend":
        return await _generate_video_recommend(req)
    elif resource_type == "resource_pack":
        return await _generate_resource_pack(req)
    else:
        raise HTTPException(status_code=400, detail=f"不支持的资源类型: {resource_type}")


async def _generate_ppt(req: GenerationRequest) -> dict:
    """生成PPT文件内容（赛题要求多模态支持）"""
    from prompts import PPT_AGENT_PROMPT

    profile = req.student_profile or {}
    user_prompt = (
        f"【学习主题】{req.topic}\n"
        f"【难度】{req.difficulty}\n"
        f"【学生画像】知识基础: {profile.get('knowledge_base', 'beginner')}, "
        f"学习风格: {profile.get('learning_style', 'reading')}\n"
        f"请生成PPT大纲。"
    )

    try:
        llm = LLMProvider()
        content = await llm.text_completion(PPT_AGENT_PROMPT, user_prompt, max_tokens=2000)
    except Exception as e:
        logger.warning(f"PPT生成LLM调用失败: {e}")
        content = f"## {req.topic} PPT大纲\n\n1. 封面\n2. 目录\n3. 核心概念\n4. 原理详解\n5. 案例演示\n6. 总结"

    # P1-7：输出内容安全审核
    content, _ = await audit_output(content, "multimodal/generate/ppt")

    # 解析PPT大纲为结构化数据
    slides = _parse_ppt_slides(content)

    # 生成真实 .pptx 文件（赛题多模态硬性要求：原仅返回大纲结构）
    from agents.ppt_builder import build_pptx
    ppt_file = build_pptx(req.topic, content, profile)
    file_url = ppt_file.get("url") if ppt_file.get("ok") else None
    file_path = ppt_file.get("path") if ppt_file.get("ok") else None

    return {
        "resource_type": "ppt",
        "topic": req.topic,
        "slides": slides,
        "total_slides": len(slides),
        "raw_content": content,
        "format": "pptx_file",
        "file_url": file_url,
        "file_path": file_path,
        "pptx_ok": ppt_file.get("ok", False),
    }


async def _generate_code(req: GenerationRequest) -> dict:
    """生成代码实操案例"""
    from prompts import CODE_PRACTICE_AGENT_PROMPT

    user_prompt = f"【学习主题】{req.topic}\n【难度】{req.difficulty}\n请生成代码实操案例。"

    try:
        llm = LLMProvider()
        content = await llm.text_completion(CODE_PRACTICE_AGENT_PROMPT, user_prompt, max_tokens=2000)
    except Exception as e:
        logger.warning(f"代码生成LLM调用失败: {e}")
        content = f"```python\n# {req.topic} 示例代码\nprint('Hello, {req.topic}')\n```"

    # P1-7：输出内容安全审核
    content, _ = await audit_output(content, "multimodal/generate/code")

    return {
        "resource_type": "code",
        "topic": req.topic,
        "code_content": content,
        "language": "python",
    }


async def _generate_video_script(req: GenerationRequest) -> dict:
    """生成教学视频脚本（赛题多模态要求）"""
    video_prompt = (
        "你是计算机408学习系统的「视频脚本Agent」。请为指定知识点生成教学视频脚本。\n\n"
        "要求：\n"
        "1. 视频时长5-8分钟\n"
        "2. 包含：开场白、知识点讲解、动画/图表描述、案例演示、总结\n"
        "3. 每个场景标注预计时长\n"
        "4. 使用Markdown格式\n\n"
        f"【知识点】{req.topic}\n"
        f"【难度】{req.difficulty}\n"
    )

    try:
        llm = LLMProvider()
        content = await llm.text_completion(video_prompt, f"请为{req.topic}生成视频脚本", max_tokens=2000)
    except Exception as e:
        logger.warning(f"视频脚本生成失败: {e}")
        content = f"## {req.topic} 教学视频脚本\n\n### 场景1 (0:00-1:00)\n开场白：欢迎学习{req.topic}\n\n### 场景2 (1:00-5:00)\n知识点讲解\n\n### 场景3 (5:00-6:00)\n总结"

    # P1-7：输出内容安全审核
    content, _ = await audit_output(content, "multimodal/generate/video_script")

    return {
        "resource_type": "video_script",
        "topic": req.topic,
        "script_content": content,
        "estimated_duration": "5-8分钟",
        "scenes": _parse_video_scenes(content),
    }


async def _generate_infographic(req: GenerationRequest) -> dict:
    """生成信息图描述"""
    infographic_prompt = (
        "你是计算机408学习系统的「信息图Agent」。请为指定知识点生成信息图设计方案。\n\n"
        "要求：\n"
        "1. 用文字描述信息图的布局和内容\n"
        "2. 包含：标题、核心数据/对比、流程图描述、颜色建议\n"
        "3. 适合学生快速理解知识点\n\n"
        f"【知识点】{req.topic}\n"
    )

    try:
        llm = LLMProvider()
        content = await llm.text_completion(infographic_prompt, f"请为{req.topic}设计信息图", max_tokens=1500)
    except Exception as e:
        logger.warning(f"信息图生成失败: {e}")
        content = f"## {req.topic} 信息图\n\n标题：{req.topic}核心要点\n布局：左中右三栏\n内容：概念定义 | 流程图 | 对比表"

    # P1-7：输出内容安全审核
    content, _ = await audit_output(content, "multimodal/generate/infographic")

    return {
        "resource_type": "infographic",
        "topic": req.topic,
        "design_content": content,
    }


async def _generate_mindmap(req: GenerationRequest) -> dict:
    """生成思维导图（Markdown格式，前端渲染为D3.js图）"""
    mindmap_prompt = (
        "你是计算机408学习系统的「思维导图Agent」。请用Markdown无序列表格式生成知识点思维导图。\n\n"
        f"【知识点】{req.topic}\n"
        "格式要求：\n"
        "- 根节点\n"
        "  - 子节点1\n"
        "    - 详细说明\n"
        "  - 子节点2\n"
    )

    try:
        llm = LLMProvider()
        content = await llm.text_completion(mindmap_prompt, f"请为{req.topic}生成思维导图", max_tokens=1500)
    except Exception as e:
        logger.warning(f"思维导图生成失败: {e}")
        content = f"- {req.topic}\n  - 核心概念\n  - 工作原理\n  - 应用场景"

    # P1-7：输出内容安全审核
    content, _ = await audit_output(content, "multimodal/generate/mindmap")

    return {
        "resource_type": "mindmap",
        "topic": req.topic,
        "mindmap_content": content,
        "format": "markdown_list",
    }


def _parse_ppt_slides(content: str) -> list[dict]:
    """解析PPT大纲为幻灯片列表"""
    slides = []
    current_slide = None

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("## ") or line.startswith("# "):
            if current_slide:
                slides.append(current_slide)
            current_slide = {"title": line.lstrip("# ").strip(), "content": []}
        elif current_slide and line:
            current_slide["content"].append(line)
        elif line.startswith("> "):
            if current_slide:
                current_slide.setdefault("notes", []).append(line.lstrip("> "))

    if current_slide:
        slides.append(current_slide)

    return slides if slides else [{"title": req_topic, "content": ["默认内容"]}]


def _parse_video_scenes(content: str) -> list[dict]:
    """解析视频脚本为场景列表"""
    scenes = []
    current_scene = None

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("### ") or line.startswith("## "):
            if current_scene:
                scenes.append(current_scene)
            current_scene = {"scene_title": line.lstrip("# ").strip(), "content": []}
        elif current_scene and line:
            current_scene["content"].append(line)

    if current_scene:
        scenes.append(current_scene)

    return scenes


@router.get("/supported-types")
async def get_supported_types(user: dict = Depends(get_current_user)):
    """获取支持的多模态资源类型"""
    return {
        "types": [
            {"id": "ppt", "name": "PPT大纲", "description": "生成结构化PPT幻灯片大纲"},
            {"id": "code", "name": "代码实操", "description": "生成可运行的Python代码案例"},
            {"id": "video_script", "name": "视频脚本", "description": "生成教学视频分场景脚本"},
            {"id": "infographic", "name": "信息图", "description": "生成信息图设计方案"},
            {"id": "mindmap", "name": "思维导图", "description": "生成Markdown格式思维导图"},
            {"id": "image", "name": "教学插图", "description": "AI生成知识点教学插图（讯飞TTI）"},
            {"id": "audio", "name": "语音旁白", "description": "AI生成教学内容语音朗读（讯飞TTS）"},
        ]
    }


# ============================================================
# 多模态生成端点（赛题核心要求：多模态内容生成）
# ============================================================

class ImageGenerationRequest(BaseModel):
    """教学插图生成请求"""
    topic: str
    prompt: Optional[str] = None  # 自定义提示词，不填则用topic


class AudioGenerationRequest(BaseModel):
    """语音合成请求"""
    text: str
    voice: str = "xiaoyan"  # 讯飞发音人


class MultimodalResourceRequest(BaseModel):
    """多模态资源生成请求（图+文+音一体）"""
    topic: str
    text_content: str
    generate_image: bool = True
    generate_audio: bool = True


@router.post("/generate-image")
async def generate_teaching_image(req: ImageGenerationRequest, user: dict = Depends(get_current_user)):
    """生成教学插图（赛题多模态要求）

    有讯飞TTI key → 生成真实AI图片(512x512 JPEG)
    无key → 生成SVG概念图（降级）
    """
    # F-015：图片生成提示词净化（直连讯飞 TTI 指令跟随模型入口，绕过统一边界）
    prompt = req.prompt or f"计算机科学教学图：{req.topic}"
    safe_prompt = sanitize_user_input(prompt)
    result = await generate_image(safe_prompt, req.topic)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "图片生成失败")

    return {
        "topic": req.topic,
        "source": result.source,
        "image_base64": result.image_base64,
        "image_svg": result.image_svg,
        "is_real_image": result.source == "xfyun",
    }


@router.post("/generate-audio")
async def generate_teaching_audio(req: AudioGenerationRequest, user: dict = Depends(get_current_user)):
    """生成语音旁白（赛题多模态要求）

    有讯飞TTS key → 生成MP3音频
    无key → 返回原文，前端用浏览器Web Speech API朗读
    """
    result = await generate_speech(req.text, req.voice)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "语音合成失败")

    return {
        "source": result.source,
        "audio_base64": result.audio_base64,
        "audio_format": result.audio_format,
        "fallback_text": result.fallback_text,
        "is_real_audio": result.source == "xfyun",
        "text_length": len(req.text),
    }


@router.post("/generate-multimodal")
async def generate_full_multimodal(req: MultimodalResourceRequest, user: dict = Depends(get_current_user)):
    """生成完整多模态资源（图+文+音）— 赛题核心：多模态学习资料

    一次调用生成：
    - 教学插图（TTI或SVG降级）
    - 语音旁白（TTS或浏览器降级）
    - 原始文本内容

    返回前端可直接渲染的多模态内容卡片数据。
    """
    # F-015：topic 净化（会经 generate_multimodal_resource → 讯飞 TTI 提示词，绕过统一边界）
    safe_topic = sanitize_user_input(req.topic)
    resource = await generate_multimodal_resource(
        topic=safe_topic,
        text_content=req.text_content,
        generate_image=req.generate_image,
        generate_audio=req.generate_audio,
    )

    return {
        "topic": req.topic,
        "text": resource.text,
        "image_base64": resource.image_base64,
        "image_svg": resource.image_svg,
        "image_source": resource.image_source,
        "audio_base64": resource.audio_base64,
        "audio_fallback_text": resource.audio_fallback_text,
        "audio_source": resource.audio_source,
        "multimodal": True,
    }


@router.get("/status")
async def multimodal_status(user: dict = Depends(get_current_user)):
    """获取多模态服务状态"""
    return get_multimodal_status()


# ════════════════════════════════════════════════
# 配音教学视频生成（MeloTTS + FFmpeg）
# ════════════════════════════════════════════════

class NarratedVideoRequest(BaseModel):
    text: str
    language: str = "zh"
    speed: float = 1.0
    bg_image: Optional[str] = None


@router.post("/generate-narrated-video")
async def generate_narrated_video_endpoint(
    req: NarratedVideoRequest,
    user: dict = Depends(get_current_user),
):
    """生成配音教学视频

    使用 MeloTTS 合成语音 + FFmpeg 合成视频（背景图 + 语音 + 字幕），
    适用于赛题要求的"多模态教学视频/动画"生成。
    """
    from services.video_dub import generate_narrated_video, is_ffmpeg_available

    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="文本不能为空")

    if not is_ffmpeg_available():
        raise HTTPException(status_code=503, detail="FFmpeg 不可用，无法生成视频")

    video_path = generate_narrated_video(
        text=req.text,
        language=req.language,
        bg_image=req.bg_image,
        speed=req.speed,
    )

    if video_path is None:
        raise HTTPException(status_code=500, detail="视频生成失败，请检查 MeloTTS 和 FFmpeg 配置")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=f"mars408_narrated_{req.language}.mp4",
    )


async def _generate_narrated_video(req: GenerationRequest) -> dict:
    """通过资源生成管线调用配音视频"""
    from services.video_dub import generate_narrated_video, is_ffmpeg_available

    if not is_ffmpeg_available():
        return {"resource_type": "narrated_video", "topic": req.topic,
                "error": "FFmpeg 不可用", "status": "failed"}

    # 先通过 LLM 生成一段讲解文本
    from prompts import TEACHER_AGENT_PROMPT
    profile = req.student_profile or {}
    user_prompt = (
        f"【学习主题】{req.topic}\n"
        f"【难度】{req.difficulty}\n"
        f"【学生画像】知识基础: {profile.get('knowledge_base', 'beginner')}\n"
        f"请生成一段约 1-2 分钟的讲解文本，适合语音朗读。"
    )
    try:
        llm = LLMProvider()
        lecture_text = await llm.text_completion(TEACHER_AGENT_PROMPT, user_prompt, max_tokens=1000)
    except Exception:
        lecture_text = f"今天我们来学习{req.topic}。这是计算机408考研中的核心知识点。"

    # P1-7：输出内容安全审核
    lecture_text, _ = await audit_output(lecture_text, "multimodal/generate/narrated_video")

    video_path = generate_narrated_video(
        text=lecture_text,
        language="zh",
        speed=1.0,
    )

    if video_path:
        return {
            "resource_type": "narrated_video",
            "topic": req.topic,
            "video_path": video_path,
            "lecture_text": lecture_text,
            "status": "ok",
        }
    return {
        "resource_type": "narrated_video",
        "topic": req.topic,
        "error": "视频生成失败",
        "status": "failed",
    }


# ════════════════════════════════════════════════
# 程序化教学视频生成（不依赖昂贵 API）
# 工作流：分镜脚本 → SVG 场景 → HTML 幻灯片
# ════════════════════════════════════════════════

class TeachingVideoRequest(BaseModel):
    topic: str
    profile: Optional[dict] = None
    knowledge_context: str = ""
    difficulty: str = "medium"
    output_format: str = "html"


@router.post("/generate-teaching-video")
async def generate_teaching_video_endpoint(
    req: TeachingVideoRequest,
    user: dict = Depends(get_current_user),
):
    """生成程序化教学视频（不依赖昂贵 AI 视频 API）"""
    return await _generate_teaching_video(req)


@router.post("/generate-teaching-video-stream")
async def generate_teaching_video_stream(
    req: TeachingVideoRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """流式生成教学视频（SSE 推送进度）

    推送事件:
    - progress: {step, total, message}
    - scene_done: {scene_id, title}
    - audio_done: {scene_id, source}
    - complete: {html, scenes, duration}
    - error: {message}
    """
    from fastapi.responses import StreamingResponse

    async def event_stream():
        # 步骤 1: LLM 生成脚本
        yield f"data: {json_mod.dumps({'type': 'progress', 'step': 1, 'total': 4, 'message': '正在生成视频分镜脚本...'})}\n\n"
        from agents.media_generator import generate_teaching_video_package
        result = await generate_teaching_video_package(
            topic=req.topic,
            profile=(req.student_profile or req.profile or {}) if hasattr(req, 'student_profile') else (req.profile or {}),
            knowledge_context=getattr(req, 'knowledge_context', ''),
            difficulty=getattr(req, 'difficulty', 'medium'),
            output_format=getattr(req, 'output_format', 'html'),
        )

        if result.get("status") == "error":
            yield f"data: {json_mod.dumps({'type': 'error', 'message': result.get('message', '视频生成失败')})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 步骤 2: 场景渲染
        scenes_count = result.get("scenes", 0)
        yield f"data: {json_mod.dumps({'type': 'progress', 'step': 2, 'total': 4, 'message': f'正在渲染 {scenes_count} 个场景...'})}\n\n"

        # 步骤 3: TTS 配音
        yield f"data: {json_mod.dumps({'type': 'progress', 'step': 3, 'total': 4, 'message': '正在生成配音...'})}\n\n"

        # 步骤 4: 完成
        yield f"data: {json_mod.dumps({'type': 'progress', 'step': 4, 'total': 4, 'message': '视频生成完成'})}\n\n"
        yield f"data: {json_mod.dumps({
            'type': 'complete',
            'html': result.get('html', ''),
            'scenes': result.get('scenes', 0),
            'duration_sec': result.get('duration_sec', 0),
            'duration_str': result.get('duration_str', ''),
            'video_script': result.get('video_script', ''),
        })}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_disconnect_guard(request, event_stream()), media_type="text/event-stream")


async def _generate_teaching_video(req) -> dict:
    """生成程序化教学视频（内部函数，供 generate 端点调用）"""
    from agents.media_generator import generate_teaching_video_package

    result = await generate_teaching_video_package(
        topic=req.topic,
        profile=(req.student_profile or req.profile or {}) if hasattr(req, 'student_profile') else (req.profile or {}),
        knowledge_context=getattr(req, 'knowledge_context', ''),
        difficulty=getattr(req, 'difficulty', 'medium'),
        output_format=getattr(req, 'output_format', 'html'),
    )

    return {
        "status": result.get("status", "ok"),
        "resource_type": "teaching_video",
        "topic": req.topic,
        "scenes": result.get("scenes", 0),
        "duration_sec": result.get("duration_sec", 0),
        "duration_str": result.get("duration_str", ""),
        "html": result.get("html", ""),
        "html_path": result.get("html_path", ""),
        "video_script": result.get("video_script", ""),
        "format": result.get("format", "html"),
    }


# ════════════════════════════════════════════════
# 新增资源类型（对标学境12种资源）
# ════════════════════════════════════════════════


async def _generate_study_notes(req) -> dict:
    """生成结构化学习笔记"""
    from prompts import STUDY_NOTES_AGENT_PROMPT
    llm = LLMProvider()
    profile = (req.student_profile or req.profile or {}) if hasattr(req, 'student_profile') else (req.profile or {})
    user_prompt = f"【学习主题】{req.topic}\n【难度】{getattr(req, 'difficulty', 'medium')}\n【学生画像】基础:{profile.get('knowledge_base','beginner')}\n请生成结构化学习笔记，包含：核心概念、关键公式/代码、典型例题、常见错误。"
    try:
        content = await llm.text_completion(STUDY_NOTES_AGENT_PROMPT, user_prompt, max_tokens=2500)
    except Exception as e:
        content = f"## {req.topic} 学习笔记\n\n### 核心概念\n\n### 关键要点\n\n### 例题"
    return {"resource_type": "study_notes", "topic": req.topic, "content": content, "format": "markdown"}


async def _generate_interactive_model(req) -> dict:
    """生成可交互模型（HTML/JS 代码片段）"""
    from prompts import INTERACTIVE_MODEL_AGENT_PROMPT
    llm = LLMProvider()
    user_prompt = f"【学习主题】{req.topic}\n请生成一个可交互的HTML教学模型，包含可视化交互控件，用于演示核心概念。"
    try:
        content = await llm.text_completion(INTERACTIVE_MODEL_AGENT_PROMPT, user_prompt, max_tokens=2000)
    except Exception as e:
        content = f"<div style='padding:20px;background:#1a1a2e;color:#fff;border-radius:8px;'><h3>{req.topic}</h3><p>可交互模型生成中...</p></div>"
    return {"resource_type": "interactive_model", "topic": req.topic, "html": content, "format": "html"}


async def _generate_video_recommend(req) -> dict:
    """推荐相关教学视频（B站/公开课等）"""
    llm = LLMProvider()
    profile = (req.student_profile or req.profile or {}) if hasattr(req, 'student_profile') else (req.profile or {})
    user_prompt = f"【学习主题】{req.topic}\n【学生基础】{profile.get('knowledge_base','beginner')}\n请推荐5个相关的教学视频资源，包含：标题、来源、时长、推荐理由、适合人群。"
    from prompts import VIDEO_RECOMMEND_AGENT_PROMPT
    try:
        content = await llm.text_completion(VIDEO_RECOMMEND_AGENT_PROMPT, user_prompt, max_tokens=1500)
    except Exception as e:
        content = f"## 推荐视频资源\n\n1. {req.topic} 精讲\n2. {req.topic} 实战\n\n（推荐基于当前学习进度）"
    return {"resource_type": "video_recommend", "topic": req.topic, "content": content, "format": "markdown"}


async def _generate_resource_pack(req) -> dict:
    """生成资源包（包含多种资源类型的合集）"""
    resource_types = ["ppt", "code", "mindmap", "study_notes"]
    results = {}
    for rt in resource_types:
        try:
            gen_req = type("GenReq", (), {"topic": req.topic, "student_profile": getattr(req, 'student_profile', None) or getattr(req, 'profile', None), "difficulty": getattr(req, 'difficulty', 'medium')})()
            if rt == "ppt":
                results[rt] = await _generate_ppt(gen_req)
            elif rt == "code":
                results[rt] = await _generate_code(gen_req)
            elif rt == "mindmap":
                results[rt] = await _generate_mindmap(gen_req)
            elif rt == "study_notes":
                results[rt] = await _generate_study_notes(gen_req)
        except Exception as e:
            results[rt] = {"error": str(e)}
    return {"resource_type": "resource_pack", "topic": req.topic, "resources": results, "count": len(resource_types)}
