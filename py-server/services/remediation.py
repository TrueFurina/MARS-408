# ============================================================
# P1 闭环触发 — 薄弱知识点检测（纯函数，无 LLM / 网络依赖）
#
# 低侵入：独立于 SkillPluginRuntime / LLMProvider，便于单元测试与复用。
# 仅负责"读掌握度 → 找出低于阈值的知识点"这一确定逻辑，
# 触发讲解（LLM）的逻辑在 api/quiz.py 中完成。
# ============================================================

from typing import Optional

# 默认单次最多讲解的薄弱点数量（可被 config.remediation_max_points 覆盖）
DEFAULT_MAX_POINTS = 3


def detect_weak_points(
    mastery_json: Optional[dict],
    threshold: float,
    max_points: int = DEFAULT_MAX_POINTS,
) -> list[str]:
    """返回掌握度低于阈值的知识点 id 列表。

    规则：
      - 仅统计数值型掌握度（int/float，排除 bool）且 < threshold 的点
      - 按掌握度升序排列（掌握度越低越优先，最需要先补救）
      - 截断到 max_points（取最薄弱的前 N 个）
      - mastery_json 为空 / 非 dict → 返回空列表（调用方据此返回空 remediation）

    Args:
        mastery_json: 形如 {point_id: 0..1} 的掌握度矩阵
        threshold: 掌握度阈值（低于即视为薄弱）
        max_points: 最多返回的知识点数量（<=0 时返回空）

    Returns:
        list[str]: 知识点 id 列表（升序、已截断）
    """
    if not isinstance(mastery_json, dict) or not mastery_json:
        return []

    weak: list[tuple[str, float]] = []
    for point_id, value in mastery_json.items():
        # bool 是 int 子类，需排除，避免 True/False 被误判为掌握度
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value < threshold:
            weak.append((point_id, float(value)))

    # 升序：掌握度最低的排在最前
    weak.sort(key=lambda item: item[1])

    safe_cap = max(int(max_points), 0)
    return [point_id for point_id, _ in weak[:safe_cap]]
