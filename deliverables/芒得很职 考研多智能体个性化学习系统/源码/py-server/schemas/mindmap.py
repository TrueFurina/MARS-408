"""思维导图 Agent 的数据模型定义

节点树结构 + 掌握度标注 + 多格式渲染辅助。
被 agents/mindmap.py 使用, 也可被路径规划 Agent 消费 (weak_points)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MasteryLevel(str, Enum):
    """知识点掌握度等级"""
    MASTERED = "mastered"      # >= 0.8 已掌握
    WEAK = "weak"              # 0.5 ~ 0.8 薄弱
    UNLEARNED = "unlearned"    # < 0.5 或画像中无记录


# Mermaid 渲染时的颜色映射 (掌握=绿, 薄弱=橙, 未学=灰)
MASTERY_COLORS = {
    MasteryLevel.MASTERED: "#1D9E75",
    MasteryLevel.WEAK: "#EF9F27",
    MasteryLevel.UNLEARNED: "#888780",
}

MASTERY_LABELS = {
    MasteryLevel.MASTERED: "已掌握",
    MasteryLevel.WEAK: "薄弱",
    MasteryLevel.UNLEARNED: "未学",
}


@dataclass
class MindMapNode:
    """思维导图的单个节点"""
    title: str                                    # 知识点名称
    level: int                                    # 层级深度 (0=根)
    children: list[MindMapNode] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)  # 核心考点
    difficulty: str = "medium"                    # easy / medium / hard

    # 掌握度标注 (Step 3 填充)
    mastery: Optional[MasteryLevel] = None
    mastery_score: float = 0.0                   # 0.0 ~ 1.0

    def count_all(self) -> int:
        """统计自身 + 所有子节点数 (不含根)"""
        total = 0
        for child in self.children:
            total += 1 + child.count_all()
        return total

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "level": self.level,
            "key_points": self.key_points,
            "difficulty": self.difficulty,
            "mastery": self.mastery.value if self.mastery else None,
            "mastery_score": self.mastery_score,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class MindMapRequest:
    """主调度 Agent 传给思维导图 Agent 的请求"""
    topic: str               # 主题, 如 "数据结构-树与二叉树"
    subject: str             # 科目, 如 "数据结构" / "操作系统"
    profile: dict            # 学生画像 (至少含 knowledge_foundation 维度)
    output_formats: list[str] = field(
        default_factory=lambda: ["mermaid", "json", "markdown"]
    )
    max_depth: int = 4       # 导图最大层级深度


@dataclass
class MindMapStats:
    """导图统计信息"""
    total: int = 0
    mastered: int = 0
    weak: int = 0
    unlearned: int = 0

    @property
    def coverage(self) -> float:
        """已掌握覆盖率"""
        return self.mastered / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "mastered": self.mastered,
            "weak": self.weak,
            "unlearned": self.unlearned,
            "coverage": round(self.coverage, 2),
        }


@dataclass
class MindMapResult:
    """思维导图 Agent 的输出"""
    tree: MindMapNode
    stats: MindMapStats
    mermaid: Optional[str] = None
    json_tree: Optional[str] = None
    markdown: Optional[str] = None
    weak_points: list[str] = field(default_factory=list)  # 薄弱知识点清单 (给路径规划 Agent 用)

    def to_dict(self) -> dict:
        """序列化为可写入 AgentState 的字典"""
        return {
            "mermaid": self.mermaid,
            "json": self.json_tree,
            "markdown": self.markdown,
            "weak_points": self.weak_points,
            "stats": self.stats.to_dict(),
            "tree": self.tree.to_dict(),
        }
