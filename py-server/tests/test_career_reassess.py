# -*- coding: utf-8 -*-
# ============================================================
# career_service · 回溯重评（⑤ 评分一致性，对标 Gradescope）单测
#
# 立论：
#   1. 重评用「当前 rubric（bars_anchor）」重跑幂等评估，不覆盖旧分（追加新记录）；
#   2. 证据链必须与重评后的 assessment 同源重建（score/rubric_text 不挂旧分）；
#   3. 只对 finished 会话生效；未知会话/情景 fail-closed 抛错。
#
# 全部 mock store/nodes，不依赖真实 DB 与 LLM，离线可复现。
# 运行：python -m pytest tests/test_career_reassess.py -q
# ============================================================

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from services import career_service

pytestmark = pytest.mark.p0_regression


# ── 测试替身数据 ──
_NEW_SEED = {
    "id": "review_requirement_alignment",
    "type": "review",
    "bars_anchor": {
        "collab": {"1": "新低", "3": "新中", "5": "新高"},
        "problem_solving": {"1": "低", "3": "中", "5": "高"},
    },
    "focus_points": ["对齐诉求"],
    "rubric_version": "1.1",
}

_OLD_BARS = {"collab": {"1": "旧低", "3": "旧中", "5": "旧高"}}

_FINISHED_STATE = {
    "session_id": "sess_test",
    "user_id": "u1",
    "task_id": None,
    "scenario_id": "review_requirement_alignment",
    "scenario_label": "需求评审质询",
    "title": "需求评审会",
    "rubric_version": "1.0",
    "status": "finished",
    "scenario_script": {
        "setting": "评审现场", "interviewer_role": "产品经理",
        "probe_plan": ["追问排期"], "dimension_weights": {"collab": 1.0},
        "bars_anchor": _OLD_BARS,
    },
    "dialogue_turns": [
        {
            "turn_index": 1, "mode": "normal", "question": "两周能做吗",
            "answer": "我建议先做核心功能、数据说话、两周交付 MVP",
            "probe_dimension": "collab",
            "evidence": {"density": 0.6, "dimension_hits": [
                {"dimension": "collab", "polarity": "positive", "note": "提出分期方案"}]},
        },
    ],
}

_OLD_ASSESSMENT = {"dimensions": {"collab": {"score": 3.0}}, "overall": 3.0}
_NEW_ASSESSMENT = {
    "dimensions": {"collab": {
        "score": 5.0, "level": "excellent", "confidence": 0.8,
        "evidence_turns": [1], "evidence_quotes": ["我建议先做核心功能"],
        "rationale": "给出分期方案",
    }},
    "overall": 5.0,
}


async def _assess_stub(script, *args, **kwargs):
    """替换 assess_session：记录调用时的 script，返回可控评估。"""
    _assess_stub.called_script = script
    return _NEW_ASSESSMENT


@pytest.fixture()
def reassess_env(monkeypatch):
    """构造可离线重评的替身环境：store 与 nodes 全部 monkeypatch。"""
    calls = {}
    monkeypatch.setattr("db.career_store.get_session_state", lambda sid: _FINISHED_STATE)
    monkeypatch.setattr("db.career_store.list_assessments_by_session",
                        lambda sid: [{"dimension_scores": _OLD_ASSESSMENT, "improvement_plan": {}}])
    monkeypatch.setattr("db.career_store.save_session_state", lambda state, **kw: calls.setdefault("saved_state", []).append(dict(state)))
    monkeypatch.setattr("agents.career_nodes.get_scenario", lambda sid: _NEW_SEED)
    _assess_stub.called_script = None
    monkeypatch.setattr("agents.career_nodes.assess_session", _assess_stub)

    def _save_assessment(session_id, user_id, assessment, improvement, evidence_chain, consistency_score, task_id):
        calls["saved_assessment"] = {
            "session_id": session_id, "assessment": assessment,
            "evidence_chain": evidence_chain, "consistency_score": consistency_score,
        }
        return "assess_new"
    monkeypatch.setattr("db.career_store.save_assessment", _save_assessment)
    return calls


def test_overall_of_handles_none_and_dict():
    assert career_service._overall_of(None) is None
    assert career_service._overall_of({"overall": 4.2}) == 4.2
    assert career_service._overall_of({"dimensions": {}}) is None


def test_build_evidence_chain_syncs_score_to_assessment(monkeypatch):
    """证据链的 score/rubric_text 必须与传入 assessment 同源，不挂旧分。"""
    monkeypatch.setattr("agents.career_nodes.get_scenario", lambda sid: _NEW_SEED)
    chain = career_service._build_evidence_chain(_FINISHED_STATE, _NEW_ASSESSMENT)
    collab = next(c for c in chain if c["dimension"] == "collab")
    assert collab["score"] == 5.0
    assert collab["rubric_text"] == "新高"          # 来自 _NEW_SEED 的 5 档
    assert collab["per_turn_evidence"][0]["answer_snippet"] == "我建议先做核心功能、数据说话、两周交付 MVP"


def test_reassess_uses_current_rubric_and_keeps_old_score(reassess_env):
    """重评：assess_session 收到「新 bars_anchor」的 script，旧分保留、新分落库。"""
    import asyncio
    result = asyncio.run(career_service.reassess_session("sess_test"))

    # assess_session 被调用时的 script 用的是新 rubric（不是旧 bars）
    assert _assess_stub.called_script is not None
    assert _assess_stub.called_script["bars_anchor"] == _NEW_SEED["bars_anchor"]
    assert _assess_stub.called_script["bars_anchor"] != _OLD_BARS

    # 版本对比与分数对比
    assert result["rubric_version_before"] == "1.0"
    assert result["rubric_version_after"] == "1.1"
    assert result["previous_overall"] == 3.0
    assert result["history_overalls"] == [3.0]   # 重评前的历史各次 overall
    assert result["new_overall"] == 5.0
    assert result["reassessed"] is True

    # 新评估已落库（追加，非覆盖），证据链与新分同源
    saved = reassess_env["saved_assessment"]
    assert saved["consistency_score"] == 5.0
    assert saved["evidence_chain"][0]["score"] == 5.0


def test_reassess_rejects_unfinished(monkeypatch):
    import asyncio
    state = dict(_FINISHED_STATE, status="ongoing")
    monkeypatch.setattr("db.career_store.get_session_state", lambda sid: state)
    with pytest.raises(ValueError):
        asyncio.run(career_service.reassess_session("sess_test"))


def test_reassess_rejects_unknown_session(monkeypatch):
    import asyncio
    monkeypatch.setattr("db.career_store.get_session_state", lambda sid: None)
    with pytest.raises(KeyError):
        asyncio.run(career_service.reassess_session("sess_missing"))


def test_reassess_rejects_unknown_scenario(monkeypatch):
    import asyncio
    monkeypatch.setattr("db.career_store.get_session_state", lambda sid: _FINISHED_STATE)
    monkeypatch.setattr("agents.career_nodes.get_scenario", lambda sid: None)
    with pytest.raises(ValueError):
        asyncio.run(career_service.reassess_session("sess_test"))
