# ============================================================
# 思维导图 Agent (MindMap Generator)
# 4步流水线: 检索参考 → Qwen2.5生成骨架 → 画像标注掌握度 → 多格式渲染
#
# 作为 generator_cluster 的子 Agent 被调用, 不直接暴露给学生。
# 输出 weak_points 供路径规划 Agent 消费。
# ============================================================

import json
import logging
from typing import Optional

from db.llm_provider import LLMProvider
from schemas.mindmap import (
    MasteryLevel,
    MASTERY_COLORS,
    MASTERY_LABELS,
    MindMapNode,
    MindMapResult,
    MindMapStats,
)

logger = logging.getLogger("netlearn.mindmap")


# ============================================================
# Prompt 模板 (后续可迁移到 prompts.py 统一管理)
# ============================================================

SKELETON_GENERATION_PROMPT = """\
你是计算机408考研(数据结构/计算机组成原理/操作系统/计算机网络)知识体系专家。
请为主题「{topic}」生成结构化的知识骨架树。

## 检索到的参考材料
{retrieved_context}

## 要求
1. 生成 {max_depth} 层深度的知识树: 根 -> 大类 -> 知识点 -> 子知识点
2. 每个节点必须包含以下字段:
   - title: 知识点名称 (简洁, 5-15字)
   - level: 层级 (0=根, 1=大类, 2=知识点, 3=子知识点)
   - key_points: 核心考点列表 (2-4个, 每个不超过20字)
   - difficulty: 难度 (easy / medium / hard)
   - children: 子节点列表
3. 覆盖408考研大纲要求的全部知识点, 不要遗漏
4. 知识点粒度适中:
   - 不要太粗 (如只写"二叉树"不展开)
   - 不要太细 (如"BST第3种删除情况的LR旋转")

## 输出格式
严格输出以下JSON, 不要任何额外文字或markdown标记:

{{
  "title": "{topic}",
  "level": 0,
  "key_points": [],
  "difficulty": "medium",
  "children": [
    {{
      "title": "...",
      "level": 1,
      "key_points": ["考点1", "考点2"],
      "difficulty": "medium",
      "children": [
        {{
          "title": "...",
          "level": 2,
          "key_points": ["..."],
          "difficulty": "easy",
          "children": []
        }}
      ]
    }}
  ]
}}"""

SKELETON_FALLBACK_PROMPT = """\
你是计算机408考研知识体系专家。请凭你的知识为主题「{topic}」生成知识骨架树。
{max_depth} 层深度, 覆盖考研大纲全部知识点。
输出格式: title / level / key_points / difficulty / children 的嵌套JSON。
只输出JSON, 不要其他文字。"""


# ============================================================
# 主入口函数 (generator_cluster 调用)
# ============================================================

async def generate_mindmap(
    topic: str,
    profile: dict,
    knowledge_context: str,
    llm: LLMProvider,
    max_depth: int = 4,
    memory_context: str = "",
) -> Optional[MindMapResult]:
    """生成思维导图

    Args:
        topic: 学习主题, 如 "TCP三次握手"
        profile: 学生画像 (含 knowledge_foundation 维度)
        knowledge_context: FrugalRAG 检索到的知识上下文 (已格式化的文本)
        llm: LLMProvider 实例
        max_depth: 导图最大层级深度
        memory_context: L1/L2/L3 三层学情记忆上下文（可选，低侵入注入）

    Returns:
        MindMapResult 或 None (生成失败时)
    """
    logger.info(f"[MindMap] 开始生成, topic={topic}")

    try:
        # Step 1: 已由 retriever 完成, knowledge_context 直接传入

        # Step 2: Qwen2.5 生成知识骨架（注入三层学情记忆，薄弱点驱动标注）
        tree = await _generate_skeleton(topic, knowledge_context, llm, max_depth, memory_context)
        if tree is None:
            logger.warning(f"[MindMap] 骨架生成失败, 返回None")
            return None

        # Step 3: 标注掌握度 (画像交叉 + 记忆薄弱点)
        _annotate_mastery(tree, profile)
        if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
            _annotate_memory_weak(tree, memory_context)

        # Step 4: 统计 + 多格式渲染
        stats = _compute_stats(tree)
        weak_points = _extract_weak_points(tree)

        result = MindMapResult(
            tree=tree,
            stats=stats,
            weak_points=weak_points,
        )
        result.mermaid = _to_mermaid(tree)
        result.json_tree = _tree_to_json(tree)
        result.markdown = _to_markdown(tree)

        logger.info(
            f"[MindMap] 完成: {stats.total}个知识点, "
            f"已掌握{stats.mastered}/薄弱{stats.weak}/未学{stats.unlearned}"
        )
        return result

    except Exception as e:
        logger.error(f"[MindMap] 生成失败: {e}", exc_info=True)
        return None


