# ============================================================
# 路径规划 Agent (PathPlanner)
# 调用 LLM 基于画像和学习效果评估，动态调整个性化学习路径
# ============================================================

import json
import logging

from agents.state import AgentState
from db.llm_provider import LLMProvider
from prompts import PATH_PLANNER_PROMPT
from agents.kg_dag import (
    topological_sort,
    SUBJECT_KEYWORD_MAP,
    SUBJECT_GROUP_SPAN,
)

logger = logging.getLogger("netlearn.path_planner")

# 科名 → 弱项起点 group（与 SUBJECT_GROUP_SPAN 同键，单一真源见 kg_dag.py 设计硬约束）。
# 注意：SUBJECT_GROUP_MAP 仅含短 key（co/ds/os…），不可用其查完整科名，否则兜回 start=1（网络组）。
COURSE_START_GROUP = {
    "computer_network": 1,
    "data_structures": 8,
    "computer_organization": 15,
    "operating_system": 22,
}


async def path_planner_node(state: AgentState) -> AgentState:
    """路径规划 Agent：调用 LLM 基于画像和评估结果，动态调整学习路径"""
    state["status"] = "path_planning"
    state["current_agent"] = "path_planner"

    profile = state.get("student_profile", {})
    diagnosis = state.get("diagnosis", {})
    consensus = state.get("consensus", {})
    critic_report = state.get("critic_report", "")
    memory_context = state.get("memory_context") or ""

    # 从思维导图 Agent 提取薄弱知识点 (mindmap → path_planner 闭环)
    mindmap_data = state.get("mindmap") or {}
    mindmap_weak_points = mindmap_data.get("weak_points", []) if isinstance(mindmap_data, dict) else []

    # 构建 LLM 路径规划提示
    user_prompt = _build_path_prompt(profile, diagnosis, consensus, critic_report, mindmap_weak_points, memory_context)

    try:
        llm = LLMProvider()
        response = await llm.text_completion(
            PATH_PLANNER_PROMPT, user_prompt,
            temperature=0.5, max_tokens=800,
        )

        path_plan = _parse_path_plan(response, profile, diagnosis)
        state["path_plan"] = path_plan
        logger.info(f"PathPlanner LLM 规划完成: path_type={path_plan.get('path_type')}")

    except Exception as e:
        logger.warning(f"PathPlanner LLM 调用失败: {e}，降级为规则规划")
        state["path_plan"] = _fallback_path_plan(profile, diagnosis, mindmap_weak_points)

    # ── INC-05 / T06：KG-DAG 拓扑路径（与 LLM/规则路径合并，不覆盖既有字段）──
    _enrich_with_kg_dag(state, profile, diagnosis, mindmap_weak_points)

    return state


def _derive_weak_groups(profile: dict, diagnosis: dict, mindmap_weak_points: list) -> list[int]:
    """从画像/诊断/导图薄弱点推导弱项 group 集合（最佳努力，解析失败不影响主流程）"""
    texts = []
    if isinstance(profile, dict):
        texts.append(str(profile.get("weak_points", "")))
        texts.append(str(profile.get("goal", "")))
    if isinstance(diagnosis, dict):
        weak_areas = diagnosis.get("weak_areas", []) or []
        texts.append(" ".join(weak_areas) if isinstance(weak_areas, list) else str(weak_areas))
    if mindmap_weak_points:
        texts.append(" ".join(mindmap_weak_points) if isinstance(mindmap_weak_points, list) else str(mindmap_weak_points))
    blob = " ".join(texts)

    weak: set[int] = set()
    for kw, subject in SUBJECT_KEYWORD_MAP.items():
        if kw in blob:
            start = COURSE_START_GROUP.get(subject, 1)
            span = SUBJECT_GROUP_SPAN.get(subject, 7)
            weak.update(range(start, start + span))
    return sorted(weak)


