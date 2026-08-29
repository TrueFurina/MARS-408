# ============================================================
# Gold Q&A 离线 A/B 评测（BM25-only，无需 E5 / torch）
# 复刻 FrugalRAG 的真实 BM25Scorer 与模板降权逻辑（与 engines/frugal_rag.py 一致），
# 在持久化语料 seed_data.SEED_KNOWLEDGE_CHUNKS 上做 before/after 对比，验证模板降权修复。
# 用法: python experiments/eval_gold_offline.py
# ============================================================
import json
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import seed_data as sd

# ── 真实 BM25Scorer（与 engines/frugal_rag.py 一致，纯复制）──
class BM25Scorer:
    def __init__(self):
        self.k1 = 1.5
        self.b = 0.75

    def score(self, query, documents):
        query_terms = self._tokenize(query)
        doc_tokens = [self._tokenize(d) for d in documents]
        total_docs = len(documents)
        df = {}
        for terms in doc_tokens:
            for term in set(terms):
                df[term] = df.get(term, 0) + 1
        avgdl = np.mean([len(t) for t in doc_tokens]) if doc_tokens else 1
        scores = []
        for doc_terms in doc_tokens:
            score = 0.0
            doc_len = len(doc_terms)
            term_freq = {}
            for term in doc_terms:
                term_freq[term] = term_freq.get(term, 0) + 1
            for term in query_terms:
                if term not in term_freq:
                    continue
                tf = term_freq[term]
                df_t = df.get(term, 0)
                idf = np.log((total_docs - df_t + 0.5) / (df_t + 0.5) + 1.0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / avgdl)
                score += idf * numerator / denominator
            scores.append(score)
        max_score = max(scores) if scores else 1.0
        return [s / max_score if max_score > 0 else 0.0 for s in scores]

    @staticmethod
    def _tokenize(text):
        words = re.findall(r'[a-zA-Z0-9_]+', text.lower())
        chinese = re.findall(r'[\u4e00-\u9fff]', text)
        return words + chinese


# ── 真实模板/近重复降权（与 engines/frugal_rag.py 一致，纯复制）──
_BOILERPLATE_PAT = re.compile(
    r"本知识点属于|本节学习目标|本章小结|本章学习要求|知识点总结|基本概念(和|与)核心"
    r"|^计算机网络是互连的|^OSI七层模型|^分组交换采用存储转发|^物理层的主要任务|^信道复用技术"
    r"|^【(考点速记|易错辨析|关键术语|典型例题|本章导学|知识拓展|真题精讲|速记口诀|避坑指南)】"
)


def boilerplate_factor(text):
    if text and _BOILERPLATE_PAT.search(text):
        return 0.4
    return 1.0


COURSE_SUBJECTS = {
    "computer_network": ["overview", "architecture", "switching", "physical", "datalink",
        "csma", "ethernet", "vlan", "network", "ip", "arp", "routing", "transport",
        "tcp", "udp", "application", "dns", "http", "ftp", "dhcp", "security", "ssl",
        "firewall", "attack", "crypto", "hash", "signature", "certificate", "ddos",
        "web_attack", "ids", "vpn"],
    "data_structures": ["ds_linear", "ds_stack", "ds_queue", "ds_string", "ds_tree", "ds_graph", "ds_search", "ds_sort"],
    "computer_organization": ["co_overview", "co_data", "co_memory", "co_isa", "co_cpu", "co_bus", "co_io"],
    "operating_system": ["os_overview", "os_process", "os_memory", "os_file", "os_io"],
}


def build_corpus():
    docs = []
    for i, c in enumerate(sd.SEED_KNOWLEDGE_CHUNKS):
        docs.append({
            "id": f"chunk_{i}",
            "text": c.get("content", ""),
            "subject": c.get("metadata", {}).get("subject", ""),
            "course": c.get("metadata", {}).get("course", ""),
        })
    return docs


def retrieve(query, course, docs, use_penalty, top_k=5):
    qterms = BM25Scorer()._tokenize(query)  # 仅用于构造，实际在 score 内使用
    bs = BM25Scorer().score(query, [d["text"] for d in docs])
    ranked = sorted(zip(docs, bs), key=lambda x: x[1], reverse=True)
    subj = COURSE_SUBJECTS.get(course, [])
    if subj:
        filt = [(d, s) for d, s in ranked if d["subject"] in subj or d["course"] == course]
        if filt:
            ranked = filt
    out = []
    for d, s in ranked[:top_k * 6]:
        if s <= 0:
            continue
        factor = boilerplate_factor(d["text"]) if use_penalty else 1.0
        out.append((d, s * factor))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:top_k]


