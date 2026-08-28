# ============================================================
# MARS-408 全端点 API 契约测试（全面深度覆盖）
# ============================================================
# 设计目标：
#   1. 可达性矩阵 —— 覆盖全部 ~55 个 API 端点，断言响应码 != 404，
#      从架构层面保证“无路由缺失 / 无拼写漂移”（这正是本次事故的根因类型）。
#   2. 关键流程精确断言 —— 认证闭环、会话 CRUD、纯逻辑闭环
#      （学习路径 / 答题 / 评估）做业务正确性校验。
#   3. LLM 依赖端点 —— 通过 conftest 的 mock_llm 注入离线 Mock，
#      确定性验证 profile/build、chat/send 等能返回结构化响应。
#
# KB 惰性灌库（幂等）；失败仅告警，端点仍应返回 200 + 结构化响应。
# ============================================================

import os
import sys
import time
import uuid
import warnings

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402

client = TestClient(app)

# ── 惰性 KB 灌库（幂等，失败仅告警）──
try:
    from db.milvus_client import vector_db
    from main import _seed_vector_db

    vector_db.connect()
    if vector_db.count("netlearn_kb") == 0:
        _seed_vector_db()
except Exception as e:  # pragma: no cover - 沙箱/无模型时跳过
    warnings.warn(f"KB 惰性灌库跳过: {e}")


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def auth_token():
    """注册一个一次性测试用户并返回 token（模块级，整文件复用）。"""
    username = f"testuser_{uuid.uuid4().hex[:10]}"
    r = client.post(
        "/api/auth/register",
        json={"username": username, "password": "pw_123456", "display_name": username},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ────────────────────────────────────────────────────────────
# 1. 全端点可达性矩阵（架构级：无路由缺失）
#    条目：(method, path, body_or_None, needs_auth)
# ────────────────────────────────────────────────────────────

REACHABILITY = [
    # 公开信息类 GET
    ("GET", "/api/status", None, False),
    ("GET", "/api/subjects", None, False),
    ("GET", "/api/knowledge/stats", None, False),
    ("GET", "/api/knowledge/list", None, False),
    ("GET", "/api/knowledge-graph", None, False),
    ("GET", "/api/config", None, False),
    ("GET", "/api/engine/teaching-rules", None, False),
    ("GET", "/api/engine/teaching-rules/prerequisites/topic1", None, False),
    ("GET", "/api/engine/lora-config", None, False),
    ("GET", "/api/engine/neural-mixer", None, False),
    ("GET", "/api/engine/status", None, False),
    ("GET", "/api/multimodal/supported-types", None, False),
    ("GET", "/api/sessions/list", None, False),
    # 认证闭环
    ("POST", "/api/auth/register",
     {"username": f"ru_{uuid.uuid4().hex[:8]}", "password": "pw", "display_name": "ru"}, False),
    ("POST", "/api/auth/login", {"username": "any", "password": "any"}, False),
    ("POST", "/api/auth/logout", None, False),
    ("GET", "/api/auth/me", None, True),
    # 用户域（需登录）
    ("GET", "/api/user/profile", None, True),
    ("GET", "/api/user/quiz-history", None, True),
    ("GET", "/api/user/conversations", None, True),
    ("PUT", "/api/user/profile", {"name": "测试名"}, True),
    ("POST", "/api/user/quiz-history", {"records": []}, True),
    ("POST", "/api/user/conversations", {"messages": []}, True),
    # 管理员 / 教师域（无 token → 鉴权闸门 401/403，仍 ≠404）
    ("GET", "/api/admin/users", None, False),
    ("GET", "/api/admin/stats", None, False),
    ("GET", "/api/teacher/students/overview", None, False),
    ("GET", "/api/teacher/knowledge-base/stats", None, False),
    ("GET", "/api/teacher/analytics/class-performance", None, False),
    ("GET", "/api/teacher/agent-performance", None, False),
    ("GET", "/api/teacher/students/s1/detail", None, False),
    ("POST", "/api/teacher/knowledge-base/import", {}, False),
    # 纯逻辑闭环
    ("POST", "/api/learning-path", {"current_chapter": 1}, False),
    ("POST", "/api/learning-path-with-resources", {"current_chapter": 1}, False),
    ("POST", "/api/quiz/submit",
     {"profile": {}, "records": [{"subject": "network", "correct": True}]}, False),
    ("POST", "/api/assessment", {"quiz_history": [{"subject": "network", "correct": True}]}, False),
    # 知识库写操作
    ("POST", "/api/knowledge/upsert",
     {"documents": [{"content": "x", "metadata": {"subject": "network"}}]}, False),
    ("POST", "/api/knowledge/delete", {"ids": ["x"]}, False),
    ("POST", "/api/knowledge/upload", {}, False),
    ("POST", "/api/knowledge/preview", {"content": "x"}, False),
    ("POST", "/api/knowledge/batch-commit",
     {"documents": [{"content": "x", "metadata": {}}]}, False),
    ("POST", "/api/knowledge/reindex", None, False),
    ("POST", "/api/knowledge/clear", None, False),
    ("POST", "/api/knowledge/graph", {"subject": "all"}, False),
    # LLM 依赖端点（可达性即可，具体响应由 mock 组精确校验）
    ("POST", "/api/profile/build", {"message": "hi", "history": []}, False),
    ("POST", "/api/agents/generate-resource", {"topic": "TCP"}, False),
    ("POST", "/api/agents/generate-resource/stream", {"topic": "TCP"}, False),
    ("POST", "/api/agents/generate-extension", {"topic": "TCP"}, False),
    ("POST", "/api/agents/generate-ppt", {"topic": "TCP"}, False),
    ("POST", "/api/agents/generate-code-practice", {"topic": "TCP"}, False),
    ("POST", "/api/chat/send", {"message": "hi", "history": []}, False),
    ("POST", "/api/chat/stream", {"message": "hi", "history": []}, False),
    ("POST", "/api/config/test-llm", None, False),
    ("POST", "/api/engine/frugal-rag-full", {"query": "TCP"}, False),
    ("POST", "/api/engine/gomarl-consensus",
     {"topic": "TCP", "proposals": ["a", "b"]}, False),
    ("POST", "/api/engine/stop-decision/update", {"decision": "continue"}, False),
    ("POST", "/api/engine/conflict-check", {"proposals": ["a", "b"]}, False),
    ("POST", "/api/engine/teaching-rules/validate", {"rules": []}, False),
    ("POST", "/api/engine/teaching-rules/agent-assign", {"topic": "TCP"}, False),
    ("POST", "/api/engine/teaching-rules/prioritize", {"rules": []}, False),
    ("POST", "/api/agents/langgraph/stream", {"message": "hi", "history": []}, False),
    ("POST", "/api/multimodal/generate", {"topic": "TCP"}, False),
    ("POST", "/api/tutor/answer", {"question": "什么是TCP?", "student_answer": "传输协议"}, False),
    ("POST", "/api/rag/search", {"query": "TCP"}, False),
    ("POST", "/api/rag/generate", {"subject": "network", "count": 1}, False),
    ("POST", "/api/sandbox", {"code": "print(1)"}, False),
    ("POST", "/api/sandbox/run", {"code": "print(1)"}, False),
    ("POST", "/api/sessions/save",
     {"conv_id": "reach_c1", "title": "t", "messages": [{"role": "user", "content": "x"}]}, False),
    # ── Skill 插件生态端点（循环75-P0 补充契约覆盖） ──
    ("GET", "/api/skills/market", None, False),
    ("GET", "/api/skills/my", None, False),
    ("GET", "/api/skills/official", None, False),
    ("GET", "/api/skills/templates", None, False),
    ("POST", "/api/skills/create",
     {"name": "reach_skill", "description": "契约测试", "icon": "🤖",
      "system_prompt": "你是一个测试技能", "category": "teaching"}, False),
    ("POST", "/api/skills/import", {"skills": []}, False),
]


@pytest.mark.parametrize("method,path,body,needs_auth", REACHABILITY)
def test_endpoint_reachable(method, path, body, needs_auth, auth_token):
    """架构级契约：每个已知端点都必须挂载且可访问（响应码 != 404）。

    404 意味着路由缺失或路径拼写漂移——这正是本次事故中
    POST /knowledge/graph 的故障类型。此测试防止回归。
    """
    headers = _auth_headers(auth_token) if needs_auth else {}
    fn = getattr(client, method.lower())
    if body is None:
        resp = fn(path, headers=headers)
    else:
        resp = fn(path, json=body, headers=headers)
    assert resp.status_code != 404, (
        f"{method} {path} 返回 404 —— 路由缺失或路径漂移！"
    )
    # 流式端点（SSE）返回 text/event-stream 而非 JSON；其余端点必须返回合法 JSON
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        assert "data:" in resp.text, (
            f"{method} {path} 流式端点未返回任何 SSE 数据帧"
        )
    else:
        try:
            resp.json()
        except ValueError:
            pytest.fail(f"{method} {path} 未返回 JSON 响应（可能未捕获的崩溃）")


# ────────────────────────────────────────────────────────────
# 2. 认证闭环精确断言
# ────────────────────────────────────────────────────────────

class TestAuthFlow:
    def test_register_returns_token(self):
        r = client.post(
            "/api/auth/register",
            json={"username": f"af_{uuid.uuid4().hex[:8]}", "password": "pw_123456",
                  "display_name": "af"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and data["token"]
        assert "user" in data

    def test_login_wrong_password_rejected(self):
        r = client.post(
            "/api/auth/login", json={"username": "nonexistent_user_x", "password": "bad"}
        )
        assert r.status_code in (400, 401, 422)

    def test_me_requires_auth(self, no_mock_auth):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_with_token(self, auth_token):
        r = client.get("/api/auth/me", headers=_auth_headers(auth_token))
        assert r.status_code == 200
        assert "id" in r.json() or "user_id" in r.json() or "username" in r.json()

    def test_logout_ok(self):
        assert client.post("/api/auth/logout").status_code == 200


# ────────────────────────────────────────────────────────────
# 3. 会话 CRUD 精确断言（存储隔离由 conftest 临时目录保证）
# ────────────────────────────────────────────────────────────

class TestSessionsCRUD:
    def test_save_then_list_then_load_then_delete(self):
        cid = f"crud_{uuid.uuid4().hex[:8]}"
        save = client.post(
            "/api/sessions/save",
            json={"conv_id": cid, "title": "我的会话",
                  "messages": [{"role": "user", "content": "你好"}]},
        )
        assert save.status_code == 200
        assert save.json().get("status") == "ok"

        listing = client.get("/api/sessions/list").json()
        assert any(s["conv_id"] == cid for s in listing["sessions"])

        loaded = client.get(f"/api/sessions/load/{cid}")
        assert loaded.status_code == 200
        assert loaded.json()["messages"][0]["content"] == "你好"

        deleted = client.delete(f"/api/sessions/delete/{cid}")
        assert deleted.status_code == 200
        # 删除后再次加载应 404
        assert client.get(f"/api/sessions/load/{cid}").status_code == 404

    def test_load_missing_404(self):
        assert client.get("/api/sessions/load/nope_xyz").status_code == 404


# ────────────────────────────────────────────────────────────
# 4. 纯逻辑闭环精确断言（不依赖 LLM）
# ────────────────────────────────────────────────────────────

class TestClosedLoopLogic:
    def test_learning_path_structure(self):
        r = client.post("/api/learning-path", json={"current_chapter": 2})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == len(data["nodes"]) == 7
        statuses = {n["status"] for n in data["nodes"]}
        assert "current" in statuses
        # current_chapter=2 表示用户正在学第2章，已完成的是其之前的章节（计网概述=第1章）
        assert data["completed"] == 1

    def test_learning_path_with_resources(self):
        r = client.post(
            "/api/learning-path-with-resources",
            json={"current_chapter": 1,
                  "profile": {"weak_points": "网络层", "knowledge_base": "network"}},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["nodes"]
        assert "resources" in data["nodes"][0]

    def test_quiz_submit_merges_profile(self):
        r = client.post(
            "/api/quiz/submit",
            json={"profile": {"knowledge_base": "beginner"},
                  "records": [
                      {"subject": "network", "correct": True},
                      {"subject": "network", "correct": False},
                  ]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["accuracy"] == 0.5
        assert isinstance(data["updated_profile"], dict)
        assert "by_subject" in data

    def test_assessment_mastery(self):
        r = client.post(
            "/api/assessment",
            json={"quiz_history": [
                {"subject": "network", "correct": True},
                {"subject": "network", "correct": True},
                {"subject": "os", "correct": False},
            ]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_questions"] == 3
        assert data["overall_accuracy"] == pytest.approx(2 / 3, abs=0.01)
        assert "mastery" in data and "trend" in data


# ────────────────────────────────────────────────────────────
# 5. LLM 依赖端点（mock_llm 注入，确定性验证）
# ────────────────────────────────────────────────────────────

@pytest.mark.usefixtures("mock_llm")
class TestLLMEndpointsWithMock:
    def test_profile_build_completes(self):
        r = client.post(
            "/api/profile/build",
            json={"message": "我学过计算机网络，视觉型学习者",
                  "history": [
                      {"role": "assistant", "content": "先了解一下你"},
                      {"role": "user", "content": "我学过计网"},
                  ]},
        )
        assert r.status_code == 200
        data = r.json()
        # mock 返回含 learning_style/knowledge_base/study_time 的 JSON → 应判定完成
        assert data["completed"] is True
        assert isinstance(data["profile"], dict)
        assert data["profile"].get("learning_style") == "visual"

    def test_chat_send_returns_response(self):
        r = client.post(
            "/api/chat/send", json={"message": "你好", "history": []}
        )
        assert r.status_code == 200
        data = r.json()
        assert "response" in data and isinstance(data["response"], str)

    def test_learning_path_with_resources_llm_adjusted(self):
        r = client.post(
            "/api/learning-path-with-resources",
            json={"current_chapter": 1,
                  "profile": {"weak_points": "网络层", "knowledge_base": "network"}},
        )
        assert r.status_code == 200
        # mock 下 text_completion 返回空串 → 兜底，llm_adjusted 应为 False（但仍返回有效结构）
        assert r.json()["llm_adjusted"] is False
