# -*- coding: utf-8 -*-
"""展示页（src/views/ShowcaseView.vue）对外宣称的两条长期不变量（2026-09-28 审查新增）

展示页是评审直接看到的页面，上面的数字**没有任何运行时报错**保护：写错既不崩也不红，
只会悄悄误导。以下两条的共同点正是：**违反时静默**。

1. 预设模板数必须等于 `db.skill_store.get_templates()` 的真实条目数 ——
   实测：页面长期写「8 个预设模板」，而真值为 **21**（模板逐年累积，页面没跟上）。
2. LangGraph 节点数必须等于 `agents/graph.py` 的真实业务节点数 ——
   「N 节点」在本仓库是**两种定义**（见审查报告 D-5）：
   「11」= 编译图业务节点数（含前置 Triage 路由），「10」= Triage 之后的主流水线本体。
   展示页对「LangGraph 图本身」的表述统一采用「11」口径，故此处锁 11。

⚠️ 范围边界（勿扩大）：内部可视化组件（LangGraphFlow / FrugalRAGPanel / EngineView）
**实际只绘制 10 个节点**，它们的「10 节点」是**准确**的，不在本测试范围内。
曾经就是因为搞不清这一点，才差点把正确的表述批量改错。
"""

import re
from pathlib import Path

# tests/ → py-server/ → 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
SHOWCASE = REPO_ROOT / "src" / "views" / "ShowcaseView.vue"


def _showcase_text() -> str:
    # 声明缺失时必须是 FAIL 而不是静默通过：没有声明就没有矛盾可查。
    assert SHOWCASE.is_file(), f"展示页缺失，无法核对对外宣称: {SHOWCASE}"
    return SHOWCASE.read_text(encoding="utf-8")


def test_showcase_preset_template_count_matches_skill_store():
    """对外展示页宣称的「预设模板数」必须等于真实模板条目数。

    2026-09-28 审查实测：页面写「8 个预设模板」，`db/skill_store.py` 的
    `_BUILTIN_TEMPLATES` 实为 **21** 条，且 `get_templates()` 不做任何过滤，
    前端拿到的就是 21 条。属典型的「数字曾经为真、后来没人同步」的漂移。
    """
    from db.skill_store import get_templates

    real = len(get_templates())
    m = re.search(r"(\d+)\s*个预设模板", _showcase_text())

    assert m, "展示页未声明预设模板数，对外口径失锚"
    assert int(m.group(1)) == real, (
        f"展示页宣称 {m.group(1)} 个预设模板，而 _BUILTIN_TEMPLATES 实为 {real} 个"
        "（模板会持续新增，该数字天然易漂，故需本断言长期兜住）"
    )


def test_showcase_langgraph_node_count_matches_graph():
    """展示页**所有**「N 节点 LangGraph」表述都必须等于图的真实业务节点数。

    这里特意用 findall 检查**每一处**而非第一处：本轮修复前，同一页面里
    标题写「11 节点」、架构场景描述写「10 节点」，观众一眼就会看到自相矛盾。
    2026-09-28 审查核定的口径：图上业务节点 = 11（不含框架虚拟节点 `__start__`）。
    """
    from agents.graph import create_agent_graph

    compiled = create_agent_graph()
    real = len([n for n in compiled.nodes if not n.startswith("__")])

    found = re.findall(r"(\d+)\s*节点\s*LangGraph", _showcase_text())
    assert found, "展示页未声明 LangGraph 节点数，对外口径失锚"

    wrong = sorted({int(n) for n in found if int(n) != real})
    assert not wrong, (
        f"展示页出现 {wrong} 节点的写法，而 agents/graph.py 真值为 {real}；"
        "同一页面必须口径一致（注：内部可视化组件只画 10 个节点，属另一种定义，不在此核对）"
    )
