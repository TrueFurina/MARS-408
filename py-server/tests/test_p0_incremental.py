# ============================================================
# P0 增量（INC-01~05）核心模块 — 纯逻辑 / 隔离测试
#
# 设计原则（环境级硬约束）：严禁触发任何真实模型 / 向量推理路径
# （torch / numpy 重路径 / 真实 E5 嵌入 / 真实 Milvus），以免 Windows 原生库
# SIGSEGV(139) 使整轮 pytest 崩溃。
#
# 测试策略：
#   - kg_dag / config.json / seed_data_expanded：纯 Python / JSON / AST 静态解析，零重依赖。
#   - evidence_check_node：在 import 前将 numpy / agents.state /
#     engines.gomarl_conflict / db.embedder 注入为轻量 Mock（sys.modules），
#     仅验证节点编排逻辑 + evidence_report 结构 + 降级路径，绝不跑真实引擎。
#   - 运行命令（隔离，避免 conftest 的 autouse 重 fixture 拉起整个 FastAPI app）：
#       cd py-server && python -m pytest tests/test_p0_incremental.py -q --noconftest
# ============================================================

import ast
import asyncio
import json
import re
import sys
import types
import importlib.util
from pathlib import Path
from unittest import mock

import pytest

# ── 将 py-server 根目录加入 sys.path（替代 conftest 的 sys.path 注入）──
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_AGENTS_DIR = _ROOT / "agents"
_SEED_FILE = _ROOT / "seed_data_expanded.py"
_CONFIG_FILE = _ROOT / "config.json"
# 净化后 config.json 不入库（gitignore）：缺失时回退已入库的脱敏范本，保证评委克隆后测试可跑
if not _CONFIG_FILE.exists():
    _example = _ROOT / "config.example.json"
    if _example.exists():
        _CONFIG_FILE = _example
_TS_EVIDENCE = (
    Path(__file__).resolve().parent.parent.parent / "src" / "utils" / "evidence.ts"
)


# ────────────────────────────────────────────────────────────
# 隔离注入：在 import evidence_check 之前，屏蔽所有重依赖模块
# ────────────────────────────────────────────────────────────
def _install_isolated_fakes():
    # numpy：只提供占位属性，绝不加载真实原生库
    if "numpy" not in sys.modules:
        np_fake = mock.MagicMock()
        np_fake.float32 = "float32"
        np_fake.array = lambda *a, **k: None
        sys.modules["numpy"] = np_fake

    # agents 包占位 + agents.state（仅提供 AgentState 类型注解用，dict 即可）
    if "agents" not in sys.modules:
        agents_pkg = types.ModuleType("agents")
        agents_pkg.__path__ = [str(_AGENTS_DIR)]
        sys.modules["agents"] = agents_pkg
    if "agents.state" not in sys.modules:
        state_mod = types.ModuleType("agents.state")
        state_mod.AgentState = dict  # 仅作类型注解
        sys.modules["agents.state"] = state_mod

    # engines.gomarl_conflict：提供 conflict_engine（异步 check_and_resolve）
    if "engines" not in sys.modules:
        engines_pkg = types.ModuleType("engines")
        sys.modules["engines"] = engines_pkg
    if "engines.gomarl_conflict" not in sys.modules:
        gomarl_mod = types.ModuleType("engines.gomarl_conflict")
        gomarl_mod.conflict_engine = mock.MagicMock(name="conflict_engine")
        sys.modules["engines.gomarl_conflict"] = gomarl_mod

    # db.embedder：embed_batch 抛异常 → 节点降级为仅事实/关键词检测（不加载真实 E5）
    # 注意：db 包仅给 __path__ 指向真实目录，绝不执行 db/__init__.py（避免拉起
    # milvus/pg/redis）；真实子模块（如 db.llm_provider）经 __path__ 解析，
    # db.embedder 单独被 mock 覆盖，避免加载真实 E5。
    if "db" not in sys.modules:
        db_pkg = types.ModuleType("db")
        db_pkg.__path__ = [str(_ROOT / "db")]
        sys.modules["db"] = db_pkg
    if "db.embedder" not in sys.modules:
        emb_mod = types.ModuleType("db.embedder")
        emb_mod.embed_batch = mock.MagicMock(
            side_effect=RuntimeError("isolated: real E5 embedder disabled")
        )
        sys.modules["db.embedder"] = emb_mod


