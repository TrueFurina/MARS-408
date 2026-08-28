"""AI Skills 创新创作平台 — 集成测试

覆盖：技能 CRUD / 市场 / 评价 / 收藏 / 运行时 / 模板
"""

import json
import pytest
from fastapi.testclient import TestClient

# ── 辅助 ──

_AUTH_HEADER = {"Authorization": "Bearer test-token"}


def _client():
    """创建测试客户端（带 Mock LLM + Mock Auth）"""
    from main import app
    from shared.auth import create_token
    # 生成一个测试 token
    token = create_token("test_user_id", role="student")
    client = TestClient(app)
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


class TestSkillCRUD:
    """技能 CRUD 测试"""

    def setup_method(self):
        self.client = _client()

    def test_create_skill(self):
        """创建技能 → 返回技能对象"""
        resp = self.client.post("/api/skills/create", json={
            "name": "测试技能",
            "description": "测试描述",
            "system_prompt": "你是一个测试助手",
            "category": "teaching",
            "tags": '["测试", "demo"]',
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["skill"]["name"] == "测试技能"
        assert data["skill"]["category"] == "teaching"
        assert data["skill"]["status"] == "draft"
        return data["skill"]["id"]

    def test_create_skill_invalid_category(self):
        """创建技能（无效分类）→ 422"""
        resp = self.client.post("/api/skills/create", json={
            "name": "测试",
            "category": "invalid_category",
        })
        assert resp.status_code == 422

    def test_get_skill(self):
        """获取技能详情"""
        skill_id = self.test_create_skill()
        resp = self.client.get(f"/api/skills/get/{skill_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill"]["id"] == skill_id

    def test_get_skill_not_found(self):
        """获取不存在的技能 → 404"""
        resp = self.client.get("/api/skills/get/nonexistent_id")
        assert resp.status_code == 404

    def test_update_skill(self):
        """更新技能名称"""
        skill_id = self.test_create_skill()
        resp = self.client.post(f"/api/skills/update/{skill_id}", json={
            "name": "更新后的名称",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill"]["name"] == "更新后的名称"

    def test_delete_skill(self):
        """删除技能"""
        skill_id = self.test_create_skill()
        resp = self.client.post(f"/api/skills/delete/{skill_id}")
        assert resp.status_code == 200
        # 确认已删除
        resp = self.client.get(f"/api/skills/get/{skill_id}")
        assert resp.status_code == 404


class TestSkillLifecycle:
    """技能生命周期测试（草稿→发布→归档）"""

    def setup_method(self):
        self.client = _client()
        resp = self.client.post("/api/skills/create", json={
            "name": "生命周期测试",
            "system_prompt": "测试",
        })
        self.skill_id = resp.json()["skill"]["id"]

    def test_publish_skill(self):
        """发布技能（draft → published）"""
        resp = self.client.post(f"/api/skills/publish/{self.skill_id}")
        assert resp.status_code == 200
        data = self.client.get(f"/api/skills/get/{self.skill_id}").json()
        assert data["skill"]["status"] == "published"

    def test_archive_skill(self):
        """归档技能（published → archived）"""
        self.client.post(f"/api/skills/publish/{self.skill_id}")
        resp = self.client.post(f"/api/skills/archive/{self.skill_id}")
        assert resp.status_code == 200
        data = self.client.get(f"/api/skills/get/{self.skill_id}").json()
        assert data["skill"]["status"] == "archived"

    def test_publish_already_published(self):
        """重复发布已发布的技能 → 400"""
        self.client.post(f"/api/skills/publish/{self.skill_id}")
        resp = self.client.post(f"/api/skills/publish/{self.skill_id}")
        assert resp.status_code == 400


class TestSkillMarket:
    """技能市场测试"""

    def setup_method(self):
        self.client = _client()
        # 创建 2 个技能并发布
        for name in ["市场测试A", "市场测试B"]:
            resp = self.client.post("/api/skills/create", json={
                "name": name, "system_prompt": "测试", "category": "teaching",
            })
            sid = resp.json()["skill"]["id"]
            self.client.post(f"/api/skills/publish/{sid}")

    def test_market_list(self):
        """市场列表返回已发布技能"""
        resp = self.client.get("/api/skills/market")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["items"]) >= 2

    def test_market_search(self):
        """市场搜索过滤"""
        resp = self.client.get("/api/skills/market?search=市场测试A")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any("市场测试A" in s["name"] for s in data["items"])

    def test_my_skills(self):
        """我的技能列表"""
        resp = self.client.get("/api/skills/my")
        assert resp.status_code == 200
        data = resp.json()
        # 至少包含刚才创建的技能
        names = [s["name"] for s in data["items"]]
        assert "市场测试A" in names


class TestSkillRating:
    """技能评价测试"""

    def setup_method(self):
        self.client = _client()
        resp = self.client.post("/api/skills/create", json={
            "name": "评价测试", "system_prompt": "测试",
        })
        self.skill_id = resp.json()["skill"]["id"]
        self.client.post(f"/api/skills/publish/{self.skill_id}")

    def test_rate_skill(self):
        """评价技能"""
        resp = self.client.post(f"/api/skills/rate/{self.skill_id}", json={
            "rating": 5, "comment": "非常好用！",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["rating"]["rating"] == 5
        assert data["rating"]["comment"] == "非常好用！"

    def test_get_ratings(self):
        """获取评价列表"""
        self.client.post(f"/api/skills/rate/{self.skill_id}", json={
            "rating": 4, "comment": "不错",
        })
        resp = self.client.get(f"/api/skills/ratings/{self.skill_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_rate_invalid_rating(self):
        """无效评分（6 分）→ 422"""
        resp = self.client.post(f"/api/skills/rate/{self.skill_id}", json={
            "rating": 6, "comment": "无效",
        })
        assert resp.status_code == 422


class TestSkillFavorite:
    """技能收藏测试"""

    def setup_method(self):
        self.client = _client()
        resp = self.client.post("/api/skills/create", json={
            "name": "收藏测试", "system_prompt": "测试",
        })
        self.skill_id = resp.json()["skill"]["id"]

    def test_favorite_flow(self):
        """收藏 → 检查 → 取消收藏 → 检查"""
        # 收藏
        resp = self.client.post(f"/api/skills/favorite/{self.skill_id}")
        assert resp.status_code == 200
        # 检查
        resp = self.client.get(f"/api/skills/favorited/{self.skill_id}")
        assert resp.json()["favorited"] is True
        # 取消收藏
        resp = self.client.post(f"/api/skills/unfavorite/{self.skill_id}")
        assert resp.status_code == 200
        resp = self.client.get(f"/api/skills/favorited/{self.skill_id}")
        assert resp.json()["favorited"] is False

    def test_favorite_list(self):
        """收藏列表"""
        self.client.post(f"/api/skills/favorite/{self.skill_id}")
        resp = self.client.get("/api/skills/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1
        assert any(s["id"] == self.skill_id for s in data["items"])


class TestSkillTemplate:
    """技能模板测试"""

    def setup_method(self):
        self.client = _client()

    def test_get_templates(self):
        """获取模板列表"""
        resp = self.client.get("/api/skills/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 8  # 8 个预设模板
        names = [t["name"] for t in data["items"]]
        assert "智能出题机器人" in names

    def test_create_from_template(self):
        """从模板创建技能"""
        # 先获取模板 ID
        resp = self.client.get("/api/skills/templates")
        template_id = resp.json()["items"][0]["id"]
        # 从模板创建
        resp = self.client.post(f"/api/skills/from-template/{template_id}", json={
            "name": "我的第一个技能",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill"]["name"] == "我的第一个技能"
        assert data["skill"]["system_prompt"]  # 模板的 system_prompt 应该被复制


class TestSkillRuntime:
    """技能运行时测试"""

    def setup_method(self):
        self.client = _client()
        resp = self.client.post("/api/skills/create", json={
            "name": "运行时测试",
            "system_prompt": "你是一个测试助手，请简短回答。",
        })
        self.skill_id = resp.json()["skill"]["id"]
        self.client.post(f"/api/skills/publish/{self.skill_id}")

    def test_run_skill(self):
        """执行技能（非流式）"""
        resp = self.client.post(f"/api/skills/run/{self.skill_id}", json={
            "message": "你好",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["response"]  # 应该有响应内容

    def test_run_skill_not_found(self):
        """执行不存在的技能 → 404"""
        resp = self.client.post("/api/skills/run/nonexistent", json={
            "message": "你好",
        })
        assert resp.status_code == 404

    def test_run_skill_not_published(self):
        """执行未发布的技能 → 正常返回（创建者执行自己的草稿）"""
        resp = self.client.post("/api/skills/create", json={
            "name": "未发布技能", "system_prompt": "测试",
        })
        draft_id = resp.json()["skill"]["id"]
        resp = self.client.post(f"/api/skills/run/{draft_id}", json={
            "message": "你好",
        })
        # 创建者可以执行自己的草稿
        assert resp.status_code == 200


class TestSkillBatch:
    """批量操作测试"""

    def setup_method(self):
        self.client = _client()

    def test_batch_delete(self):
        """批量删除"""
        # 创建 3 个技能
        ids = []
        for i in range(3):
            resp = self.client.post("/api/skills/create", json={
                "name": f"批量删除测试{i}", "system_prompt": "测试",
            })
            ids.append(resp.json()["skill"]["id"])
        # 批量删除
        resp = self.client.post("/api/skills/batch-delete", json={
            "skill_ids": ids,
        })
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 3