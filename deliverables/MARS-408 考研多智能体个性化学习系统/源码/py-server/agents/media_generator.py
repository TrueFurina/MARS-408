# ============================================================
# 多模态媒体生成 Agent — 增强版
# 赛题要求：多模态教学资源（视频/动画/图解/信息图）
# 生成内容：分镜脚本 + SVG 示意图 + Mermaid 图 + 信息图设计
# ============================================================

import logging
import re
from typing import Optional

from db.llm_provider import LLMProvider

logger = logging.getLogger("netlearn.media_generator")


# ── 视频脚本生成（增强版，含多模态融合） ──

VIDEO_SCRIPT_ENHANCED_PROMPT = """\
你是计算机考研学习系统的「多模态视频制作Agent」。
你的任务是为学生生成一段完整的教学视频/动画制作方案，包含分镜脚本、视觉设计、动画效果说明。

## 核心要求
1. 视频时长 3-5 分钟，覆盖知识点的完整讲解
2. 每个分镜包含：画面描述、旁白文案、动画效果、配图建议
3. 输出格式必须严格遵循以下模板

## 输出格式
---VIDEO_START---
## 分镜 1: [场景标题] (0:00-0:XX)
**画面**: [详细视觉描述，含颜色、布局、元素位置]
**旁白**: [口语化配音文案，适合 TTS]
**动画**: [元素进出/移动/变化效果描述]
**配图**: [建议配图类型：流程图/对比图/示意图]
**时长**: XX秒

## 分镜 2: ...
---VIDEO_END---
## 视频信息
- **总时长**: X分钟
- **视觉风格**: [科技感/卡通/写实/混合]
- **配乐建议**: [轻快/严肃/科技感]
- **关键视觉元素**: [需要用到的核心视觉隐喻]
"""


async def generate_enhanced_video_script(
    topic: str,
    profile: Optional[dict] = None,
    knowledge_context: str = "",
    difficulty: str = "medium",
    memory_context: str = "",
) -> str:
    """生成增强版视频脚本（含多模态融合设计，可选注入三层学情记忆）"""
    llm = LLMProvider()

    style = (profile or {}).get("learning_style", "visual")
    level = (profile or {}).get("knowledge_base", "beginner")
    weak = (profile or {}).get("weak_points", "")

    style_hint = {
        "visual": "多用图解、动画、流程图等视觉元素，画面丰富",
        "auditory": "注重旁白讲解质量，画面简洁清晰",
        "hands-on": "加入实操演示和交互环节",
        "reading": "画面中加入文字标注和知识点摘要",
    }.get(style, "平衡视觉和听觉元素")

    user_prompt = (
        f"【学习主题】{topic}\n"
        f"【难度】{difficulty}\n"
        f"【学生画像】基础水平: {level}, 学习风格: {style}\n"
        f"【风格要求】{style_hint}\n"
    )
    if weak:
        user_prompt += f"【薄弱点】{weak}（重点讲解）\n"
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        user_prompt += f"【历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_context[:500]}\n"
    if knowledge_context:
        user_prompt += f"\n【知识参考】\n{knowledge_context[:2000]}\n"

    try:
        result = await llm.text_completion(
            VIDEO_SCRIPT_ENHANCED_PROMPT, user_prompt,
            temperature=0.7, max_tokens=2500,
        )
        return result
    except Exception as e:
        logger.error(f"视频脚本生成失败: {e}")
        return _fallback_video_script(topic)


def _fallback_video_script(topic: str) -> str:
    """降级视频脚本"""
    return (
        f"---VIDEO_START---\n"
        f"## 分镜 1: 开场引入 (0:00-0:30)\n"
        f"**画面**: 标题动画，显示「{topic}」\n"
        f"**旁白**: 大家好，今天我们来学习{topic}\n"
        f"**动画**: 标题渐入，背景科技感粒子效果\n"
        f"**配图**: 标题卡片\n"
        f"**时长**: 30秒\n\n"
        f"## 分镜 2: 核心概念讲解 (0:30-2:30)\n"
        f"**画面**: 核心概念图解，分步展示\n"
        f"**旁白**: 详细讲解核心概念和原理\n"
        f"**动画**: 逐步绘制图示，关键元素高亮\n"
        f"**配图**: 流程图/结构图\n"
        f"**时长**: 120秒\n\n"
        f"## 分镜 3: 案例演示 (2:30-4:00)\n"
        f"**画面**: 具体案例演示，代码/数据展示\n"
        f"**旁白**: 通过案例加深理解\n"
        f"**动画**: 代码逐行高亮，数据动态变化\n"
        f"**配图**: 代码截图/数据图表\n"
        f"**时长**: 90秒\n\n"
        f"## 分镜 4: 总结回顾 (4:00-5:00)\n"
        f"**画面**: 知识点回顾卡片+思维导图\n"
        f"**旁白**: 总结今天学到的核心内容\n"
        f"**动画**: 思维导图逐层展开\n"
        f"**配图**: 思维导图\n"
        f"**时长**: 60秒\n"
        f"---VIDEO_END---\n"
        f"## 视频信息\n"
        f"- **总时长**: 5分钟\n"
        f"- **视觉风格**: 科技感\n"
        f"- **配乐建议**: 轻快\n"
        f"- **关键视觉元素**: 流程图、思维导图\n"
    )


