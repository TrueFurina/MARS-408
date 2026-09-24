# -*- coding: utf-8 -*-
"""cn_distinction 专项测试（D15 死路由接线启用后的补测）

范围：只测引擎层 `engines/cn_distinction.py` 的确定性行为 ——
数据集完整性、摘要级裁剪、查询命中/未命中、随机抽题可复现、关键词判分边界。

诚信：本模块判分是**确定性关键词匹配**（引擎自述不假装 AI 打分），
因此这里的断言全部可复现，不依赖 LLM / 网络 / 数据库。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engines import cn_distinction as cd


# ------------------------------------------------------------------
# 数据集完整性（防内容腐化）
# ------------------------------------------------------------------

def test_pairs_dataset_not_empty_and_unique_ids():
    pairs = cd.CN_DISTINCTION_PAIRS
    assert len(pairs) >= 10, f"辨析对数量异常：{len(pairs)}"
    ids = [p["id"] for p in pairs]
    assert len(ids) == len(set(ids)), f"存在重复 id：{ids}"


@pytest.mark.parametrize("pair", cd.CN_DISTINCTION_PAIRS, ids=lambda p: p["id"])
def test_each_pair_has_complete_quiz(pair):
    for field in ("id", "title", "category", "confusion", "key_points"):
        assert pair.get(field), f"{pair.get('id')} 缺失字段 {field}"
    assert isinstance(pair["key_points"], list) and pair["key_points"], "key_points 不能为空"

    quiz = pair["quiz"]
    for field in ("question", "expected_keywords", "answer"):
        assert quiz.get(field), f"{pair['id']}.quiz 缺失字段 {field}"
    assert quiz["expected_keywords"], f"{pair['id']} 判分关键词不能为空（否则无法判分）"
    assert all(isinstance(k, str) and k for k in quiz["expected_keywords"])


# ------------------------------------------------------------------
# get_pairs / get_pair
# ------------------------------------------------------------------

def test_get_pairs_strips_quiz():
    """get_pairs 是摘要级视图：必须不含 quiz（避免答案泄漏给列表接口）。"""
    pairs = cd.get_pairs()
    assert len(pairs) == len(cd.CN_DISTINCTION_PAIRS)
    for p in pairs:
        assert "quiz" not in p, f"{p['id']} 摘要视图不应含 quiz（答案泄漏风险）"


def test_get_pair_hit_and_miss():
    first = cd.CN_DISTINCTION_PAIRS[0]
    assert cd.get_pair(first["id"])["id"] == first["id"]
    assert cd.get_pair("__not_exist__") is None


# ------------------------------------------------------------------
# get_random_quiz：可复现 + 字段齐全
# ------------------------------------------------------------------

def test_get_random_quiz_is_reproducible_with_seed():
    a = cd.get_random_quiz(random.Random(20260719))
    b = cd.get_random_quiz(random.Random(20260719))
    assert a == b, "同 seed 抽题结果必须一致"


def test_get_random_quiz_fields():
    q = cd.get_random_quiz(random.Random(7))
    for field in ("pair_id", "pair_title", "question", "expected_keywords", "answer"):
        assert q.get(field), f"抽题结果缺失字段 {field}"
    assert cd.get_pair(q["pair_id"]) is not None


# ------------------------------------------------------------------
# grade_quiz：确定性关键词判分边界
# ------------------------------------------------------------------

def _quiz_with(kws):
    return {"question": "q", "expected_keywords": kws, "answer": "a"}


def test_grade_all_keywords_hit():
    quiz = _quiz_with(["利用率", "灵活"])
    r = cd.grade_quiz(quiz, "分组交换利用率高且灵活")
    assert r["score"] == 1.0
    assert r["passed"] is True
    assert r["missed_keywords"] == []


def test_grade_none_hit_and_empty_answer():
    quiz = _quiz_with(["利用率", "灵活"])
    for ans in ("", "不知道", None):
        r = cd.grade_quiz(quiz, ans)
        assert r["score"] == 0.0
        assert r["passed"] is False
        assert len(r["missed_keywords"]) == 2


def test_grade_half_hit_is_passing_boundary():
    """2 个关键词命中 1 个 → score=0.5，passed 边界为 >=0.5（应为 True）。"""
    quiz = _quiz_with(["利用率", "灵活"])
    r = cd.grade_quiz(quiz, "利用率高")
    assert r["score"] == 0.5
    assert r["passed"] is True


def test_grade_missing_keywords_field_does_not_divide_by_zero():
    r = cd.grade_quiz({"question": "q", "answer": "a"}, "任意作答")
    assert r["score"] == 0.0
    assert r["passed"] is False


def test_grade_is_case_insensitive_and_deterministic():
    quiz = _quiz_with(["TCP", "UDP"])
    lower = cd.grade_quiz(quiz, "tcp 与 udp")
    upper = cd.grade_quiz(quiz, "TCP 与 UDP")
    assert lower == upper
    assert lower["score"] == 1.0


def test_grade_returns_reference_answer():
    quiz = _quiz_with(["迭代"])
    r = cd.grade_quiz(quiz, "")
    assert r["answer"] == quiz["answer"]