# ============================================================
# Step 2: Qwen2.5 生成知识骨架树
# ============================================================

async def _generate_skeleton(
    topic: str,
    knowledge_context: str,
    llm: LLMProvider,
    max_depth: int,
    memory_context: str = "",
) -> Optional[MindMapNode]:
    """调用 LLM 生成知识骨架, 返回解析后的 MindMapNode 树（可选注入三层学情记忆）"""
    if knowledge_context and knowledge_context.strip():
        prompt = SKELETON_GENERATION_PROMPT.format(
            topic=topic,
            retrieved_context=knowledge_context,
            max_depth=max_depth,
        )
    else:
        prompt = SKELETON_FALLBACK_PROMPT.format(
            topic=topic,
            max_depth=max_depth,
        )

    # L1/L2/L3 三层学情记忆（低侵入注入：薄弱点驱动导图重点标注）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        prompt += f"\n\n【学生历史学情记忆】\n{memory_context[:500]}\n请对其中标注的薄弱知识点在导图中重点突出。"

    response = await llm.text_completion(
        system_prompt="你是计算机408考研知识体系专家, 只输出JSON。",
        user_prompt=prompt,
        temperature=0.3,    # 低温度保证结构稳定
        max_tokens=4096,
    )

    tree_dict = _parse_json_response(response)
    if tree_dict is None:
        logger.warning(f"[MindMap] JSON解析失败, response前200字: {response[:200]}")
        return None

    return _dict_to_node(tree_dict, level=0)


# ============================================================
# Step 3: 标注掌握度 (画像交叉, 纯程序化, 不调LLM)
# ============================================================

def _annotate_mastery(node: MindMapNode, profile: dict) -> None:
    """递归标注每个节点的掌握度

    profile 结构 (兼容两种格式):
        格式A (knowledge_foundation 嵌套):
            {"knowledge_foundation": {"数据结构": {"二叉树遍历": {"mastery": 0.9}}}}
        格式B (扁平 weak_points):
            {"weak_points": "二叉树遍历,AVL平衡树", "knowledge_base": "beginner"}

    匹配策略:
        1. 从 knowledge_foundation 精确/包含匹配 (带长度比例校验)
        2. 降级到 weak_points 关键词匹配
        3. 未匹配 -> UNLEARNED
    """
    knowledge_foundation = profile.get("knowledge_foundation", {})
    weak_points_str = profile.get("weak_points", "")
    weak_points_set = set()
    if weak_points_str and isinstance(weak_points_str, str):
        weak_points_set = {w.strip() for w in weak_points_str.split(",") if w.strip()}

    # 从 knowledge_foundation 提取扁平化的知识点→分数映射
    profile_data = {}
    if isinstance(knowledge_foundation, dict) and knowledge_foundation:
        for subj, points in knowledge_foundation.items():
            if isinstance(points, dict):
                for pt_name, pt_val in points.items():
                    if isinstance(pt_val, dict):
                        profile_data[pt_name] = pt_val.get("mastery", 0.0)
                    elif isinstance(pt_val, (int, float)):
                        profile_data[pt_name] = float(pt_val)

    _annotate_node_recursive(node, profile_data, weak_points_set)