# ── SVG 教学示意图生成 ──

SVG_DIAGRAM_PROMPT = """\
你是一个计算机教学SVG图解生成器。请为指定知识点生成一个教学示意图的SVG代码。

## 要求
1. 输出纯SVG代码（不含HTML包裹）
2. 尺寸: 800x600
3. 配色: 科技蓝(#3b82f6) + 紫色(#8b5cf6) + 白色文字
4. 包含: 标题、核心结构/流程、标注说明
5. 适合直接嵌入网页展示

## 输出格式
```svg
<svg ...>
...
</svg>
```
"""


async def generate_teaching_diagram(topic: str, knowledge_context: str = "") -> str:
    """生成教学示意图 SVG"""
    llm = LLMProvider()
    user_prompt = f"【知识点】{topic}\n\n请生成一个教学示意图SVG，展示{topic}的核心概念和结构。"
    if knowledge_context:
        user_prompt += f"\n\n【参考】\n{knowledge_context[:1000]}"

    try:
        result = await llm.text_completion(SVG_DIAGRAM_PROMPT, user_prompt, temperature=0.5, max_tokens=2000)
        svg = _extract_svg(result)
        return svg
    except Exception as e:
        logger.warning(f"SVG生成失败: {e}")
        return _fallback_svg(topic)


