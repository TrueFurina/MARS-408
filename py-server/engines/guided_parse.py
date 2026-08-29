# ============================================================
# 思路引导式解析引擎（guided_parse）
# ------------------------------------------------------------
# 对一道题，生成「苏格拉底式」分步引导（不直接给答案，而是引导学生自己推出）。
#
# 诚信约束（与 error_attributor 一致）：
#   - 优先真实调用讯飞星火 X2→DeepSeek 通道（auto）生成分步引导；
#   - LLM 不可用（无 .env 凭证/网络）→ 明确 degraded=True 走规则模板，
#     绝不谎称「AI 已分析」。
#
# 两者都给出可复现的分步提示，模板版基于题型/科目/知识点做确定性脚手架，
# 标注 source=template 以便前端诚实展示。
# ============================================================

import json
import logging
import re
from typing import Optional

logger = logging.getLogger("netlearn.guided_parse")

# 题型判定关键词
_CALC_HINTS = ["计算", "求", "换算", "推导", "证明", "算出", "地址", "容量", "大小", "序列", "编码"]
_EXPLAIN_HINTS = ["简述", "说明", "论述", "比较", "辨析", "解释", "为什么", "区别", "如何理解"]


def _detect_qtype(question: dict) -> str:
    """选择题 / 计算题 / 论述题 三分类（确定性）。"""
    opts = question.get("options")
    if opts and (isinstance(opts, dict) or isinstance(opts, list)):
        return "choice"
    text = (question.get("question") or question.get("stem") or question.get("content") or "").lower()
    if any(h in (question.get("question") or question.get("stem") or question.get("content") or "") for h in _CALC_HINTS):
        return "calc"
    if any(h in (question.get("question") or question.get("stem") or question.get("content") or "") for h in _EXPLAIN_HINTS):
        return "explain"
    return "general"


def _template_guide(question: dict) -> list:
    """规则降级：基于题型生成通用引导步骤（确定性、可复现）。"""
    kp = question.get("knowledge_point") or question.get("kp") or "本题考查点"
    qtype = _detect_qtype(question)
    subject = question.get("subject", "")

    base = [
        f"① 审题：圈出题干关键词，明确它落在哪一科目/章节——本题落点：{kp}（{subject or '见题干'}）。",
        "② 回忆：调出该知识点的核心定义、判定条件或公式，先不急着下结论。",
    ]
    if qtype == "choice":
        base.append("③ 辨析选项：先排除明显违背定义的干扰项，再比较剩余选项的适用边界。")
        base.append("④ 验证：用你选的答案回代题干，确认无矛盾再落笔。")
    elif qtype == "calc":
        base.append("③ 列已知求未知：写下题目给出的所有已知量，明确目标量，选对公式/算法。")
        base.append("④ 分步计算：注意单位换算与进位/截断，最后用数量级粗检结果是否合理。")
    elif qtype == "explain":
        base.append("③ 搭框架：先给结论，再分『是什么—为什么—举例/对比』展开。")
        base.append("④ 收尾：用一句话回扣题干，避免答非所问。")
    else:
        base.append("③ 拆解：把大问题拆成小问，逐个小问找对应知识点。")
        base.append("④ 验证：用结论反推题干条件，确认逻辑闭环。")
    return base


def _extract_steps(text: str) -> Optional[list]:
    """从 LLM 输出里稳健提取步骤列表（支持 JSON 数组或编号列表两种形态）。"""
    if not text:
        return None
    # 1) JSON 数组
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    s, e = cleaned.find("["), cleaned.rfind("]")
    if s != -1 and e > s:
        try:
            arr = json.loads(cleaned[s: e + 1])
            if isinstance(arr, list) and all(isinstance(x, str) for x in arr) and arr:
                return arr
        except json.JSONDecodeError:
            pass
    # 2) 编号列表：1. / ① / 一、
    items = re.findall(r"(?:^|\n)\s*(?:\d+[.、]|[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十][.、])\s*(.+)", text)
    if len(items) >= 2:
        return [it.strip() for it in items if it.strip()]
    return None


async def generate_guide(question: dict, use_llm: bool = True) -> dict:
    """生成思路引导。返回 {source, steps, degraded, qtype}。"""
    qtype = _detect_qtype(question)
    qtext = question.get("question") or question.get("stem") or question.get("content") or ""
    opts = question.get("options") or {}
    opts_str = ""
    if isinstance(opts, dict):
        opts_str = "；".join(f"{k}. {v}" for k, v in opts.items())
    elif isinstance(opts, list):
        opts_str = "；".join(str(o) for o in opts)

    if use_llm:
        try:
            from db.llm_provider import LLMProvider
            system_prompt = (
                "你是计算机专业考研（408）辅导老师，擅长『苏格拉底式』引导。"
                "给定一道题的题干与选项，不要直接给答案，而是输出 3-5 个引导步骤，"
                "帮助学生自己推出结论。每步一句，循序渐进、由浅入深。"
                "只输出一个 JSON 字符串数组，例如 [\"第一步…\",\"第二步…\"]，不要额外文字。"
            )
            user_prompt = f"【题干】{qtext}\n【选项】{opts_str or '（无）'}\n请输出引导步骤 JSON 数组。"
            provider = LLMProvider()
            resp = await provider.text_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=700,
                timeout=30,
            )
            steps = _extract_steps(resp)
            if steps:
                return {
                    "source": "llm",
                    "steps": steps,
                    "degraded": False,
                    "qtype": qtype,
                }
        except Exception as e:
            logger.warning("思路引导 LLM 不可用，降级规则模板: %s", e)

    return {
        "source": "template",
        "steps": _template_guide(question),
        "degraded": True,
        "qtype": qtype,
    }