def _annotate_node_recursive(
    node: MindMapNode,
    profile_data: dict,
    weak_points_set: set,
) -> None:
    """递归标注单个节点及其子树"""
    score = _lookup_mastery_score(node.title, profile_data)

    # 如果 knowledge_foundation 没匹配到, 检查 weak_points
    if score == 0.0 and node.title in weak_points_set:
        score = 0.5  # 薄弱点标记为 WEAK (刚好达到薄弱阈值)

    node.mastery_score = score
    node.mastery = _score_to_level(score)

    for child in node.children:
        _annotate_node_recursive(child, profile_data, weak_points_set)


def _annotate_memory_weak(root: MindMapNode, memory_context: str) -> None:
    """从 L1/L2/L3 记忆上下文提取薄弱关键词，递归标注命中节点为薄弱（低侵入）

    对标 HKU-DeepTutor 记忆驱动：记忆薄弱点在导图中优先突出。
    """
    import re as _re
    # 兼容 "薄弱点: xxx" / "薄弱: xxx" / "薄弱点：xxx" 三种格式（P0① 实测修复：
    # 原正则 "薄弱[：:]" 无法匹配 "薄弱点:" —— "薄弱"与冒号之间隔了"点"字，导致标注失效）
    weak_block = _re.search(r"薄弱点?[：:]\s*(.+?)(?:\n|$)", memory_context or "")
    if not weak_block:
        return
    weak_terms = [w.strip().lower() for w in weak_block.group(1).split(",") if w.strip()]
    if not weak_terms:
        return

    def _walk(node: MindMapNode) -> None:
        title = (node.title or "").lower()
        # 双向包含匹配：薄弱词是标题子串（正向）或标题是薄弱词子串（LLM 精简标题，P0① 修复）
        if any(t in title or title in t for t in weak_terms):
            # 记忆薄弱点命中 → 统一置标准薄弱分 0.5。
            # 覆盖：未标注(0.0)/未学(UNLEARNED 0.0)/画像较低分/已掌握(>0.5 降级)；
            # 已为 0.5(WEAK) 时保持。端到端实测修复：_annotate_mastery 先行会把
            # 未匹配节点标为 UNLEARNED(0.0)，原 mastery is None 判断在此场景失效。
            if node.mastery_score != 0.5:
                node.mastery_score = 0.5
        for child in (node.children or []):
            _walk(child)

    _walk(root)


def _lookup_mastery_score(title: str, profile_data: dict) -> float:
    """在画像数据中查找知识点的掌握度分数

    匹配策略:
        1. 精确名称匹配
        2. 包含匹配 + 长度比例校验 (防止 "二叉树" 误匹配 "二叉树遍历")
           只有当短串长度 >= 长串长度 * 0.7 时才算包含匹配
        3. 未匹配 -> 返回 0.0
    """
    # 1. 精确匹配
    if title in profile_data:
        return float(profile_data[title])

    # 2. 包含匹配 (带长度比例校验)
    for key, val in profile_data.items():
        if not isinstance(key, str) or not key:
            continue
        min_len = min(len(title), len(key))
        max_len = max(len(title), len(key))
        if max_len == 0 or min_len / max_len < 0.7:
            continue
        if title in key or key in title:
            return float(val)

    # 3. 未匹配
    return 0.0


def _score_to_level(score: float) -> MasteryLevel:
    if score >= 0.8:
        return MasteryLevel.MASTERED
    elif score >= 0.5:
        return MasteryLevel.WEAK
    else:
        return MasteryLevel.UNLEARNED


# ============================================================
# Step 4a: 统计 + 薄弱点提取
# ============================================================

def _compute_stats(tree: MindMapNode) -> MindMapStats:
    stats = MindMapStats()
    _count_recursive(tree, stats, is_root=True)
    return stats


