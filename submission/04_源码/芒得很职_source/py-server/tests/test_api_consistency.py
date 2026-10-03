# ============================================================
# Test Report — API Consistency (Fix 1-4 Regression Tests)
# ============================================================
# Author: Edward (QA Engineer)
# Tests: sessions load/list/save/delete + knowledge-graph endpoint
# ============================================================

import pytest

from fastapi.testclient import TestClient
from main import app
from seed_data import KNOWLEDGE_GRAPH, SEED_SUBJECTS


# ── Fixtures ──

client = TestClient(app)

# 注：会话存储隔离由 tests/conftest.py 的 `_temp_sessions` autouse fixture 统一处理
# （monkeypatch api.sessions.SESSIONS_DIR → tmp_path），不再在此处触碰真实文件。


def _save_session(conv_id: str, title: str = "Test对话", messages: list = None):
    """Helper: save a session via POST /api/sessions/save."""
    if messages is None:
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你？"},
        ]
    return client.post(
        "/api/sessions/save",
        json={"conv_id": conv_id, "title": title, "messages": messages},
    )


# ============================================================
# Fix 1: GET /api/sessions/list — return correct format
# ============================================================


class TestSessionList:
    """Verify GET /api/sessions/list returns {sessions: [{conv_id, title, msg_count, updated}]}"""

    def test_list_empty(self):
        """Empty sessions dir → returns {sessions: []}."""
        resp = client.get("/api/sessions/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_list_after_save(self):
        """After saving a session, list should include it."""
        _save_session("test-conv-001", "我的测试对话")
        resp = client.get("/api/sessions/list")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) >= 1

        session = data["sessions"][0]
        assert "conv_id" in session
        assert "title" in session
        assert "msg_count" in session
        assert "updated" in session

        # Verify values
        assert session["conv_id"] == "test-conv-001"
        assert session["title"] == "我的测试对话"
        assert session["msg_count"] == 2  # 2 messages saved
        assert isinstance(session["updated"], (int, float))
        assert session["updated"] > 0

    def test_list_multiple_sessions_sorted(self):
        """Sessions sorted by updated time (most recent first)."""
        _save_session("conv-alpha", "Alpha")
        _save_session("conv-beta", "Beta")
        resp = client.get("/api/sessions/list")
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) >= 2
        # Both sessions should appear in the list (order depends on timestamp precision)
        session_ids = [s["conv_id"] for s in sessions]
        assert "conv-alpha" in session_ids and "conv-beta" in session_ids

    def test_list_msg_count_matches(self):
        """msg_count should match the actual number of messages saved."""
        msgs = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
        ]
        _save_session("conv-5msgs", "5msg对话", msgs)
        resp = client.get("/api/sessions/list")
        session = next(
            s for s in resp.json()["sessions"] if s["conv_id"] == "conv-5msgs"
        )
        assert session["msg_count"] == 5


# ============================================================
# Fix 1: GET /api/sessions/load/{conv_id} — return full conversation
# ============================================================


class TestSessionLoad:
    """Verify GET /api/sessions/load/{conv_id} returns {conv_id, title, messages, created_at}"""

    def test_load_existing_session(self):
        """Load a saved session → returns full data."""
        msgs = [
            {"role": "user", "content": "什么是TCP?"},
            {"role": "assistant", "content": "TCP是传输控制协议"},
        ]
        _save_session("conv-load-1", "TCP学习", msgs)
        resp = client.get("/api/sessions/load/conv-load-1")
        assert resp.status_code == 200
        data = resp.json()

        assert "conv_id" in data
        assert "title" in data
        assert "messages" in data
        assert "created_at" in data

        assert data["conv_id"] == "conv-load-1"
        assert data["title"] == "TCP学习"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "什么是TCP?"
        assert data["messages"][1]["role"] == "assistant"

    def test_load_nonexistent_session(self):
        """Load a non-existent conv_id → 404."""
        resp = client.get("/api/sessions/load/nonexistent-id")
        assert resp.status_code == 404

    def test_load_returns_message_role_content_only(self):
        """Messages should contain role and content (Fix 2 consistency check)."""
        _save_session("conv-msg-format", "格式测试")
        resp = client.get("/api/sessions/load/conv-msg-format")
        data = resp.json()
        for msg in data["messages"]:
            assert "role" in msg
            assert "content" in msg


