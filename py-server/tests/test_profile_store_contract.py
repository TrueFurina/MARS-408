# -*- coding: utf-8 -*-
"""db/profile_store.py 画像域单测（M-4 ② 拆出的新模块，此前仅 73% 覆盖）

用唯一前缀的测试 uid 写入项目既有 SQLite 库（不清理、不删除任何数据，
仅追加唯一 id 的记录），断言集中在契约语义上：
  - 画像/答题历史/会话/快照的读写往返
  - 空输入必须是 no-op（不是报错）
  - 会话按 (user_id, conv_id) upsert，不得产生重复行
  - 落库 JSON 损坏时必须回退成默认值，而不是把异常抛给调用方
"""

import uuid

from db.core import get_conn
from db.profile_store import (
    append_quiz_history,
    get_conversations,
    get_profile,
    get_profile_snapshots,
    get_quiz_history,
    save_conversations,
    save_profile,
    save_profile_snapshot,
)

# 每次运行生成唯一前缀。首次提交时用固定 uid，导致第二次运行读到上一次残留数据、
# 顺序断言在"全量重复跑"时失败（单跑过、全量挂）。红线是只追加不删除历史数据，
# 唯一 id 让重复运行互不干扰，同时不需要任何清理动作。
RUN_TAG = uuid.uuid4().hex[:8]
UID = f"__pytest_ps_{RUN_TAG}__"


class TestProfileRoundTrip:
    def test_save_then_get(self):
        save_profile(UID, {"chinese": 0.6, "note": "单元测试"})
        assert get_profile(UID) == {"chinese": 0.6, "note": "单元测试"}

    def test_save_overwrites_previous(self):
        save_profile(UID, {"v": 1})
        save_profile(UID, {"v": 2})
        assert get_profile(UID) == {"v": 2}

    def test_unknown_user_returns_none(self):
        assert get_profile(UID + "_absent") is None

    def test_empty_user_id_returns_none(self):
        assert get_profile("") is None


class TestQuizHistory:
    def test_empty_records_is_noop(self):
        before = get_quiz_history(UID)
        append_quiz_history(UID, [])
        assert get_quiz_history(UID) == before

    def test_append_and_read_back_preserves_order(self):
        uid = UID + "_quiz"
        append_quiz_history(uid, [
            {"subject": "ds", "correct": True, "difficulty": "easy", "timestamp": "2026-01-01 00:00:00"},
            {"subject": "os", "correct": False, "difficulty": "hard", "timestamp": "2026-01-02 00:00:00"},
        ])
        rows = get_quiz_history(uid)
        assert [r["subject"] for r in rows] == ["ds", "os"]
        assert rows[0]["correct"] is True and rows[1]["correct"] is False
        assert isinstance(rows[1]["correct"], bool), "correct 必须回读为布尔值而非 0/1"

    def test_missing_timestamp_filled_with_current_time(self):
        uid = UID + "_quiz_ts"
        append_quiz_history(uid, [{"subject": "net", "correct": True}])
        row = get_quiz_history(uid)[0]
        assert row["timestamp"], "缺省时间戳应由 store 补齐，不得为空"

    def test_defaults_applied_for_missing_fields(self):
        uid = UID + "_quiz_defaults"
        append_quiz_history(uid, [{"correct": False}])
        row = get_quiz_history(uid)[0]
        assert row["subject"] == "" and row["difficulty"] == "medium"


