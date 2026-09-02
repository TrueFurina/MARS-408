"""验证运行中后端的真实检索路径：E5 向量是否生效、是否命中相关段落。
不依赖 LLM，只验证 FrugalRAG.retrieve 在 connect() 后的行为。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def log(*a):
    print(*a, flush=True)

from shared.container import get_container
vd = get_container().vector_db
log("connect 前 _mem_store =", vd._mem_store)
log("MILVUS_AVAILABLE =", __import__("db.milvus_client", fromlist=["MILVUS_AVAILABLE"]).MILVUS_AVAILABLE)
vd.connect()
cnt = vd._mem_store.count("netlearn_kb") if vd._mem_store else None
log("connect 后 _mem_store 文档数 =", cnt)

from engines.frugal_rag import FrugalRAG
fr = FrugalRAG()
log("cosine_threshold =", fr.cosine_threshold, "vector_weight =", fr.vector_weight, "bm25_weight =", fr.bm25_weight)

import asyncio
QUERIES = [
    ("TCP三次握手为什么不能简化为两次", "计算机网络"),
    ("进程与线程的区别", "操作系统"),
    ("快速排序的时间复杂度", "数据结构"),
    ("Cache 映射方式有哪些", "计算机组成原理"),
]

async def go():
    for q, course in QUERIES:
        res = await fr.retrieve(q, course=course, top_k=5)
        degraded = any(r.get("_degraded") for r in res)
        log(f"\n[query] {q}  course={course}")
        log(f"  命中={len(res)}  是否BM25降级={degraded}")
        for i, r in enumerate(res[:3], 1):
            log(f"  #{i} score={r.get('score',0):.3f} subj={r.get('metadata',{}).get('subject','')} src={r.get('_source','')}")
            log(f"      {repr(r.get('text','')[:90])}")

asyncio.run(go())
log("\nDONE")
