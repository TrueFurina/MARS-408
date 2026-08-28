# ============================================================
# API — AI 知识图谱生成（/api/knowledge-graph/*）
# 从文本/课程资料自动抽取实体关系，构建知识图谱
# 供前端可视化和 FrugalRAG/PathPlanner 消费
# ============================================================

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from shared.auth import get_current_user

logger = logging.getLogger("netlearn.knowledge_graph")
router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])


# ── 请求/响应模型 ──


class ExtractRequest(BaseModel):
    text: str = Field(..., max_length=10000, description="课程文本内容")
    subject: str = Field("computer_network", description="科目")
    enhance: bool = Field(True, description="是否优化增强")


class BatchExtractRequest(BaseModel):
    texts: list[dict] = Field(..., description="文本片段列表 [{id, title, content}]")
    subject: str = Field("computer_network", description="科目")
    merge: bool = Field(True, description="是否合并结果")


class KGQueryRequest(BaseModel):
    query: str = Field(..., max_length=500, description="查询关键词")
    subject: Optional[str] = Field(None, description="科目过滤")


# ── 助手函数 ──


def _user_id(user: dict) -> str:
    return user.get("user_id") or user.get("id") or user.get("sub", "")


def _user_name(user: dict) -> str:
    return user.get("display_name") or user.get("username", "用户")


# ── API 端点 ──


@router.post("/extract")
async def api_extract_knowledge_graph(
    body: ExtractRequest,
    user: dict = Depends(get_current_user),
):
    """从文本提取知识图谱实体和关系

    使用 LLM 从课程文本中自动抽取知识点实体和它们之间的关系，
    返回结构化 JSON 和前端可视化用的 vis.js 格式数据。
    """
    from agents.knowledge_graph import extract_entities_and_relations, kg_to_vis_json

    if len(body.text) < 20:
        raise HTTPException(status_code=422, detail="文本内容太短，至少需要 20 个字符")

    result = await extract_entities_and_relations(
        text=body.text,
        subject=body.subject,
        enhance=body.enhance,
    )

    # 生成可视化格式
    result["vis"] = kg_to_vis_json(result)

    return {
        "status": "ok",
        "subject": body.subject,
        "entities": result.get("entities", []),
        "relationships": result.get("relationships", []),
        "stats": result.get("stats", {}),
        "vis": result.get("vis", {"nodes": [], "edges": []}),
    }


@router.post("/batch-extract")
async def api_batch_extract(
    body: BatchExtractRequest,
    user: dict = Depends(get_current_user),
):
    """批量从多个文本片段生成知识图谱

    支持并行抽取多个文本片段并合并为完整图谱。
    """
    from agents.knowledge_graph import generate_knowledge_graph

    if not body.texts:
        raise HTTPException(status_code=422, detail="文本列表不能为空")
    if len(body.texts) > 10:
        raise HTTPException(status_code=422, detail="一次最多处理 10 个文本片段")

    result = await generate_knowledge_graph(
        texts=body.texts,
        subject=body.subject,
        merge=body.merge,
    )

    return {
        "status": "ok",
        "subject": body.subject,
        "merged": body.merge,
        **result,
    }


@router.post("/search")
async def api_search_kg(
    body: KGQueryRequest,
    user: dict = Depends(get_current_user),
):
    """在知识图谱中搜索相关实体和关系

    根据关键词搜索匹配的实体，返回关联的关系网络。
    """
    from db.skill_store import list_skills

    keyword = body.query.lower()
    # 从技能的知识库中搜索匹配的知识点
    # 这里简化实现：从已存储的图谱数据中搜索
    result = {
        "query": body.query,
        "entities": [],
        "relationships": [],
        "stats": {"entity_count": 0, "relation_count": 0},
    }

    # 如果有关联的图谱数据文件，从中搜索
    import os
    import json as json_mod

    kg_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "knowledge_graphs")
    if os.path.exists(kg_dir):
        for fname in os.listdir(kg_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(kg_dir, fname), "r", encoding="utf-8") as f:
                    data = json_mod.load(f)
                for e in data.get("entities", []):
                    if keyword in e.get("name", "").lower():
                        result["entities"].append(e)
                for r in data.get("relationships", []):
                    if keyword in r.get("type", "").lower():
                        result["relationships"].append(r)
            except Exception:
                continue

    # L1/L2/L3 三层学情记忆增强（低侵入：记忆薄弱点命中实体打标，个性化图谱）
    try:
        from services.memory_service import build_memory_context
        memory_ctx = build_memory_context(_user_id(user), session_id=None, max_episodes=4)
        if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
            # 从记忆上下文提取薄弱关键词，命中实体打标 weak_memory=true
            import re as _re
            weak_block = _re.search(r"薄弱[：:]\s*(.+?)(?:\n|$)", memory_ctx)
            if weak_block:
                weak_terms = [w.strip() for w in weak_block.group(1).split(",") if w.strip()]
                for e in result["entities"]:
                    name = (e.get("name") or "").lower()
                    if any(t.lower() in name for t in weak_terms):
                        e["weak_memory"] = True
    except Exception as _me:
        logger.debug(f"知识图谱记忆增强失败(降级): {_me}")

    result["stats"] = {
        "entity_count": len(result["entities"]),
        "relation_count": len(result["relationships"]),
    }

    return {"status": "ok", **result}