def _count_recursive(node: MindMapNode, stats: MindMapStats, is_root: bool = False) -> None:
    if not is_root:
        stats.total += 1
        if node.mastery == MasteryLevel.MASTERED:
            stats.mastered += 1
        elif node.mastery == MasteryLevel.WEAK:
            stats.weak += 1
        else:
            stats.unlearned += 1
    for child in node.children:
        _count_recursive(child, stats)


def _extract_weak_points(tree: MindMapNode) -> list[str]:
    """提取薄弱和未学的知识点, 供路径规划 Agent 使用"""
    weak = []
    _collect_weak(tree, weak, is_root=True)
    return weak


def _collect_weak(node: MindMapNode, weak: list[str], is_root: bool = False) -> None:
    if not is_root and node.mastery in (MasteryLevel.WEAK, MasteryLevel.UNLEARNED):
        weak.append(node.title)
    for child in node.children:
        _collect_weak(child, weak)


# ============================================================
# Step 4b: Mermaid 渲染
# ============================================================

def _to_mermaid(tree: MindMapNode) -> str:
    """转换为 Mermaid mindmap 语法"""
    lines = ["mindmap"]
    _node_to_mermaid(tree, lines, depth=1)
    return "\n".join(lines)


def _node_to_mermaid(node: MindMapNode, lines: list[str], depth: int) -> None:
    indent = "  " * depth

    if depth == 1:
        lines.append(f"{indent}root(({node.title}))")
    else:
        node_id = f"id_{depth}_{abs(hash(node.title)) % 10000}"
        if node.mastery == MasteryLevel.MASTERED:
            lines.append(f'{indent}{node_id}["{node.title}"]:::mastered')
        elif node.mastery == MasteryLevel.WEAK:
            lines.append(f'{indent}{node_id}{{"{node.title}"}}:::weak')
        else:
            lines.append(f"{indent}{node.title}")
        if node.key_points:
            for kp in node.key_points[:2]:
                lines.append(f"{indent}  - {kp}")

    for child in node.children:
        _node_to_mermaid(child, lines, depth + 1)


# ============================================================
# Step 4c: JSON 渲染
# ============================================================

def _tree_to_json(tree: MindMapNode, indent: int = 2) -> str:
    return json.dumps(tree.to_dict(), ensure_ascii=False, indent=indent)


# ============================================================
# Step 4d: Markdown 渲染 (Markmap 兼容)
# ============================================================

def _to_markdown(tree: MindMapNode) -> str:
    lines = []
    _node_to_markdown(tree, lines, depth=1)
    return "\n".join(lines)


def _node_to_markdown(node: MindMapNode, lines: list[str], depth: int) -> None:
    prefix = "#" * min(depth, 6)
    mastery_tag = ""
    if depth > 1 and node.mastery:
        label = MASTERY_LABELS.get(node.mastery, "")
        score_pct = int(node.mastery_score * 100)
        mastery_tag = f" `{label} {score_pct}%`"

    lines.append(f"{prefix} {node.title}{mastery_tag}")

    if node.key_points:
        lines.append("")
        for kp in node.key_points:
            lines.append(f"- {kp}")

    if node.children:
        lines.append("")

    for child in node.children:
        _node_to_markdown(child, lines, depth + 1)
        lines.append("")


# ============================================================
# 工具方法
# ============================================================

def _parse_json_response(response: str) -> Optional[dict]:
    """解析 LLM 返回的 JSON (容错处理)"""
    cleaned = response.strip()

    # 去掉 markdown 代码块标记
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        # 尝试提取 JSON 子串
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                pass
        logger.warning(f"[MindMap] JSON解析失败: {e}")
        return None


def _dict_to_node(d: dict, level: int) -> MindMapNode:
    """将字典递归转换为 MindMapNode"""
    node = MindMapNode(
        title=d.get("title", ""),
        level=level,
        key_points=d.get("key_points", []),
        difficulty=d.get("difficulty", "medium"),
    )
    for child_dict in d.get("children", []):
        child = _dict_to_node(child_dict, level + 1)
        node.children.append(child)
    return node
