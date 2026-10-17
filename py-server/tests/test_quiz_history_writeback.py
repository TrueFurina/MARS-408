# ============================================================
# 单元测试：答题历史落库（掌握度唯一数据源）
#
# 背景（2026-10-18 实证）：
#   `/quiz/submit`（quiz.py:224）与步骤化答题完成（quiz.py:449-474）此前
#   **从不写 user_quiz_history** —— 只写画像 / L2 语义记忆 / L3 情景 / 错题本。
#   而 `GET /user/mastery` 的唯一数据源就是答题历史 ⇒ 真实用户做完题，
#   掌握度恒为 0（全 pct=0 → 前端 allZero → 掌握度地图只显示占位图）。
#
# 契约：
#   1) 提交答题 / 步骤化答题完成 → 各追加一条 history（一条记录一行）；
#   2) 落库 subject 走 normalize_subject（与薄弱点/知识点同一套规范英文键）；
#   3) 落库失败 fail-open：绝不因历史写库失败而让答题接口 500。
#
# 设计：以 monkeypatch 替身接管 `api.quiz.append_quiz_history` 断言调用参数，
# 避免测试向真实 data/*.db 写历史行（断言调用即可证明落库路径接通）。
#
# 运行：python -m pytest tests/test_quiz_history_writeback.py -v
# ============================================================

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.unit

from api import quiz as quiz_api  # noqa: E402
from api.quiz import quiz_submit, submit_step_answer  # noqa: E402
from models import QuizRecord, QuizSubmitRequest  # noqa: E402

# 防污染预导入（本文件 patch 的是 api.quiz 上的绑定，先确保模块已导入）
import api.quiz  # noqa: E402,F401

USER = {"user_id": "u_history_wb", "role": "student"}


class _Spy:
    """记录型替身：记录每次调用的 (user_id, records)。"""

    def __init__(self, raises=None):
        self.calls: list[tuple[str, list[dict]]] = []
        self.raises = raises

    def __call__(self, user_id, records):
        self.calls.append((user_id, records))
        if self.raises is not None:
            raise self.raises


def _install_spy(monkeypatch, raises=None) -> _Spy:
    spy = _Spy(raises=raises)
    # raising=False：红灯阶段 api.quiz 尚无该绑定，用例应因"未被调用"而红，
    # 而不是因 patch 目标不存在而 error。
    monkeypatch.setattr("api.quiz.append_quiz_history", spy, raising=False)
    return spy


def _req(*records: QuizRecord) -> QuizSubmitRequest:
    return QuizSubmitRequest(profile={}, records=list(records))


def _rec(subject: str, correct: bool, difficulty: str = "medium") -> QuizRecord:
    return QuizRecord(subject=subject, correct=correct, difficulty=difficulty)


# ════════════════════════════════════════════════════════════
# 1. /quiz/submit
# ════════════════════════════════════════════════════════════

async def test_submit_appends_normalized_history(monkeypatch):
    """提交答题 → 落一条 history，subject 归一化为规范英文键。"""
    spy = _install_spy(monkeypatch)
    await quiz_submit(_req(
        _rec("ds_tree", True, "medium"),
        _rec("os", False, "hard"),
    ), USER)

    assert len(spy.calls) == 1, "提交一次答题必须落库一次"
    user_id, records = spy.calls[0]
    assert user_id == USER["user_id"]
    assert [r["subject"] for r in records] == ["data_structures", "operating_system"], \
        "章节级/短键必须归一化为规范英文键"
    assert [r["correct"] for r in records] == [True, False]
    assert [r["difficulty"] for r in records] == ["medium", "hard"]


async def test_submit_chinese_subject_normalized(monkeypatch):
    """中文科目名同样归一化（历史遗留口径兜底）。"""
    spy = _install_spy(monkeypatch)
    await quiz_submit(_req(_rec("计算机组成原理", True)), USER)
    assert spy.calls[0][1][0]["subject"] == "computer_organization"


async def test_submit_history_failure_is_non_blocking(monkeypatch):
    """历史落库抛错 → fail-open：答题接口照常返回，不 500。"""
    _install_spy(monkeypatch, raises=RuntimeError("db locked"))
    resp = await quiz_submit(_req(_rec("data_structures", True)), USER)
    assert resp.total == 1 and resp.correct_count == 1


# ════════════════════════════════════════════════════════════
# 2. 步骤化答题完成
# ════════════════════════════════════════════════════════════

async def test_step_answer_appends_history_on_finish(monkeypatch):
    """步骤化答题完成 → 落一条 history（subject 已是规范键，原样落库）。"""
    spy = _install_spy(monkeypatch)
    res = await submit_step_answer(
        "step_tcp_1",
        quiz_api.StepAnswerRequest(question_id="step_tcp_1", step_index=2, answer="wrong"),
        USER,
    )
    assert res.finished is True
    assert len(spy.calls) == 1
    user_id, records = spy.calls[0]
    assert user_id == USER["user_id"]
    assert records == [{"subject": "computer_network", "correct": False, "difficulty": "hard"}]


async def test_step_answer_no_history_before_finish(monkeypatch):
    """未完成最后一步 → 不落库（与掌握度回写同一时机）。"""
    spy = _install_spy(monkeypatch)
    res = await submit_step_answer(
        "step_tcp_1",
        quiz_api.StepAnswerRequest(question_id="step_tcp_1", step_index=0, answer="wrong"),
        USER,
    )
    assert res.finished is False
    assert spy.calls == []


async def test_step_answer_history_failure_is_non_blocking(monkeypatch):
    """步骤化答题历史落库抛错 → fail-open，仍返回步骤结果。"""
    _install_spy(monkeypatch, raises=RuntimeError("db locked"))
    res = await submit_step_answer(
        "step_tcp_1",
        quiz_api.StepAnswerRequest(question_id="step_tcp_1", step_index=2, answer="wrong"),
        USER,
    )
    assert res.finished is True
    assert res.correct is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