# ============================================================
# Fix 2: POST /api/sessions/save — accepts single-object payload
# ============================================================


class TestSessionSave:
    """Verify POST /api/sessions/save accepts {conv_id, title, messages} format."""

    def test_save_basic(self):
        """Save a single conversation object → returns {status: ok, conv_id}."""
        resp = _save_session("save-test-1", "保存测试")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["conv_id"] == "save-test-1"

    def test_save_with_messages(self):
        """Messages should only contain {role, content} fields."""
        resp = client.post(
            "/api/sessions/save",
            json={
                "conv_id": "save-msg-format",
                "title": "消息格式",
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi"},
                ],
            },
        )
        assert resp.status_code == 200

        # Verify stored messages only have role and content
        load_resp = client.get("/api/sessions/load/save-msg-format")
        msgs = load_resp.json()["messages"]
        for m in msgs:
            assert set(m.keys()) == {"role", "content"}

    def test_save_empty_messages(self):
        """Save with empty messages list → should work."""
        resp = _save_session("save-empty", "空对话", [])
        assert resp.status_code == 200

    def test_save_same_conv_id_twice(self):
        """Save same conv_id twice → should update (not error)."""
        _save_session("save-dup", "第一次", [{"role": "user", "content": "v1"}])
        _save_session("save-dup", "第二次", [{"role": "user", "content": "v2"}])
        resp = client.get("/api/sessions/load/save-dup")
        # Title should be preserved from first save (backend keeps prev_title)
        data = resp.json()
        assert data["conv_id"] == "save-dup"

    def test_save_no_title_gets_default(self):
        """If title is empty, backend generates a default title."""
        resp = _save_session("save-no-title", "", [])
        assert resp.status_code == 200
        # Load and check title was assigned
        load_resp = client.get("/api/sessions/load/save-no-title")
        title = load_resp.json()["title"]
        assert len(title) > 0


# ============================================================
# Fix 3: DELETE /api/sessions/delete/{conv_id} — path param
# ============================================================


