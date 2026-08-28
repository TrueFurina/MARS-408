# ============================================================
# 审阅 Agent (Critic / Validator)
# 对生成结果进行事实核查，确保内容准确性
# 复用现有 prompts.py 中的 CRITIC_PROMPT
# ============================================================

import logging

from agents.state import AgentState
from db.llm_provider import LLMProvider
from prompts import CRITIC_PROMPT

logger = logging.getLogger("netlearn.critic")


async def critic_node(state: AgentState) -> AgentState:
    """审阅 Agent：检查生成内容准确性"""
    state["status"] = "reviewing"
    state["current_agent"] = "critic"

    topic = state.get("topic_label") or state.get("topic", "")
    teacher_doc = state.get("teacher_doc", "")
    quiz = state.get("quiz", "")
    code_practice = state.get("code_practice", "")
    ppt_outline = state.get("ppt_outline", "")
    memory_context = state.get("memory_context") or ""

    # 构建审阅内容（审核 Teacher + Quiz + Code + PPT，代码和PPT最易出错）
    content_to_review = f"【主题】{topic}\n\n"

    # L1/L2/L3 三层学情记忆（低侵入注入：审阅时参考学生薄弱点，针对性核查）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        content_to_review += f"【学生历史学情记忆】\n{memory_context[:600]}\n\n"

    if teacher_doc:
        content_to_review += f"## 教学文档（待审核）\n{teacher_doc[:3000]}\n\n"
    if quiz:
        content_to_review += f"## 练习题（待审核）\n{quiz[:2000]}\n\n"
    if code_practice:
        content_to_review += f"## 代码实操案例（待审核）\n{code_practice[:2000]}\n\n"
    if ppt_outline:
        content_to_review += f"## PPT大纲（待审核）\n{ppt_outline[:1500]}\n"

    try:
        llm = LLMProvider()
        # 要求 LLM 以 JSON 格式输出审阅结果（避免靠 "❌" 关键词的不可靠判定）
        review_prompt = (
            f"{content_to_review}\n\n"
            f"请以 JSON 格式输出审阅结果，必须包含 verdict 字段。\n"
            f'格式: {{"verdict": "passed"|"flagged"|"regenerate", "issues": ["..."]}}'
        )
        critic_report = await llm.text_completion(
            CRITIC_PROMPT, review_prompt, temperature=0.3, max_tokens=600
        )
        state["critic_report"] = critic_report

        # 解析 LLM 输出的 JSON 判定（降级：字符串匹配兜底）
        verdict = _parse_critic_verdict(critic_report)
        if verdict in ("flagged", "regenerate"):
            consensus = state.get("consensus", {})
            consensus["status"] = verdict
            consensus["flagged_issues"] = consensus.get("flagged_issues", []) + [
                "Critic 审阅发现问题（见 critic_report）"
            ]
            state["consensus"] = consensus
            # 在节点内自增重试计数（路由函数是纯函数，修改不持久化，必须在节点内自增）
            r = state.get("regenerate_round", 0)
            state["regenerate_round"] = r + 1
            logger.info(f"Critic 标记: verdict={verdict}, round={r + 1}")
        elif verdict == "passed":
            consensus = state.get("consensus", {})
            consensus["status"] = "passed"
            state["consensus"] = consensus

    except Exception as e:
        logger.warning(f"Critic LLM 调用失败: {e}")
        state["critic_report"] = f"审阅 Agent 调用失败: {e}"
        # LLM 失败时不做判定，标记为 passed 避免误杀
        consensus = state.get("consensus", {})
        consensus["status"] = "passed"
        state["consensus"] = consensus

    return state


def _parse_critic_verdict(report: str) -> str:
    """解析审阅报告的判定结果（JSON 优先，关键词兜底）"""
    import json as _json
    # 优先尝试 JSON 解析
    try:
        start = report.find("{")
        end = report.rfind("}")
        if start != -1 and end != -1:
            data = _json.loads(report[start:end + 1])
            verdict = data.get("verdict", "")
            if verdict in ("passed", "flagged", "regenerate"):
                return verdict
    except (_json.JSONDecodeError, ValueError):
        pass
    # 降级：关键词检查（比原来更精确，排除否定句式）
    has_error_marker = ("❌" in report) or ("存在错误" in report) or ("需要修正" in report)
    has_negation = ("没有❌" in report) or ("不存在错误" in report) or ("未发现错误" in report)
    if has_error_marker and not has_negation:
        return "flagged"
    return "passed"
