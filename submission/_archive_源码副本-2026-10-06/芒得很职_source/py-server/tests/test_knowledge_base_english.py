"""课程知识库 + 英语工作区 — 集成测试

覆盖：教材导入/搜索/提问 / 英语词库/单词/测验
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


class TestKnowledgeBase:
    """课程知识库测试"""

    def setup_method(self):
        self.client = _client()

    def test_list_textbooks(self):
        """列出教材"""
        resp = self.client.get("/api/knowledge-base/textbooks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_search_no_textbooks(self):
        """搜索空知识库"""
        resp = self.client.post("/api/knowledge-base/search", json={
            "query": "TCP",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_ask_without_textbook(self):
        """提问（无教材时）"""
        resp = self.client.post("/api/knowledge-base/ask", json={
            "selected_text": "TCP是一种传输层协议",
            "question": "请解释",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "answer" in data


class TestEnglishWorkspace:
    """英语工作区测试"""

    def setup_method(self):
        self.client = _client()

    def test_get_vocabulary_cet4(self):
        """获取 CET-4 词汇"""
        resp = self.client.get("/api/english/vocabulary?level=cet4&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["words"]) == 5
        assert data["total"] >= 10

    def test_get_vocabulary_postgrad(self):
        """获取考研词汇"""
        resp = self.client.get("/api/english/vocabulary?level=postgrad&limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["words"]) == 3

    def test_get_word_detail(self):
        """获取单词详情"""
        resp = self.client.get("/api/english/word/abandon")
        assert resp.status_code == 200
        data = resp.json()
        assert data["word"]["word"] == "abandon"
        assert "graph" in data
        assert len(data["graph"]["nodes"]) >= 1

    def test_get_word_not_found(self):
        """不存在的单词 → 404"""
        resp = self.client.get("/api/english/word/nonexistent")
        assert resp.status_code == 404

    def test_generate_quiz(self):
        """生成词汇测验"""
        resp = self.client.post("/api/english/quiz?level=cet4&count=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["questions"]) == 5
        for q in data["questions"]:
            assert "word" in q
            assert "options" in q
            assert len(q["options"]) == 4
            assert "answer" in q