# ============================================================
# 学习效果评估反馈 Agent (Feedback Agent)
# 赛题加分项⑤：学习效果评估闭环
# 功能：评估学习效果 → 生成评估报告 → 反馈调整路径
# ============================================================

import logging
import json
from typing import Optional

from db.llm_provider import LLMProvider

logger = logging.getLogger("netlearn.feedback_agent")


# ── 评估 Prompt ──

FEEDBACK_EVALUATE_PROMPT = """\
你是计算机408考研学习系统的「学习效果评估Agent」。
你的任务是根据学生的学习数据，进行多维度学习效果评估，并生成结构化的评估报告和调整建议。

## 评估维度
1. **知识点掌握度**：各章节/知识点的掌握程度（0-100）
2. **薄弱环节**：掌握度低于60%的知识点，标注优先级
3. **学习进度**：当前进度 vs 目标进度，评估是否落后
4. **学习效率**：单位时间内的掌握度提升速度
5. **趋势分析**：最近7天的掌握度变化趋势（上升/稳定/下降）

## 输出格式
必须输出JSON格式，严格按照以下结构：
```json
{
  "mastery_by_topic": {
    "topic_name": {"score": 0-100, "level": "mastered|weak|unlearned", "trend": "up|stable|down"}
  },
  "weak_points": [{"topic": "知识点名", "priority": "high|medium|low", "suggestion": "学习建议"}],
  "overall": {
    "avg_mastery": 0-100,
    "progress_pct": 0-100,
    "efficiency": "high|medium|low",
    "trend": "up|stable|down"
  },
  "adjustment": {
    "action": "continue|review|retake|accelerate",
    "description": "调整说明",
    "focus_areas": ["重点调整方向"]
  }
}
```
"""


async def evaluate_learning(
    profile: dict,
    quiz_history: list[dict],
    study_sessions: list[dict],
    knowledge_graph: Optional[dict] = None,
    memory_context: str = "",
) -> dict:
    """评估学习效果，返回结构化评估报告

    Args:
        profile: 学生画像
        quiz_history: 答题历史 [{subject, chapter, correct, difficulty, timestamp}]
        study_sessions: 学习会话 [{topic, duration_min, resource_type, timestamp}]
        knowledge_graph: 知识图谱（可选）
        memory_context: L1/L2/L3 三层学情记忆上下文（可选，低侵入注入）

    Returns:
        评估报告 dict
    """
    llm = LLMProvider()

    # 构建评估输入
    eval_input = _build_eval_input(profile, quiz_history, study_sessions, knowledge_graph, memory_context)

    try:
        result = await llm.text_completion(
            FEEDBACK_EVALUATE_PROMPT, eval_input,
            temperature=0.3, max_tokens=2000,
        )
        report = _parse_eval_result(result)
        logger.info(f"学习效果评估完成: avg_mastery={report.get('overall', {}).get('avg_mastery', 'N/A')}")
        return report
    except Exception as e:
        logger.error(f"学习效果评估失败: {e}")
        return _fallback_eval(quiz_history)


def _build_eval_input(
    profile: dict,
    quiz_history: list[dict],
    study_sessions: list[dict],
    knowledge_graph: Optional[dict] = None,
    memory_context: str = "",
) -> str:
    """构建评估输入（含可选 L1/L2/L3 学情记忆上下文）"""
    parts = ["【学生画像】"]

    # 画像
    profile_summary = {k: v for k, v in profile.items() if k in [
        "knowledge_base", "learning_style", "goal", "weak_points",
        "progress", "study_time", "preferred_difficulty"
    ]}
    parts.append(json.dumps(profile_summary, ensure_ascii=False, indent=2))

    # L1/L2/L3 三层学情记忆（低侵入注入：记忆薄弱点/掌握度并入评估输入）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append(f"\n【历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_context[:600]}")

    # 答题历史统计
    if quiz_history:
        total = len(quiz_history)
        correct = sum(1 for q in quiz_history if q.get("correct"))
        parts.append(f"\n【答题统计】\n总题数: {total}, 正确数: {correct}, 正确率: {correct/total*100:.1f}%")

        # 按章节统计
        chapters = {}
        for q in quiz_history:
            ch = q.get("chapter", "未知")
            if ch not in chapters:
                chapters[ch] = {"total": 0, "correct": 0}
            chapters[ch]["total"] += 1
            if q.get("correct"):
                chapters[ch]["correct"] += 1

        parts.append("\n【各章节正确率】")
        for ch, stats in sorted(chapters.items()):
            rate = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
            parts.append(f"- {ch}: {rate:.0f}% ({stats['correct']}/{stats['total']})")

        # 最近 10 条答题记录
        parts.append("\n【最近答题】")
        for q in quiz_history[-10:]:
            parts.append(f"- {q.get('chapter','?')} {q.get('subject','?')}: {'✅' if q.get('correct') else '❌'} ({q.get('difficulty','medium')})")

    # 学习会话统计
    if study_sessions:
        total_duration = sum(s.get("duration_min", 0) for s in study_sessions)
        parts.append(f"\n【学习统计】\n总学习时长: {total_duration}分钟, 总会话数: {len(study_sessions)}")

    parts.append("\n请根据以上数据，输出JSON格式的多维度评估报告。")
    return "\n".join(parts)


