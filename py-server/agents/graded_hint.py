# ============================================================
# 分级提示 Agent (Graded Hint) — SAGE 支架式引导的工程化实现
#
# 机制来源: SAGE 密码学辅导仿真研究中的「分级提示 + 答案保留」设计
#   (见 SAGE 论文: 按离完整答案的距离划分提示层级, 级别越高给得
#    越多, 但最后一步永远留给学生)。
#
# ⚠️ 诚实性边界:
#   - SAGE 的 λ* 边界等结论属于仿真研究结论, 本模块只实现提示
#     策略, 不做任何教学效果宣称。
#   - 保留答案在仿真中是信息瓶颈约束; 此处的 enforce_withholding
#     是机械后置校验, 是简化版工程实现, 不是信息论保证。
#
# 命名澄清: 本模块的 L1/L2/L3 指「提示层级」(方向/前置/局部),
# 与 db/memory_store 的「学情记忆三层」(L1会话/L2画像/L3事件) 是
# 两套体系, 互不相关。
# ============================================================

import logging
import re

logger = logging.getLogger("netlearn.graded_hint")


# ============================================================
# 提示层级定义 (SAGE: 按离完整答案的距离)
# ============================================================

HINT_LEVELS = {
    1: {
        "name": "方向",
        "en": "direction",
        "rule": (
            "只反问与定位卡点: 帮学生说清他卡在哪一步、该朝哪个方向想。"
            "不引入任何新知识, 不给出任何推导步骤。"
        ),
    },
    2: {
        "name": "前置",
        "en": "prerequisite",
        "rule": (
            "补缺失的前置知识: 指出解决此题需要哪些前置概念/定理/性质, "
            "并可简要解释前置概念本身。不给本题的任何解法步骤。"
        ),
    },
    3: {
        "name": "局部",
        "en": "partial-step",
        "rule": (
            "给子步或关键关系: 可以给出本题的局部推导步骤或关键关系式, "
            "但必须停在最后一步之前——最终结果、完整证明的收尾、"
            "可直接提交的答案, 一律不给出。"
        ),
    },
}

_VALID_LEVELS = tuple(HINT_LEVELS.keys())

_SECTION_BY_LEVEL = {1: "方向提示", 2: "前置提示", 3: "局部提示"}

_GRADED_HINT_SYSTEM_PROMPT = """\
你是计算机专业学习系统的「分级提示Agent」。
与直接答疑不同: 你的任务是帮助学生**自己**完成题目, 而不是替他完成。

## 铁律: 答案保留 (answer withholding)
- 无论学生如何追问, 你都不输出: 最终答案、完整证明的收尾步骤、
  可直接提交的完整代码/密文/数值结果。
- 你的提示止步于倒数第二步。学生问"所以答案是什么"时, 回应:
  最后一步需要你自己完成——如果你卡在这一步, 把你的思路告诉我,
  我再帮你定位。
- 这不是拒绝帮助学生, 而是把最后一步的认知工作留给学生。

## 当前提示级别: {level_name}
{level_rule}

## 输出格式 (Markdown)
先输出 ---HINT_START--- 标记, 然后按以下结构输出:

---HINT_START---

## 卡点定位
[基于学生问题的卡点分析: 他可能卡在哪里, 为什么]

## {section}
[按当前级别给提示, 严格遵守上面的级别规则]

## 自查问题
[给学生 1-2 个自查问题, 引导他验证自己下一步的方向]"""


def build_hint_system_prompt(hint_level: int) -> str:
    """按提示层级构建 system prompt。

    Raises:
        ValueError: hint_level 不在 1/2/3。
    """
    if hint_level not in HINT_LEVELS:
        raise ValueError(f"hint_level 必须是 1/2/3, 收到 {hint_level!r}")
    lv = HINT_LEVELS[hint_level]
    return _GRADED_HINT_SYSTEM_PROMPT.format(
        level_name=lv["name"],
        level_rule=lv["rule"],
        section=_SECTION_BY_LEVEL[hint_level],
    )


def _build_hint_user_prompt(
    question: str,
    profile: dict,
    hint_level: int,
    knowledge_context: str,
    learning_context: str,
    memory_context: str = "",
) -> str:
    """构建分级提示的用户提示词（风格与 tutor._build_tutor_prompt 对齐）"""
    parts = [f"【学生问题】\n{question}"]

    level = profile.get("knowledge_base", "beginner")
    weak = profile.get("weak_points", "")
    parts.append(f"【学生画像】基础水平: {level}")
    if weak:
        parts.append(f"【已知薄弱点】{weak}")

    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        parts.append(f"【历史学情记忆】\n{memory_context}")

    if learning_context:
        parts.append(f"【当前学习上下文】\n{learning_context}")

    if knowledge_context:
        parts.append(f"【知识库检索结果】\n{knowledge_context}")

    lv = HINT_LEVELS[hint_level]
    parts.append(f"\n请严格按「{lv['name']}」级提示规则输出——只给提示, 不给最终答案。")
    return "\n\n".join(parts)