@router.get("/stats")
async def api_kg_stats(user: dict = Depends(get_current_user)):
    """获取知识图谱统计信息"""
    import os
    import json as json_mod

    kg_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "knowledge_graphs")
    stats = {
        "total_graphs": 0,
        "total_entities": 0,
        "total_relations": 0,
        "by_subject": {},
    }

    if os.path.exists(kg_dir):
        for fname in os.listdir(kg_dir):
            if not fname.endswith(".json"):
                continue
            stats["total_graphs"] += 1
            try:
                with open(os.path.join(kg_dir, fname), "r", encoding="utf-8") as f:
                    data = json_mod.load(f)
                stats["total_entities"] += len(data.get("entities", []))
                stats["total_relations"] += len(data.get("relationships", []))
                subject = data.get("subject", "unknown")
                if subject not in stats["by_subject"]:
                    stats["by_subject"][subject] = {"graphs": 0, "entities": 0, "relations": 0}
                stats["by_subject"][subject]["graphs"] += 1
                stats["by_subject"][subject]["entities"] += len(data.get("entities", []))
                stats["by_subject"][subject]["relations"] += len(data.get("relationships", []))
            except Exception:
                continue

    return {"status": "ok", "stats": stats}


@router.get("/list")
async def api_list_graphs(user: dict = Depends(get_current_user)):
    """列出已保存的知识图谱"""
    import os
    import json as json_mod

    kg_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "knowledge_graphs")
    graphs = []

    if os.path.exists(kg_dir):
        for fname in sorted(os.listdir(kg_dir), reverse=True):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(kg_dir, fname), "r", encoding="utf-8") as f:
                    data = json_mod.load(f)
                graphs.append({
                    "id": fname.replace(".json", ""),
                    "subject": data.get("subject", "unknown"),
                    "entity_count": len(data.get("entities", [])),
                    "relation_count": len(data.get("relationships", [])),
                    "created_at": data.get("created_at", ""),
                })
            except Exception:
                continue

    return {"status": "ok", "graphs": graphs[:20]}


# ── 大纲导入 ──


class SyllabusImportRequest(BaseModel):
    syllabus_text: str = Field(..., max_length=10000, description="教学大纲文本")
    subject: str = Field("general", description="科目")


@router.post("/import-syllabus")
async def api_import_syllabus(
    body: SyllabusImportRequest,
    user: dict = Depends(get_current_user),
):
    """从教学大纲智能导入知识图谱"""
    from agents.knowledge_graph import import_from_syllabus
    result = await import_from_syllabus(
        syllabus_text=body.syllabus_text,
        subject=body.subject,
    )
    return {
        "status": "ok",
        "entities": result.get("entities", []),
        "relationships": result.get("relationships", []),
        "stats": result.get("stats", {}),
        "vis": result.get("vis", {"nodes": [], "edges": []}),
    }


# ── 资源推荐 ──


class ResourceRecommendRequest(BaseModel):
    entity_name: str = Field(..., max_length=200, description="知识点名称")
    subject: str = Field("general", description="科目")


@router.post("/recommend-resources")
async def api_recommend_resources(
    body: ResourceRecommendRequest,
    user: dict = Depends(get_current_user),
):
    """为知识点推荐关联资源"""
    from agents.knowledge_graph import recommend_resources
    resources = await recommend_resources(
        entity_name=body.entity_name,
        subject=body.subject,
    )
    return {"status": "ok", "resources": resources}


# ── 学习路径推荐 ──


class LearningPathRequest(BaseModel):
    kg_id: str = Field(..., description="知识图谱 ID")
    start_entity: str = Field("", description="起始知识点 ID")


@router.post("/learning-path")
async def api_learning_path(
    body: LearningPathRequest,
    user: dict = Depends(get_current_user),
):
    """基于知识图谱推荐学习路径"""
    from agents.knowledge_graph import load_knowledge_graph, recommend_learning_path
    kg_data = load_knowledge_graph(body.kg_id)
    if not kg_data:
        raise HTTPException(status_code=404, detail="知识图谱不存在")
    path = recommend_learning_path(kg_data, start_entity=body.start_entity)
    return {"status": "ok", "path": path, "total_steps": len(path)}


# ── 导出 ──


@router.get("/export/{kg_id}")
async def api_export_graph(
    kg_id: str,
    fmt: str = "json",
    user: dict = Depends(get_current_user),
):
    """导出知识图谱（json/text/mermaid）"""
    from agents.knowledge_graph import (
        load_knowledge_graph, export_graph_as_mermaid, export_graph_as_text,
    )
    kg_data = load_knowledge_graph(kg_id)
    if not kg_data:
        raise HTTPException(status_code=404, detail="知识图谱不存在")

    if fmt == "mermaid":
        content = export_graph_as_mermaid(kg_data)
        media_type = "text/plain"
    elif fmt == "text":
        content = export_graph_as_text(kg_data)
        media_type = "text/plain"
    else:
        import json
        content = json.dumps(kg_data, ensure_ascii=False, indent=2)
        media_type = "application/json"

    from fastapi.responses import Response
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=knowledge-graph-{kg_id}.{fmt}"},
    )