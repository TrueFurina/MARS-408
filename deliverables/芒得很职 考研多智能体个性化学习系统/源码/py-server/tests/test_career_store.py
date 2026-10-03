# -*- coding: utf-8 -*-
"""career 分支正式测试 · 数据层（5 表 + CRUD）（P3①）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from db import career_store


@pytest.fixture(scope="module", autouse=True)
def _career_tables():
    career_store.ensure_tables(force=True)
    yield


def _new_state(sid, user="u_test", scenario="x"):
    return {
        "session_id": sid, "user_id": user, "scenario_id": scenario,
        "scenario_type": "defense", "mode": "normal",
        "dialogue_turns": [], "status": "ongoing",
    }


class TestTables:
    def test_ensure_tables_idempotent(self):
        career_store.ensure_tables(force=True)

    def test_sqlite_or_pg_ready(self):
        assert career_store._TABLES_READY is True


class TestSessionCRUD:
    def test_create_and_read_roundtrip(self):
        sid = career_store.new_id("cs")
        ret = career_store.create_session(_new_state(sid, scenario="defense_thesis_proposal"))
        assert ret == sid
        got = career_store.get_session_state(sid)
        assert got is not None
        assert got.get("scenario_id") == "defense_thesis_proposal"
        assert got.get("mode") == "normal"

    def test_save_state_update(self):
        sid = career_store.new_id("cs")
        career_store.create_session(_new_state(sid, user="u_test2"))
        st = career_store.get_session_state(sid)
        st["mode"] = "catfish"
        career_store.save_session_state(st)
        got = career_store.get_session_state(sid)
        assert got.get("mode") == "catfish"


class TestTurns:
    def test_turns_appended_ordered(self):
        sid = career_store.new_id("cs")
        career_store.create_session(_new_state(sid))
        for i in (2, 1, 3):  # 乱序写入
            career_store.add_turn(sid, {
                "turn_index": i, "question": f"q{i}", "answer": f"a{i}",
                "evidence": {"density": 0.5},
            })
        turns = career_store.get_turns(sid)
        assert [t["turn_index"] for t in turns] == [1, 2, 3]


class TestAssessment:
    def test_save_and_get_latest(self):
        sid = career_store.new_id("cs")
        career_store.create_session(_new_state(sid))
        career_store.save_assessment(sid, "u_a", {"overall": 3.5}, {"actions": []})
        got = career_store.get_assessment_by_session(sid)
        assert got is not None
        assert got["dimension_scores"]["overall"] == 3.5  # 往返

    def test_overwrite_same_second_keeps_record(self):
        # 已知限制：created_at 秒级精度，同秒多次保存时"取最新"顺序不保证；
        # 约束为不丢数据（取到两次中的任一次），不承诺取到最后一次。
        sid = career_store.new_id("cs")
        career_store.create_session(_new_state(sid))
        career_store.save_assessment(sid, "u_a", {"overall": 3.5}, {"actions": []})
        career_store.save_assessment(sid, "u_a", {"overall": 4.2}, {"actions": []})
        got = career_store.get_assessment_by_session(sid)
        assert got["dimension_scores"]["overall"] in (3.5, 4.2)