def _extract_svg(text: str) -> str:
    """从 LLM 输出中提取 SVG 代码"""
    match = re.search(r'```svg\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r'(<svg[\s\S]*?</svg>)', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _fallback_svg(topic: str) -> str:
    """降级 SVG"""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" width="800" height="600">
  <rect width="800" height="600" fill="#0f0f1a" rx="12"/>
  <text x="400" y="60" text-anchor="middle" fill="#f8fafc" font-size="24" font-weight="bold">{topic}</text>
  <rect x="50" y="100" width="700" height="400" fill="rgba(255,255,255,0.03)" rx="8" stroke="rgba(255,255,255,0.1)"/>
  <text x="400" y="300" text-anchor="middle" fill="#94a3b8" font-size="16">教学示意图生成中...</text>
</svg>'''


# ── Mermaid 图生成 ──

MERMAID_DIAGRAM_PROMPT = """\
你是一个Mermaid图表生成器。请为指定知识点生成Mermaid格式的图表。

## 支持的图表类型
- flowchart: 流程图/结构图
- mindmap: 思维导图
- sequenceDiagram: 时序图
- classDiagram: 类图
- graph: 关系图

## 输出格式
先输出图表类型，再输出Mermaid代码。
```mermaid
...
```
"""


async def generate_mermaid_diagram(topic: str, diagram_type: str = "flowchart") -> str:
    """生成Mermaid教学图表"""
    llm = LLMProvider()
    user_prompt = (
        f"【知识点】{topic}\n"
        f"【图表类型】{diagram_type}\n\n"
        f"请生成一个{diagram_type}类型的Mermaid图表，展示{topic}的核心结构。"
    )

    try:
        result = await llm.text_completion(MERMAID_DIAGRAM_PROMPT, user_prompt, temperature=0.5, max_tokens=1500)
        mermaid = _extract_mermaid(result)
        return mermaid
    except Exception as e:
        logger.warning(f"Mermaid生成失败: {e}")
        return ""


def _extract_mermaid(text: str) -> str:
    """从 LLM 输出中提取 Mermaid 代码"""
    match = re.search(r'```mermaid\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


# ── 统一多模态资源生成 ──


async def generate_full_media_package(
    topic: str,
    profile: Optional[dict] = None,
    knowledge_context: str = "",
    difficulty: str = "medium",
) -> dict:
    """生成完整多模态媒体包（视频脚本+SVG+Mermaid+信息图）"""
    from agents.mindmap import generate_mindmap
    from agents.video_script import generate_video_script
    from schemas.mindmap import MindMapRequest

    # 并行生成各媒体类型
    import asyncio

    async def _gen_video():
        return await generate_enhanced_video_script(topic, profile, knowledge_context, difficulty)

    async def _gen_diagram():
        return await generate_teaching_diagram(topic, knowledge_context)

    async def _gen_mermaid():
        return await generate_mermaid_diagram(topic, "flowchart")

    async def _gen_mindmap():
        mm_req = MindMapRequest(
            topic=topic,
            subject=profile.get("subject", "computer_network") if profile else "computer_network",
            profile=profile or {},
        )
        try:
            mm = await generate_mindmap(mm_req)
            return mm.to_dict() if mm else None
        except Exception:
            return None

    results = await asyncio.gather(
        _gen_video(), _gen_diagram(), _gen_mermaid(), _gen_mindmap(),
        return_exceptions=True,
    )

    video_script = results[0] if not isinstance(results[0], Exception) else ""
    svg_diagram = results[1] if not isinstance(results[1], Exception) else ""
    mermaid_code = results[2] if not isinstance(results[2], Exception) else ""
    mindmap_data = results[3] if not isinstance(results[3], Exception) else None

    return {
        "topic": topic,
        "video_script": video_script,
        "svg_diagram": svg_diagram,
        "mermaid_code": mermaid_code,
        "mindmap": mindmap_data,
        "media_types": ["video_script", "svg_diagram", "mermaid", "mindmap"],
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }


# ── 视频合成（不依赖昂贵 API，程序化生成教学视频） ──


async def generate_teaching_video_package(
    topic: str,
    profile: Optional[dict] = None,
    knowledge_context: str = "",
    difficulty: str = "medium",
    output_format: str = "html",
) -> dict:
    """生成完整教学视频包（脚本 + SVG 场景 + HTML 幻灯片）

    工作流：
    1. 生成增强版视频脚本（含分镜）
    2. 解析脚本 → 结构化场景列表
    3. 为每个场景生成 SVG 图解
    4. 组装为 HTML 幻灯片（可播放/可录屏）
    5. 可选：FFmpeg 合成 MP4

    Args:
        topic: 学习主题
        profile: 学生画像
        knowledge_context: 知识上下文
        difficulty: 难度
        output_format: "html" | "mp4" | "both"

    Returns:
        {"status", "video_script", "scenes", "duration", "html_path", "html"}
    """
    # 1. 生成视频脚本
    script = await generate_enhanced_video_script(topic, profile, knowledge_context, difficulty)

    # 2. 调用视频合成服务
    from services.video_generator import generate_teaching_video

    result = generate_teaching_video(
        topic=topic,
        video_script=script,
        output_format=output_format,
    )

    result["video_script"] = script
    result["generated_at"] = __import__("datetime").datetime.now().isoformat()
    return result


# ── 真实数字人视频生成（P1-5②，调讯飞 generate_video）──


async def generate_real_video(topic: str, script: str, profile: Optional[dict] = None) -> dict:
    """调讯飞数字人视频大模型生成真实视频。

    成功返回 {ok:True, video_url, audio_url, task_id}；
    失败/无凭证返回 {ok:False, fallback:"script", script}（降级为脚本，不抛异常）。

    Args:
        topic: 学习主题
        script: 视频脚本文本（分镜脚本）
        profile: 学生画像（可选）

    Returns:
        包含 ok/video_url/audio_url/task_id 或 fallback/script 的 dict。
    """
    try:
        from db.xfyun_services import generate_video, has_credentials

        if not has_credentials():
            logger.info("[generate_real_video] 讯飞凭证未配置，降级为脚本")
            return _fallback_script(script)

        # 从脚本中提取用于视频生成的 prompt（截断至讯飞限制）
        prompt = script[:2000] if script else topic

        # 读取 word_count 配置
        try:
            from config import load_config
            word_count = load_config().get("video_generation", {}).get("word_count", 120)
        except Exception:
            word_count = 120

        result = await generate_video(prompt=prompt, word_count=word_count)

        if result.success and result.video_url:
            logger.info(f"[generate_real_video] 视频生成成功: {result.video_url[:80]}...")
            return {
                "ok": True,
                "video_url": result.video_url,
                "audio_url": result.audio_url or "",
                "task_id": result.task_id,
                "text": result.text,
            }
        else:
            logger.warning(f"[generate_real_video] 视频生成失败，降级为脚本: {result.error}")
            return _fallback_script(script, error=result.error)

    except Exception as e:
        logger.error(f"[generate_real_video] 异常，降级为脚本: {e}")
        return _fallback_script(script, error=str(e))


def _fallback_script(script: str, error: str = "") -> dict:
    """降级返回：视频生成失败时返回脚本文本，不中断主流程。"""
    return {
        "ok": False,
        "fallback": "script",
        "script": script,
        "error": error or "视频生成不可用，已降级为脚本",
    }