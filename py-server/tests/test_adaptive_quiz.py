"""P2 自适应选题 — 纯逻辑单测（无 DB / 无 LLM 依赖，可独立运行）。

运行：
    cd py-server && python tests/test_adaptive_quiz.py
或：
    cd py-server && python -m pytest tests/test_adaptive_quiz.py -q
"""

import os
import sys

# 确保 py-server 在 sys.path，便于独立运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.quiz_engine import (
    filter_questions_for_weak_points,
    STEP_QUESTIONS,
    normalize_subject,
    weak_points_from_history,
)
from services.remediation import detect_weak_points


def test_normalize_subject_aliases():
    # 课程级已是规范值
    assert normalize_subject("computer_network") == "computer_network"
    # 中文 408 科目 → 课程级
    assert normalize_subject("计算机网络") == "computer_network"
    assert normalize_subject("数据结构") == "data_structures"
    assert normalize_subject("计算机组成原理") == "computer_organization"
    assert normalize_subject("计组") == "computer_organization"
    assert normalize_subject("操作系统") == "operating_system"
    # 网络分层子主题 → 计算机网络（408 中"计算机网络"科目的子集）
    for sub in ("overview", "physical", "datalink", "network", "transport",
                "网络层", "传输层", "数据链路层", "物理层"):
        assert normalize_subject(sub) == "computer_network"
    # 无法识别原样返回
    assert normalize_subject("unknown_xyz") == "unknown_xyz"


def test_filter_with_alias_weak_points():
    # 薄弱点用 network 分层 / 中文命名，必须仍能匹配到对应课程级题库
    weak = ["network", "操作系统"]
    res = filter_questions_for_weak_points(weak, difficulty="all")
    assert res, "别名归一化后应匹配到题目"
    subs = {q.subject for q in res}
    assert "computer_network" in subs
    assert "operating_system" in subs
    assert not any(q.subject in ("data_structures", "computer_organization") for q in res)


def test_weak_points_from_history_fallback():
    # 语义掌握度为空时，用答题历史按科目正确率推断薄弱科目（纯函数，无需 DB）
    fake_history = [
        {"subject": "overview", "correct": True, "difficulty": "easy"},
        {"subject": "network", "correct": False, "difficulty": "medium"},
        {"subject": "network", "correct": False, "difficulty": "hard"},
        {"subject": "transport", "correct": False, "difficulty": "medium"},
        {"subject": "transport", "correct": True, "difficulty": "easy"},
        {"subject": "datalink", "correct": False, "difficulty": "medium"},
        {"subject": "physical", "correct": True, "difficulty": "easy"},
        {"subject": "physical", "correct": True, "difficulty": "easy"},
    ]
    weak = weak_points_from_history(fake_history, threshold=0.6)
    # network(0.0) / transport(0.5) / datalink(0.0) 低于 0.6 → 薄弱，均归一化为 computer_network
    assert weak, "应至少推断出 1 个薄弱科目"
    assert all(w == "computer_network" for w in weak)
    res = filter_questions_for_weak_points(weak, "all")
    assert res and all(q.subject == "computer_network" for q in res)


def test_filter_by_weak_subjects():
    weak = ["computer_network", "data_structures"]
    res = filter_questions_for_weak_points(weak, difficulty="all")
    assert res, "应返回至少一道匹配题"
    assert all(q.subject in weak for q in res)
    other = {q.subject for q in STEP_QUESTIONS} - set(weak)
    assert not any(q.subject in other for q in res)


def test_filter_difficulty():
    weak = ["computer_network"]
    hard = filter_questions_for_weak_points(weak, difficulty="hard")
    assert hard, "computer_network 应有 hard 题"
    assert all(q.difficulty == "hard" for q in hard)
    all_cn = filter_questions_for_weak_points(weak, difficulty="all")
    assert len(hard) <= len(all_cn)


def test_empty_weak_points():
    assert filter_questions_for_weak_points([]) == []
    assert filter_questions_for_weak_points(None) == []


def test_adaptive_pipeline():
    # 模拟掌握度：computer_network 与 operating_system 薄弱，data_structures 良好
    mastery = {
        "computer_network": 0.3,
        "data_structures": 0.9,
        "operating_system": 0.2,
    }
    weak = detect_weak_points(mastery, threshold=0.6, max_points=3)
    assert "computer_network" in weak and "operating_system" in weak
    assert "data_structures" not in weak
    res = filter_questions_for_weak_points(weak, "all")
    assert res, "薄弱科目在题库中应能匹配到题目"
    assert all(q.subject in weak for q in res)


if __name__ == "__main__":
    test_normalize_subject_aliases()
    test_filter_by_weak_subjects()
    test_filter_difficulty()
    test_empty_weak_points()
    test_filter_with_alias_weak_points()
    test_weak_points_from_history_fallback()
    test_adaptive_pipeline()
    print("ALL P2 adaptive-selection tests PASSED")
