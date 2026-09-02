#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""真实语料检索评测：BM25-only(降级基线) vs E5 向量 vs 混合。

产出服务于两件事：
  1. 给出"E5 恢复后检索到底提升多少"的真实数字（大创中期用得上的一手证据）
  2. A/B 判定 e5 官方前缀（query:/passage:）在当前语料上是否更优，避免拍脑袋

指标：Recall@5、MRR@10、Groundedness（答案要点在 top5 上下文中的覆盖率）
数据集：experiments/gold_qa.json（30 题，四科均衡，带 answer_facts）

用法（在 py-server 目录下）：
    .venv/Scripts/python.exe ../scripts/eval_retrieval_real.py [--prefix]
      --prefix  检索时给 query 加 "query: " 前缀（须与 --prefix 重建的库配套）
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path


# gold 评测集用细粒度 subject（tcp/ip/dns/...），而语料对计网采用 OSI/TCP-IP 分层粒度
# （transport/network/datalink/application/physical/security/cn）。不做映射会有 7 个
# subject 永远匹配不上（占 30 题中约 8 题），指标被恒定拉低而非真实反映检索质量。
# 以下映射按计算机网络学科常规归属建立，映射错误会直接暴露在指标里，故保留在代码内可见。
GOLD_SUBJECT_MAP = {
    "tcp": ["transport", "cn"],
    "ip": ["network", "cn"],
    "routing": ["network", "cn"],
    "arp": ["network", "datalink", "cn"],
    "dns": ["application", "cn"],
    "http": ["application", "cn"],
    "ssl": ["application", "security", "cn"],
}

HERE = Path(__file__).resolve().parent
PY_SERVER = HERE.parent / "py-server"
KB_JSON = PY_SERVER / "vectordb_data" / "netlearn_kb.json"
GOLD = PY_SERVER / "experiments" / "gold_qa.json"
OUT_DIR = PY_SERVER / "experiments" / "results"

sys.path.insert(0, str(PY_SERVER))


# ── BM25（与 engines/frugal_rag.py 一致）──
class BM25:
    def __init__(self, docs: list[str]):
        self.k1, self.b = 1.5, 0.75
        self.docs = [self.tok(d) for d in docs]
        self.df: dict[str, int] = {}
        for t in self.docs:
            for w in set(t):
                self.df[w] = self.df.get(w, 0) + 1
        self.avgdl = sum(len(t) for t in self.docs) / max(len(self.docs), 1)
        self.n = len(self.docs)

    @staticmethod
    def tok(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9_]+", text.lower()) + re.findall(r"[\u4e00-\u9fff]", text)

    def score(self, query: str) -> list[float]:
        qt = set(self.tok(query))
        out = []
        for d in self.docs:
            s, dl = 0.0, len(d)
            tf: dict[str, int] = {}
            for w in d:
                tf[w] = tf.get(w, 0) + 1
            for w in qt:
                if w not in tf:
                    continue
                f = tf[w]
                idf = math.log(
                    (self.n - self.df.get(w, 0) + 0.5) / (self.df.get(w, 0) + 0.5) + 1.0
                )
                s += idf * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )
            out.append(s)
        m = max(out) if out else 1.0
        return [x / m if m > 0 else 0.0 for x in out]


def expand_subject(expected: str) -> list[str]:
    """gold 细粒度 subject → 语料中可能的 subject 候选（含家族前缀，如 ds_stack→ds_stack）"""
    base = GOLD_SUBJECT_MAP.get(expected, [expected])
    out = []
    for b in base:
        out.append(b)
        out.append(b + "_")  # 家族前缀哨兵，命中 ds_stack_xxx 之类
    return out


def _hit(sub: str, cands: list[str]) -> bool:
    for c in cands:
        if c.endswith("_"):
            if sub.startswith(c[:-1] + "_"):
                return True
        elif sub == c or sub.startswith(c + "_") or c.startswith(sub):
            return True
    return False


def recall_at_k(ranked: list[int], cands: list[str], metas: list[dict], k: int) -> float:
    """命中判定：top-k 中至少一条属于期望 subject（家族前缀匹配）"""
    for idx in ranked[:k]:
        if _hit(str(metas[idx].get("subject", "")), cands):
            return 1.0
    return 0.0


def mrr(ranked: list[int], cands: list[str], metas: list[dict], k: int = 10) -> float:
    for rank, idx in enumerate(ranked[:k], 1):
        if _hit(str(metas[idx].get("subject", "")), cands):
            return 1.0 / rank
    return 0.0


def groundedness(facts: list[str], ctx: list[str]) -> float:
    if not facts:
        return 0.0
    blob = " ".join(ctx)
    hit = sum(1 for f in facts if f.strip() in blob)
    return hit / len(facts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", action="store_true")
    ap.add_argument("--topk", type=int, default=5)
    args = ap.parse_args()

    kb = json.load(open(KB_JSON, encoding="utf-8"))
    texts, metas = kb["texts"], kb["metas"]
    gold = json.load(open(GOLD, encoding="utf-8"))

    import numpy as np

    # 命中判定用的期望 subject（gold 用 expected_subject 粗粒度，语料 subject 更细）
    # 例如 expected_subject="tcp" 对应语料 "tcp"、"tcp_flow" 等
    print(f"[eval] 语料 {len(texts)} 条 / 题目 {len(gold)} 题 / prefix={args.prefix}")

    emb = np.asarray(kb["embeddings"], dtype=np.float32)
    zero_rows = int((np.linalg.norm(emb, axis=1) < 1e-6).sum())
    print(f"[eval] 零向量行 = {zero_rows} / {len(emb)}")

    bm25 = BM25(texts)

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(str(PY_SERVER / "models" / "e5-base-v2"))
    q_prefix = "query: " if args.prefix else ""

    per_mode: dict[str, dict[str, float]] = {}
    for mode in ("bm25", "e5", "hybrid"):
        r5, mrrs, gr = [], [], []
        for q in gold:
            query = q["question"]
            if mode in ("bm25", "hybrid"):
                s_bm = np.asarray(bm25.score(query), dtype=np.float32)
            if mode in ("e5", "hybrid"):
                qv = model.encode([q_prefix + query], normalize_embeddings=True)[0]
                s_e5 = emb @ np.asarray(qv, dtype=np.float32)
            if mode == "bm25":
                s = s_bm
            elif mode == "e5":
                s = s_e5
            else:
                s = 0.5 * s_bm + 0.5 * s_e5
            ranked = list(np.argsort(-s)[:10])
            cands = expand_subject(q["expected_subject"])
            r5.append(recall_at_k(ranked, cands, metas, args.topk))
            mrrs.append(mrr(ranked, cands, metas, 10))
            gr.append(groundedness(q.get("answer_facts", []), [texts[i] for i in ranked[: args.topk]]))
        per_mode[mode] = {
            f"recall@{args.topk}": round(sum(r5) / len(r5), 4),
            "mrr@10": round(sum(mrrs) / len(mrrs), 4),
            "groundedness": round(sum(gr) / len(gr), 4),
        }
        print(f"[eval] {mode:7s} -> {per_mode[mode]}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "with-prefix" if args.prefix else "no-prefix"
    out = OUT_DIR / f"retrieval_eval_real_{tag}.json"
    payload = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "corpus_size": len(texts),
        "gold_size": len(gold),
        "query_prefix": args.prefix,
        "zero_vector_rows": zero_rows,
        "modes": per_mode,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[eval] 结果已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
