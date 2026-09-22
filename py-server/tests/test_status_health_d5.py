"""D5 回归测试：/api/status 必须停止硬编码 "ok"，显式暴露静默降级。

验证点：
1. 默认形态：返回 200，含 status / degraded_reasons / health，health 含五大组件。
2. 强制降级：当 PostgreSQL「已配置启用」却回落 SQLite 兜底时，status 必须为 "degraded"
   且 degraded_reasons 含 postgresql 相关原因（杜绝「绿光可骗人」）。
"""
import config
from db.pg_client import pg_client as _pg
from db.redis_client import redis_client as _rc


def test_status_shape_and_keys(client):
    """默认环境下 /api/status 形状正确，且 health 覆盖五组件。"""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["degraded_reasons"], list)
    assert "health" in body

    health = body["health"]
    assert set(health.keys()) == {
        "vector_db",
        "postgresql",
        "redis",
        "embedding",
        "llm",
    }
    # vector_db 真实连通性信号
    assert health["vector_db"]["mode"] in ("milvus", "inmemory")
    assert isinstance(health["vector_db"]["milvus_connected"], bool)
    # embedding 降级计数（E5 失败零向量占位）字段存在
    assert "fallback_zero_docs" in health["embedding"]
    assert isinstance(health["embedding"]["fallback_zero_docs"], int)
    # llm 可用性字段存在
    assert isinstance(health["llm"]["available"], bool)


def test_status_reports_pg_fallback_as_degraded(client, monkeypatch):
    """D5 核心：PG 已配置却回落 SQLite 兜底 → status=degraded 且说明原因。"""
    # 改写全局单例运行期属性（monkeypatch 自动还原）
    monkeypatch.setattr(_pg, "_enabled", True, raising=False)
    monkeypatch.setattr(_pg, "_is_fallback", True, raising=False)
    monkeypatch.setattr(_rc, "_enabled", False, raising=False)

    orig = config.load_config

    def fake_config():
        c = orig()
        c.setdefault("postgresql", {})["enabled"] = True
        c.setdefault("redis", {})["enabled"] = False
        c.setdefault("milvus", {})["enabled"] = False
        return c

    monkeypatch.setattr(config, "load_config", fake_config, raising=False)

    resp = client.get("/api/status")
    body = resp.json()
    assert body["status"] == "degraded"
    assert any("postgresql" in reason for reason in body["degraded_reasons"]), (
        body["degraded_reasons"]
    )
    # health.postgresql 必须反映回落状态
    assert body["health"]["postgresql"]["fallback_sqlite"] is True
    assert body["health"]["postgresql"]["configured"] is True