def groundedness(facts, ctx):
    if not facts:
        return 0.0
    hits = sum(1 for f in facts if f in ctx)
    return hits / len(facts)


# CN 粗粒度对齐：seed 语料用 network/transport/security/application 等粗标签，
# Gold 集用 tcp/ip 等细标签；此处做粗细映射，使 subject_recall 反映"命中正确课程章节"。
CN_COARSE = {
    "tcp": "transport", "ip": "network", "routing": "network",
    "dns": "application", "http": "application", "arp": "network", "ssl": "security",
}


def _effective_subject(g):
    subj = g["expected_subject"]
    if g["course"] == "computer_network":
        return CN_COARSE.get(subj, subj)
    return subj


def evaluate(use_penalty):
    docs = build_corpus()
    gold = json.load(open(os.path.join(os.path.dirname(__file__), "gold_qa.json"), encoding="utf-8"))
    per = []
    by_course = {}
    for g in gold:
        course = g["course"]
        exp = _effective_subject(g)
        res = retrieve(g["question"], course, docs, use_penalty)
        ctx = " ".join(d["text"] for d, _ in res)
        subj_hit = any(d["subject"] == exp for d, _ in res)
        subj_hit_subst = any(
            d["subject"] == exp and boilerplate_factor(d["text"]) == 1.0
            for d, _ in res
        )
        gd = groundedness(g["answer_facts"], ctx)
        template_share = sum(1 for d, _ in res if boilerplate_factor(d["text"]) < 1.0) / max(len(res), 1)
        per.append({
            "id": g["id"], "course": course, "subject_recall@5": 1.0 if subj_hit else 0.0,
            "substantive_hit": 1.0 if subj_hit_subst else 0.0,
            "groundedness": round(gd, 3), "template_share": round(template_share, 3),
            "answerable": 1.0 if gd >= 0.6 else 0.0,
        })
        by_course.setdefault(course, []).append(per[-1])
    return per, by_course


def summarize(per, by_course, tag):
    print(f"\n=== {tag} ===")
    overall = {
        "subject_recall@5": round(np.mean([p["subject_recall@5"] for p in per]), 3),
        "substantive_hit": round(np.mean([p["substantive_hit"] for p in per]), 3),
        "mean_groundedness": round(np.mean([p["groundedness"] for p in per]), 3),
        "answerable_rate": round(np.mean([p["answerable"] for p in per]), 3),
        "template_share_in_top5": round(np.mean([p["template_share"] for p in per]), 3),
    }
    print("OVERALL:", json.dumps(overall, ensure_ascii=False))
    for c in ["computer_network", "data_structures", "computer_organization", "operating_system"]:
        ps = by_course.get(c, [])
        if not ps:
            continue
        print(f"  {c}: recall={np.mean([p['subject_recall@5'] for p in ps]):.3f} "
              f"subst_hit={np.mean([p['substantive_hit'] for p in ps]):.3f} "
              f"gd={np.mean([p['groundedness'] for p in ps]):.3f} "
              f"ans={np.mean([p['answerable'] for p in ps]):.3f} "
              f"tmpl={np.mean([p['template_share'] for p in ps]):.3f}")
    return overall


if __name__ == "__main__":
    t0 = time.time()
    before = evaluate(False)
    after = evaluate(True)
    ob_before = summarize(before[0], before[1], "BEFORE（无模板降权）")
    ob_after = summarize(after[0], after[1], "AFTER（模板降权 0.4）")
    print("\n=== 提升（AFTER - BEFORE）===")
    print(f"  subject_recall@5 : {ob_after['subject_recall@5'] - ob_before['subject_recall@5']:+.3f}")
    print(f"  substantive_hit  : {ob_after['substantive_hit'] - ob_before['substantive_hit']:+.3f}")
    print(f"  mean_groundedness: {ob_after['mean_groundedness'] - ob_before['mean_groundedness']:+.3f}")
    print(f"  answerable_rate  : {ob_after['answerable_rate'] - ob_before['answerable_rate']:+.3f}")
    print(f"  template_share   : {ob_after['template_share_in_top5'] - ob_before['template_share_in_top5']:+.3f} （越低越好）")
    print(f"\n总耗时 {time.time()-t0:.1f}s")