def _parse_eval_result(text: str) -> dict:
    """解析 LLM 输出的评估结果（复用共享 JSON 提取工具）"""
    from shared.llm_utils import extract_json_from_llm_output
    result = extract_json_from_llm_output(text)
    if result:
        return result
    return _fallback_eval([])


def _fallback_eval(quiz_history: list[dict]) -> dict:
    """降级评估（基于规则而不是LLM）"""
    # 按章节统计
    chapters = {}
    for q in quiz_history:
        ch = q.get("chapter", "未知")
        if ch not in chapters:
            chapters[ch] = {"total": 0, "correct": 0, "scores": []}
        chapters[ch]["total"] += 1
        if q.get("correct"):
            chapters[ch]["correct"] += 1
        chapters[ch]["scores"].append(100 if q.get("correct") else 0)

    mastery_by_topic = {}
    weak_points = []
    for ch, stats in chapters.items():
        score = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
        level = "mastered" if score >= 80 else ("weak" if score >= 50 else "unlearned")
        mastery_by_topic[ch] = {
            "score": round(score),
            "level": level,
            "trend": "stable",
        }
        if score < 60:
            weak_points.append({
                "topic": ch,
                "priority": "high" if score < 40 else "medium",
                "suggestion": f"建议重新学习{ch}，重点突破薄弱环节",
            })

    total_quiz = len(quiz_history)
    correct = sum(1 for q in quiz_history if q.get("correct"))
    avg_mastery = correct / total_quiz * 100 if total_quiz > 0 else 0

    return {
        "mastery_by_topic": mastery_by_topic,
        "weak_points": weak_points,
        "overall": {
            "avg_mastery": round(avg_mastery),
            "progress_pct": round(avg_mastery),
            "efficiency": "medium",
            "trend": "stable",
        },
        "adjustment": {
            "action": "review" if weak_points else "continue",
            "description": f"发现 {len(weak_points)} 个薄弱环节，建议重点复习",
            "focus_areas": [w["topic"] for w in weak_points[:3]],
        },
    }


# ── 路径调整建议 ──

PATH_ADJUST_PROMPT = """\
你是计算机408考研学习系统的「学习路径调整Agent」。
你的任务是根据学习效果评估报告，动态调整学习路径和资源推送策略。

## 输入
- 当前学习路径
- 评估报告（含薄弱点、掌握度、趋势）
- 学生画像

## 输出
调整后的学习路径建议，包含：
1. 需要调整的节点
2. 新增的补救节点
3. 资源推送优先级
4. 时间安排建议
"""


async def adjust_learning_path(
    current_path: list[dict],
    eval_report: dict,
    profile: dict,
) -> dict:
    """根据评估报告调整学习路径"""
    llm = LLMProvider()

    weak_points = eval_report.get("weak_points", [])
    adjustment = eval_report.get("adjustment", {})

    # 没有薄弱点，不需要调整
    if not weak_points and adjustment.get("action") == "continue":
        return {
            "adjusted": False,
            "path": current_path,
            "message": "学习效果良好，按原计划继续",
        }

    # 构建调整输入
    input_parts = [
        "【当前学习路径】",
        json.dumps(current_path, ensure_ascii=False, indent=2),
        "\n【评估报告】",
        json.dumps(eval_report, ensure_ascii=False, indent=2),
        "\n请根据薄弱点，在路径中插入补救节点，调整学习优先级。",
    ]

    try:
        result = await llm.text_completion(
            PATH_ADJUST_PROMPT, "\n".join(input_parts),
            temperature=0.4, max_tokens=1500,
        )
        # 尝试解析JSON（复用共享提取工具）
        from shared.llm_utils import extract_json_from_llm_output
        parsed = extract_json_from_llm_output(result)
        if parsed:
            return parsed
    except Exception as e:
        logger.warning(f"路径调整失败: {e}")

    # 降级：基于规则调整
    return _fallback_adjustment(current_path, weak_points)


def _fallback_adjustment(current_path: list[dict], weak_points: list) -> dict:
    """降级路径调整"""
    weak_topics = {w["topic"] for w in weak_points}
    adjusted = []
    inserted = []

    for node in current_path:
        adjusted.append(node)
        # 如果节点是薄弱点，标记为需要复习
        if node.get("name") in weak_topics:
            node["status"] = "review_needed"
            node["priority"] = "high"

    # 对不在路径中的薄弱点，插入补救节点
    path_names = {n.get("name") for n in current_path}
    for w in weak_points:
        if w["topic"] not in path_names:
            remediation = {
                "name": w["topic"],
                "type": "remediation",
                "priority": w.get("priority", "high"),
                "status": "pending",
                "suggestion": w.get("suggestion", ""),
            }
            adjusted.append(remediation)
            inserted.append(w["topic"])

    return {
        "adjusted": True,
        "path": adjusted,
        "message": f"已根据评估结果调整路径，新增 {len(inserted)} 个补救节点",
        "inserted_nodes": inserted,
        "action": "review" if weak_points else "continue",
    }