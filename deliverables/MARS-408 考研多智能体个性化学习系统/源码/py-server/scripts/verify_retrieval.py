import asyncio, sys
sys.path.insert(0, '.')
from db.milvus_client import vector_db
from engines.frugal_rag import frugal_rag
from collections import Counter

CASES = [
    ("快速排序的原理和时间复杂度", "data_structures"),
    ("进程调度的算法有哪些", "operating_system"),
    ("TCP 三次握手过程", "computer_network"),
    ("Cache 的映射方式", "computer_organization"),
]


async def main():
    vector_db.connect()
    for q, course in CASES:
        res = await frugal_rag.retrieve(q, course=course, top_k=8, use_kg_enhance=False)
        subj = Counter(r.get("metadata", {}).get("subject", "?") for r in res)
        cross = sum(1 for r in res if not str(r.get("metadata", {}).get("subject", "")).startswith(course[:2]))
        top = res[0] if res else None
        print(f"\nQ[{course}] {q}")
        print(f"  返回 {len(res)} 条 | 跨课程 {cross} | top1={top.get('metadata',{}).get('subject','?') if top else '-'}: {top.get('text','')[:40].replace(chr(10),' ') if top else ''}")
        print(f"  subject分布: {dict(subj)}")


asyncio.run(main())
