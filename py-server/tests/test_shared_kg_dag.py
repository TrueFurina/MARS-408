# ============================================================
# WS1 覆盖率补全 — shared/kg_dag.py（知识图谱 DAG / 1-26 组拓扑排序）
#
# 此前在测试套件中零引用（grep shared.<mod> 无命中），却是 metadata.group 的
# 「单一真源」（seed / _seed_vector_db / path_planner 均引用）。纯 typing 依赖，
# 可脱离 conftest 独立运行：
#   py-server/.venv/Scripts/python.exe -m pytest tests/test_shared_kg_dag.py --noconftest -q
#
# 覆盖：chapter_to_group 精确命中与前缀兜底、GROUP_PREREQS 线性链、
#       topological_sort 完整 26 组且满足依赖序、subject_chapters_in_order 去重有序
# ================================================================

from shared.kg_dag import (
    GROUP_PREREQS,
    SUBJECT_GROUP_MAP,
    SUBJECT_GROUP_SPAN,
    chapter_to_group,
    subject_chapters_in_order,
    topological_sort,
)


# ─────────────────────── 数据真源自检 ───────────────────────

def test_all_groups_within_1_to_26():
    for k, v in SUBJECT_GROUP_MAP.items():
        assert 1 <= v <= 26, f"{k} 的 group={v} 越界（应为 1-26）"


def test_prereqs_form_linear_chain():
    # 线性链：g 依赖 g-1（2..26），1 无前置
    assert set(GROUP_PREREQS) == set(range(2, 27))
    for g in range(2, 27):
        assert GROUP_PREREQS[g] == [g - 1]


def test_subject_group_span_matches_four_subjects():
    assert set(SUBJECT_GROUP_SPAN) == {
        "computer_network", "data_structures",
        "computer_organization", "operating_system",
    }


# ───────────────────── chapter_to_group ─────────────────────

def test_chapter_to_group_exact_hit():
    assert chapter_to_group("network") == 4
    assert chapter_to_group("os_process") == 23


def test_chapter_to_group_prefix_fallback():
    # 未知 subject 按前缀兜底，保证每条 chunk 都落进 1-26
    assert chapter_to_group("co_unknown_xyz") == 15
    assert chapter_to_group("os_unknown_xyz") == 22
    assert chapter_to_group("ds_unknown_xyz") == 8


def test_chapter_to_group_unknown_defaults_to_1():
    assert chapter_to_group("totally_unknown") == 1
    assert chapter_to_group("") == 1


# ───────────────────── topological_sort ─────────────────────

def test_topological_sort_covers_all_26_groups():
    order = topological_sort()
    assert sorted(order) == list(range(1, 27)), "拓扑结果必须覆盖 1-26 且无遗漏/重复"


def test_topological_sort_respects_dependency_order():
    # 线性链 1→2→…→26 下，唯一合法拓扑序即严格升序
    assert topological_sort() == list(range(1, 27))


def test_topological_sort_with_weak_groups_still_valid():
    # 弱项优先不得破坏依赖：线性链下顺序仍为 1..26（弱项前置在链内无空间）
    order = topological_sort(weak_groups=[5, 10, 20])
    assert order == list(range(1, 27))


def test_topological_sort_with_profile_does_not_crash():
    order = topological_sort(profile={"goal": "exam"})
    assert sorted(order) == list(range(1, 27))


def test_topological_sort_with_invalid_profile_types():
    # profile 非 dict / None 时按 general 处理，不得抛异常
    assert sorted(topological_sort(profile=None)) == list(range(1, 27))
    assert sorted(topological_sort(profile="bad")) == list(range(1, 27))


# ─────────────────── subject_chapters_in_order ───────────────────

def test_subject_chapters_in_order_dedup_and_ordered():
    seq = subject_chapters_in_order()
    assert len(seq) > 0
    assert len(seq) == len(set(seq)), "科目序列不得重复"
    # 首个 group(1) 对应 overview（SUBJECT_GROUP_MAP 中首个 value==1 的键）
    assert seq[0] == "overview"


def test_subject_chapters_in_order_respects_group_order():
    seq = subject_chapters_in_order()
    groups = [SUBJECT_GROUP_MAP[s] for s in seq]
    assert groups == sorted(groups), "科目序列必须按 group 升序（与拓扑序一致）"
