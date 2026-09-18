# ============================================================
# API — 科目 + 知识图谱
# 从 learning.py 拆分 (D-05)
# ============================================================

import logging

from fastapi import APIRouter, Depends
from seed_data import SEED_SUBJECTS, KNOWLEDGE_GRAPH
from shared.auth import get_current_user

logger = logging.getLogger("netlearn.subjects")

router = APIRouter(prefix="", tags=["subjects"])


@router.get("/subjects")
async def subjects_list(user: dict = Depends(get_current_user)):
    """获取所有科目章节"""
    return {"subjects": SEED_SUBJECTS, "knowledge_graph": KNOWLEDGE_GRAPH}


@router.get("/knowledge-graph")
async def knowledge_graph_get(subject: str = "all", user: dict = Depends(get_current_user)):
    """获取知识图谱数据，按科目过滤"""
    # 408 四科 group 映射（与 seed_data.py 合并后的实际 group 编号一致）
    # 计网: groups 13-19 (seed_data KNOWLEDGE_GRAPH 原始编号)
    # DS:   groups 1-4 (原始) + 8-14 (调整 +7)
    # CO:   groups 5-7 (原始) + 15-21 (调整 +14)
    # OS:   groups 8-12 (原始) + 22-26 (调整 +21)
    group_map = {
        # 计网 (KNOWLEDGE_GRAPH 原始编号，未偏移)
        "overview": 13, "physical": 14, "datalink": 15,
        "network": 16, "transport": 17, "application": 18, "security": 19,
        # 数据结构 (DS_KNOWLEDGE_GRAPH 偏移 +7)
        "ds_linear": 8, "ds_stack": 9, "ds_string": 10, "ds_tree": 11,
        "ds_graph": 12, "ds_search": 13, "ds_sort": 14,
        # 计组 (CO_KNOWLEDGE_GRAPH 偏移 +14)
        "co_overview": 15, "co_data": 16, "co_memory": 17,
        "co_isa": 18, "co_cpu": 19, "co_bus": 20, "co_io": 21,
        # OS (OS_KNOWLEDGE_GRAPH 偏移 +21)
        "os_overview": 22, "os_process": 23, "os_memory": 24,
        "os_file": 25, "os_io": 26,
    }

    nodes = KNOWLEDGE_GRAPH.get("nodes", [])
    edges = KNOWLEDGE_GRAPH.get("edges", [])

    if subject != "all" and subject in group_map:
        target_group = group_map[subject]
        # 支持单个 group 过滤
        filtered_nodes = [n for n in nodes if n.get("group") == target_group]
        node_ids = {n["id"] for n in filtered_nodes}
        filtered_edges = [e for e in edges if e.get("source") in node_ids and e.get("target") in node_ids]
        return {"nodes": filtered_nodes, "edges": filtered_edges}

    return {"nodes": nodes, "edges": edges}
