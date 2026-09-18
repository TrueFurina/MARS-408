#!/usr/bin/env python3
# ============================================================
# Gold Q&A — LLM 作答准确率评测（端到端真实通道）
#
# 与 eval_gold.py / eval_gold_offline.py（只测检索可检索性）互补：
#   本脚本让真实大模型(讯飞星火 X2 → DeepSeek 兜底，auto 通道)基于检索上下文
#   作答 Gold 题，并度量"答案准确率"，而非"答案是否可检索到"。
#
# 评测指标：
#   ① fact_coverage : LLM 答案覆盖 gold answer_facts 的比例（词面，离线可算）
#   ② judge_score   : LLM-as-judge 把答案与 answer_key 比对给的 0~1 分（需二次调用）
#   ③ answerable_rate: judge_score >= 0.6 的题占比
#
# 运行（需 .env 提供 LLM 凭证，且已 pip install -r requirements.txt）：
#     python experiments/eval_llm.py                 # BM25 检索上下文（无需 E5）
#     python experiments/eval_llm.py --live          # 用真实 FrugalRAG 检索（需 E5 + 向量库）
#     python experiments/eval_llm.py --no-judge      # 只算 fact_coverage，不发 judge 调用
#     python experiments/eval_llm.py --limit 5       # 先小样本 smoke test
#
# 注：本脚本本地不可跑（需 .env 凭证 + 联网）；写成即用框架，凭证就绪即执行。
#     所有输出真实，无美化，符合诚信红线。
# ============================================================
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # py-server
sys.path.insert(0, str(Path(__file__).resolve().parent))          # experiments

import eval_gold_offline as E  # 复用 BM25 检索 + gold 加载 + groundedness

COURSES = ["computer_network", "data_structures", "computer_organization", "operating_system"]


def _build_context(question, course, use_live, top_k=5):
    """取检索上下文文本。use_live=True 走真实 FrugalRAG（需 E5），否则离线 BM25。"""
    if use_live:
        try:
            from engines.frugal_rag import FrugalRAG
            docs, _ = FrugalRAG().retrieve(question, course, top_k=top_k)
            return "\n\n".join(d.get("text", "") for d in docs)
        except Exception as e:
            print(f"  [warn] live 检索失败，回退 BM25: {e}")
    docs = E.build_corpus()
    res = E.retrieve(question, course, docs, True, top_k=top_k)
    return "\n\n".join(d["text"] for d, _ in res)


def _ask_llm(llm, question, context):
    """用真实 LLM 通道作答。返回答案字符串。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是 408 计算机专业考研辅导助手。请基于【参考资料】用中文准确作答，"
                "条理清晰，只使用资料中可支撑的要点，不确定时明确说明。"
            ),
        },
        {
            "role": "user",
            "content": f"【参考资料】\n{context}\n\n【问题】{question}",
        },
    ]
    resp = llm.chat(messages=messages, temperature=0.2, max_tokens=800)
    return resp["choices"][0]["message"]["content"].strip()


def _judge(llm, question, answer, answer_key):
    """LLM-as-judge：把答案与标准要点比对，返回 0~1 分。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是严格的考研阅卷人。给定题目、学生答案、标准要点，"
                "请只输出一个 0 到 1 之间的小数（保留 2 位），表示答案正确性，"
                "不要输出任何解释。"
            ),
        },
        {
            "role": "user",
            "content": f"题目：{question}\n标准要点：{answer_key}\n学生答案：{answer}\n正确性分数：",
        },
    ]
    try:
        resp = llm.chat(messages=messages, temperature=0.0, max_tokens=8)
        txt = resp["choices"][0]["message"]["content"].strip()
        return float(txt)
    except Exception:
        return 0.0


def main():
    ap = argparse.ArgumentParser(description="Gold Q&A LLM 作答准确率评测")
    ap.add_argument("--live", action="store_true", help="用真实 FrugalRAG 检索（需 E5）")
    ap.add_argument("--no-judge", action="store_true", help="只算 fact_coverage，不发 judge 调用")
    ap.add_argument("--limit", type=int, default=0, help="只评前 N 题（smoke test）")
    ap.add_argument("--out", default="experiments/results/llm_eval_latest.json", help="结果输出路径")
    args = ap.parse_args()

    from db.llm_provider import LLMProvider
    llm = LLMProvider()  # auto: 讯飞 X2 → DeepSeek 兜底

    gold = json.load(open(os.path.join(os.path.dirname(__file__), "gold_qa.json"), encoding="utf-8"))
    if args.limit:
        gold = gold[: args.limit]

    per = []
    by_course = {c: [] for c in COURSES}
    t0 = time.time()
    for g in gold:
        course = g["course"]
        ctx = _build_context(g["question"], course, args.live)
        answer = _ask_llm(llm, g["question"], ctx)
        fc = E.groundedness(g["answer_facts"], answer)  # 答案对 gold facts 的覆盖率
        judge = _judge(llm, g["question"], answer, g.get("answer_key", "")) if not args.no_judge else None
        rec = {
            "id": g["id"], "course": course,
            "fact_coverage": round(fc, 3),
            "judge_score": round(judge, 3) if judge is not None else None,
            "answerable": (judge >= 0.6) if judge is not None else None,
            "answer": answer,
        }
        per.append(rec)
        by_course.setdefault(course, []).append(rec)
        print(f"Q[{g['id']}] {course} fact_cov={fc:.2f} judge={judge if judge is None else round(judge,2)}")

    overall = {
        "n": len(per),
        "mean_fact_coverage": round(sum(p["fact_coverage"] for p in per) / max(len(per), 1), 3),
    }
    if not args.no_judge:
        js = [p["judge_score"] for p in per if p["judge_score"] is not None]
        overall["mean_judge_score"] = round(sum(js) / max(len(js), 1), 3)
        overall["answerable_rate"] = round(sum(1 for p in per if p["answerable"]) / max(len(per), 1), 3)
    for c in COURSES:
        ps = by_course.get(c, [])
        if not ps:
            continue
        line = f"  {c}: fact_cov={sum(p['fact_coverage'] for p in ps)/len(ps):.3f}"
        if not args.no_judge:
            line += f" judge={sum(p['judge_score'] for p in ps if p['judge_score'] is not None)/len(ps):.3f}"
        print(line)

    print("OVERALL:", json.dumps(overall, ensure_ascii=False))
    print(f"总耗时 {time.time()-t0:.1f}s")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"overall": overall, "per": per}, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"结果已写: {out_path}")


if __name__ == "__main__":
    main()
