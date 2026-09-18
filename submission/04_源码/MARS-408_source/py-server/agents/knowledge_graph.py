# ============================================================
# AI 知识图谱生成 Agent (Knowledge Graph Generator)
# 从文本/课程资料中自动抽取实体和关系，构建结构化知识图谱
#
# 工作流: 文本输入 → LLM 实体抽取 → LLM 关系抽取 → 图谱构建 → 可视化 JSON
# 消费端: FrugalRAG 检索增强 / PathPlanner 路径规划 / 前端可视化
# ============================================================

import json
import logging
import os
import re
import uuid
from typing import Optional

from db.llm_provider import LLMProvider

logger = logging.getLogger("netlearn.knowledge_graph")


# ═══════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════

ENTITY_EXTRACTION_PROMPT = """\
你是一个计算机教育领域的知识图谱构建专家。
你的任务是从给定的课程文本中，提取所有重要的知识点实体和它们之间的关系。

## 实体类型
- concept: 核心概念（如 "TCP三次握手", "虚拟内存", "快速排序"）
- chapter: 章节/模块（如 "计算机网络-运输层", "数据结构-排序"）
- algorithm: 算法/方法（如 "二分查找", "LRU置换算法"）
- protocol: 协议/标准（如 "TCP", "HTTP", "IP"）
- structure: 数据结构（如 "链表", "栈", "二叉树"）
- property: 属性/特征（如 "时间复杂度O(n)", "可靠性"）

## 关系类型
- prerequisite: A 是 B 的前置知识（A → B）
- contains: A 包含 B（章节 → 概念）
- similar: A 与 B 相似/对比
- example: A 是 B 的实例/例子
- application: A 应用于 B

## 实体属性（必须为每个实体标注）
- importance: 重要程度（high/medium/low）
- tags: 标签数组（如 ["重点", "难点", "考点"]）
- cognitive_level: 认知维度（记忆/理解/应用/分析/评价/创造）
- category: 知识分类（事实性/概念性/程序性/元认知）

## 输出格式
必须输出 JSON 格式，严格按以下结构：
```json
{
  "entities": [
    {
      "id": "e1", "name": "实体名称", "type": "concept",
      "description": "简要描述",
      "importance": "high",
      "tags": ["重点", "考点"],
      "cognitive_level": "理解",
      "category": "概念性"
    }
  ],
  "relationships": [
    {"source": "e1", "target": "e2", "type": "prerequisite", "description": "关系描述"}
  ]
}
```

## 要求
1. 实体 ID 用 e1, e2, e3... 格式
2. 每个实体必须有 unique 的 ID 和 name
3. 关系必须连接已有的实体 ID
4. 提取不少于 5 个实体，不多于 30 个实体
"""


KG_ENHANCE_PROMPT = """\
你是一个知识图谱优化专家。
现有从课程文本中提取的知识图谱实体和关系，请根据以下要求进行优化：

1. 补充缺失的实体间关系
2. 合并重复或相似的实体
3. 添加跨章节的关联关系
4. 标注每个实体的重要程度（high/medium/low）

## 输出格式
与输入相同的 JSON 结构，但增加 importance 字段：
```json
{
  "entities": [
    {"id": "e1", "name": "实体名称", "type": "concept", "description": "描述", "importance": "high"}
  ],
  "relationships": [...]
}
```
"""


# ═══════════════════════════════════════════════════════════════
# 核心函数
# ═══════════════════════════════════════════════════════════════


