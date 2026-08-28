# ============================================================
# MARS-408 完整学习闭环集成测试
# ============================================================
# 模拟一名考生的真实旅程，串联核心端点并断言状态演进的连贯性：
#   画像构建  →  学习路径规划  →  在线答题（更新画像）  →  学习效果评估
# 使用 conftest 的 mock_llm 注入离线 Mock，确保离线确定性跑通。
# ============================================================

import os
import sys
import uuid
import pytest

# segv_env：本模块调用真实 torch/numpy 嵌入等，Windows 原生库下触发 SIGSEGV；
# 仅 CI/Linux 干净环境运行，本地 Windows 由 conftest 自动跳过。
pytestmark = pytest.mark.segv_env

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402

client = TestClient(app)


@pytest.mark.usefixtures("mock_llm")
class TestLearningJourney:
    """端到端用户旅程：画像 → 路径 → 答题 → 评估。"""

    def test_full_journey_state_transition(self):
        # ── 1. 注册并登录 ──
        username = f"journey_{uuid.uuid4().hex[:8]}"
        reg = client.post(
            "/api/auth/register",
            json={"username": username, "password": "pw_123456", "display_name": username},
        )
        assert reg.status_code == 200
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # ── 2. 对话式画像构建（mock 返回结构化画像）──
        prof_resp = client.post(
            "/api/profile/build",
            json={
                "message": "我学过计算机网络，视觉型，每天学2小时，目标是考研",
                "history": [
                    {"role": "assistant", "content": "先了解一下你的情况"},
                    {"role": "user", "content": "我学过计网，视觉型"},
                ],
            },
        )
        assert prof_resp.status_code == 200
        prof_data = prof_resp.json()
        assert prof_data["completed"] is True
        profile = prof_data["profile"]
        assert profile and profile.get("learning_style") == "visual"

        # ── 3. 基于画像生成个性化学习路径 ──
        progress = profile.get("progress", 1)
        path_resp = client.post(
            "/api/learning-path", json={"current_chapter": progress, "profile": profile}
        )
        assert path_resp.status_code == 200
        path_data = path_resp.json()
        assert path_data["nodes"]
        current_node = next(
            (n for n in path_data["nodes"] if n["status"] == "current"), None
        )
        assert current_node is not None, "应存在当前学习节点"

        # ── 4. 在线答题，更新画像 ──
        quiz_resp = client.post(
            "/api/quiz/submit",
            json={
                "profile": profile,
                "records": [
                    {"subject": "network", "correct": True},
                    {"subject": "network", "correct": True},
                    {"subject": "network", "correct": False},
                ],
            },
        )
        assert quiz_resp.status_code == 200
        quiz_data = quiz_resp.json()
        assert quiz_data["accuracy"] == pytest.approx(2 / 3, abs=0.01)
        updated_profile = quiz_data["updated_profile"]
        assert updated_profile is not None

        # 答题后画像应被合并（含 recent_accuracy）
        assert "recent_accuracy" in updated_profile

        # ── 5. 学习效果评估，闭合反馈 ──
        assess_resp = client.post(
            "/api/assessment",
            json={
                "quiz_history": [
                    {"subject": "network", "correct": True},
                    {"subject": "network", "correct": True},
                    {"subject": "network", "correct": False},
                    {"subject": "os", "correct": False},
                ],
                "profile": updated_profile,
            },
        )
        assert assess_resp.status_code == 200
        assess_data = assess_resp.json()
        assert assess_data["total_questions"] == 4
        # 4 题中 2 正确 → 0.5；network 正确率 2/3，os 正确率 0
        assert assess_data["overall_accuracy"] == pytest.approx(0.5, abs=0.01)
        assert "mastery" in assess_data and assess_data["mastery"]
        assert assess_data["trend"] in ("上升", "稳定", "下降")

        # ── 闭环连贯性断言 ──
        # 评估应按正确率给出薄弱科目（os 正确率 0 < 0.5 → 进入 weak_focus）
        assert "os" in assess_data["mastery"]
        assert assess_data["mastery"]["os"] == 0.0
        assert "os" in assess_data["weak_focus"]
