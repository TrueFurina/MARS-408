# ============================================================
# 学情诊断 Agent (Diagnostician)
# 构建学生画像上下文，交由 LLM 进行深度学情诊断
#
# 诚实说明（代码审查 2026-07-04）：
#   本节点本身不执行"分析"计算——它把 8 维度画像拼接为上下文提示词，
#   真正的诊断推理由 LLM 完成；本节点负责画像构建、LLM 调用与结果解析。
#   降级模式（LLM 不可用时）仅做基于画像字段的规则映射，不做推理。
# ============================================================

import json
import logging

from agents.state import AgentState
from db.llm_provider import LLMProvider
from prompts import DIAGNOSTICIAN_PROMPT

logger = logging.getLogger("netlearn.diagnostician")


async def diagnostician_node(state: AgentState) -> AgentState:
    """学情诊断 Agent：构建 8 维度画像上下文并交由 LLM 诊断薄弱点与聚焦方向"""
    state["status"] = "diagnosing"
    state["current_agent"] = "diagnostician"

    profile = state.get("student_profile", {})
    memory_context = state.get("memory_context") or ""

    # 构建用户提示 — 将8维度画像传给 LLM
    user_prompt = _build_diagnosis_prompt(profile, memory_context)

    try:
        llm = LLMProvider()
        response = await llm.text_completion(
            DIAGNOSTICIAN_PROMPT, user_prompt,
            temperature=0.3, max_tokens=800,
        )

        diagnosis = _parse_diagnosis(response, profile)
        state["diagnosis"] = diagnosis
        logger.info(f"Diagnostician LLM 诊断完成: level={diagnosis.get('level')}, "
                     f"weak_areas={diagnosis.get('weak_areas')}")

    except Exception as e:
        logger.warning(f"Diagnostician LLM 调用失败: {e}，降级为规则诊断")
        diagnosis = _fallback_diagnosis(profile)
        state["diagnosis"] = diagnosis

    return state


def _build_diagnosis_prompt(profile: dict, memory_context: str = "") -> str:
    """构建诊断提示词（含可选 L1/L2/L3 学情记忆上下文）"""
    parts = [
        f"【学生画像8维度】",
        f"1. 知识基础(knowledge_base): {profile.get('knowledge_base', 'beginner')}",
        f"2. 学习风格(learning_style): {profile.get('learning_style', 'reading')}",
        f"3. 学习目标(goal): {profile.get('goal', 'general')}",
        f"4. 薄弱知识点(weak_points): {profile.get('weak_points', '未指定')}",
        f"5. 学习进度(progress): 第{profile.get('progress', 0)}章",
        f"6. 专注方向(interest_area): {profile.get('interest_area', 'general')}",
        f"7. 每日学习时间(study_time): {profile.get('study_time', '1-2h')}",
        f"8. 难度偏好(preferred_difficulty): {profile.get('preferred_difficulty', 'medium')}",
        "",
    ]
    # L1/L2/L3 三层学情记忆（低侵入注入：memory_service.build_memory_context 组装）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append("【历史学情记忆（L1会话上下文/L2长期画像/L3情景事件）】")
        parts.append(memory_context)
        parts.append("")
        parts.append("请根据以上画像与历史学情记忆进行深度诊断分析。")
    else:
        parts.append("请根据以上画像进行深度诊断分析。")
    return "\n".join(parts)


def _parse_diagnosis(text: str, profile: dict) -> dict:
    """解析 LLM 诊断输出（JSON格式）"""
    # 尝试提取 JSON
    try:
        # 找到 JSON 起始和结束
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_str = text[start:end + 1]
            data = json.loads(json_str)
            # 确保必要字段存在
            data.setdefault("level", profile.get("knowledge_base", "beginner"))
            data.setdefault("style", profile.get("learning_style", "reading"))
            data.setdefault("goal", profile.get("goal", "general"))
            data.setdefault("weak_areas", [])
            data.setdefault("progress", profile.get("progress", 0))
            data.setdefault("study_time", profile.get("study_time", "1-2h"))
            data.setdefault("recommended_depth", "基础")
            data.setdefault("recommended_format", "结构化文档")
            data.setdefault("attention_flags", profile.get("interest_area", "general"))
            data.setdefault("time_budget", "标准版")
            return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"诊断 JSON 解析失败: {e}")

    return _fallback_diagnosis(profile)


def _fallback_diagnosis(profile: dict) -> dict:
    """降级：规则诊断（LLM不可用时使用）"""
    weak_areas = []
    weak_points = profile.get("weak_points", "")
    if weak_points:
        weak_areas = [w.strip() for w in weak_points.split(",") if w.strip()]

    return {
        "level": profile.get("knowledge_base", "beginner"),
        "style": profile.get("learning_style", "reading"),
        "goal": profile.get("goal", "general"),
        "weak_areas": weak_areas,
        "weak_root_cause": "（降级模式：未调用 LLM，无法归因；以下基于画像字段规则映射）",
        "gap_analysis": f"当前进度第{profile.get('progress', 0)}章，目标{profile.get('goal', 'general')}",
        "recommended_focus": weak_areas[:3] if weak_areas else ["基础概念"],
        "learning_strategy": "建议从薄弱点入手，结合学习风格选择资源类型",
        "time_assessment": profile.get("study_time", "1-2h") + " 可用",
        "recommended_depth": "基础" if profile.get("knowledge_base") in ("none", "beginner") else "进阶",
        "recommended_format": {
            "visual": "思维导图 + 动画",
            "reading": "结构化文档 + 表格",
            "hands-on": "代码实操 + 练习题",
            "auditory": "逐步讲解 + 案例",
        }.get(profile.get("learning_style", "reading"), "结构化文档"),
        "attention_flags": profile.get("interest_area", "general"),
        "time_budget": {"0-1h": "精简版", "1-2h": "标准版", "2-4h": "深度版", "4h+": "全面版"}.get(
            profile.get("study_time", "1-2h"), "标准版"
        ),
        "progress": profile.get("progress", 0),
        "study_time": profile.get("study_time", "1-2h"),
    }
