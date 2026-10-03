"""临时诊断：用真实 retrieve 复现 CN 每题 top5，定位 groundedness 低真因。"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_gold_offline as E

docs = E.build_corpus()
gold = json.load(open(os.path.join(os.path.dirname(__file__), "gold_qa.json"), encoding="utf-8"))

print("=== CN 逐题诊断（真实 BM25 + 降权）===")
for g in gold:
    if g["course"] != "computer_network":
        continue
    res = E.retrieve(g["question"], "computer_network", docs, True, top_k=5)
    ctx = " ".join(d["text"] for d, _ in res)
    gd = E.groundedness(g["answer_facts"], ctx)
    miss = [f for f in g["answer_facts"] if f not in ctx]
    exp = E._effective_subject(g)
    print(f"\nQ[{g['id']}] {g['question']}")
    print(f"  expected_subject={exp} groundedness={gd:.2f} missed_facts={miss}")
    for i, (d, s) in enumerate(res):
        star = "*" if d["subject"] == exp else " "
        print(f"  {i+1}{star} [{d['subject']:>12}] score={s:.3f} | {d['text'][:42].replace(chr(10),' ')}")
