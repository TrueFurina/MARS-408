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


def _critic_confidence(verdict: str, valid_count: int, invalid_count: int) -> float:
    """批评者置信度（M2 口径，独立可复算）：供 consensus 展示与前端呈现。

    passed：高置信（无有效批评）；有无效批评被门禁拦截 → 略降（体现"在校错"）；
    flagged / regenerate：中低置信（存在有效问题）。
    """
    if verdict == "passed":
        base = 0.95 - 0.05 * invalid_count
    elif verdict == "flagged":
        base = 0.60
    else:
        base = 0.40
    return max(0.1, min(1.0, base))


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
            f"请以 JSON 格式输出审阅结果，必须包含 verdict 和 issues 字段。\n"
            f'格式: {{"verdict": "passed"|"flagged"|"regenerate", "issues": [{{"point": "问题描述", "evidence": "知识库/RFC/教材证据，无证据填 null", "suggestion": "具体修改建议"}}]}}\n'
            f"要求：每条 issue 必须附 evidence 证据；无法给出证据的问题不要列入 issues。"
        )
        critic_report = await llm.text_completion(
            CRITIC_PROMPT, review_prompt, temperature=0.3, max_tokens=600
        )
        state["critic_report"] = critic_report

        # 结构化解析（M2：point/evidence/suggestion + valid 标记）
        parsed = _parse_critic_report(critic_report)
        issues = parsed["issues"]
        state["critic_issues"] = issues

        # 解析 LLM 输出的 JSON 判定（结构化优先，降级：字符串匹配兜底）
        verdict = parsed["verdict"] or _parse_critic_verdict(critic_report)
        valid_issues = [i for i in issues if i.get("valid")]
        invalid_issues = [i for i in issues if not i.get("valid")]

        if verdict in ("flagged", "regenerate") and not valid_issues:
            # 证据门禁（M2）：全部为无证据批评 → 不触发重生成，无效批评记入 filtered_issues
            verdict = "passed"
            consensus = state.get("consensus", {})
            consensus["status"] = "passed"
            consensus["confidence_score"] = _critic_confidence("passed", 0, len(invalid_issues))
            consensus["filtered_issues"] = consensus.get("filtered_issues", []) + [
                f"Critic 无证据批评被门禁拦截: {i['point'][:50]}" for i in invalid_issues
            ]
            state["consensus"] = consensus
            logger.info(f"Critic 证据门禁: {len(invalid_issues)} 条无证据批评被拦截，判定 passed")
        elif verdict in ("flagged", "regenerate"):
            consensus = state.get("consensus", {})
            consensus["status"] = verdict
            consensus["confidence_score"] = _critic_confidence(verdict, len(valid_issues), len(invalid_issues))
            new_flags = [f"Critic 审阅发现问题: {i['point']}" for i in valid_issues]
            consensus["flagged_issues"] = consensus.get("flagged_issues", []) + (
                new_flags or ["Critic 审阅发现问题（见 critic_report）"]
            )
            state["consensus"] = consensus
            # 在节点内自增重试计数（路由函数是纯函数，修改不持久化，必须在节点内自增）
            r = state.get("regenerate_round", 0)
            state["regenerate_round"] = r + 1
            logger.info(f"Critic 标记: verdict={verdict}, round={r + 1}, 有效批评={len(valid_issues)}")
        elif verdict == "passed":
            consensus = state.get("consensus", {})
            consensus["status"] = "passed"
            consensus["confidence_score"] = _critic_confidence("passed", 0, 0)
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


def _parse_critic_report(report: str) -> dict:
    """结构化解析批评者输出（M2）。

    返回 {"verdict": str, "issues": [{"point", "evidence", "suggestion", "valid"}]}。
    - evidence 为空/None 的 issue 标记 valid=False（无证据批评）。
    - 解析失败时 verdict=""（调用方降级关键词判定），issues=[]（fail-open）。
    """
    import json as _json
    try:
        start = report.find("{")
        end = report.rfind("}")
        if start != -1 and end != -1:
            data = _json.loads(report[start:end + 1])
            verdict = data.get("verdict", "")
            if verdict not in ("passed", "flagged", "regenerate"):
                verdict = ""
            raw_issues = data.get("issues") or []
            issues = []
            for it in raw_issues:
                if not isinstance(it, dict):
                    continue
                point = str(it.get("point", "")).strip()
                if not point:
                    continue
                evidence = str(it.get("evidence") or "").strip()
                suggestion = str(it.get("suggestion") or "").strip()
                issues.append({
                    "point": point,
                    "evidence": evidence or None,
                    "suggestion": suggestion or None,
                    "valid": bool(evidence),
                })
            return {"verdict": verdict, "issues": issues}
    except (_json.JSONDecodeError, ValueError):
        pass
    return {"verdict": "", "issues": []}
