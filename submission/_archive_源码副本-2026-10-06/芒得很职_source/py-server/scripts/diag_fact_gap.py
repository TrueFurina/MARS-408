"""逐题诊断 fact 掉点根因：内容缺失 vs 检索未召回。

对每题打印：期望知识点排名、fact 覆盖率、缺失的具体事实词、top-10 命中科目。
目的：区分"KB 缺内容"还是"内容在但检索没排上来"，避免盲补语料。

用法：.venv/Scripts/python.exe scripts/diag_fact_gap.py
"""
import asyncio, sys, json, re
from collections import defaultdict

sys.path.insert(0, '.')
from db.milvus_client import vector_db
from engines.frugal_rag import frugal_rag

SUBJECT_ALIAS = {
    'tcp': 'transport', 'udp': 'transport',
    'ip': 'network', 'routing': 'network', 'arp': 'network',
    'dns': 'application', 'http': 'application', 'ssl': 'security',
}


async def main():
    vector_db.connect()
    gold = json.load(open('experiments/gold_qa.json', encoding='utf-8'))

    for q in gold:
        course = q['course']
        exp = SUBJECT_ALIAS.get(q['expected_subject'], q['expected_subject'])
        facts = q.get('answer_facts', [])
        res = await frugal_rag.retrieve(q['question'], course=course, top_k=10, use_kg_enhance=False)

        rank = None
        for i, r in enumerate(res):
            if r.get('metadata', {}).get('subject') == exp:
                rank = i + 1
                break
        joined = ' '.join(r.get('text', '') for r in res)
        _norm = lambda s: re.sub(r'\s+', '', s)
        joined_n = _norm(joined)
        miss = [f for f in facts if _norm(f) not in joined_n]
        top_subjects = [r.get('metadata', {}).get('subject') for r in res[:5]]
        fr = (len(facts) - len(miss)) / len(facts) if facts else 1.0
        flag = 'OK ' if fr >= 0.8 else ('mid' if fr > 0 else 'ZERO')
        print(f"[{flag}] {q['id']:8s} exp={exp:12s} rank={rank if rank else '-':>2} fr={fr:4.0%} "
              f"miss={miss} top5={top_subjects}")


asyncio.run(main())
