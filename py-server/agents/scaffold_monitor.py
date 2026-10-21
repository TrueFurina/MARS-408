# ============================================================
# 支架健康监测 (Scaffold Monitor) — SAGE λ 监测的工程化实现
#
# 机制来源: SAGE 命题 1 的运行时判据——「教师不追求某个固定的最优
# λ, 只看学生还能不能继续往下做」。论文给出三类支架失灵信号:
#   ① 学生解释不了提示  ② 反复索要答案  ③ 撤掉辅助迁移不动。
#
# 本模块实现其中**可由对话日志自动检测**的一类: 反复索要答案
# (其余两类分别需要学生复述与撤除后测, 属未来工作, 不在此冒充)。
#
# ⚠️ 诚实性边界:
#   - 这是基于关键词的规则判据, 不是学习状态测量;
#   - 状态含义是「当前对话里的行为信号」, 不是学生能力画像;
#   - 机制来源为 SAGE 仿真研究设计, 不构成教学效果宣称。
# ============================================================

import logging

logger = logging.getLogger("netlearn.scaffold_monitor")

# 绕过提示、直接索要答案的行为模式（命中即信号; 规则可迭代）
ASK_ANSWER_PATTERNS = [
    "直接给答案",
    "直接告诉我",
    "答案是什么",
    "答案是啥",
    "告诉我答案",
    "就告诉我吧",
    "别提示了",
    "不要提示了",
    "不想想了",
    "你直接说",
    "完整代码",
    "帮我写完",
    "帮我把",
    "完整证明",
    "最终答案",
]

# 监测窗口: 最近 N 轮学生消息
WINDOW_SIZE = 6

# 阈值: 窗口内命中 >= 2 次 → collapsed; == 1 → warning
COLLAPSE_THRESHOLD = 2

_ADVICE = {
    "healthy": "支架工作正常。维持当前提示级别, 继续看学生能否完成二次作答。",
    "warning": "出现索要答案的苗头。建议观察学生能否解释上一次提示; 解释不了就把提示降一级。",
    "collapsed": (
        "当前支架可能已经失灵: 学生在绕过提示直接索要答案。"
        "建议把提示降回更基础的级别（如方向级）, 或先布置一个无辅助的小任务; "
        "按答案保留规则, 不要给完整答案。"
    ),
}


def monitor_scaffold_health(recent_questions: list[str]) -> dict:
    """按最近学生消息判支架健康（纯函数, 零状态）。

    Args:
        recent_questions: 最近的（按时间正序）学生消息文本, 取最后
            WINDOW_SIZE 条进入窗口。

    Returns:
        {
            "status": "healthy" | "warning" | "collapsed",
            "hits": int,               # 窗口内命中消息数
            "window_size": int,        # 实际进入窗口的消息数
            "signals": [命中的消息片段...],
            "advice": str,             # 面向教师的应对建议
        }
    """
    window = [q for q in (recent_questions or []) if isinstance(q, str) and q.strip()][-WINDOW_SIZE:]
    signals = []
    for q in window:
        if any(pat in q for pat in ASK_ANSWER_PATTERNS):
            signals.append(q.strip()[:60])

    hits = len(signals)
    if hits >= COLLAPSE_THRESHOLD:
        status = "collapsed"
    elif hits == 1:
        status = "warning"
    else:
        status = "healthy"

    if status != "healthy":
        logger.info("[ScaffoldMonitor] status=%s hits=%s window=%s", status, hits, len(window))

    return {
        "status": status,
        "hits": hits,
        "window_size": len(window),
        "signals": signals,
        "advice": _ADVICE[status],
    }
