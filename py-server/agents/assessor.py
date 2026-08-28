# ============================================================
# 评估反馈 Agent (Assessor)
# 调用 LLM 对生成资源进行多维度质量评估
# 为 Critic 和 GOMARL 共识提供前置评分
# ============================================================

import json
import logging

from agents.state import AgentState
from db.llm_provider import LLMProvider
from prompts import ASSESSOR_PROMPT

logger = logging.getLogger("netlearn.assessor")


async def assessor_node(state: AgentState) -> AgentState:
    """评估反馈 Agent：调用 LLM 对生成资源做多维度质量评估 + 学习效果预估"""
    state["status"] = "assessing"
    state["current_agent"] = "assessor"

    profile = state.get("student_profile", {})
    diagnosis = state.get("diagnosis", {})
    consensus = state.get("consensus", {})
    memory_context = state.get("memory_context") or ""

    # 收集所有已生成资源的摘要（7种资源全覆盖）
    resource_summaries = _collect_resource_summaries(state)

    # 构建评估提示
    user_prompt = _build_assessment_prompt(profile, diagnosis, consensus, resource_summaries, memory_context)

    try:
        llm = LLMProvider()
        response = await llm.text_completion(
            ASSESSOR_PROMPT, user_prompt,
            temperature=0.3, max_tokens=600,
        )

        assessment = _parse_assessment(response, profile, diagnosis)

    except Exception as e:
        logger.warning(f"Assessor LLM 调用失败: {e}，降级为规则评估")
        assessment = _fallback_assessment(profile, diagnosis)

    # 将评估结果写入共识预备字段
    if consensus is None:
        state["consensus"] = {}
    state["consensus"]["pre_assessment"] = assessment

    return state


def _collect_resource_summaries(state: dict) -> str:
    """收集所有已生成资源的摘要文本（7种资源全覆盖）"""
    parts = []

    teacher_doc = state.get("teacher_doc", "")
    if teacher_doc:
        parts.append(f"### 讲解文档\n{teacher_doc[:400]}")

    quiz = state.get("quiz", "")
    if quiz:
        parts.append(f"### 练习题\n{quiz[:300]}")

    extension = state.get("extension", "")
    if extension:
        parts.append(f"### 拓展阅读\n{extension[:300]}")

    code_practice = state.get("code_practice", "")
    if code_practice:
        parts.append(f"### 代码实操\n{code_practice[:400]}")

    ppt_outline = state.get("ppt_outline", "")
    if ppt_outline:
        parts.append(f"### PPT大纲\n{ppt_outline[:300]}")

    video_script = state.get("video_script", "")
    if video_script:
        parts.append(f"### 视频脚本\n{video_script[:300]}")

    mindmap_data = state.get("mindmap")
    if mindmap_data and isinstance(mindmap_data, dict):
        stats = mindmap_data.get("stats", {})
        weak_points = mindmap_data.get("weak_points", [])
        parts.append(
            f"### 思维导图\n知识点总数: {stats.get('total', 0)}, "
            f"已掌握: {stats.get('mastered', 0)}, "
            f"薄弱: {stats.get('weak', 0)}, "
            f"未学: {stats.get('unlearned', 0)}\n"
            f"薄弱知识点: {', '.join(weak_points[:5]) if weak_points else '无'}"
        )

    return "\n\n".join(parts) if parts else "（资源尚未生成）"


def _build_assessment_prompt(profile: dict, diagnosis: dict, consensus: dict, resource_summaries: str = "", memory_context: str = "") -> str:
    """构建评估提示词（含可选 L1/L2/L3 学情记忆上下文）"""
    parts = [
        "【学生画像】",
        f"- 知识基础: {profile.get('knowledge_base', 'beginner')}",
        f"- 学习风格: {profile.get('learning_style', 'reading')}",
        f"- 学习目标: {profile.get('goal', 'general')}",
        f"- 薄弱点: {profile.get('weak_points', '未指定')}",
        f"- 学习时间: {profile.get('study_time', '1-2h')}",
        f"- 难度偏好: {profile.get('preferred_difficulty', 'medium')}",
        "",
        "【诊断报告】",
        f"- 推荐聚焦: {diagnosis.get('recommended_focus', '未指定')}",
        f"- 学习策略: {diagnosis.get('learning_strategy', '未指定')}",
        f"- 推荐深度: {diagnosis.get('recommended_depth', '基础')}",
        "",
        "【共识结果概要】",
        f"- 共识状态: {consensus.get('status', 'pending')}",
        f"- 综合评分: {consensus.get('overall_score', 'N/A')}",
        f"- 标记问题: {consensus.get('flagged_issues', [])}",
    ]

    # L1/L2/L3 三层学情记忆（低侵入注入：memory_service.build_memory_context 组装）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append("")
        parts.append("【历史学情记忆（L1会话/L2长期画像/L3情景事件）】")
        parts.append(memory_context)

    # 附带所有已生成资源的摘要
    if resource_summaries and resource_summaries != "（资源尚未生成）":
        parts.append(f"\n【已生成资源摘要（7种资源）】\n{resource_summaries}")
    else:
        # 降级：从 consensus.merged_content 取
        merged = consensus.get("merged_content", "")
        if merged:
            parts.append(f"\n【生成内容摘要】\n{merged[:500]}")

    parts.append("\n请对以上资源进行6维度质量评估。")
    return "\n".join(parts)


def _parse_assessment(text: str, profile: dict, diagnosis: dict) -> dict:
    """解析 LLM 评估输出（JSON格式）"""
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_str = text[start:end + 1]
            data = json.loads(json_str)

            # 确保必要字段
            data.setdefault("pre_score", 7.0)
            data.setdefault("level_match", True)
            data.setdefault("style_match", True)
            data.setdefault("time_feasible", True)
            data.setdefault("estimated_study_minutes", 60)
            data.setdefault("weak_focus", False)
            data.setdefault("difficulty_alignment", profile.get("preferred_difficulty", "medium"))
            data.setdefault("improvement_suggestions", "")

            # 标记评估来源
            data["assessment_source"] = "llm"
            return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"评估 JSON 解析失败: {e}")

    return _fallback_assessment(profile, diagnosis)


def _fallback_assessment(profile: dict, diagnosis: dict) -> dict:
    """降级：规则评估（诚实标注：非LLM评估，仅供参考）"""
    level = profile.get("knowledge_base", "beginner")
    study_time = profile.get("study_time", "1-2h")
    preferred_diff = profile.get("preferred_difficulty", "medium")

    # 仅基于画像字段做基础推断，不编造具体分数
    weak_areas = diagnosis.get("weak_areas", [])
    level_match = not (level in ("none", "beginner") and preferred_diff == "hard")

    return {
        # 降级模式不编造分数，标记为规则推断
        "accuracy": None,
        "difficulty_match": None,
        "style_match": None,
        "completeness": None,
        "practicality": None,
        "time_feasible": None,
        "pre_score": None,
        "level_match": level_match,
        "style_match": True,
        "time_feasible": True,
        "difficulty_alignment": preferred_diff,
        "estimated_study_minutes": {"0-1h": 30, "1-2h": 60, "2-4h": 120, "4h+": 180}.get(study_time, 60),
        "weak_focus": bool(weak_areas),
        "improvement_suggestions": "【规则降级】LLM评估不可用，以上分数字段为None（非真实评估值）。建议启用LLM后重新评估。",
        "assessment_source": "rule_fallback_incomplete",
    }
