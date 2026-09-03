"""Live 检索路由冒烟测试（修正版）：用 `with TestClient` 触发 startup
（加载 KB），再走真实 HTTP 路由 /api/rag/search 验证检索正确性。
"""
import sys
sys.path.insert(0, ".")

import main
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from db.milvus_client import vector_db
_dummy = {"user_id": "smoke", "id": "smoke", "role": "admin"}
main.app.dependency_overrides[get_current_user] = lambda: _dummy
main.app.dependency_overrides[require_llm_quota] = lambda: _dummy

from fastapi.testclient import TestClient

with TestClient(main.app) as client:
    print("KB count after startup:", vector_db.count("netlearn_kb"))

    def search(q, course):
        r = client.post("/api/rag/search", json={"query": q, "course": course, "top_k": 5})
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
        return r.json()["results"]

    print("\n=== DS 题：栈和队列区别 ===")
    res = search("栈和队列的主要区别是什么？说明LIFO和FIFO", "data_structures")
    subs = [x["metadata"].get("subject") for x in res]
    print("top5 subjects:", subs)
    print("top1:", res[0]["content"][:60] if res else "EMPTY")

    print("\n=== OS 题：页面置换算法 ===")
    res2 = search("页面置换算法有哪些？", "operating_system")
    subs2 = [x["metadata"].get("subject") for x in res2]
    print("top5 subjects:", subs2)

    print("\n=== 跨课程校验 ===")
    cross = [s for s in subs if s and not s.startswith("ds")]
    print("DS 结果越界科目:", cross if cross else "无（通过）")
    cross2 = [s for s in subs2 if s and not s.startswith("os")]
    print("OS 结果越界科目:", cross2 if cross2 else "无（通过）")