class TestConversations:
    def test_empty_list_is_noop(self):
        save_conversations(UID, [])
        assert get_conversations(UID + "_never") == []

    def test_round_trip_structure(self):
        uid = UID + "_conv"
        save_conversations(uid, [{
            "id": "c1", "title": "三次握手",
            "messages": [{"role": "user", "content": "讲讲三次握手"}],
        }])
        rows = get_conversations(uid)
        assert len(rows) == 1
        assert rows[0]["id"] == "c1" and rows[0]["title"] == "三次握手"
        assert rows[0]["messages"][0]["content"] == "讲讲三次握手"
        assert rows[0]["updated_at"], "应记录更新时间"

    def test_same_conv_id_upserts_not_duplicates(self):
        """(user_id, conv_id) 唯一：二次保存必须覆盖，否则会话列表会重复。"""
        uid = UID + "_conv_upsert"
        save_conversations(uid, [{"id": "c9", "title": "旧标题", "messages": []}])
        save_conversations(uid, [{"id": "c9", "title": "新标题", "messages": [{"role": "user", "content": "x"}]}])
        rows = get_conversations(uid)
        assert len(rows) == 1
        assert rows[0]["title"] == "新标题"

    def test_corrupted_messages_json_falls_back_to_empty_list(self):
        """落库 JSON 被写坏时，读取必须降级为空列表而非抛异常。"""
        uid = UID + "_conv_corrupt"
        save_conversations(uid, [{"id": "c-bad", "title": "坏数据", "messages": []}])
        with get_conn() as _:
            pass
        conn = get_conn()
        conn.execute(
            "UPDATE user_conversations SET messages_json=? WHERE user_id=? AND conv_id=?",
            ("{不是合法 JSON", uid, "c-bad"),
        )
        conn.commit()
        rows = get_conversations(uid)
        assert rows and rows[0]["messages"] == []


class TestProfileSnapshots:
    def test_save_returns_positive_id(self):
        sid = save_profile_snapshot(UID + "_snap", {"stage": "initial"})
        assert isinstance(sid, int) and sid > 0

    def test_list_returns_snapshots_with_structure(self):
        uid = UID + "_snap_list"
        save_profile_snapshot(uid, {"n": 1})
        save_profile_snapshot(uid, {"n": 2})
        rows = get_profile_snapshots(uid, limit=10)
        assert len(rows) >= 2
        assert set(rows[0]) >= {"id", "snapshot", "created_at"}
        assert isinstance(rows[0]["snapshot"], dict)

    def test_limit_is_respected(self):
        uid = UID + "_snap_limit"
        for i in range(4):
            save_profile_snapshot(uid, {"i": i})
        assert len(get_profile_snapshots(uid, limit=2)) == 2

    def test_unknown_user_returns_empty_list(self):
        assert get_profile_snapshots(UID + "_no_snap") == []

    def test_corrupted_snapshot_json_falls_back_to_empty_dict(self):
        uid = UID + "_snap_corrupt"
        sid = save_profile_snapshot(uid, {"ok": True})
        conn = get_conn()
        conn.execute(
            "UPDATE profile_snapshots SET snapshot_json=? WHERE id=?", ("[坏掉的", sid)
        )
        conn.commit()
        rows = get_profile_snapshots(uid)
        target = [r for r in rows if r["id"] == sid]
        assert target and target[0]["snapshot"] == {}


class TestCompatibilityDelegation:
    """拆域后 db.user_store 必须继续提供这些符号（动态委托，不是快照）。"""

    def test_user_store_delegates_to_profile_store(self):
        import db.profile_store as ps
        import db.user_store as us

        for name in ("save_profile", "get_profile", "append_quiz_history", "get_quiz_history",
                     "save_conversations", "get_conversations",
                     "save_profile_snapshot", "get_profile_snapshots"):
            assert getattr(us, name) is getattr(ps, name), f"{name} 应动态委托到 profile_store"

    def test_delegation_follows_replacement(self):
        """动态委托的关键性质：替换 profile_store 的符号后 user_store 立刻跟随（非静态快照）。"""
        import db.profile_store as ps
        import db.user_store as us

        original = ps.get_profile
        sentinel = lambda uid: {"sentinel": True}  # noqa: E731
        ps.get_profile = sentinel
        try:
            assert us.get_profile is sentinel
        finally:
            ps.get_profile = original
        assert us.get_profile is original
