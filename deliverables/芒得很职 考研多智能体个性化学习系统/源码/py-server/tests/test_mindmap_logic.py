# ============================================================
# 单元测试骨架：MindMapAgent 纯逻辑（零原生库依赖）
#
# 只覆盖 agents/mindmap.py 的纯程序化函数，不触发任何 LLM / embedder /
# numpy / torch / 网络。可在 CI 干净环境直接 pytest 收集并运行。
#
# 覆盖点（对应测试覆盖盲区 T1–T5 补充）：
#   - _lookup_mastery_score  0.7 长度比例模糊匹配的命中/未命中边界
#   - _score_to_level        0.5 / 0.8 阈值边界（MASTERED/WEAK/UNLEARNED）
#   - _to_mermaid / _to_markdown  已知输入→输出渲染快照
#   - _parse_json_response   带 ``` 围栏与畸形 JSON 的容错
#   - _annotate_mastery      画像→掌握度标注流水线（纯逻辑集成）
#
# 注意：_to_mermaid 内部用 abs(hash(title))%10000 生成节点 id，
# hash() 受 PYTHONHASHSEED 影响；本文件通过在同进程内用相同 hash 表达式
# 计算期望值，保证快照在单次运行内确定性一致（不依赖环境变量）。
# ============================================================

import pytest

pytestmark = pytest.mark.unit

from schemas.mindmap import MindMapNode, MasteryLevel
from agents.mindmap import (
    _lookup_mastery_score,
    _score_to_level,
    _to_mermaid,
    _to_markdown,
    _parse_json_response,
    _annotate_mastery,
    _annotate_memory_weak,
)


# ────────────────────────────────────────────────────────────
# _lookup_mastery_score：0.7 长度比例模糊匹配边界
# ────────────────────────────────────────────────────────────

def test_lookup_mastery_exact_match():
    pd = {"二叉树遍历": 0.9}
    assert _lookup_mastery_score("二叉树遍历", pd) == 0.9


def test_lookup_mastery_contains_hit_above_07_ratio():
    # title 完全包含于 key，且 min/max 长度比 >= 0.7 → 命中
    # len("二叉搜索树")=5, len("二叉搜索树遍历")=7, 5/7≈0.714
    pd = {"二叉搜索树遍历": 0.7}
    assert _lookup_mastery_score("二叉搜索树", pd) == 0.7


def test_lookup_mastery_contains_miss_below_07_ratio():
    # 短串远小于长串，长度比 < 0.7 → 不命中
    # 这正是防 "二叉树" 误匹配 "二叉树遍历" 的边界（3/5=0.6 < 0.7）
    pd = {"二叉树遍历": 0.9}
    assert _lookup_mastery_score("二叉树", pd) == 0.0


def test_lookup_mastery_ratio_boundary_07_inclusive():
    # 构造恰好 0.7 的长度比（title 7 / key 10）且包含 → 应命中（阈值含 0.7）
    pd = {"abcdefghij": 0.85}  # key 长度 10
    assert _lookup_mastery_score("abcdefg", pd) == 0.85  # title 长度 7, 7/10=0.7


def test_lookup_mastery_ratio_just_below_07_miss():
    # 长度比 0.6 (< 0.7) 即使包含也不命中
    pd = {"abcdefghij": 0.85}  # key 长度 10
    assert _lookup_mastery_score("abcdef", pd) == 0.0  # title 长度 6, 6/10=0.6


def test_lookup_mastery_no_containment_but_high_ratio_miss():
    # 长度比 = 1.0 但互不包含 → 仍不命中
    pd = {"苹果": 0.4}
    assert _lookup_mastery_score("香蕉", pd) == 0.0


def test_lookup_mastery_empty_profile_returns_zero():
    assert _lookup_mastery_score("任意知识点", {}) == 0.0


# ────────────────────────────────────────────────────────────
# _score_to_level：0.5 / 0.8 阈值边界
# ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected", [
    (0.9, MasteryLevel.MASTERED),
    (0.8, MasteryLevel.MASTERED),      # 阈值含 0.8
    (0.799, MasteryLevel.WEAK),
    (0.5, MasteryLevel.WEAK),          # 阈值含 0.5
    (0.49, MasteryLevel.UNLEARNED),
    (0.0, MasteryLevel.UNLEARNED),
    (-0.1, MasteryLevel.UNLEARNED),
])
def test_score_to_level_thresholds(score, expected):
    assert _score_to_level(score) == expected


# ────────────────────────────────────────────────────────────
# _to_mermaid：渲染快照（节点 id 用同进程 hash 表达式保证确定性）
# ────────────────────────────────────────────────────────────