async def extract_entities_and_relations(
    text: str,
    subject: str = "computer_network",
    enhance: bool = True,
) -> dict:
    """从文本中提取知识图谱实体和关系

    Args:
        text: 课程文本内容
        subject: 科目（用于上下文提示）
        enhance: 是否进行优化增强

    Returns:
        {"entities": [...], "relationships": [...], "stats": {...}}
    """
    llm = LLMProvider()

    # Step 1: 实体抽取
    user_prompt = (
        f"【科目】{subject}\n\n"
        f"【课程文本】\n{text[:4000]}\n\n"
        f"请从以上文本中提取知识点实体和它们之间的关系。"
    )

    try:
        result = await llm.text_completion(
            ENTITY_EXTRACTION_PROMPT, user_prompt,
            temperature=0.3, max_tokens=3000,
        )
        kg_data = _parse_kg_result(result)
    except Exception as e:
        logger.error(f"实体抽取 LLM 调用失败: {e}")
        kg_data = {"entities": [], "relationships": []}

    # Step 2: 优化增强
    if enhance and (kg_data["entities"] or kg_data["relationships"]):
        try:
            enhance_input = json.dumps(kg_data, ensure_ascii=False, indent=2)
            enhance_result = await llm.text_completion(
                KG_ENHANCE_PROMPT, enhance_input,
                temperature=0.3, max_tokens=2000,
            )
            enhanced = _parse_kg_result(enhance_result)
            if enhanced.get("entities"):
                kg_data = enhanced
        except Exception as e:
            logger.warning(f"图谱优化 LLM 调用失败，使用原始结果: {e}")

    # 统计信息
    kg_data["stats"] = {
        "entity_count": len(kg_data.get("entities", [])),
        "relation_count": len(kg_data.get("relationships", [])),
        "entity_types": _count_types(kg_data.get("entities", []), "type"),
        "relation_types": _count_types(kg_data.get("relationships", []), "type"),
    }

    return kg_data


def _parse_kg_result(text: str) -> dict:
    """解析 LLM 输出的 JSON 结果"""
    try:
        # 提取 ```json ... ``` 或 ``` ... ``` 之间的内容
        match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())
        # 直接解析 JSON
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"解析 KG 结果失败: {e}")
    return {"entities": [], "relationships": []}


