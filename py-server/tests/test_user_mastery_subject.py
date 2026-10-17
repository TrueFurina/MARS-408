# ============================================================
# 单元测试：GET /api/user/mastery 的 subject 口径（api/user.py）
#
# 背景（2026-10-18 只读取证结论）：
#   掌握度地图页用 `w.subject === m.subject` / `k.subject === m.subject`
#   严格相等做联动筛选。但两侧词表根本不是同一套：
#     - 薄弱点 w.subject 与知识点 kp.subject：恒为 STEP_QUESTIONS 的
#       规范英文键（computer_network / data_structures /
#       computer_organization / operating_system）；
#     - 掌握度 m.subject：等于答题历史落库原文，而
#       db.profile_store.append_quiz_history 原样写入、不归一化。
#       实测 data/netlearn_users.db 的 user_quiz_history.subject 取值是
#       章节级键（network / ds_tree / co_cpu / os_memory …）与短键
#       （os / net / ds），中文科目名从未命中 ⇒ 两侧交集为空 ⇒ 点击
#       科目卡片永远筛不出薄弱点。
#
#   本文件锁定修复契约：/user/mastery 必须把 subject 归一化到规范英文键
#   （供筛选），并用独立 label 字段承载中文展示名。
#
# 设计纪律：
#   - 无真实 DB 读写：api.user.get_quiz_history 以 monkeypatch 替身接管
#     （api/user.py 顶部 from-import 了该符号，patch 模块属性即生效）。
#   - 直接调用端点协程并显式传 user，不走 HTTP / 不做登录，避免依赖
#     真实用户与鉴权状态。
#   - 无 LLM / 无网络。
#
# 运行：python -m pytest tests/test_user_mastery_subject.py -v
# ============================================================

import os
import sys

import pytest

# 确保 py-server 根目录在 sys.path，使 `from api import user` 可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.unit

import api.review  # noqa: E402,F401  （防污染预导入：_subject_label 惰性 import 它）
import api.user as user_api  # noqa: E402
from engines.quiz_engine import normalize_subject  # noqa: E402

# 规范英文键 ←→ 中文展示名（与 api/review.py SUBJECT_NAMES 的课程级四项一致）
CANONICAL = {
    "computer_network": "计算机网络",
    "data_structures": "数据结构",
    "computer_organization": "计算机组成原理",
    "operating_system": "操作系统",
}


def _history(*pairs):
    """构造答题历史：pairs 为 (subject, correct) 二元组。"""
    return [{"subject": s, "correct": c, "difficulty": "medium", "timestamp": "2026-10-18 10:00:00"}
            for s, c in pairs]


@pytest.fixture
def mastery(monkeypatch):
    """返回可调用的掌握度端点，历史由 fixture 使用者注入。"""
    captured = {}

    def _call(history):
        captured["history"] = history
        monkeypatch.setattr(user_api, "get_quiz_history", lambda uid: history)
        return user_api.get_user_mastery(user={"user_id": "u_mastery_test"})

    return _call


# ── 1. 章节级键 → 规范英文 ────────────────────────────────────────────

async def test_mastery_normalizes_chapter_keys_to_canonical(mastery):
    # 实测落库的章节级键（data/netlearn_users.db 真实取值）
    items = await mastery(_history(
        ("ds_tree", True), ("ds_sort", False),
        ("co_cpu", True),
        ("os_memory", False),
        ("network", True),
    ))
    subjects = {it["subject"] for it in items}
    assert subjects == {"data_structures", "computer_organization",
                        "operating_system", "computer_network"}
    # 同科目的两条记录必须聚合到同一张卡片上（ds_tree + ds_sort → data_structures）
    ds = next(it for it in items if it["subject"] == "data_structures")
    assert ds["pct"] == 50  # 1 对 1 错


async def test_mastery_normalizes_short_keys(mastery):
    # 短键 os/net/ds 是 DB 里的多数派（各 50 条）
    items = await mastery(_history(("os", False), ("net", True), ("ds", True)))
    assert {it["subject"] for it in items} == {"operating_system",
                                               "computer_network",
                                               "data_structures"}


async def test_normalize_subject_new_aliases():
    """别名表层：新增键必须落到规范英文键（与端点层断言互为表里）。"""
    for key in ("os", "os_memory", "os_overview", "os_process"):
        assert normalize_subject(key) == "operating_system", key
    for key in ("net", "network", "transport", "overview", "physical", "datalink"):
        assert normalize_subject(key) == "computer_network", key
    for key in ("ds", "ds_linear", "ds_tree", "ds_sort", "ds_graph"):
        assert normalize_subject(key) == "data_structures", key
    for key in ("co", "co_overview", "co_data", "co_memory", "co_cpu"):
        assert normalize_subject(key) == "computer_organization", key


# ── 2. subject（筛选键）与 label（展示名）分离 ─────────────────────────

async def test_mastery_subject_is_canonical_and_label_is_chinese(mastery):
    items = await mastery(_history(("ds_tree", True), ("co_cpu", False),
                                   ("os", True), ("net", False)))
    by_subject = {it["subject"]: it["label"] for it in items}
    # subject 必须是规范英文键，label 必须是中文展示名，二者不得相等
    for subj, label in by_subject.items():
        assert subj in CANONICAL, f"subject 未归一化: {subj}"
        assert label == CANONICAL[subj], f"label 与 subject 不匹配: {subj} -> {label}"
        assert label != subj, "label 不得再等于 subject（否则口径分离失效）"


async def test_mastery_label_is_never_empty(mastery):
    """label 必须有非空中文展示名，不能留空字符串。"""
    items = await mastery(_history(("overview", True), ("co_cpu", True),
                                   ("os_process", True), ("ds_linear", True)))
    assert items, "归一化后应有聚合结果"
    for it in items:
        assert it["label"], f"label 为空: {it}"
        assert it["label"].strip(), f"label 为空白: {it}"


# ── 3. 空历史兜底 ────────────────────────────────────────────────────

async def test_mastery_empty_history_fallback_four_items(mastery):
    items = await mastery([])
    assert len(items) == 4
    # 兜底项同样必须遵守「subject 规范英文 + label 中文」契约
    by_subject = {it["subject"]: it["label"] for it in items}
    assert set(by_subject) == set(CANONICAL)
    for subj, label in by_subject.items():
        assert label == CANONICAL[subj]
        assert label != subj
    assert all(it["pct"] == 0 for it in items)


# ── 4. 空串 subject 不得聚成科目 ──────────────────────────────────────

async def test_mastery_skips_empty_subject_records(mastery):
    """DB 实测有 50 条 subject='' 的历史；不得聚成一个空键科目。"""
    items = await mastery(_history(("", False), ("", True), ("ds_tree", True)))
    subjects = [it["subject"] for it in items]
    assert "" not in subjects, "空 subject 不得聚合为科目"
    assert None not in subjects
    assert subjects == ["data_structures"]


async def test_mastery_only_empty_subjects_falls_back(mastery):
    """全部记录 subject 为空 ⇒ 视为无有效历史，走四项兜底。"""
    items = await mastery(_history(("", False), ("", True)))
    assert len(items) == 4
    assert {it["subject"] for it in items} == set(CANONICAL)
    assert all(it["pct"] == 0 for it in items)
