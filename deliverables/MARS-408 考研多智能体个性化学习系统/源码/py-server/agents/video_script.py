# ============================================================
# 多模态视频脚本 Agent (Video Script Generator) — Lite 降级版
# 生成教学视频/动画的分镜脚本、旁白文案、配图建议
#
# Lite 版: 只生成文本脚本, 不实际渲染视频
# Full 版升级: 接入图像/动画生成工具 → 拼接配音 → 输出 MP4
#
# 作为 generator_cluster 的子 Agent 被调用。
# ============================================================

import logging
from typing import Optional

from db.llm_provider import LLMProvider
from engines.frugal_rag import format_retrieval_for_llm

logger = logging.getLogger("netlearn.video_script")


# ============================================================
# Prompt 模板
# ============================================================

VIDEO_SCRIPT_SYSTEM_PROMPT = """\
你是计算机408考研学习系统的「多模态视频Agent」。
你的任务是为学生生成一段教学视频的分镜脚本, 帮助通过视觉方式理解知识点。

你擅长将抽象的计算机概念转化为直观的视觉隐喻和动画场景。

## 输出要求
1. 视频时长 2-3 分钟 (约 6-8 个分镜)
2. 每个分镜包含:
   - 场景标题
   - 画面描述 (要画什么/展示什么)
   - 旁白文案 (口语化, 适合 TTS 配音)
   - 动画/动效说明 (元素如何移动/变化)
   - 时长 (秒)

## 输出格式
先输出 ---VIDEO_START--- 标记, 然后按以下格式输出:

---VIDEO_START---

## 分镜 1: [场景标题] (0:00-0:15)
**画面**: [详细描述画面内容]
**旁白**: [配音文案, 口语化]
**动画**: [元素运动说明]
**时长**: 15秒

## 分镜 2: ...

## 视频信息
- **总时长**: X分钟
- **风格**: [动画/实拍/混合]
- **配乐建议**: [轻快/严肃/科技感]
- **目标受众**: [学生画像对应的学习阶段]"""


# ============================================================
# 主入口函数
# ============================================================

async def generate_video_script(
    topic: str,
    profile: dict,
    knowledge_context: str,
    llm: LLMProvider,
    task_instruction: str = "",
    memory_context: str = "",
) -> str:
    """生成教学视频脚本 (Lite 版: 纯文本, 不渲染视频)

    Args:
        topic: 学习主题
        profile: 学生画像 (认知风格决定视频风格)
        knowledge_context: FrugalRAG 检索到的知识上下文
        llm: LLMProvider 实例
        task_instruction: planner 下发的任务指令 (可选)
        memory_context: L1/L2/L3 三层学情记忆上下文（可选，低侵入注入）

    Returns:
        视频脚本的 Markdown 文本
    """
    logger.info(f"[VideoScript] 开始生成, topic={topic}")

    user_prompt = _build_prompt(topic, profile, knowledge_context, task_instruction, memory_context)

    try:
        result = await llm.text_completion(
            VIDEO_SCRIPT_SYSTEM_PROMPT, user_prompt,
            temperature=0.6,  # 稍高温度增加创意
            max_tokens=2000,
        )
        logger.info(f"[VideoScript] 生成完成, 长度={len(result)}")
        return result

    except Exception as e:
        logger.error(f"[VideoScript] 生成失败: {e}")
        return f"## 视频脚本生成失败\n\n错误: {e}"


def _build_prompt(
    topic: str,
    profile: dict,
    knowledge_context: str,
    task_instruction: str,
    memory_context: str = "",
) -> str:
    """构建用户提示（含可选 L1/L2/L3 学情记忆上下文）"""
    parts = [
        f"【学习主题】{topic}",
        f"【任务指令】{task_instruction or '生成一段2-3分钟的教学视频脚本'}",
    ]

    # 学生画像 — 认知风格影响视频风格
    style = profile.get("learning_style", "reading")
    level = profile.get("knowledge_base", "beginner")
    weak = profile.get("weak_points", "")

    style_hint = {
        "visual": "请多用图解、动画、流程图等视觉元素",
        "auditory": "请注重旁白的讲解质量, 画面可以简洁",
        "hands-on": "请加入实操演示和交互环节",
        "reading": "请在画面中加入文字标注和知识点摘要",
    }.get(style, "请平衡视觉和听觉元素")

    parts.append(f"【学生画像】基础水平: {level}, 学习风格: {style}")
    parts.append(f"【风格要求】{style_hint}")
    if weak:
        parts.append(f"【薄弱点】{weak}（请在视频中重点讲解这些知识点）")

    # L1/L2/L3 三层学情记忆（低侵入注入：记忆薄弱点驱动视频讲解重点）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append(f"【历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_context[:500]}")

    if knowledge_context:
        parts.append(f"\n{knowledge_context}")

    parts.append("\n请先输出 ---VIDEO_START---，然后输出视频分镜脚本。")
    return "\n\n".join(parts)