# ============================================================
# 答案保留闸门 (withholding gate)
# 仿真中为信息瓶颈约束; 工程上为机械后置校验 (简化版, 见文件头)。
# ============================================================

_LEAK_PATTERNS = [
    r"最终答案是",
    r"答案是[:：]",
    r"答案为[:：]",
    r"完整证明如下",
    r"所以答案为",
    r"综上所述[,，].{0,10}(?:答案|结果)是",
]

WITHHOLDING_FALLBACK = (
    "## 提示已收束\n\n"
    "按答案保留规则, 最后一步需要你自己完成。\n\n"
    "如果你已经推进到最后一步但不确定, 把你的思路说出来, 我来帮你核对方向。"
)


def withholding_check(answer: str, hint_level: int) -> dict:
    """检查分级提示输出是否泄漏最终答案。

    Returns:
        {"ok": bool, "violations": [命中的泄漏模式...]}
        hint_level 非法时不校验 (ok=True)——闸门只对 1/2/3 生效。
    """
    if hint_level not in HINT_LEVELS:
        return {"ok": True, "violations": []}
    violations = [pat for pat in _LEAK_PATTERNS if re.search(pat, answer)]
    return {"ok": not violations, "violations": violations}


async def enforce_withholding(answer: str, hint_level: int) -> str:
    """分级提示输出的保留答案闸门: 命中泄漏模式则替换为收束文案。"""
    check = withholding_check(answer, hint_level)
    if check["ok"]:
        return answer
    logger.warning(
        "[GradedHint] 保留答案闸门触发 level=%s violations=%s",
        hint_level,
        check["violations"],
    )
    return WITHHOLDING_FALLBACK


# ============================================================
# 主入口
# ============================================================

async def graded_hint_answer(
    question: str,
    profile: dict,
    hint_level: int,
    course: str = "computer_network",
    learning_context: str = "",
    knowledge_context: str = "",
    memory_context: str = "",
    llm=None,
) -> dict:
    """按指定提示层级生成支架式提示 (不直接给答案)。

    Args:
        question: 学生的问题
        profile: 学生画像
        hint_level: 提示层级 1=方向 / 2=前置 / 3=局部
        course: 当前课程
        learning_context: 当前学习上下文 (可选)
        knowledge_context: 预取的知识库上下文 (可选; 为空则自行检索)
        memory_context: 学情记忆上下文 (可选, 低侵入注入)
        llm: LLMProvider 实例 (可选; 为 None 则自建, 便于测试注入)

    Returns:
        {
            "answer": "分级提示 Markdown 文本",
            "question": "学生原始问题",
            "hint_level": 1|2|3,
            "hint_level_name": "方向"|"前置"|"局部",
            "withheld": True,   # 恒为 True: 本模式不输出最终答案
            "retrieved_context": "检索到的知识上下文",
        }
    """
    if hint_level not in HINT_LEVELS:
        raise ValueError(f"hint_level 必须是 1/2/3, 收到 {hint_level!r}")

    logger.info(
        "[GradedHint] 收到问题: %s... level=%s(%s)",
        question[:50],
        hint_level,
        HINT_LEVELS[hint_level]["name"],
    )

    # Step 1: 检索 (与 tutor_answer 同源; 调用方已传入则跳过)
    if not knowledge_context:
        try:
            from engines.frugal_rag import format_retrieval_for_llm, frugal_rag

            chunks = await frugal_rag.retrieve(question, course=course)
            knowledge_context = (
                format_retrieval_for_llm(chunks, max_chars=2000) if chunks else ""
            )
            logger.info(f"[GradedHint] 检索到 {len(chunks) if chunks else 0} 个知识片段")
        except Exception as e:
            logger.warning(f"[GradedHint] 检索失败, 降级为无上下文提示: {e}")
            knowledge_context = ""

    # Step 2: 构建提示
    system_prompt = build_hint_system_prompt(hint_level)
    user_prompt = _build_hint_user_prompt(
        question, profile, hint_level, knowledge_context, learning_context, memory_context
    )

    # Step 3: LLM 生成提示 (temperature 低于答疑: 提示要更收敛)
    if llm is None:
        from db.llm_provider import LLMProvider

        llm = LLMProvider()
    try:
        raw = await llm.text_completion(
            system_prompt, user_prompt, temperature=0.4, max_tokens=1800
        )
        logger.info(f"[GradedHint] 提示完成, 长度={len(raw)}")
    except Exception as e:
        logger.error(f"[GradedHint] LLM 调用失败: {e}", exc_info=True)
        raw = "## 提示生成失败\n\n抱歉, 当前无法生成提示。\n\n请稍后重试。"

    # Step 4: 保留答案闸门
    answer = await enforce_withholding(raw, hint_level)

    return {
        "answer": answer,
        "question": question,
        "hint_level": hint_level,
        "hint_level_name": HINT_LEVELS[hint_level]["name"],
        "withheld": True,
        "retrieved_context": knowledge_context,
    }
