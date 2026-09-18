# ============================================================
# 错题智能归因引擎（error_attributor）
# ------------------------------------------------------------
# 功能：对一道被标记错误的题目，自动分析「为什么错」，输出结构化归因：
#   error_type        错误类型枚举（概念混淆/审题错误/计算失误/思路偏差/记忆遗忘/知识盲区）
#   confidence        置信度 0~1
#   reason            中文解释
#   knowledge_points  命中的知识点列表
#   review_suggestion 复习建议
#   provider          实际使用的 LLM 通道名（auto = X2→DeepSeek 自动回退）
#   degraded          True 表示 LLM 不可用，已降级为规则启发式（诚信：明确标注）
#
# 诚信约束：
#   - 优先真实调用讯飞星火 X2→DeepSeek 通道（auto）；
#   - 若全部通道不可用（无 .env 凭证/网络），明确 degraded=True 并走规则降级，
#     绝不谎称「AI 已分析」。
# ============================================================

import json
import logging
import re
from typing import Optional

logger = logging.getLogger("netlearn.error_attributor")

# ── 错误类型字典（与 user_store 既有 error_type 取值兼容）──
ERROR_TYPES = {
    "concept": "概念混淆",
    "misread": "审题错误",
    "calculation": "计算失误",
    "logic": "思路偏差",
    "memory": "记忆遗忘",
    "blindspot": "知识盲区",
}
ERROR_TYPE_KEYS = list(ERROR_TYPES.keys())


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 输出中稳健提取 JSON（容忍 ```json 围栏、前后缀闲话）。"""
    if not text:
        return None
    # 去掉代码围栏
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    # 优先找最外层 {...}
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    return None


def _heuristic_attribution(question: dict, wrong_answer: str, correct_answer: str) -> dict:
    """规则降级归因：无 LLM 时使用，置信度低且明确标注 degraded。"""
    wa = (wrong_answer or "").strip()
    ca = (correct_answer or "").strip()
    qtext = (question.get("question") or question.get("stem") or
             question.get("content") or str(question)).strip()

    # 1) 完全没作答 / 空 -> 知识盲区
    if not wa:
        return {
            "error_type": "blindspot",
            "error_label": ERROR_TYPES["blindspot"],
            "confidence": 0.45,
            "reason": "未给出答案，疑似该知识点完全未掌握（知识盲区）。",
            "knowledge_points": [question.get("knowledge_point", "")],
            "review_suggestion": "回到课本/讲义对应章节，先建立基本概念再做题。",
            "provider": "rule-fallback",
            "degraded": True,
        }

    # 2) 数值型答案且都能解析 -> 计算失误
    def _num(s):
        try:
            return float(str(s).replace(",", "").strip())
        except Exception:
            return None
    wa_n, ca_n = _num(wa), _num(ca)
    if wa_n is not None and ca_n is not None and wa_n != ca_n:
        return {
            "error_type": "calculation",
            "error_label": ERROR_TYPES["calculation"],
            "confidence": 0.55,
            "reason": "答案为数值且数值不一致，最可能是计算/代入失误。",
            "knowledge_points": [question.get("knowledge_point", "")],
            "review_suggestion": "重新推导一遍，注意单位换算与公式代入步骤。",
            "provider": "rule-fallback",
            "degraded": True,
        }

    # 3) 选项型：错误选项与正确选项语义相近 -> 概念混淆
    opts = question.get("options") or {}
    if isinstance(opts, dict) and ca in opts and wa in opts:
        return {
            "error_type": "concept",
            "error_label": ERROR_TYPES["concept"],
            "confidence": 0.5,
            "reason": "错误选项与正确选项属于同一考点的不同表述，疑似概念辨析不清。",
            "knowledge_points": [question.get("knowledge_point", "")],
            "review_suggestion": "对比两个选项的适用场景，整理该考点的辨析清单。",
            "provider": "rule-fallback",
            "degraded": True,
        }

    # 4) 默认 -> 思路偏差（最常见的兜底）
    return {
        "error_type": "logic",
        "error_label": ERROR_TYPES["logic"],
        "confidence": 0.4,
        "reason": "规则降级无法精确定位，初步判定为解题思路偏差。",
        "knowledge_points": [question.get("knowledge_point", "")],
        "review_suggestion": "对照解析梳理解题步骤，找出断点。",
        "provider": "rule-fallback",
        "degraded": True,
    }


async def attribute_error(
    question: dict,
    wrong_answer: str,
    correct_answer: str,
    explanation: Optional[str] = None,
) -> dict:
    """对错题做智能归因。返回含 degraded 标志的结构化 dict。

    question: 题目 dict（至少含 question/stem、answer、knowledge_point、options 等可选字段）
    wrong_answer / correct_answer: 字符串
    explanation: 题目已有解析（可选，作为 LLM 上下文）
    """
    # 构建题目上下文
    qtext = question.get("question") or question.get("stem") or question.get("content") or ""
    opts = question.get("options") or {}
    opts_str = ""
    if isinstance(opts, dict):
        opts_str = "；".join(f"{k}. {v}" for k, v in opts.items())
    elif isinstance(opts, list):
        opts_str = "；".join(str(o) for o in opts)

    system_prompt = (
        "你是计算机专业考研（408）错题分析助手。给定一道题的题干、选项、"
        "学生错误答案、正确答案与解析，请判断学生『为什么错』。"
        "只输出一个 JSON 对象，字段严格如下：\n"
        "{\n"
        '  "error_type": 从 ["concept","misread","calculation","logic","memory","blindspot"] 中选唯一值,'
        '  "confidence": 0到1之间的浮点数,'
        '  "reason": 中文，说明判断依据（<=60字）,'
        '  "knowledge_points": 字符串数组，命中的知识点,'
        '  "review_suggestion": 中文，给学生的复习建议（<=60字)\n'
        "}\n"
        "error_type 含义：concept=概念混淆, misread=审题错误, calculation=计算失误, "
        "logic=思路偏差, memory=记忆遗忘, blindspot=知识盲区。不要输出任何额外文字。"
    )
    user_prompt = (
        f"【题干】{qtext}\n"
        f"【选项】{opts_str or '（无）'}\n"
        f"【学生错误答案】{wrong_answer}\n"
        f"【正确答案】{correct_answer}\n"
        f"【解析】{explanation or '（无）'}\n"
        "请输出归因 JSON。"
    )

    try:
        from db.llm_provider import LLMProvider
        provider = LLMProvider()  # auto: X2 → DeepSeek
        resp_text = await provider.text_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=600,
            timeout=30,
        )
        data = _extract_json(resp_text)
        if not data or data.get("error_type") not in ERROR_TYPE_KEYS:
            raise ValueError("LLM 输出不可解析或 error_type 非法")
        et = data["error_type"]
        return {
            "error_type": et,
            "error_label": ERROR_TYPES.get(et, et),
            "confidence": float(data.get("confidence", 0.7)),
            "reason": str(data.get("reason", "")),
            "knowledge_points": list(data.get("knowledge_points", []) or []),
            "review_suggestion": str(data.get("review_suggestion", "")),
            "provider": "auto",
            "degraded": False,
        }
    except Exception as e:  # LLMUnavailable / 超时 / 解析失败 → 规则降级
        logger.warning("错题归因 LLM 不可用，降级规则启发式: %s", e)
        h = _heuristic_attribution(question, wrong_answer, correct_answer)
        h.update({
            "error_label": ERROR_TYPES.get(h["error_type"], h["error_type"]),
            "provider": "rule-fallback",
            "degraded": True,
        })
        return h
