# ============================================================
# Triage 分级路由 — 多智能体三评审集成 · 增量一
#
# 作用：在完整 10 节点流水线之前，用轻量规则判断任务风险等级。
#   - low  : 寒暄 / 简短答疑 / 无知识诉求 → 走 tutor/chat 快路径（零评审）
#   - high : 知识点讲解 / 习题 / 原理 / 机制 → 走完整流水线 + 三评审
#
# 设计约束：
#   - 零 LLM 成本（纯规则 + 关键词启发式），可解释、可单测、可快速迭代。
#   - 安全默认：拿不准一律判 high（宁可多评审，不可漏评审）。
#   - 不依赖任何外部服务，导入零副作用。
# ============================================================

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("netlearn.triage")

# ── 分级常量 ──
LEVEL_LOW = "low"
LEVEL_HIGH = "high"

# ── 高风险信号关键词（命中任一 → high）──
# 知识诉求类：讲解/解释/原理/机制/流程/区别/为什么/如何
# 练习类：习题/练习/题目/例题/考点/真题/作业
_HIGH_KEYWORDS = [
    # 讲解/解释诉求
    "什么是", "啥是", "讲解", "解释", "原理", "机制", "流程", "过程",
    "区别", "差异", "对比", "为什么", "为何", "如何", "怎么", "怎样",
    "详解", "介绍", "知识点", "概念", "定义", "规则", "协议", "算法",
    "结构", "层次", "模型", "组成", "特点", "作用", "含义", "举例",
    # 练习/习题诉求
    "习题", "练习", "题目", "例题", "考点", "真题", "作业", "试题",
    "解题", "求解", "计算", "推导", "证明", "选择", "填空", "简答",
    # 明确科目/难度信号（说明是正式学习请求）
    "数据结构", "操作系统", "计算机网络", "计算机组成", "408", "考研",
]

# ── 低风险信号关键词（命中任一且无 HIGH 命中 → low）──
# 寒暄/社交/情绪/简单确认，不含知识诉求
_LOW_KEYWORDS = [
    "你好", "您好", "hi", "hello", "嗨", "哈喽",
    "谢谢", "感谢", "再见", "拜拜", "晚安", "早安", "早上好", "下午好",
    "加油", "辛苦了", "在吗", "在不在",
    "好的", "好嘞", "嗯", "明白", "知道了", "了解", "收到", "ok", "好的呢",
    "开心", "高兴", "棒", "厉害", "赞",
]

# ── 启发式阈值 ──
_MIN_LOW_LEN = 8          # 请求短于该长度才可能被判 low
_HIGH_HIT_NEEDED = 1      # 命中高风险关键词个数阈值


@dataclass
class TriageResult:
    """Triage 判定结果"""
    level: str                                # "low" | "high"
    reason: str = ""                          # 判定依据（可展示、可调试）
    hit_high: list[str] = field(default_factory=list)   # 命中的高风险信号
    hit_low: list[str] = field(default_factory=list)    # 命中的低风险信号


def _hits(text: str, keywords: list[str]) -> list[str]:
    """返回文本命中的关键词列表（大小写不敏感）。"""
    lower = (text or "").lower()
    return [kw for kw in keywords if kw.lower() in lower]


def classify_request(
    user_request: str,
    topic: str = "",
    course: str = "",
    difficulty: str = "",
    profile: dict | None = None,
) -> TriageResult:
    """分级路由分类器（纯函数，零 LLM 成本）。

    Args:
        user_request: 用户原始请求（必填）
        topic: 学习主题（可选，参与判定）
        course: 课程（可选，参与判定）
        difficulty: 难度（可选，参与判定）
        profile: 学生画像（可选，预留，当前不参与）

    Returns:
        TriageResult: 分级结果。安全默认 high。
    """
    text = (user_request or "").strip()
    combined = f"{text} {topic or ''} {course or ''}"

    result = TriageResult(level=LEVEL_HIGH)

    # 空输入：无法判断 → 安全默认 high
    if not text:
        result.reason = "空输入，安全默认 high"
        return result

    # 1. 高风险信号优先（命中任一 → high）
    result.hit_high = _hits(combined, _HIGH_KEYWORDS)
    if len(result.hit_high) >= _HIGH_HIT_NEEDED:
        result.level = LEVEL_HIGH
        result.reason = f"命中高风险信号: {result.hit_high[:5]}"
        return result

    # 2. 明确难度/科目 → 正式学习请求 → high
    if difficulty and difficulty != "easy":
        result.reason = f"难度={difficulty}，视为正式学习请求"
        return result
    if course and course.strip():
        result.reason = f"指定课程={course}，视为正式学习请求"
        return result

    # 3. 低风险信号：命中且请求很短 → low
    result.hit_low = _hits(text, _LOW_KEYWORDS)
    if result.hit_low and len(text) < _MIN_LOW_LEN:
        result.level = LEVEL_LOW
        result.reason = f"短请求命中低风险信号: {result.hit_low[:5]}"
        return result

    # 4. 兜底：有实质内容但无明确信号 → 安全默认 high
    result.reason = "无明确低风险信号，安全默认 high"
    return result


def triage_node(state: dict) -> dict:
    """LangGraph 节点：在 coordinator 之前执行，把分级结果写入共享状态。

    不改变任何业务字段，仅新增 triage_level / triage_reason / triage_hits，
    供 MAPPO 策略层按分级调节评审强度（增量四预留）。
    """
    try:
        result = classify_request(
            user_request=state.get("user_request", ""),
            topic=state.get("topic", ""),
            course=state.get("course", ""),
            difficulty=state.get("difficulty", ""),
            profile=state.get("student_profile") or {},
        )
        state["triage_level"] = result.level
        state["triage_reason"] = result.reason
        state["triage_hits"] = {
            "high": result.hit_high,
            "low": result.hit_low,
        }
        logger.info(
            "Triage 判定: level=%s, reason=%s",
            result.level, result.reason,
        )
    except Exception as e:  # noqa: BLE001 — 分级失败绝不断流水线
        logger.warning(f"Triage 判定失败，安全默认 high: {e}")
        state["triage_level"] = LEVEL_HIGH
        state["triage_reason"] = f"Triage 异常，安全默认 high: {e}"
        state["triage_hits"] = {"high": [], "low": []}
    return state
