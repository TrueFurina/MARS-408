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

from engines.quiz_engine import filter_questions_for_weak_points, STEP_QUESTIONS
from services.remediation import detect_weak_points


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
    test_filter_by_weak_subjects()
    test_filter_difficulty()
    test_empty_weak_points()
    test_adaptive_pipeline()
    print("ALL P2 adaptive-selection tests PASSED")