def test_to_mermaid_snapshot():
    root = MindMapNode(
        title="根主题", level=0,
        children=[
            MindMapNode(title="已掌握点", level=1, mastery=MasteryLevel.MASTERED,
                        key_points=["要点A", "要点B"]),
            MindMapNode(title="薄弱点", level=1, mastery=MasteryLevel.WEAK,
                        key_points=["要点C"]),
            MindMapNode(title="未学点", level=1, mastery=MasteryLevel.UNLEARNED),
        ],
    )
    out = _to_mermaid(root)

    # 同进程内用相同 hash 表达式推导期望值，避免 PYTHONHASHSEED 抖动
    m = lambda t: f"id_2_{abs(hash(t)) % 10000}"
    expected = "\n".join([
        "mindmap",
        "  root((根主题))",
        f'    {m("已掌握点")}["已掌握点"]:::mastered',
        "      - 要点A",
        "      - 要点B",
        f'    {m("薄弱点")}{{"薄弱点"}}:::weak',
        "      - 要点C",
        "    未学点",
    ])
    assert out == expected


# ────────────────────────────────────────────────────────────
# _to_markdown：渲染快照（纯确定性，无 hash）
# ────────────────────────────────────────────────────────────

def test_to_markdown_snapshot():
    root = MindMapNode(
        title="根主题", level=0,
        children=[
            MindMapNode(title="薄弱点", level=1, mastery=MasteryLevel.WEAK,
                        mastery_score=0.6, key_points=["SYN", "ACK"]),
        ],
    )
    out = _to_markdown(root)
    expected = "\n".join([
        "# 根主题",
        "",
        "## 薄弱点 `薄弱 60%`",
        "",
        "- SYN",
        "- ACK",
        "",
    ])
    assert out == expected


# ────────────────────────────────────────────────────────────
# _parse_json_response：``` 围栏 & 畸形 JSON 容错
# ────────────────────────────────────────────────────────────

def test_parse_json_clean():
    assert _parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_with_fences():
    resp = '```json\n{"a": 1, "b": [1, 2]}\n```'
    assert _parse_json_response(resp) == {"a": 1, "b": [1, 2]}


def test_parse_json_fenced_with_language_and_trailing_ws():
    resp = '```json\n{"x": "y"}\n```   '
    assert _parse_json_response(resp) == {"x": "y"}


def test_parse_json_malformed_surrounded_by_text():
    # 含前后噪声文本 + 完整 JSON 子串 → 应提取首个 { 到最后的 } 子串
    resp = '以下是结果：{"inner": {"k": 1}} 完毕'
    assert _parse_json_response(resp) == {"inner": {"k": 1}}


def test_parse_json_nested_braces_extracted():
    resp = 'prefix {"a": {"b": 2}} suffix'
    assert _parse_json_response(resp) == {"a": {"b": 2}}


def test_parse_json_garbage_returns_none():
    # 完全无花括号 → 无法解析 → None
    assert _parse_json_response("这根本不是 json") is None


def test_parse_json_only_fence_returns_none():
    # 只有围栏标记，无 JSON 内容 → None
    assert _parse_json_response("```") is None


def test_parse_json_unparseable_returns_none():
    # 有花括号但结构损坏，提取子串后仍无法解析 → None
    assert _parse_json_response('{"a": }') is None


# ────────────────────────────────────────────────────────────
# _annotate_mastery：画像→掌握度标注流水线（纯逻辑集成）
# ────────────────────────────────────────────────────────────

def test_annotate_mastery_pipeline():
    tree = MindMapNode(
        title="根", level=0,
        children=[
            MindMapNode(title="二叉树遍历", level=1),
            MindMapNode(title="AVL平衡树", level=1),
        ],
    )
    # 格式A: knowledge_foundation 精确匹配；格式B: weak_points 关键词降级匹配
    profile = {
        "knowledge_foundation": {"二叉树": {"二叉树遍历": {"mastery": 0.9}}},
        "weak_points": "AVL平衡树",
    }
    _annotate_mastery(tree, profile)

    # 二叉树遍历：精确命中 knowledge_foundation → 0.9 → MASTERED
    assert tree.children[0].mastery_score == 0.9
    assert tree.children[0].mastery == MasteryLevel.MASTERED

    # AVL平衡树：knowledge_foundation 无匹配 → weak_points 命中 → 0.5 → WEAK
    assert tree.children[1].mastery_score == 0.5
    assert tree.children[1].mastery == MasteryLevel.WEAK

    # 根：未匹配 → 0.0 → UNLEARNED
    assert tree.mastery_score == 0.0
    assert tree.mastery == MasteryLevel.UNLEARNED


# ────────────────────────────────────────────────────────────
# _annotate_memory_weak：L1/L2/L3 记忆薄弱点递归标注（P0① 补充）
# ────────────────────────────────────────────────────────────