_install_isolated_fakes()

# 以隔离方式加载 evidence_check（不触发任何重依赖）
_spec = importlib.util.spec_from_file_location(
    "agents.evidence_check", str(_AGENTS_DIR / "evidence_check.py")
)
evidence_check = importlib.util.module_from_spec(_spec)
sys.modules["agents.evidence_check"] = evidence_check
_spec.loader.exec_module(evidence_check)

# kg_dag 为纯 Python，直接安全导入
import agents.kg_dag as kg_dag  # noqa: E402


# ────────────────────────────────────────────────────────────
# 工具：AST 抽取 seed_data_expanded.py 中所有 "group": <int> 取值
# ────────────────────────────────────────────────────────────
def _collect_seed_groups(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    groups = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "group"
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, int)
                ):
                    groups.add(v.value)
    return groups


# ────────────────────────────────────────────────────────────
# 工具：正则抽取 TS interface 字段名（静态比对，不触发 tsc）
# ────────────────────────────────────────────────────────────
def _extract_ts_interface_fields(path: Path, interface: str) -> set:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    m = re.search(
        r"export\s+interface\s+" + re.escape(interface) + r"\s*\{(.*?)\n\}",
        text,
        re.S,
    )
    if not m:
        return set()
    fields = set()
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        mm = re.match(r"(\w+)(\?)?\s*:", line)
        if mm:
            fields.add(mm.group(1))
    return fields


# ============================================================
# 1) kg_dag.chapter_to_group
# ============================================================
class TestChapterToGroup:
    def test_exact_subject_mapping(self):
        cases = {
            "overview": 1, "physical": 2, "datalink": 3, "network": 4,
            "transport": 5, "application": 6, "security": 7, "cn": 4,
            "ds": 8, "ds_linear": 8, "ds_stack": 9, "ds_string": 10,
            "ds_tree": 11, "ds_graph": 12, "ds_search": 13, "ds_sort": 14,
            "ds_queue": 9,
            "co": 15, "co_overview": 15, "co_data": 16, "co_isa": 16,
            "co_memory": 17, "co_cpu": 18, "co_bus": 19, "co_io": 20,
            "os": 22, "os_overview": 22, "os_process": 23, "os_memory": 24,
            "os_file": 25, "os_io": 26,
        }
        for subj, expected in cases.items():
            assert kg_dag.chapter_to_group(subj) == expected, f"{subj} -> {expected}"

    def test_prefix_fallback(self):
        # 单一真源前缀：co_→15 / os_→22 / ds_→8
        assert kg_dag.chapter_to_group("co_intro") == 15
        assert kg_dag.chapter_to_group("os_intro") == 22
        assert kg_dag.chapter_to_group("ds_intro") == 8
        assert kg_dag.chapter_to_group("net_intro") == 1
        # 完全未知前缀 -> 1
        assert kg_dag.chapter_to_group("foobar") == 1
        # 完整科名（computer_organization / data_structures / operating_system）不以
        # co_/os_/ds_ 开头（而是 computer_/data_/operating_），按 chapter_to_group 契约
        # 不属于可识别的短 key / 前缀，落兜底 1。
        # 注意：完整科名→group 的映射缺口是 path_planner._derive_weak_groups 的已知
        # 源码 Bug（见 TestWeakGroupDerivation），此处仅锁定 chapter_to_group 自身契约。
        assert kg_dag.chapter_to_group("computer_organization") == 1
        assert kg_dag.chapter_to_group("data_structures") == 1
        assert kg_dag.chapter_to_group("operating_system") == 1

    def test_return_in_range(self):
        samples = [
            "co", "os", "ds", "network", "overview", "unknown",
            "computer_organization", "data_structures", "operating_system",
            "net_xyz", "cn", "os_file",
        ]
        for s in samples:
            g = kg_dag.chapter_to_group(s)
            assert isinstance(g, int) and 1 <= g <= 26, f"{s} -> {g} 越界"


