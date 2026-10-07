"""视频生成 + 反馈 Agent — 集成测试

覆盖：视频生成工作流 / 反馈评估 / 路径调整
"""

import pytest
from fastapi.testclient import TestClient


def _client():
    from main import app
    from shared.auth import create_token
    token = create_token("test_user_id", role="student")
    client = TestClient(app)
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


# 合法分镜脚本（含 ---VIDEO_START/END--- 标记与 `## 分镜 N:` 分块）。
# 用于把 LLM 出参钉死，从而**确定性**验证「零 API 成本」的程序化合成链路：
# 分镜 → SVG 场景 → HTML 幻灯片。
_STORYBOARD_SCRIPT = """---VIDEO_START---
## 分镜 1: 开场引入 (0:00-0:30)
**画面**: 标题动画，显示学习主题
**旁白**: 大家好，今天我们来学习三次握手
**动画**: 标题渐入
**时长**: 30秒

## 分镜 2: 核心概念讲解 (0:30-2:30)
**画面**: 核心概念图解，分步展示
**旁白**: 详细讲解三次握手的报文交互过程
**动画**: 逐步绘制图示
**时长**: 120秒

## 分镜 3: 案例演示 (2:30-4:00)
**画面**: 抓包案例演示
**旁白**: 通过抓包加深理解
**时长**: 90秒

## 分镜 4: 总结回顾 (4:00-5:00)
**画面**: 知识点回顾卡片
**旁白**: 总结今天学到的核心内容
**时长**: 60秒
---VIDEO_END---"""


@pytest.fixture
def storyboard_llm(monkeypatch):
    """把 LLM 脚本生成钉死为一份合法分镜脚本。

    为什么必须钉死（2026-10-08 实测，非推测）：
    ``tests/conftest.py`` 的 autouse ``mock_llm`` 让 ``text_completion``
    **成功返回**字符串 ``"mock llm response"``，因此
    ``agents/media_generator._fallback_video_script`` 那条「LLM 抛异常 → 4 场景模板
    脚本」的降级路径**不会被触发**；该 17 字符串进入
    ``services/video_generator.parse_storyboard`` 后走 ``_parse_scenes_fallback``，
    而后者跳过长度 < 20 的分块（17 < 20）→ 0 场景 →
    ``generate_teaching_video`` 返回 ``status="error"`` → 端点 status=error。

    这正是这两个用例此前被 ``xfail(strict=False)`` 吸收的原因：单跑记 XFAIL、
    全量记 XPASS —— **既不通过也不失败，零回归信号**（与 ``c93c2eb`` 注释所称
    「mock LLM 下走降级路径产出模板视频、故实际为 xpass」相反：降级只在 LLM
    真抛异常时发生，mock 下脚本生成是「成功」的）。

    钉死出参后，本用例确定性地断言「给定合法分镜脚本，端点必产出
    status=ok / ≥1 场景 / >0 时长 / 含 ``<svg`` 与品牌水印」。
    """
    from db.llm_provider import LLMProvider

    async def _fake_text_completion(self, system_prompt, user_prompt, *args, **kwargs):
        return _STORYBOARD_SCRIPT

    monkeypatch.setattr(LLMProvider, "text_completion", _fake_text_completion)


class TestVideoGeneration:
    """教学视频生成测试

    断言「零 API 成本」的程序化合成链路（分镜 → SVG → HTML 幻灯片）。
    LLM 出参由 ``storyboard_llm`` fixture 钉死，故既不依赖真实模型，
    也不受 conftest 通用 mock 出参长度影响。
    """

    def setup_method(self):
        self.client = _client()

    def test_generate_teaching_video(self, storyboard_llm):
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
        assert "芒得很职" in data.get("html", "")

    def test_generate_video_with_cache(self, storyboard_llm):
        """连续两次生成同一 topic 均成功

        注：函数名与原标题声称测「缓存命中」，但
        ``services/video_generator._cache_set`` 全仓**零调用点**（缓存写入为死代码），
        读取分支 ``if cached and cached == video_script: pass`` 也是空操作 ——
        缓存路径实际不可达。本用例能验证的是「同 topic 重复调用幂等」，
        不是缓存命中。缓存是否落地属产品决策，此处只如实标注，不擅自实现。
        """
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
        assert "芒得很职" in svg

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