def _count_types(items: list[dict], key: str) -> dict:
    """统计类型分布"""
    counts = {}
    for item in items:
        t = item.get(key, "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


# ═══════════════════════════════════════════════════════════════
# 图谱序列化
# ═══════════════════════════════════════════════════════════════


def kg_to_vis_json(kg_data: dict) -> dict:
    """转换为前端可视化友好的 JSON 格式

    输出格式适配 vis.js / D3.js 力导向图:
    {
        "nodes": [{id, label, title, group, value}],
        "edges": [{from, to, label, arrows, dashes}]
    }
    """
    nodes = []
    edges = []

    type_colors = {
        "concept": "#7c6af2",
        "chapter": "#3b82f6",
        "algorithm": "#06b6d4",
        "protocol": "#22c55e",
        "structure": "#f59e0b",
        "property": "#f472b6",
    }

    for entity in kg_data.get("entities", []):
        etype = entity.get("type", "concept")
        importance = entity.get("importance", "medium")
        size = {"high": 30, "medium": 22, "low": 16}.get(importance, 22)
        nodes.append({
            "id": entity["id"],
            "label": entity["name"],
            "title": f"{entity.get('name', '')}\n{entity.get('description', '')}",
            "group": etype,
            "color": type_colors.get(etype, "#7c6af2"),
            "value": size,
            "font": {"size": 14, "color": "#f8fafc"},
        })

    for rel in kg_data.get("relationships", []):
        edges.append({
            "from": rel["source"],
            "to": rel["target"],
            "label": rel.get("type", ""),
            "arrows": "to",
            "dashes": rel.get("type") == "similar",
            "color": {"color": "#94a3b8", "opacity": 0.7},
            "font": {"size": 11, "color": "#94a3b8"},
        })

    return {"nodes": nodes, "edges": edges}


# ═══════════════════════════════════════════════════════════════
# 批量文本处理（支持整章/整科）
# ═══════════════════════════════════════════════════════════════


async def generate_knowledge_graph(
    texts: list[dict],
    subject: str = "computer_network",
    merge: bool = True,
) -> dict:
    """从多个文本片段生成知识图谱

    Args:
        texts: [{id, title, content}] 文本片段列表
        subject: 科目
        merge: 是否合并所有片段的结果

    Returns:
        {"entities": [...], "relationships": [...], "stats": {...}, "vis": {...}}
    """
    import asyncio

    # 并行抽取每个片段
    async def _extract_one(t: dict) -> dict:
        combined = f"【{t.get('title', '')}】\n{t.get('content', '')}"
        return await extract_entities_and_relations(combined, subject, enhance=False)

    tasks = [_extract_one(t) for t in texts[:5]]  # 最多并行处理 5 段
    results = await asyncio.gather(*tasks, return_exceptions=True)

    if merge:
        # 合并所有结果
        all_entities = []
        all_relations = []
        seen_entities = set()
        seen_relations = set()

        for r in results:
            if isinstance(r, Exception):
                continue
            for e in r.get("entities", []):
                if e["name"] not in seen_entities:
                    seen_entities.add(e["name"])
                    all_entities.append(e)
            for rel in r.get("relationships", []):
                key = f"{rel['source']}-{rel['type']}-{rel['target']}"
                if key not in seen_relations:
                    seen_relations.add(key)
                    all_relations.append(rel)

        # 重新生成 ID
        id_map = {}
        for i, e in enumerate(all_entities):
            old_id = e["id"]
            e["id"] = f"e{i + 1}"
            id_map[old_id] = e["id"]

        for rel in all_relations:
            rel["source"] = id_map.get(rel["source"], rel["source"])
            rel["target"] = id_map.get(rel["target"], rel["target"])

        kg_data = {
            "entities": all_entities,
            "relationships": all_relations,
            "stats": {
                "entity_count": len(all_entities),
                "relation_count": len(all_relations),
                "entity_types": _count_types(all_entities, "type"),
                "relation_types": _count_types(all_relations, "type"),
            },
        }
    else:
        kg_data = {"results": results, "stats": {"count": len(results)}}

    # 生成可视化数据
    if merge:
        kg_data["vis"] = kg_to_vis_json(kg_data)

    return kg_data


# ═══════════════════════════════════════════════════════════════
# 图谱持久化（保存/加载/导出/导入）
# ═══════════════════════════════════════════════════════════════

_KG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "knowledge_graphs")


def _ensure_kg_dir():
    os.makedirs(_KG_DIR, exist_ok=True)