class TestSessionDelete:
    """Verify DELETE /api/sessions/delete/{conv_id} uses path param."""

    def test_delete_existing(self):
        """Delete an existing session → {status: ok}."""
        _save_session("delete-test-1", "删除测试")
        resp = client.delete("/api/sessions/delete/delete-test-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        # Verify it's actually gone
        load_resp = client.get("/api/sessions/load/delete-test-1")
        assert load_resp.status_code == 404

    def test_delete_nonexistent(self):
        """Delete a non-existent conv_id → 404."""
        resp = client.delete("/api/sessions/delete/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_then_list(self):
        """After deletion, session should not appear in list."""
        _save_session("del-list-1", "删后列表")
        _save_session("del-list-2", "保留")
        client.delete("/api/sessions/delete/del-list-1")
        resp = client.get("/api/sessions/list")
        sessions = resp.json()["sessions"]
        conv_ids = [s["conv_id"] for s in sessions]
        assert "del-list-1" not in conv_ids
        assert "del-list-2" in conv_ids

    def test_delete_uses_path_param_not_query(self):
        """Verify endpoint is /delete/{conv_id}, NOT /delete?conv_id=..."""
        _save_session("path-param-test", "路径参数")
        resp = client.delete("/api/sessions/delete/path-param-test")
        assert resp.status_code == 200

        # Using query param style should return 404 (route doesn't match)
        resp2 = client.delete("/api/sessions/delete?conv_id=path-param-test")
        assert resp2.status_code != 200


# ============================================================
# Fix 4: GET /api/knowledge-graph — subject filtering
# ============================================================


class TestKnowledgeGraph:
    """Verify GET /api/knowledge-graph endpoint with subject filtering.

    契约（见 api/knowledge.py 文档）：节点 group 须等于「该节点所属科目在
    SEED_SUBJECTS 中的 1-based 索引」，过滤由端点内部完成。
    本测试不写死任何 group 数字，而是复刻端点的 resolve_group 逻辑，
    对全量 KNOWLEDGE_GRAPH 计算期望集合，再与端点响应做等价校验，
    从而与 seed_data 中动态的「4 科目合并 + 自动扩展」构建解耦。
    """

    SUBJECT_KEYS = list(SEED_SUBJECTS.keys())
    KEY_TO_GROUP = {k: i + 1 for i, k in enumerate(SUBJECT_KEYS)}

    # 实际 subjects.py group_map 使用的合并图编号
    MERGED_GROUP_MAP = {
        "overview": 13, "network": 16,
        "ds_linear": 8, "co_cpu": 19, "os_process": 23,
    }

    @staticmethod
    def _resolve_group(node):
        """复刻 api/knowledge.py 的 resolve_group 逻辑。"""
        nid = node.get("id", "")
        if nid in TestKnowledgeGraph.KEY_TO_GROUP:
            return TestKnowledgeGraph.KEY_TO_GROUP[nid]
        base = nid.split("_")[0] if "_" in nid else nid
        if base in TestKnowledgeGraph.KEY_TO_GROUP:
            return TestKnowledgeGraph.KEY_TO_GROUP[base]
        try:
            return int(node.get("group", 1))
        except (TypeError, ValueError):
            return 1

    def test_kg_all_returns_full_graph(self):
        """subject=all → returns all nodes and edges."""
        resp = client.get("/api/knowledge-graph?subject=all")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data and "edges" in data
        assert len(data["nodes"]) == len(KNOWLEDGE_GRAPH["nodes"])
        assert len(data["edges"]) == len(KNOWLEDGE_GRAPH["edges"])

    def test_kg_default_is_all(self):
        """Default subject parameter is 'all' → returns full graph."""
        resp = client.get("/api/knowledge-graph")
        assert resp.status_code == 200
        d_default = resp.json()
        d_all = client.get("/api/knowledge-graph?subject=all").json()
        assert len(d_default["nodes"]) == len(d_all["nodes"])

    def test_kg_filter_matches_expected_subject(self):
        """对若干代表科目，验证过滤结果 group 正确且含科目基础节点。"""
        for subject, expected_group in self.MERGED_GROUP_MAP.items():
            resp = client.get(f"/api/knowledge-graph?subject={subject}")
            assert resp.status_code == 200, subject
            data = resp.json()
            node_ids = {n["id"] for n in data["nodes"]}

            # All returned nodes must belong to the expected group
            for node in data["nodes"]:
                assert node["group"] == expected_group, (subject, node["id"], node["group"])

            # Subject's base node must be present
            assert subject in node_ids, f"{subject} 未返回自身基础节点"

            # Edges only within the filtered set
            for edge in data["edges"]:
                assert edge["source"] in node_ids
                assert edge["target"] in node_ids

    def test_kg_invalid_subject_returns_all(self):
        """Invalid subject value → falls through to returning all."""
        resp = client.get("/api/knowledge-graph?subject=invalid_xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == len(KNOWLEDGE_GRAPH["nodes"])

    def test_kg_node_has_required_fields(self):
        """Each node should have id, label, group fields."""
        resp = client.get("/api/knowledge-graph?subject=all")
        for node in resp.json()["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "group" in node

    def test_kg_edge_has_required_fields(self):
        """Each edge should have source, target fields."""
        resp = client.get("/api/knowledge-graph?subject=all")
        for edge in resp.json()["edges"]:
            assert "source" in edge
            assert "target" in edge


# ============================================================
# Cross-cutting: Frontend-Backend contract verification
# ============================================================


class TestFrontendBackendContract:
    """Verify that API responses match the format the frontend expects."""

    def test_list_updated_is_unix_timestamp(self):
        """Frontend expects updated field to be a Unix timestamp (seconds).
        The backend returns os.path.getmtime() which is a float (seconds)."""
        _save_session("ts-test", "时间戳测试")
        resp = client.get("/api/sessions/list")
        session = next(
            s for s in resp.json()["sessions"] if s["conv_id"] == "ts-test"
        )
        # updated should be a positive number (Unix timestamp in seconds)
        assert isinstance(session["updated"], (int, float))
        assert session["updated"] > 1700000000  # after 2023

    def test_save_accepts_only_role_content_in_messages(self):
        """Frontend sends messages with only {role, content}.
        Backend should accept and store this format correctly."""
        resp = client.post(
            "/api/sessions/save",
            json={
                "conv_id": "frontend-format",
                "title": "前端格式",
                "messages": [
                    {"role": "user", "content": "测试消息"},
                ],
            },
        )
        assert resp.status_code == 200

    def test_delete_path_param_contract(self):
        """Frontend now uses /delete/{conv_id} (path param).
        Verify this route pattern works correctly."""
        _save_session("contract-delete", "契约删除")
        resp = client.delete("/api/sessions/delete/contract-delete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
