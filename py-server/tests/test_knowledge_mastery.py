"""P4 知识点级（章节级）掌握度 —— 基于真实答题正确/错误计数，mastery = 正确/(正确+错误)。

运行：
    cd py-server && python tests/test_knowledge_mastery.py
或：
    cd py-server && python -m pytest tests/test_knowledge_mastery.py -q -o addopts=""
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.quiz_engine import (
    WeakPointTracker,
    StepQuestion,
    QuestionStep,
    StepResult,
)


def _make_question(subject="computer_network", chapter="tcp_congestion"):
    return StepQuestion(
        id="q_km",
        subject=subject,
        chapter=chapter,
        difficulty="hard",
        question_text="x",
        steps=[
            QuestionStep(step_name=f"s{i}", description="", check_type="choice",
                         answer="a", error_type_if_wrong="concept_confusion")
            for i in range(3)
        ],
        error_type_map={"concept_confusion": "子网划分"},
    )


def _results(correct_idx=(0, 1), wrong_idx=(2,)):
    out = []
    for i in range(3):
        if i in wrong_idx:
            out.append(StepResult(step_index=i, step_name=f"s{i}", correct=False, error_type="concept_confusion"))
        else:
            out.append(StepResult(step_index=i, step_name=f"s{i}", correct=True, error_type="correct"))
    return out


def test_knowledge_mastery_real_ratio():
    # 完成 3 步：step0/1 答对、step2 答错 → success=2, error=1 → mastery=2/3
    q = _make_question()
    results = _results(correct_idx=(0, 1), wrong_idx=(2,))
    t = WeakPointTracker()
    t.record_error(q, results, "u_km_1")
    t.record_success(q, results, "u_km_1")

    pts = t.get_knowledge_mastery("u_km_1", "computer_network")
    chap = [p for p in pts if p["chapter"] == "tcp_congestion"]
    assert chap, "应返回 tcp_congestion 章节掌握度"
    p = chap[0]
    assert p["success_count"] == 2
    assert p["error_count"] == 1
    assert abs(p["mastery"] - 2 / 3) < 1e-9, f"mastery 应为 2/3，实为 {p['mastery']}"


def test_knowledge_mastery_all_correct():
    # 全部答对 → success=3, error=0 → mastery=1.0
    q = _make_question()
    results = _results(correct_idx=(0, 1, 2), wrong_idx=())
    t = WeakPointTracker()
    t.record_error(q, results, "u_km_2")
    t.record_success(q, results, "u_km_2")

    pts = t.get_knowledge_mastery("u_km_2", "computer_network")
    p = [x for x in pts if x["chapter"] == "tcp_congestion"][0]
    assert p["mastery"] == 1.0
    assert p["error_count"] == 0
    assert p["success_count"] == 3


def test_knowledge_mastery_unpracticed_is_none():
    # 全新用户：tracker 无数据，但应列出该 subject 全部章节且 mastery=None（不造假）
    t = WeakPointTracker()
    pts = t.get_knowledge_mastery("u_km_fresh", "computer_network")
    assert pts, "应至少列出 computer_network 的章节"
    assert all(p["mastery"] is None for p in pts), "未练习章节 mastery 必须为 None"
    assert any(p["chapter"] == "tcp_congestion" for p in pts)


def test_weak_topics_excludes_chapter_marker():
    # 章节级聚合条目（concept=_CHAPTER_MARKER）不得进入薄弱点清单
    q = _make_question()
    results = _results(correct_idx=(0, 1), wrong_idx=(2,))
    t = WeakPointTracker()
    t.record_error(q, results, "u_km_3")
    t.record_success(q, results, "u_km_3")

    weak = t.get_weak_topics("u_km_3", "computer_network")
    assert all(wp.concept != WeakPointTracker._CHAPTER_MARKER for wp in weak), \
        "薄弱点清单不应包含章节级掌握度聚合条目"
    # 具体错因 concept（子网划分）应仍在清单中
    assert any(wp.concept == "子网划分" for wp in weak), "具体错因 concept 应进入薄弱点清单"