# ============================================================
# 2) kg_dag.topological_sort
# ============================================================
class TestTopologicalSort:
    def test_full_coverage_and_unique(self):
        order = kg_dag.topological_sort()
        assert isinstance(order, list)
        assert len(order) == 26
        assert set(order) == set(range(1, 27))

    def test_valid_topological_order(self):
        order = kg_dag.topological_sort()
        pos = {g: i for i, g in enumerate(order)}
        for g in range(2, 27):
            for p in kg_dag.GROUP_PREREQS.get(g, []):
                assert pos[p] < pos[g], f"prereq {p} 应在 {g} 之前"

    def test_acyclic(self):
        # 长度为 26 且为 1..26 的全排列 => 必然无环
        order = kg_dag.topological_sort()
        assert sorted(order) == list(range(1, 27))

    def test_weak_groups_keep_valid_order(self):
        for weak in ([5], [15], [26], [3, 10, 20]):
            order = kg_dag.topological_sort(weak_groups=weak)
            assert set(order) == set(range(1, 27))
            pos = {g: i for i, g in enumerate(order)}
            for g in range(2, 27):
                for p in kg_dag.GROUP_PREREQS.get(g, []):
                    assert pos[p] < pos[g]

    def test_weak_priority_no_earlier_than_prereqs(self):
        # 纯线性依赖链下，弱项只能在其先决之后出现；order[0] 必为 1
        order = kg_dag.topological_sort(weak_groups=[26])
        assert order[0] == 1
        assert order == list(range(1, 27))


# ============================================================
# 3) group 偏移一致性（kg_dag ↔ seed_data_expanded）
# ============================================================
class TestGroupOffsetConsistency:
    def test_seed_groups_15_26_present(self):
        groups = _collect_seed_groups(_SEED_FILE)
        missing = [g for g in range(15, 27) if g not in groups]
        assert not missing, f"seed_data_expanded 缺少 group: {missing}"

    def test_subject_span_coverage(self):
        # 已知 subject → 期望落在对应四科 group 区间（设计文档 §7.2）
        checks = {
            "overview": (1, 7), "network": (1, 7), "security": (1, 7),
            "ds": (8, 14), "ds_tree": (8, 14), "ds_sort": (8, 14),
            "co": (15, 21), "co_memory": (15, 21), "co_io": (15, 21),
            "os": (22, 26), "os_memory": (22, 26), "os_io": (22, 26),
        }
        for subj, (lo, hi) in checks.items():
            g = kg_dag.chapter_to_group(subj)
            assert lo <= g <= hi, f"{subj} -> {g} 不在 [{lo},{hi}]"


# ============================================================
# 4) config.json 解析
# ============================================================
class TestConfigJson:
    def setup_method(self):
        self.cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))

    def test_milvus_enabled(self):
        assert self.cfg["milvus"]["enabled"] is True

    def test_llm_channels_present(self):
        assert "deepseek" in self.cfg
        assert "xfyun" in self.cfg
        # qwen 为既有 dormant 回退，不强制
        assert self.cfg["deepseek"].get("base_url")
        assert self.cfg["xfyun"].get("base_url")

    def test_knowledge_courses_four_subjects(self):
        courses = self.cfg["knowledge"]["courses"]
        for c in ["data_structures", "computer_network",
                  "operating_system", "computer_organization"]:
            assert c in courses