def _enrich_with_kg_dag(state: AgentState, profile: dict, diagnosis: dict, mindmap_weak_points: list):
    """基于 408 四科知识图谱 DAG 生成拓扑有序的章节序列，写入 path_plan.kg_ordered_chapters。

    画像弱项 group 置顶；LLM/规则路径字段保持不变（KG 路径作为增强/兜底，无 RL）。
    """
    try:
        weak_groups = _derive_weak_groups(profile, diagnosis, mindmap_weak_points)
        ordered = topological_sort(weak_groups, profile)
        if isinstance(state.get("path_plan"), dict):
            state["path_plan"]["kg_ordered_chapters"] = ordered
            state["path_plan"]["kg_weak_groups"] = weak_groups
            logger.info(f"PathPlanner KG-DAG 路径生成: {len(ordered)} 个 group，弱项 {weak_groups}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"KG-DAG 路径增强失败，跳过: {e}")


def _build_path_prompt(
    profile: dict,
    diagnosis: dict,
    consensus: dict,
    critic_report: str,
    mindmap_weak_points: list = None,
    memory_context: str = "",
) -> str:
    """构建路径规划提示词（含可选 L1/L2/L3 学情记忆上下文）"""
    parts = [
        f"【学生画像】",
        f"- 知识基础: {profile.get('knowledge_base', 'beginner')}",
        f"- 学习风格: {profile.get('learning_style', 'reading')}",
        f"- 学习目标: {profile.get('goal', 'general')}",
        f"- 薄弱点: {profile.get('weak_points', '未指定')}",
        f"- 学习进度: 第{profile.get('progress', 0)}章",
        f"- 每日学习时间: {profile.get('study_time', '1-2h')}",
        f"- 难度偏好: {profile.get('preferred_difficulty', 'medium')}",
        "",
        f"【诊断报告】",
        f"- 推荐聚焦: {diagnosis.get('recommended_focus', '未指定')}",
        f"- 学习策略: {diagnosis.get('learning_strategy', '未指定')}",
        f"- 推荐深度: {diagnosis.get('recommended_depth', '基础')}",
        f"- 时间评估: {diagnosis.get('time_assessment', '未指定')}",
        "",
        f"【学习效果评估】",
        f"- 共识状态: {consensus.get('status', 'done')}",
        f"- 综合评分: {consensus.get('overall_score', 'N/A')}",
    ]

    # L1/L2/L3 三层学情记忆（低侵入注入：memory_service.build_memory_context 组装）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append("")
        parts.append("【历史学情记忆（L1会话/L2长期画像/L3情景事件）】")
        parts.append(memory_context)

    # 思维导图 Agent 产出的薄弱知识点 (关键闭环数据)
    if mindmap_weak_points:
        parts.append("")
        parts.append(f"【思维导图知识点掌握度分析】")
        parts.append(f"- 薄弱/未学知识点: {', '.join(mindmap_weak_points[:10])}")
        parts.append(f"- (请在学习路径中优先安排这些知识点的学习)")

    if critic_report:
        # 截取审阅报告前300字符
        parts.append(f"\n【审阅报告摘要】\n{critic_report[:300]}")

    parts.append("\n请根据以上信息，为该学生规划接下来的7章学习路径（含每章学习模式和推荐资源）。")
    return "\n".join(parts)


def _parse_path_plan(text: str, profile: dict, diagnosis: dict) -> dict:
    """解析 LLM 路径规划输出"""
    # PathPlanner 的输出格式是一行 JSON 数组
    try:
        # 尝试提取 JSON 数组
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            json_str = text[start:end + 1]
            chapter_plan = json.loads(json_str)

            if isinstance(chapter_plan, list) and len(chapter_plan) > 0:
                goal = profile.get("goal", "general")
                path_type_map = {
                    "exam": "考试冲刺路径",
                    "practical": "实践技能路径",
                    "theory": "理论深化路径",
                    "general": "综合学习路径",
                }

                return {
                    "current_chapter": profile.get("progress", 0),
                    "next_chapter": min(profile.get("progress", 0) + 1, 7),
                    "recommended_duration": {"0-1h": "15min/节", "1-2h": "30min/节", "2-4h": "45min/节", "4h+": "60min/节"}.get(
                        profile.get("study_time", "1-2h"), "30min/节"
                    ),
                    "difficulty_tier": profile.get("preferred_difficulty", "medium"),
                    "weak_focus_chapters": diagnosis.get("weak_areas", [])[:3],
                    "goal_aligned_path": [ch.get("chapter", "") for ch in chapter_plan[:4]],
                    "path_type": path_type_map.get(goal, "综合学习路径"),
                    "chapter_plan": chapter_plan,
                    "planning_source": "llm",
                }
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"路径规划 JSON 解析失败: {e}")

    return _fallback_path_plan(profile, diagnosis)


def _fallback_path_plan(profile: dict, diagnosis: dict, mindmap_weak_points: list = None) -> dict:
    """降级：规则路径规划"""
    progress = profile.get("progress", 0)
    study_time = profile.get("study_time", "1-2h")
    preferred_diff = profile.get("preferred_difficulty", "medium")
    weak_points = profile.get("weak_points", "")
    goal = profile.get("goal", "general")
    interest_area = profile.get("interest_area", "general")

    path_plan = {
        "current_chapter": progress,
        "next_chapter": min(progress + 1, 7),
        "recommended_duration": {"0-1h": "15min/节", "1-2h": "30min/节", "2-4h": "45min/节", "4h+": "60min/节"}.get(study_time, "30min/节"),
        "difficulty_tier": preferred_diff,
        "weak_focus_chapters": [],
        "goal_aligned_path": [],
        "planning_source": "rule",
    }

    # 合并画像薄弱点 + 思维导图分析出的薄弱知识点
    all_weak = []
    if weak_points:
        all_weak.extend([w.strip() for w in weak_points.split(",") if w.strip()])
    if mindmap_weak_points:
        # 去重，优先放思维导图分析的薄弱点
        for wp in mindmap_weak_points:
            if wp not in all_weak:
                all_weak.append(wp)
    path_plan["weak_focus_chapters"] = all_weak[:5]

    if goal == "exam":
        path_plan["goal_aligned_path"] = ["网络层与传输层（高频考点）", "数据链路层与物理层（基础题）", "应用层协议（常考）"]
        path_plan["path_type"] = "考试冲刺路径"
    elif goal == "practical":
        path_plan["goal_aligned_path"] = ["网络层协议分析（IP/路由）", "传输层实践（TCP/UDP抓包）", "应用层实操（HTTP/DNS/SMTP）"]
        path_plan["path_type"] = "实践技能路径"
    elif goal == "theory":
        path_plan["goal_aligned_path"] = ["计算机网络体系结构（OSI/TCP-IP）", "数据链路层算法（CSMA/CD/CA）", "网络层核心算法（路由/拥塞控制）"]
        path_plan["path_type"] = "理论深化路径"
    else:
        path_plan["goal_aligned_path"] = ["计算机网络概述（体系结构/性能指标）", "物理层与数据链路层", "网络层与传输层"]
        path_plan["path_type"] = "综合学习路径"

    if interest_area == "security":
        path_plan["emphasis"] = "网络安全章节重点加强"
    elif interest_area == "programming":
        path_plan["emphasis"] = "代码实操和协议实现"
    elif interest_area == "protocol":
        path_plan["emphasis"] = "协议原理与对比分析"

    return path_plan
