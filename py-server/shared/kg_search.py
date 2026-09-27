# ============================================================
# 已保存知识图谱的实体/关系检索（M-3）
# ------------------------------------------------------------
# 原实现位于 agents/knowledge_graph.py 的 search_kg_entities，被
# engines/frugal_rag 用于「KG 增强查询」，形成 engines → agents 反向依赖
# （只能靠函数内延迟导入规避）。本函数只依赖 os/json + KG 目录，无智能体状态，
# 故下沉 shared：db / engines / agents 同向依赖它。
#
# agents/knowledge_graph.py 保留委托再导出，_KG_DIR 亦以本模块为单一真源。
# ============================================================

import json
import os

# 已保存知识图谱的落盘目录（py-server/data/knowledge_graphs）
_KG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "knowledge_graphs")


def search_kg_entities(query: str, subject: str = "general") -> dict:
    """在已保存的知识图谱中搜索匹配的实体和关系

    Args:
        query: 搜索关键词
        subject: 科目过滤

    Returns:
        {"entities": [...], "relationships": [...]}
    """
    keyword = query.lower()
    all_entities = []
    all_relations = []

    if not os.path.exists(_KG_DIR):
        return {"entities": [], "relationships": []}

    for fname in os.listdir(_KG_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_KG_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            if subject != "general" and data.get("subject") != subject:
                continue
            for e in data.get("entities", []):
                if keyword in e.get("name", "").lower() or keyword in e.get("description", "").lower():
                    all_entities.append(e)
            for r in data.get("relationships", []):
                if keyword in r.get("type", "").lower():
                    all_relations.append(r)
        except Exception:
            continue

    return {"entities": all_entities[:10], "relationships": all_relations[:10]}