# ============================================================
# 5) evidence_check 报告结构 + 节点编排（隔离引擎 mock）
# ============================================================
def _make_state(**fields):
    state = {
        "teacher_doc": None, "quiz": None, "code_practice": None,
        "ppt_outline": None, "extension": None, "mindmap": None,
        "video_script": None, "media_plan": None, "course": "computer_network",
    }
    state.update(fields)
    return state


def _fake_engine_result():
    return {
        "overall_consistency": 0.82,
        "total_conflicts": 2,
        "resolved": 1,
        "unresolved": 1,
        "conflicts": [
            {
                "agent_a": "teacher", "agent_b": "quiz", "type": "factual",
                "description": "冲突1", "evidence": [{"text": "x", "score": 0.9, "source": "s"}],
                "resolution": "采纳综合修正", "confidence": 0.95,
            },
            {
                "agent_a": "ppt", "agent_b": "extension", "type": "semantic",
                "description": "冲突2", "evidence": [],
                "resolution": "无法判断，需人工审核", "confidence": 0.4,
            },
        ],
    }


class TestEvidenceReportStructure:
    def test_build_report_required_fields(self):
        state = _make_state(teacher_doc="讲解", quiz="题目")
        report = evidence_check._build_report(state, _fake_engine_result(), 12.5)
        for f in ("status", "overall_consistency", "consistency_score",
                  "total_conflicts", "resolved", "unresolved", "conflicts",
                  "checked_agents", "course", "elapsed_ms"):
            assert f in report, f"缺少字段 {f}"
        assert report["status"] == "ok"
        assert report["total_conflicts"] == 2
        assert report["checked_agents"] == ["teacher", "quiz"]

    def test_build_report_conflict_mapping(self):
        state = _make_state(teacher_doc="a", quiz="b")
        report = evidence_check._build_report(state, _fake_engine_result(), 1.0)
        c0, c1 = report["conflicts"]
        # 严重度映射：factual->high / semantic->medium
        assert c0["severity"] == "high"
        assert c1["severity"] == "medium"
        # 处置映射：含「采纳」->adopt / 无法判断->human_review
        assert c0["disposition"] == "adopt"
        assert c1["disposition"] == "human_review"
        # evidence 结构透传
        assert c0["evidence"][0]["text"] == "x"
        assert c0["evidence"][0]["score"] == 0.9
        assert c0["confidence"] == 0.95
        assert "__" in c0["id"]

    def test_empty_report_has_error_field(self):
        state = _make_state()
        rep = evidence_check._empty_report(state, 3.0, "error", error="boom")
        assert rep["error"] == "boom"
        assert rep["status"] == "error"
        for f in ("overall_consistency", "consistency_score", "total_conflicts",
                  "resolved", "unresolved", "conflicts", "checked_agents",
                  "course", "elapsed_ms"):
            assert f in rep

    def test_sse_report_field_set_matches_evidence_ts(self):
        ts_fields = _extract_ts_interface_fields(_TS_EVIDENCE, "EvidenceReport")
        assert ts_fields, "未能从 evidence.ts 解析 EvidenceReport 字段"
        state = _make_state(teacher_doc="a", quiz="b")
        build_fields = set(evidence_check._build_report(state, _fake_engine_result(), 1.0).keys())
        empty_fields = set(evidence_check._empty_report(state, 1.0, "error", error="x").keys())
        # 后端两个 builder 的字段集合都应是 EvidenceReport 契约的子集
        assert build_fields <= ts_fields, f"build_report 越界字段: {build_fields - ts_fields}"
        assert empty_fields <= ts_fields, f"empty_report 越界字段: {empty_fields - ts_fields}"
        # 必需（非可选）字段全部被覆盖；error 为可选，仅出现在降级/错误路径
        required = ts_fields - {"error"}
        assert required <= (build_fields | empty_fields)


