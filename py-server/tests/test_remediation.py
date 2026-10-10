# ============================================================
# 单元测试：detect_weak_points（P1 闭环触发 —— 纯函数，无 LLM / 网络）
# 直接运行：python -m pytest tests/test_remediation.py -v
# ============================================================

import os
import sys

# 确保 py-server 根目录在 sys.path，使 `from services.remediation import ...` 可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.remediation import detect_weak_points


def test_returns_only_points_below_threshold():
    mastery = {"a": 0.3, "b": 0.8, "c": 0.5, "d": 0.59}
    res = detect_weak_points(mastery, 0.6)
    assert set(res) == {"a", "c", "d"}
    assert "b" not in res


def test_threshold_is_strictly_less():
    # 等于阈值不算薄弱
    mastery = {"a": 0.6, "b": 0.599}
    res = detect_weak_points(mastery, 0.6)
    assert res == ["b"]


def test_sorts_ascending_by_value():
    mastery = {"x": 0.4, "y": 0.2, "z": 0.5}
    assert detect_weak_points(mastery, 0.6) == ["y", "x", "z"]


def test_respects_cap():
    mastery = {f"p{i}": 0.1 + i * 0.01 for i in range(10)}
    res = detect_weak_points(mastery, 0.6, max_points=3)
    assert len(res) == 3
    assert res == ["p0", "p1", "p2"]


def test_empty_and_invalid_mastery_returns_empty():
    assert detect_weak_points({}, 0.6) == []
    assert detect_weak_points(None, 0.6) == []
    assert detect_weak_points("not a dict", 0.6) == []
    assert detect_weak_points([], 0.6) == []


def test_bool_values_are_not_treated_as_mastery():
    # bool 是 int 的子类，必须排除，避免 True/False 被误判为掌握度
    mastery = {"a": True, "b": 0.3, "c": False}
    res = detect_weak_points(mastery, 0.6)
    assert res == ["b"]


def test_no_points_below_threshold_returns_empty():
    mastery = {"a": 0.9, "b": 0.8}
    assert detect_weak_points(mastery, 0.6) == []


def test_zero_max_points_returns_empty():
    mastery = {"a": 0.1}
    assert detect_weak_points(mastery, 0.6, max_points=0) == []