def test_memory_weak_forward_hit():
    """薄弱词为节点标题子串 → 命中并置薄弱分 0.5"""
    tree = MindMapNode(
        title="根", level=0,
        children=[MindMapNode(title="TCP拥塞控制算法", level=1)],
    )
    _annotate_memory_weak(tree, "【学生长期画像】\n薄弱：TCP拥塞控制\n- goal: exam")
    assert tree.children[0].mastery_score == 0.5


def test_memory_weak_reverse_hit():
    """薄弱词为节点标题的超集（LLM 精简标题）→ 应命中（P0① 输出不稳定修复点）"""
    tree = MindMapNode(
        title="根", level=0,
        children=[MindMapNode(title="拥塞控制", level=1)],
    )
    _annotate_memory_weak(tree, "【学生长期画像】\n薄弱：TCP拥塞控制\n- goal: exam")
    assert tree.children[0].mastery_score == 0.5


def test_memory_weak_empty_context():
    """空记忆上下文 → 不崩溃、不标注"""
    tree = MindMapNode(title="根", level=0, children=[MindMapNode(title="TCP", level=1)])
    _annotate_memory_weak(tree, "")
    _annotate_memory_weak(tree, None)  # type: ignore[arg-type]
    assert tree.children[0].mastery_score == 0.0


def test_memory_weak_no_weak_block():
    """记忆上下文无「薄弱：」块 → 不标注"""
    tree = MindMapNode(title="根", level=0, children=[MindMapNode(title="TCP", level=1)])
    _annotate_memory_weak(tree, "【学生长期画像】\n- goal: exam")
    assert tree.children[0].mastery_score == 0.0


def test_memory_weak_multi_terms():
    """多个薄弱词 → 各自命中对应节点"""
    tree = MindMapNode(
        title="根", level=0,
        children=[
            MindMapNode(title="TCP三次握手", level=1),
            MindMapNode(title="AVL平衡树", level=1),
            MindMapNode(title="进程调度", level=1),
        ],
    )
    _annotate_memory_weak(tree, "薄弱：TCP三次握手,AVL平衡树")
    assert tree.children[0].mastery_score == 0.5
    assert tree.children[1].mastery_score == 0.5
    assert tree.children[2].mastery_score == 0.0  # 未命中保持默认


def test_memory_weak_overwrites_high_score():
    """已掌握(0.9)节点被薄弱词命中 → 降为薄弱 0.5"""
    node = MindMapNode(title="TCP拥塞控制", level=1)
    node.mastery_score = 0.9
    node.mastery = MasteryLevel.MASTERED
    tree = MindMapNode(title="根", level=0, children=[node])
    _annotate_memory_weak(tree, "薄弱：TCP拥塞控制")
    assert node.mastery_score == 0.5


def test_memory_weak_unifies_low_score():
    """已标注较低分(0.3)节点被命中 → 统一置标准薄弱分 0.5（P0① 端到端实测修复语义）"""
    node = MindMapNode(title="TCP拥塞控制", level=1)
    node.mastery_score = 0.3
    node.mastery = MasteryLevel.WEAK  # 模拟已通过 _annotate_mastery 标注
    tree = MindMapNode(title="根", level=0, children=[node])
    _annotate_memory_weak(tree, "薄弱：TCP拥塞控制")
    assert node.mastery_score == 0.5


def test_memory_weak_colon_variants():
    """全角/半角冒号均可解析"""
    tree_a = MindMapNode(title="根", level=0, children=[MindMapNode(title="TCP", level=1)])
    _annotate_memory_weak(tree_a, "薄弱：TCP")
    assert tree_a.children[0].mastery_score == 0.5
    tree_b = MindMapNode(title="根", level=0, children=[MindMapNode(title="TCP", level=1)])
    _annotate_memory_weak(tree_b, "薄弱: TCP")
    assert tree_b.children[0].mastery_score == 0.5


def test_memory_weak_case_insensitive():
    """英文薄弱词大小写不敏感"""
    tree = MindMapNode(title="根", level=0, children=[MindMapNode(title="TCP/IP Model", level=1)])
    _annotate_memory_weak(tree, "薄弱：tcp/ip")
    assert tree.children[0].mastery_score == 0.5


def test_memory_weak_recursive_children():
    """薄弱词命中深层子节点"""
    leaf = MindMapNode(title="拥塞控制", level=2)
    mid = MindMapNode(title="传输层", level=1, children=[leaf])
    tree = MindMapNode(title="根", level=0, children=[mid])
    _annotate_memory_weak(tree, "薄弱：拥塞控制")
    assert leaf.mastery_score == 0.5
    assert mid.mastery_score == 0.0  # 非命中节点不被误标
