"""真实检索量化评测（gold Q&A harness）。

基于 experiments/gold_qa.json 的 30 题四科 gold，跑真实 frugal_rag.retrieve
（E5 + BM25 混合，已修），输出：
  - Subject Recall@k：期望知识点(expected_subject)是否进入 top-k（课程正确性）
  - MRR：按 expected_subject 首次命中排名的均倒数
  - Fact Recall@10：答案要点(answer_facts)在 top-10 文本中的覆盖率均值
  - 跨课程污染率：结果 subject 不在本课程合法标签集的比例

用法：.venv/Scripts/python.exe scripts/eval_retrieval_gold.py
"""
import asyncio, sys, json, datetime, re
from collections import defaultdict

sys.path.insert(0, '.')
from db.milvus_client import vector_db
from engines.frugal_rag import frugal_rag

K = 10
KS = [1, 3, 5, 10]

# gold expected_subject 用协议名（tcp/ip/routing...），KB 用分层标签
# （transport/network/...）。CN 题需归一化才能诚实衡量"是否检到该主题"。
SUBJECT_ALIAS = {
    'tcp': 'transport', 'udp': 'transport',
    'ip': 'network', 'routing': 'network', 'arp': 'network',
    'dns': 'application', 'http': 'application',
    'ssl': 'security',
}


def norm_subject(exp: str) -> str:
    return SUBJECT_ALIAS.get(exp, exp)


async def main():
    vector_db.connect()
    gold = json.load(open('experiments/gold_qa.json', encoding='utf-8'))
    n = len(gold)

    subj_hit = {k: 0 for k in KS}
    mrr_ranks = []
    fact_hits = []
    cross_results = 0
    total_results = 0
    per = defaultdict(lambda: {'n': 0, 'subj5': 0, 'mrr': [], 'fact': []})

    for q in gold:
        course = q['course']
        exp = q['expected_subject']
        exp_kb = norm_subject(exp)  # 归一化到 KB 标签
        facts = q.get('answer_facts', [])
        valid = set(frugal_rag._get_course_subjects(course))

        res = await frugal_rag.retrieve(q['question'], course=course, top_k=K, use_kg_enhance=False)

        rank = None
        for i, r in enumerate(res):
            if r.get('metadata', {}).get('subject') == exp_kb:
                rank = i + 1
                break
        if rank:
            for k in KS:
                if rank <= k:
                    subj_hit[k] += 1
            mrr_ranks.append(1.0 / rank)
            per[course]['mrr'].append(1.0 / rank)
        if rank and rank <= 5:
            per[course]['subj5'] += 1

        joined = ' '.join(r.get('text', '') for r in res)
        # 去空格归一化：消除 gold 事实与 chunk 文本间的空格/异体词假象
        # （如 "O(n log n)" vs "O(nlogn)"、"next 数组" vs "next数组"、"20 字节" vs "20字节"）
        _norm = lambda s: re.sub(r'\s+', '', s)
        joined_n = _norm(joined)
        fh = (sum(1 for f in facts if _norm(f) in joined_n) / len(facts)) if facts else 0.0
        fact_hits.append(fh)
        per[course]['fact'].append(fh)
        per[course]['n'] += 1

        for r in res:
            total_results += 1
            if r.get('metadata', {}).get('subject') not in valid:
                cross_results += 1

    print(f"题目数: {n} | 结果总数: {total_results}")
    print("— 课程正确性（期望知识点是否进入 top-k）—")
    for k in KS:
        print(f"  Subject Recall@{k:<2}: {subj_hit[k] / n:6.1%}")
    print(f"  MRR (expected_subject 首命中): {sum(mrr_ranks) / n:.3f}")
    print("— 内容覆盖 —")
    print(f"  Fact Recall@{K} (答案要点覆盖率均值): {sum(fact_hits) / n:6.1%}")
    print("— 跨课程污染 —")
    print(f"  越界结果占比: {cross_results / total_results:6.1%}")
    print("— 分科 —")
    for c, v in sorted(per.items()):
        m = sum(v['mrr']) / len(v['mrr']) if v['mrr'] else 0.0
        f = sum(v['fact']) / len(v['fact']) if v['fact'] else 0.0
        print(f"  {c:22s} n={v['n']:2d} subj@5={v['subj5'] / v['n']:5.0%} "
              f"MRR={m:.3f} fact@{K}={f:5.0%}")

    # 落盘：可复现结果（大创"改实"证据链交付物）
    corpus_size = vector_db.count("netlearn_kb")
    # Reranker 实际状态（懒加载，评测循环内首次 retrieve 时已触发加载）
    _rk = getattr(frugal_rag, "_reranker", None)
    reranker_status = (
        "enabled(local:bge-reranker-base)"
        if _rk is not None and not getattr(_rk, "_disabled", False)
        else "disabled(load_failed_or_offline)"
    )
    out = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "harness": "gold_qa",
        "corpus_size": corpus_size,
        "gold_size": n,
        "vector_status": "e5_real",
        "reranker": reranker_status,
        "metrics": {
            "subject_recall@k": {str(k): round(subj_hit[k] / n, 4) for k in KS},
            "mrr": round(sum(mrr_ranks) / n, 4) if mrr_ranks else 0.0,
            "fact_recall@10": round(sum(fact_hits) / n, 4),
            "cross_course_pollution": round(cross_results / total_results, 4),
        },
        "per_course": {
            c: {
                "n": v["n"],
                "subj@5": round(v["subj5"] / v["n"], 4),
                "mrr": round(sum(v["mrr"]) / len(v["mrr"]), 4) if v["mrr"] else 0.0,
                "fact@10": round(sum(v["fact"]) / len(v["fact"]), 4) if v["fact"] else 0.0,
            }
            for c, v in sorted(per.items())
        },
    }
    out_path = "experiments/results/retrieval_eval_gold_2026-09-03.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n[结果已落盘] {out_path}")


asyncio.run(main())
