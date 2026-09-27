# ============================================================
# 知识图谱 DAG（KG-DAG）—— 兼容别名（M-3 重构后）
# ------------------------------------------------------------
# 实现已下沉至 shared/kg_dag.py：本模块是纯数据表 + 纯函数，但 db/graph_db.py
# 需要引用它，留在 agents 会形成 db → agents 反向依赖。下沉后方向单一。
#
# 本文件仅做**委托再导出**，不复制任何实现（单一真值源 = shared/kg_dag）。
# 新代码请直接 `from shared.kg_dag import ...`。
# ============================================================

from shared.kg_dag import (  # noqa: F401
    GROUP_PREREQS,
    SUBJECT_GROUP_MAP,
    SUBJECT_GROUP_SPAN,
    SUBJECT_KEYWORD_MAP,
    _weak_group_for_subject,
    chapter_to_group,
    subject_chapters_in_order,
    topological_sort,
)

__all__ = [
    "GROUP_PREREQS",
    "SUBJECT_GROUP_MAP",
    "SUBJECT_GROUP_SPAN",
    "SUBJECT_KEYWORD_MAP",
    "_weak_group_for_subject",
    "chapter_to_group",
    "subject_chapters_in_order",
    "topological_sort",
]
