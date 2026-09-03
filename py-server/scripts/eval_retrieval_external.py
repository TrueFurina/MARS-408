"""独立外部评测集（去环）真实检索量化评测。

目的：打破"gold_qa.json 与 KB 同源"的循环论证嫌疑。
本集题目来自**历年计算机统考 408 真题（公开/回忆版）**，属外部权威来源，
并非由本项目 KB 内容派生撰写；据此验证 FrugalRAG 对"非 KB  authored"真实问题的知识可检索性。

复用 eval_retrieval_gold.py 的同一 retrieve 路径与指标口径：
  - Subject Recall@k：期望知识点(expected_subject)是否进入 top-k
  - MRR：按 expected_subject 首次命中排名的均倒数
  - Fact Recall@10：答案要点(answer_facts)在 top-10 文本中的覆盖率均值
  - 跨课程污染率：结果 subject 不在本课程合法标签集的比例

用法：.venv/Scripts/python.exe scripts/eval_retrieval_external.py
"""
import asyncio, sys, json, datetime, re
from collections import defaultdict

sys.path.insert(0, '.')
from db.milvus_client import vector_db
from engines.frugal_rag import frugal_rag, _reranker

K = 10
KS = [1, 3, 5, 10]

# 外部集 expected_subject 已直接采用 KB 标签（transport/network/application/
# datalink/ds_sort/...），无需协议名别名；保留占位以保持与 gold harness 一致。
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
    gold = json.load(open('experiments/gold_qa_external.json', encoding='utf-8'))
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
        exp_kb = norm_subject(exp)
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

    print(f"题目数(外部真题): {n} | 结果总数: {total_results}")
    print("— 课程正确性（期望知识点是否进入 top-k）—")
    for k in KS:
        print(f"  Subject Recall@{k:<2}: {subj_hit[k] / n:6.1%}")
    print(f"  MRR (expected_subject 首命中): {sum(mrr_ranks) / n:.3f}")
    print("— 内容覆盖（去环：外部真题答案要点覆盖率）—")
    print(f"  Fact Recall@{K} (答案要点覆盖率均值): {sum(fact_hits) / n:6.1%}")
    print("— 跨课程污染 —")
    print(f"  越界结果占比: {cross_results / total_results:6.1%}")
    print("— 分科 —")
    for c, v in sorted(per.items()):
        m = sum(v['mrr']) / len(v['mrr']) if v['mrr'] else 0.0
        f = sum(v['fact']) / len(v['fact']) if v['fact'] else 0.0
        print(f"  {c:22s} n={v['n']:2d} subj@5={v['subj5'] / v['n']:5.0%} "
              f"MRR={m:.3f} fact@{K}={f:5.0%}")

    corpus_size = vector_db.count("netlearn_kb")
    _rk = _reranker
    reranker_status = (
        "enabled(local:bge-reranker-base)"
        if _rk is not None and getattr(_rk, "_model", None) is not None
        and not getattr(_rk, "_disabled", False)
        else "disabled(load_failed_or_offline)"
    )
    out = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "harness": "gold_qa_external",
        "provenance": "历年计算机统考408真题（公开/回忆版），外部独立来源，非本KB派生",
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
    out_path = "experiments/results/retrieval_eval_external_2026-09-03.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n[结果已落盘] {out_path}")


asyncio.run(main())
