"""视频生成 + 反馈 Agent — 集成测试

覆盖：视频生成工作流 / 反馈评估 / 路径调整
"""

import json
import pytest
from fastapi.testclient import TestClient


def _client():
    from main import app
    from shared.auth import create_token
    token = create_token("test_user_id", role="student")
    client = TestClient(app)
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


class TestVideoGeneration:
    """教学视频生成测试（需要真实 LLM 连接）"""

    def setup_method(self):
        self.client = _client()

    @pytest.mark.xfail(reason="需要真实 LLM 连接，在 CI 中可能超时")
    def test_generate_teaching_video(self):
        """生成教学视频（零 API 成本方案）"""
        resp = self.client.post("/api/multimodal/generate-teaching-video", json={
            "topic": "TCP三次握手",
            "difficulty": "medium",
            "output_format": "html",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["resource_type"] == "teaching_video"
        assert data["scenes"] >= 1
        assert data["duration_sec"] > 0
        # HTML 幻灯片内容
        assert "<svg" in data.get("html", "")
        assert "NetLearn" in data.get("html", "")

    @pytest.mark.xfail(reason="需要真实 LLM 连接，在 CI 中可能超时")
    def test_generate_video_with_cache(self):
        """视频生成缓存（相同 topic 命中缓存）"""
        topic = "TCP三次握手"
        # 第一次调用
        resp1 = self.client.post("/api/multimodal/generate-teaching-video", json={
            "topic": topic, "difficulty": "medium",
        })
        assert resp1.status_code == 200
        # 第二次调用（命中缓存）
        resp2 = self.client.post("/api/multimodal/generate-teaching-video", json={
            "topic": topic, "difficulty": "medium",
        })
        assert resp2.status_code == 200
        assert resp2.json()["scenes"] >= 1

    def test_video_parse_storyboard(self):
        """解析分镜脚本"""
        from services.video_generator import parse_storyboard
        script = """---VIDEO_START---
## 分镜 1: 开场 (0:00-0:15)
**画面**: 标题动画
**旁白**: 大家好
**时长**: 15秒
---VIDEO_END---
"""
        scenes = parse_storyboard(script)
        assert len(scenes) >= 1
        assert scenes[0]["duration_sec"] == 15

    def test_video_scene_svg(self):
        """生成场景 SVG"""
        from services.video_generator import generate_scene_svg, parse_storyboard
        script = """---VIDEO_START---
## 分镜 1: 开场 (0:00-0:15)
**画面**: 标题动画
**旁白**: 大家好
**时长**: 15秒
---VIDEO_END---
"""
        scenes = parse_storyboard(script)
        svg = generate_scene_svg(scenes[0], "TCP三次握手")
        assert "<svg" in svg
        assert "NetLearn" in svg

    def test_video_template_types(self):
        """所有场景模板类型均可渲染"""
        from services.video_generator import (
            generate_scene_svg, parse_storyboard, SCENE_TEMPLATES,
        )
        script = "---VIDEO_START---\n" + "\n".join(
            f"## 分镜 {i}: 场景{i} (0:00-0:15)\n**画面**: 内容\n**旁白**: 测试\n**时长**: 15秒"
            for i in range(len(SCENE_TEMPLATES))
        ) + "\n---VIDEO_END---"
        scenes = parse_storyboard(script)
        for scene in scenes:
            svg = generate_scene_svg(scene, "测试主题")
            assert "<svg" in svg
            assert scene["template_type"] in SCENE_TEMPLATES


class TestFeedbackAgent:
    """反馈 Agent 测试"""

    def setup_method(self):
        self.client = _client()

    def test_evaluate_learning(self):
        """学习效果评估"""
        from agents.feedback_agent import evaluate_learning
        import asyncio
        result = asyncio.run(evaluate_learning(
            profile={"knowledge_base": "beginner", "weak_points": "TCP,UDP"},
            quiz_history=[
                {"subject": "computer_network", "chapter": "运输层",
                 "correct": True, "difficulty": "medium", "timestamp": "2026-07-01"},
                {"subject": "computer_network", "chapter": "网络层",
                 "correct": False, "difficulty": "hard", "timestamp": "2026-07-02"},
            ],
            study_sessions=[],
        ))
        assert "mastery_by_topic" in result
        assert "overall" in result
        assert "weak_points" in result
        assert result["overall"]["avg_mastery"] >= 0

    def test_adjust_learning_path(self):
        """路径调整"""
        from agents.feedback_agent import adjust_learning_path
        import asyncio
        result = asyncio.run(adjust_learning_path(
            current_path=[{"name": "计网基础", "status": "in_progress"}],
            eval_report={
                "weak_points": [{"topic": "TCP", "priority": "high", "suggestion": "建议复习"}],
                "adjustment": {"action": "review", "description": "需要复习"},
            },
            profile={"knowledge_base": "beginner"},
        ))
        assert "adjusted" in result
        assert "path" in result

    def test_fallback_eval(self):
        """降级评估（无 LLM 时基于规则）"""
        from agents.feedback_agent import _fallback_eval
        result = _fallback_eval([
            {"subject": "计网", "chapter": "运输层", "correct": True},
            {"subject": "计网", "chapter": "网络层", "correct": False},
        ])
        assert "mastery_by_topic" in result
        assert "运输层" in result["mastery_by_topic"]
        assert result["mastery_by_topic"]["运输层"]["score"] == 100


class TestRecommendations:
    """画像驱动推荐测试"""

    def setup_method(self):
        self.client = _client()

    def test_recommendations_api(self):
        """推荐 API 返回结构化推荐"""
        resp = self.client.post("/api/recommendations", json={
            "profile": {
                "knowledge_base": "beginner",
                "weak_points": "TCP, UDP",
                "learning_style": "visual",
                "progress": 2,
            },
            "quiz_history": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["recommendations"]) >= 3
        # 应该有基础入门推荐
        titles = [r["title"] for r in data["recommendations"]]
        assert any("基础" in t or "入门" in t for t in titles)

    def test_recommendations_advanced(self):
        """高级用户推荐"""
        resp = self.client.post("/api/recommendations", json={
            "profile": {
                "knowledge_base": "advanced",
                "weak_points": "",
                "learning_style": "reading",
                "progress": 9,
            },
            "quiz_history": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recommendations"]) >= 2
        titles = [r["title"] for r in data["recommendations"]]
        assert any("冲刺" in t or "拔高" in t for t in titles)


class TestProfileSnapshot:
    """画像快照测试"""

    def setup_method(self):
        self.client = _client()

    def test_save_and_get_snapshot(self):
        """保存快照 → 获取快照历史"""
        resp = self.client.post("/api/profile/snapshot", json={
            "profile": {
                "knowledge_base": "beginner",
                "weak_points": "TCP",
                "progress": 2,
            },
        })
        assert resp.status_code == 200
        snapshot_id = resp.json()["snapshot_id"]
        assert snapshot_id > 0

        # 获取历史
        resp = self.client.get("/api/profile/snapshots?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["snapshots"]) >= 1
        assert data["snapshots"][0]["snapshot"]["profile"]["knowledge_base"] == "beginner"