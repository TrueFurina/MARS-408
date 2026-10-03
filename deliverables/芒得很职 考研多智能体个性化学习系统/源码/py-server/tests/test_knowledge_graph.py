"""AI 知识图谱生成器 — 集成测试

覆盖：实体抽取 / 图谱持久化 / 导出 / 学习路径推荐
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


class TestKGEntityExtraction:
    """实体抽取测试"""

    def setup_method(self):
        self.client = _client()

    def test_parse_kg_result(self):
        """解析 LLM 输出"""
        from agents.knowledge_graph import _parse_kg_result
        text = '```json\n{"entities": [{"id": "e1", "name": "TCP", "type": "protocol"}], "relationships": []}\n```'
        result = _parse_kg_result(text)
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "TCP"

    def test_parse_fallback(self):
        """降级解析（无标记时）"""
        from agents.knowledge_graph import _parse_kg_result
        result = _parse_kg_result('{"entities": [{"id": "e1", "name": "test"}]}')
        assert len(result["entities"]) == 1

    def test_count_types(self):
        """统计类型分布"""
        from agents.knowledge_graph import _count_types
        items = [{"type": "concept"}, {"type": "concept"}, {"type": "protocol"}]
        counts = _count_types(items, "type")
        assert counts["concept"] == 2
        assert counts["protocol"] == 1

    def test_kg_to_vis_json(self):
        """转换为可视化 JSON"""
        from agents.knowledge_graph import kg_to_vis_json
        kg = {"entities": [{"id": "e1", "name": "TCP", "type": "protocol"}], "relationships": []}
        vis = kg_to_vis_json(kg)
        assert len(vis["nodes"]) == 1
        assert vis["nodes"][0]["label"] == "TCP"


class TestKGPersistence:
    """图谱持久化测试"""

    def setup_method(self):
        self.client = _client()

    def test_save_and_load(self):
        """保存并加载图谱"""
        from agents.knowledge_graph import save_knowledge_graph, load_knowledge_graph, delete_knowledge_graph
        kg_id = save_knowledge_graph(
            {"entities": [{"id": "e1", "name": "测试实体", "type": "concept"}], "relationships": []},
            name="测试图谱", subject="test",
        )
        assert kg_id
        loaded = load_knowledge_graph(kg_id)
        assert loaded is not None
        assert len(loaded["entities"]) == 1
        assert loaded["entities"][0]["name"] == "测试实体"
        delete_knowledge_graph(kg_id)
        assert load_knowledge_graph(kg_id) is None

    def test_list_graphs(self):
        """列出图谱"""
        from agents.knowledge_graph import save_knowledge_graph, list_knowledge_graphs, delete_knowledge_graph
        kg_id = save_knowledge_graph({"entities": [], "relationships": []}, name="列表测试")
        graphs = list_knowledge_graphs()
        assert len(graphs) >= 1
        delete_knowledge_graph(kg_id)

    def test_export_import(self):
        """导出导入 JSON"""
        from agents.knowledge_graph import save_knowledge_graph, export_knowledge_graph_json, import_knowledge_graph_json, delete_knowledge_graph
        kg_id = save_knowledge_graph(
            {"entities": [{"id": "e1", "name": "导出测试", "type": "concept"}], "relationships": []},
        )
        json_str = export_knowledge_graph_json(kg_id)
        assert json_str
        assert "导出测试" in json_str
        delete_knowledge_graph(kg_id)
        # 导入
        new_id = import_knowledge_graph_json(json_str)
        assert new_id
        delete_knowledge_graph(new_id)


class TestKGExport:
    """导出功能测试"""

    def test_export_mermaid(self):
        from agents.knowledge_graph import export_graph_as_mermaid
        kg = {"entities": [{"id": "e1", "name": "TCP", "type": "protocol"}], "relationships": []}
        mermaid = export_graph_as_mermaid(kg)
        assert "mermaid" in mermaid
        assert "TCP" in mermaid

    def test_export_text(self):
        from agents.knowledge_graph import export_graph_as_text
        kg = {"entities": [{"id": "e1", "name": "TCP", "type": "protocol", "importance": "high"}], "relationships": []}
        text = export_graph_as_text(kg)
        assert "TCP" in text
        assert "high" in text


class TestKGLearningPath:
    """学习路径推荐测试"""

    def test_recommend_learning_path(self):
        from agents.knowledge_graph import recommend_learning_path
        kg = {
            "entities": [
                {"id": "e1", "name": "基础", "type": "concept"},
                {"id": "e2", "name": "进阶", "type": "concept"},
                {"id": "e3", "name": "高级", "type": "concept"},
            ],
            "relationships": [
                {"source": "e1", "target": "e2", "type": "prerequisite"},
                {"source": "e2", "target": "e3", "type": "prerequisite"},
            ],
        }
        path = recommend_learning_path(kg)
        assert len(path) == 3
        assert path[0]["entity_name"] == "基础"
        assert path[2]["entity_name"] == "高级"


class TestKGAPI:
    """知识图谱 API 测试"""

    def setup_method(self):
        self.client = _client()

    def test_extract_api(self):
        """提取端点可达"""
        resp = self.client.post("/api/knowledge-graph/extract", json={
            "text": "TCP是一种传输层协议，提供可靠的连接服务。UDP是一种无连接协议。",
            "subject": "computer_network",
            "enhance": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "vis" in data

    def test_stats_api(self):
        """统计端点可达"""
        resp = self.client.get("/api/knowledge-graph/stats")
        assert resp.status_code == 200

    def test_list_api(self):
        """列表端点可达"""
        resp = self.client.get("/api/knowledge-graph/list")
        assert resp.status_code == 200

    def test_search_api(self):
        """搜索端点可达"""
        resp = self.client.post("/api/knowledge-graph/search", json={
            "query": "TCP",
        })
        assert resp.status_code == 200

    def test_batch_extract_api(self):
        """批量提取端点可达"""
        resp = self.client.post("/api/knowledge-graph/batch-extract", json={
            "texts": [
                {"id": "1", "title": "TCP", "content": "TCP是一种传输层协议。"},
            ],
            "subject": "computer_network",
            "merge": True,
        })
        assert resp.status_code == 200