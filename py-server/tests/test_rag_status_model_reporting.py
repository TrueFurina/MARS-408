"""回归测试：/api/rag/status 必须如实上报生效嵌入模型，而不是写死常量。

背景：rag_status 的返回体曾硬编码 ``embedding_model: intfloat/multilingual-e5-base``，
与 embedder 的「生效模型由 config.json 决定」语义脱节。一旦在 config 切到 e5-base-v2，
status 端点（已修）会说真话，但 rag/status 仍在撒谎 —— 同类 P0 缺陷。
本测试把向量库与 config 桩掉，直接调用 rag_status，断言返回体跟随生效模型。
"""

import asyncio
from unittest.mock import MagicMock


def test_rag_status_reports_effective_embedding_model(monkeypatch):
    import db.milvus_client as mc
    import api.rag as rag

    fake_db = MagicMock()
    fake_db.count.return_value = 2245
    fake_db.get_all_with_texts.return_value = ([], 2245)
    monkeypatch.setattr(mc, "vector_db", fake_db)

    captured = {}

    def fake_cfg():
        captured["called"] = True
        return {"model": "intfloat/e5-base-v2", "dimension": 768}

    monkeypatch.setattr(rag, "get_embedding_config", fake_cfg)

    result = asyncio.run(rag.rag_status(user={}))

    assert captured.get("called"), "rag_status 必须读取 embedding 配置而非写死常量"
    assert result["embedding_model"] == "intfloat/e5-base-v2", result
    assert result["dimension"] == 768, result