class TestEvidenceCheckNode:
    def _run(self, state):
        return asyncio.run(evidence_check.evidence_check_node(state))

    def test_node_happy_path(self):
        evidence_check.conflict_engine.check_and_resolve = mock.AsyncMock(
            return_value=_fake_engine_result()
        )
        state = _make_state(
            teacher_doc="讲解文档内容", quiz="题库内容", code_practice="代码",
            ppt_outline="PPT", extension="拓展", mindmap={"mermaid": "graph TD"},
            video_script="视频脚本", media_plan="多媒体",
        )
        out = self._run(state)
        rep = out["evidence_report"]
        assert rep["status"] == "ok"
        assert rep["total_conflicts"] == 2
        assert set(rep["checked_agents"]) == {
            "teacher", "quiz", "code_practice", "ppt", "extension",
            "mindmap", "video", "media",
        }
        assert out["current_agent"] == "evidence_check"

    def test_node_degrade_on_engine_exception(self):
        evidence_check.conflict_engine.check_and_resolve = mock.AsyncMock(
            side_effect=RuntimeError("engine boom")
        )
        state = _make_state(teacher_doc="讲解", quiz="题目")
        # 必须不抛异常，降级返回 error 报告
        out = self._run(state)
        rep = out["evidence_report"]
        assert rep["status"] == "error"
        assert "engine boom" in rep["error"]
        assert rep["total_conflicts"] == 0

    def test_node_empty_results_ok(self):
        evidence_check.conflict_engine.check_and_resolve = mock.AsyncMock(
            return_value=_fake_engine_result()
        )
        state = _make_state()  # 全部为空
        out = self._run(state)
        rep = out["evidence_report"]
        assert rep["status"] == "ok"
        assert rep["total_conflicts"] == 0
        assert rep["checked_agents"] == []


# ============================================================
# 6) path_planner._derive_weak_groups — 弱项 group 推导（INC-05 / T06）
#
# ⚠️ 源码 Bug 复现：SUBJECT_KEYWORD_MAP 的值是「完整科名」
#    (computer_organization / data_structures / operating_system / computer_network)，
#    但 _derive_weak_groups 用 SUBJECT_GROUP_MAP.get(subject, 1) 去查「短 key 表」，
#    完整科名不在 SUBJECT_GROUP_MAP 中 → 一律兜底为 1（网络 1-7）。
#    结果：学生弱项在 数据结构/计组/操作系统 时，KG-DAG 路径错误地优先网络组 1-7。
#    修复建议：新增「完整科名 → 起始 group」映射（如
#    {"computer_network":1,"data_structures":8,"computer_organization":15,
#     "operating_system":22}），在 _derive_weak_groups 中替换 SUBJECT_GROUP_MAP.get。
# ============================================================
class TestWeakGroupDerivation:
    def _weak(self, weak_points: str):
        import agents.path_planner as pp  # 惰性导入，隔离；纯 Python，无重依赖
        return pp._derive_weak_groups({"weak_points": weak_points}, {}, [])

    def test_data_structures_maps_to_8_14(self):
        groups = self._weak("数据结构 树 图")
        assert any(8 <= g <= 14 for g in groups), f"数据结构弱项应落到 8-14: {groups}"
        assert not any(g <= 7 for g in groups), f"数据结构弱项错误混入网络组 1-7: {groups}"

    def test_computer_organization_maps_to_15_21(self):
        groups = self._weak("计组 CPU 流水线")
        assert any(15 <= g <= 21 for g in groups), f"计组弱项应落到 15-21: {groups}"

    def test_operating_system_maps_to_22_26(self):
        groups = self._weak("操作系统 进程 死锁")
        assert any(22 <= g <= 26 for g in groups), f"操作系统弱项应落到 22-26: {groups}"

    def test_network_maps_to_1_7(self):
        groups = self._weak("网络 子网划分")
        assert any(1 <= g <= 7 for g in groups), f"网络弱项应落到 1-7: {groups}"


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--noconftest"])
