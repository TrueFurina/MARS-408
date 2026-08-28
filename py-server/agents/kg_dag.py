# ============================================================
# 知识图谱 DAG（KG-DAG）— 408 四科 group(1-26) 拓扑排序
#
# INC-05 / T06：为 PathPlanner 提供「基于知识图谱依赖顺序 + 画像驱动」
# 的章节/分组序列。无 RL（真实 RL 归 P2）。
#
# 设计硬约束（设计文档 §7.2）：
#   计网 computer_network      → 1-7
#   数据结构 data_structures    → 8-14
#   计算机组成 computer_organization → 15-21
#   操作系统 operating_system   → 22-26
# 本文件是 metadata.group 的「单一真源」：seed_data_expanded 注入 chunk.group、
# main._seed_vector_db 注入 metadata.group、path_planner 拓扑排序均引用此处。
# ============================================================

from typing import Optional

# ── subject → group 映射（单一真源）──
# 一个 subject 可映射到其科内的某个 group；多个 subject 共享同一 group 是允许的
# （group 是「章节分组编号」，并非 subject 唯一编号）。
SUBJECT_GROUP_MAP = {
    # 计算机网络 (1-7)
    "overview": 1, "physical": 2, "datalink": 3, "network": 4, "transport": 5,
    "application": 6, "security": 7, "cn": 4,
    # 数据结构 (8-14)
    "ds": 8, "ds_linear": 8, "ds_stack": 9, "ds_string": 10, "ds_tree": 11,
    "ds_graph": 12, "ds_search": 13, "ds_sort": 14, "ds_queue": 9,
    # 计算机组成原理 (15-21)
    "co": 15, "co_overview": 15, "co_data": 16, "co_isa": 16, "co_memory": 17,
    "co_cpu": 18, "co_bus": 19, "co_io": 20,
    # 操作系统 (22-26)
    "os": 22, "os_overview": 22, "os_process": 23, "os_memory": 24,
    "os_file": 25, "os_io": 26,
}

# 四科 group 范围（用于「四科全覆盖」校验与弱项推导）
SUBJECT_GROUP_SPAN = {
    "computer_network": 7,
    "data_structures": 7,
    "computer_organization": 7,
    "operating_system": 5,
}

# 关键词 → 科目（用于从画像/诊断薄弱文本推导弱项 group 起点）
SUBJECT_KEYWORD_MAP = {
    "计网": "computer_network", "计算机网络": "computer_network", "网络": "computer_network",
    "数据结构": "data_structures", "DS": "data_structures",
    "计组": "computer_organization", "计算机组成": "computer_organization", "组成原理": "computer_organization",
    "操作系统": "operating_system", "OS": "operating_system",
}

# 科内 g→g+1 依赖；科间默认 计网1-7→数据结构8-14→计组15-21→操作系统22-26
# 线性链 1→2→…→26 天然编码上述约束（8 依赖 7，15 依赖 14，22 依赖 21）。
GROUP_PREREQS: dict[int, list[int]] = {g: [g - 1] for g in range(2, 27)}


def chapter_to_group(subject: str, chapter: Optional[str] = None) -> int:
    """subject(以及可选 chapter) → group(1-26)。

    找不到精确 subject 时按前缀兜底，保证每条 chunk 都能落入 1-26 的某个 group。
    """
    if subject in SUBJECT_GROUP_MAP:
        return SUBJECT_GROUP_MAP[subject]
    s = subject or ""
    if s.startswith("co_"):
        return 15
    if s.startswith("os_"):
        return 22
    if s.startswith("ds_"):
        return 8
    return 1


def _weak_group_for_subject(subject: str) -> int:
    return SUBJECT_GROUP_MAP.get(subject, 1)


def topological_sort(
    weak_groups: Optional[list[int]] = None,
    profile: Optional[dict] = None,
) -> list[int]:
    """对 1-26 个 group 做拓扑排序。

    Args:
        weak_groups: 画像/诊断判定的弱项 group 列表，会被优先排到前面（仍保持依赖关系）。
        profile: 学生画像（用于 goal 调整科间顺序，默认保持 计网→数据→计组→操作系统）。

    Returns:
        依赖有序的 group 序列（1-26 拓扑序，弱项前置）。
    """
    weak = set(weak_groups or [])
    goal = (profile or {}).get("goal", "general") if isinstance(profile, dict) else "general"

    # 构造邻接表与入度（线性链 1→26）
    indeg = {g: 0 for g in range(1, 27)}
    adj: dict[int, list[int]] = {g: [] for g in range(1, 27)}
    for g in range(1, 27):
        for pre in GROUP_PREREQS.get(g, []):
            adj[pre].append(g)
            indeg[g] += 1

    # 可用节点中，弱项优先、其次小组号优先
    def _priority(g: int):
        return (0 if g in weak else 1, g)

    available = [g for g in range(1, 27) if indeg[g] == 0]
    order: list[int] = []
    while available:
        available.sort(key=_priority)
        g = available.pop(0)
        order.append(g)
        for ng in adj[g]:
            indeg[ng] -= 1
            if indeg[ng] == 0:
                available.append(ng)

    # 若 profile.goal 需要把某一科整体前置（如 exam 更重 OS），可在 order 上做稳定重排；
    # 默认顺序（线性依赖）已满足「KG 依赖 + 弱项优先」，此处保持最小变更。
    _ = goal  # 预留：未来可按 goal 调整科间相对顺序
    return order


def subject_chapters_in_order(profile: Optional[dict] = None) -> list[str]:
    """返回四科 subject 的拓扑顺序（按 group 起点排序），供前端/路径展示使用。"""
    ordered = topological_sort(profile=profile)
    seen = []
    for g in ordered:
        subj = next((k for k, v in SUBJECT_GROUP_MAP.items() if v == g), None)
        if subj and subj not in seen:
            seen.append(subj)
    return seen