def save_knowledge_graph(kg_data: dict, name: str = "", subject: str = "general") -> str:
    """保存知识图谱到文件

    Args:
        kg_data: 图谱数据（含 entities, relationships）
        name: 图谱名称
        subject: 科目

    Returns:
        图谱 ID
    """
    _ensure_kg_dir()
    kg_id = uuid.uuid4().hex[:12]
    import datetime
    record = {
        "id": kg_id,
        "name": name or f"知识图谱_{kg_id[:8]}",
        "subject": subject,
        "created_at": datetime.datetime.now().isoformat(),
        "entities": kg_data.get("entities", []),
        "relationships": kg_data.get("relationships", []),
        "stats": kg_data.get("stats", {}),
    }
    path = os.path.join(_KG_DIR, f"{kg_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return kg_id


def load_knowledge_graph(kg_id: str) -> Optional[dict]:
    """从文件加载知识图谱"""
    path = os.path.join(_KG_DIR, f"{kg_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def list_knowledge_graphs() -> list[dict]:
    """列出所有已保存的知识图谱"""
    _ensure_kg_dir()
    graphs = []
    for fname in sorted(os.listdir(_KG_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_KG_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            graphs.append({
                "id": data.get("id", fname.replace(".json", "")),
                "name": data.get("name", "未命名"),
                "subject": data.get("subject", "unknown"),
                "entity_count": len(data.get("entities", [])),
                "relation_count": len(data.get("relationships", [])),
                "created_at": data.get("created_at", ""),
            })
        except Exception:
            continue
    return graphs


def delete_knowledge_graph(kg_id: str) -> bool:
    """删除知识图谱"""
    path = os.path.join(_KG_DIR, f"{kg_id}.json")
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


def export_knowledge_graph_json(kg_id: str) -> Optional[str]:
    """导出知识图谱为 JSON 字符串"""
    data = load_knowledge_graph(kg_id)
    if not data:
        return None
    return json.dumps(data, ensure_ascii=False, indent=2)


def import_knowledge_graph_json(json_str: str) -> Optional[str]:
    """从 JSON 字符串导入知识图谱"""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None
    if not data.get("entities") and not data.get("relationships"):
        return None
    kg_id = save_knowledge_graph(
        kg_data=data,
        name=data.get("name", "导入图谱"),
        subject=data.get("subject", "general"),
    )
    return kg_id


# ═══════════════════════════════════════════════════════════════
# 教材/大纲智能导入
# ═══════════════════════════════════════════════════════════════


async def import_from_syllabus(syllabus_text: str, subject: str = "general") -> dict:
    """从教学大纲智能导入知识点

    支持:
    - 章节结构识别（自动解析章节目录）
    - 知识点提取（从章节描述中提取核心概念）
    - 关系推断（基于章节顺序推断前置/后置关系）
    - 标签自动标注（根据上下文判断重点/难点/考点）

    Args:
        syllabus_text: 教学大纲文本（含章节结构和知识点描述）
        subject: 科目

    Returns:
        知识图谱数据
    """
    llm = LLMProvider()

    SYLLABUS_IMPORT_PROMPT = """\
你是一个教学大纲智能解析专家。
你的任务是从课程教学大纲中，提取知识点结构并构建知识图谱。

## 教学大纲通常包含
1. 课程基本信息（名称、学时、考核方式）
2. 章节安排（各章节标题和内容概要）
3. 教学目标和重难点

## 提取要求
1. 识别并提取所有章节和知识点实体
2. 根据章节顺序推断前置/后置关系
3. 根据教学大纲中的"重点""难点"标注，给知识点打标签
4. 标注每个知识点的认知维度（记忆/理解/应用/分析/评价/创造）

## 输出格式
与标准知识图谱 JSON 格式一致。
"""

    user_prompt = (
        f"【科目】{subject}\n\n"
        f"【教学大纲】\n{syllabus_text[:5000]}\n\n"
        f"请从以上教学大纲中提取知识点结构，构建知识图谱。"
    )

    try:
        result = await llm.text_completion(
            SYLLABUS_IMPORT_PROMPT, user_prompt,
            temperature=0.3, max_tokens=3000,
        )
        kg_data = _parse_kg_result(result)
    except Exception as e:
        logger.error(f"大纲导入 LLM 调用失败: {e}")
        kg_data = {"entities": [], "relationships": []}

    # 自动保存
    if kg_data.get("entities"):
        save_knowledge_graph(kg_data, name=f"大纲导入_{subject}", subject=subject)

    kg_data["stats"] = {
        "entity_count": len(kg_data.get("entities", [])),
        "relation_count": len(kg_data.get("relationships", [])),
        "entity_types": _count_types(kg_data.get("entities", []), "type"),
        "relation_types": _count_types(kg_data.get("relationships", []), "type"),
    }
    kg_data["vis"] = kg_to_vis_json(kg_data)

    return kg_data


# ═══════════════════════════════════════════════════════════════
# 资源关联
# ═══════════════════════════════════════════════════════════════


async def recommend_resources(entity_name: str, subject: str = "general") -> list[dict]:
    """为知识点推荐关联资源"""
    from engines.frugal_rag import frugal_rag
    resources = []
    try:
        chunks = await frugal_rag.retrieve(entity_name, course=subject, top_k=5)
        for chunk in (chunks or [])[:5]:
            resources.append({
                "type": "knowledge", "title": chunk.get("title", chunk.get("text", "")[:50]),
                "description": chunk.get("text", "")[:200], "source": "知识库",
            })
    except Exception:
        pass
    resources.append({"type": "exercise", "title": f"{entity_name} 专项练习", "description": f"针对「{entity_name}」的练习题", "action": "practice", "source": "系统生成"})
    resources.append({"type": "video", "title": f"{entity_name} 教学视频", "description": f"关于「{entity_name}」的教学视频", "action": "video", "source": "系统生成"})
    resources.append({"type": "mindmap", "title": f"{entity_name} 思维导图", "description": f"关于「{entity_name}」的知识梳理", "action": "mindmap", "source": "系统生成"})
    return resources


# ═══════════════════════════════════════════════════════════════
# 学习路径推荐
# ═══════════════════════════════════════════════════════════════


def recommend_learning_path(kg_data: dict, start_entity: str = "") -> list[dict]:
    """基于知识图谱推荐学习路径（拓扑排序）"""
    entities = kg_data.get("entities", [])
    relations = kg_data.get("relationships", [])
    prerequisites = {}
    for rel in relations:
        if rel.get("type") == "prerequisite":
            prerequisites.setdefault(rel["target"], []).append(rel["source"])

    in_degree = {e["id"]: 0 for e in entities}
    for target, sources in prerequisites.items():
        in_degree[target] = len(sources)

    queue = [eid for eid, deg in in_degree.items() if deg == 0]
    if start_entity in in_degree:
        queue = [start_entity]

    visited, path = set(), []
    while queue and len(path) < len(entities):
        current = queue.pop(0)
        if current in visited: continue
        visited.add(current)
        entity = next((e for e in entities if e["id"] == current), None)
        if entity:
            path.append({"step": len(path) + 1, "entity_id": current, "entity_name": entity.get("name", current), "type": entity.get("type", "concept")})
        for rel in relations:
            if rel.get("type") == "prerequisite" and rel["source"] == current and rel["target"] not in visited and rel["target"] not in queue:
                queue.append(rel["target"])
        for eid in in_degree:
            if eid not in visited and eid not in queue:
                queue.append(eid)
    return path


# ═══════════════════════════════════════════════════════════════
# 导出功能
# ═══════════════════════════════════════════════════════════════


def export_graph_as_mermaid(kg_data: dict) -> str:
    """将知识图谱导出为 Mermaid 流程图格式"""
    entities = kg_data.get("entities", [])
    relations = kg_data.get("relationships", [])
    lines = ["```mermaid", "graph TD"]
    for e in entities:
        eid = e["id"].replace("-", "_")
        label = e.get("name", eid).replace('"', "'")
        lines.append(f'    {eid}["{label}"]')
    for r in relations:
        src = r["source"].replace("-", "_")
        tgt = r["target"].replace("-", "_")
        rtype = r.get("type", "related")
        lines.append(f'    {src} -->|"{rtype}"| {tgt}')
    lines.append("```")
    return "\n".join(lines)


def export_graph_as_text(kg_data: dict) -> str:
    """将知识图谱导出为纯文本格式"""
    entities = kg_data.get("entities", [])
    relations = kg_data.get("relationships", [])
    lines = ["=== 知识图谱导出 ===", f"总计: {len(entities)} 个实体, {len(relations)} 条关系", ""]
    lines.append("--- 实体列表 ---")
    for e in entities:
        tags = ", ".join(e.get("tags", []))
        lines.append(f"  [{e.get('type','?')}] {e.get('name','?')} ({e.get('importance','medium')}) {tags}")
    lines.append("")
    lines.append("--- 关系列表 ---")
    for r in relations:
        src_name = next((e.get("name", e["id"]) for e in entities if e["id"] == r["source"]), r["source"])
        tgt_name = next((e.get("name", e["id"]) for e in entities if e["id"] == r["target"]), r["target"])
        lines.append(f"  {src_name} --[{r.get('type','?')}]--> {tgt_name}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 知识图谱搜索（供 FrugalRAG 增强检索使用）
# ═══════════════════════════════════════════════════════════════


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