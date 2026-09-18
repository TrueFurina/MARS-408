#!/usr/bin/env python3
# ============================================================
# MARS-408 Benchmark — FrugalRAG vs 全量检索, NeuralMixer vs 加权投票
#
# 实验1: FrugalRAG(查询重写+阈值融合+BM25+topk) vs 全量检索(无重写/无阈值)
#   指标: 返回chunks数 / 估算token / 端到端延迟(ms) / Recall@k / MRR
# 实验2: NeuralMixer(训练后GroupMixerNet) vs 简单加权投票
#   指标: Cohen's Kappa (方法间一致性) / 准确率 (vs 弱标注)
#
# 产出:
#   experiments/results/benchmark_<date>.json
#   experiments/results/fig_cost.png
#   experiments/results/fig_mixer.png
#
# 用法:
#   cd py-server
#   python experiments/benchmark.py
# ============================================================

import os
import sys
import json
import time
import logging
import statistics
import random
from pathlib import Path
from datetime import date

# ── 离线模式（避免 HuggingFace 网络访问）──
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# ── 项目根 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

# matplotlib 非交互后端
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# sklearn (Cohen's Kappa)
from sklearn.metrics import cohen_kappa_score

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("benchmark")
logger.setLevel(logging.INFO)

# ── 项目模块（延迟导入关键依赖）──
from db.milvus_client import InMemoryVectorStore
from db.embedder import embed_text, embed_batch
from engines.frugal_rag import BM25Scorer, FrugalRAG


# ============================================================
# 全局配置
# ============================================================
TOP_K = 5                 # FrugalRAG / 全量检索统一 top-k
CANDIDATE_MULTIPLIER = 6  # FrugalRAG 候选扩展倍数（与 FrugalRAG.retrieve 一致）
COSINE_THRESHOLD = 0.65   # FrugalRAG 余弦阈值（与 config.json 一致）
BM25_WEIGHT = 0.3
VECTOR_WEIGHT = 0.7
EST_TOKEN_PER_CHAR = 1 / 1.8  # 中文 ~1.8 字/token，英文 ~4 字符/token，混合取折中
RANDOM_SEED = 20260719


# ============================================================
# FrugalRAG 课程 → subject 映射（与 engines/frugal_rag.py 一致）
# ============================================================
COURSE_SUBJECTS = FrugalRAG._COURSE_SUBJECTS


# ============================================================
# 工具函数
# ============================================================

def estimate_tokens(text: str) -> int:
    """估算文本 token 数（中英混合近似）"""
    if not text:
        return 0
    # 中文按 1.8 字/token，英文按 4 字符/token
    cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - cn_chars
    return int(cn_chars / 1.8 + other_chars / 4)


def total_tokens(chunks: list[dict]) -> int:
    return sum(estimate_tokens(c.get("text", "")) for c in chunks)


def compute_recall_at_k(results: list[dict], expected_subjects: set, k: int = 5) -> float:
    """Recall@k (binary): top-k 中是否存在至少一个匹配 expected_subjects 的结果"""
    if not expected_subjects or not results:
        return 0.0
    top_k = results[:k]
    for r in top_k:
        if r.get("metadata", {}).get("subject", "") in expected_subjects:
            return 1.0
    return 0.0


def compute_precision_at_k(results: list[dict], expected_subjects: set, k: int = 5) -> float:
    """Precision@k: top-k 中匹配 expected_subjects 的比例"""
    if not results:
        return 0.0
    top_k = results[:k]
    hits = sum(1 for r in top_k if r.get("metadata", {}).get("subject", "") in expected_subjects)
    return hits / len(top_k)


def compute_mrr(results: list[dict], expected_subjects: set) -> float:
    """MRR: 第一个匹配结果的倒数排名"""
    for i, r in enumerate(results):
        if r.get("metadata", {}).get("subject", "") in expected_subjects:
            return 1.0 / (i + 1)
    return 0.0


def median(values: list) -> float:
    return float(statistics.median(values)) if values else 0.0


def mean(values: list) -> float:
    return float(statistics.mean(values)) if values else 0.0


# ============================================================
# 实验1: FrugalRAG vs 全量检索
# ============================================================

def frugalrag_retrieve(store: InMemoryVectorStore, bm25: BM25Scorer,
                       query: str, course: str, top_k: int = TOP_K) -> list[dict]:
    """复刻 FrugalRAG.retrieve 流程（不含 redis/pg/cache/reranker/个性化）

    流程: E5向量化 → 向量检索 top_k*6 → 课程 subject 软过滤 → 余弦阈值 →
          BM25 → 加权融合(0.7*vec + 0.3*bm25) → top_k
    """
    # 1. E5 向量化
    query_vec = embed_text(query)

    # 2. 向量检索（全局集合 netlearn_kb, top_k*6 候选）
    candidates = store.query("netlearn_kb", query_vec, top_k=top_k * CANDIDATE_MULTIPLIER)
    if not candidates:
        return []

    # 3. 课程 subject 软过滤（与 FrugalRAG 一致：过滤后空则回退全局 top-k）
    course_subjects = COURSE_SUBJECTS.get(course, [])
    if course_subjects:
        matched = [c for c in candidates
                   if c.get("metadata", {}).get("subject", "") in course_subjects
                   or c.get("metadata", {}).get("course", "") == course]
        if matched:
            candidates = matched

    # 4. 余弦阈值过滤（阈值太严则放宽到 top-k 分数）
    filtered = [c for c in candidates if c.get("score", 0) >= COSINE_THRESHOLD]
    if not filtered:
        filtered = candidates[:top_k]

    # 5. BM25 关键词匹配
    doc_texts = [c.get("text", "") for c in filtered]
    bm25_scores = bm25.score(query, doc_texts)

    # 6. 加权融合排序
    for i, chunk in enumerate(filtered):
        vs = chunk.get("score", 0)
        bs = bm25_scores[i]
        chunk["_vector_score"] = vs
        chunk["_bm25_score"] = bs
        chunk["score"] = VECTOR_WEIGHT * vs + BM25_WEIGHT * bs
    filtered.sort(key=lambda x: x["score"], reverse=True)

    return filtered[:top_k]


def full_retrieve(store: InMemoryVectorStore, query: str, top_k: int = TOP_K) -> list[dict]:
    """全量检索基线: E5向量化 → 向量检索 top_k → 直接返回（无重写/无阈值/无BM25）"""
    query_vec = embed_text(query)
    results = store.query("netlearn_kb", query_vec, top_k=top_k)
    return results


def run_experiment1(queries: list[dict]) -> dict:
    """实验1主流程"""
    logger.info("=== 实验1: FrugalRAG vs 全量检索 ===")

    # 加载向量库
    store = InMemoryVectorStore(persist_path=str(PROJECT_ROOT / "vectordb_data"))
    loaded = store._load("netlearn_kb")
    if not loaded:
        raise RuntimeError("netlearn_kb 向量库加载失败")
    n_chunks = store.count("netlearn_kb")
    logger.info(f"向量库加载: {n_chunks} chunks")

    bm25 = BM25Scorer()

    # warmup embedder（首次加载模型慢，避免计入延迟）
    logger.info("预热嵌入模型...")
    _ = embed_text("预热查询")

    per_query = []
    for i, q in enumerate(queries):
        qid = q["id"]
        qtext = q["text"]
        course = q["course"]
        expected = set(q["expected_subjects"])

        # A: FrugalRAG
        t0 = time.perf_counter()
        res_a = frugalrag_retrieve(store, bm25, qtext, course, top_k=TOP_K)
        lat_a = (time.perf_counter() - t0) * 1000

        # B: 全量检索
        t0 = time.perf_counter()
        res_b = full_retrieve(store, qtext, top_k=TOP_K)
        lat_b = (time.perf_counter() - t0) * 1000

        rec_a = compute_recall_at_k(res_a, expected, k=TOP_K)
        rec_b = compute_recall_at_k(res_b, expected, k=TOP_K)
        prec_a = compute_precision_at_k(res_a, expected, k=TOP_K)
        prec_b = compute_precision_at_k(res_b, expected, k=TOP_K)
        mrr_a = compute_mrr(res_a, expected)
        mrr_b = compute_mrr(res_b, expected)

        per_query.append({
            "id": qid,
            "course": course,
            "query": qtext,
            "expected_subjects": list(expected),
            "frugalrag": {
                "n_chunks": len(res_a),
                "tokens": total_tokens(res_a),
                "latency_ms": round(lat_a, 2),
                "recall@5": round(rec_a, 4),
                "precision@5": round(prec_a, 4),
                "mrr": round(mrr_a, 4),
                "top1_subject": res_a[0]["metadata"].get("subject", "") if res_a else "",
                "top1_score": round(res_a[0]["score"], 4) if res_a else 0.0,
            },
            "full_retrieval": {
                "n_chunks": len(res_b),
                "tokens": total_tokens(res_b),
                "latency_ms": round(lat_b, 2),
                "recall@5": round(rec_b, 4),
                "precision@5": round(prec_b, 4),
                "mrr": round(mrr_b, 4),
                "top1_subject": res_b[0]["metadata"].get("subject", "") if res_b else "",
                "top1_score": round(res_b[0]["score"], 4) if res_b else 0.0,
            },
        })

        if (i + 1) % 7 == 0:
            logger.info(f"  实验1 进度: {i+1}/{len(queries)}")

    # 汇总
    fr_chunks = [pq["frugalrag"]["n_chunks"] for pq in per_query]
    fr_tokens = [pq["frugalrag"]["tokens"] for pq in per_query]
    fr_lat = [pq["frugalrag"]["latency_ms"] for pq in per_query]
    fr_rec = [pq["frugalrag"]["recall@5"] for pq in per_query]
    fr_prec = [pq["frugalrag"]["precision@5"] for pq in per_query]
    fr_mrr = [pq["frugalrag"]["mrr"] for pq in per_query]
    fu_chunks = [pq["full_retrieval"]["n_chunks"] for pq in per_query]
    fu_tokens = [pq["full_retrieval"]["tokens"] for pq in per_query]
    fu_lat = [pq["full_retrieval"]["latency_ms"] for pq in per_query]
    fu_rec = [pq["full_retrieval"]["recall@5"] for pq in per_query]
    fu_prec = [pq["full_retrieval"]["precision@5"] for pq in per_query]
    fu_mrr = [pq["full_retrieval"]["mrr"] for pq in per_query]

    summary = {
        "n_queries": len(per_query),
        "kb_chunks": n_chunks,
        "top_k": TOP_K,
        "frugalrag": {
            "mean_chunks": round(mean(fr_chunks), 2),
            "mean_tokens": round(mean(fr_tokens), 2),
            "median_tokens": round(median(fr_tokens), 2),
            "mean_latency_ms": round(mean(fr_lat), 2),
            "median_latency_ms": round(median(fr_lat), 2),
            "mean_recall@5": round(mean(fr_rec), 4),
            "mean_precision@5": round(mean(fr_prec), 4),
            "mean_mrr": round(mean(fr_mrr), 4),
        },
        "full_retrieval": {
            "mean_chunks": round(mean(fu_chunks), 2),
            "mean_tokens": round(mean(fu_tokens), 2),
            "median_tokens": round(median(fu_tokens), 2),
            "mean_latency_ms": round(mean(fu_lat), 2),
            "median_latency_ms": round(median(fu_lat), 2),
            "mean_recall@5": round(mean(fu_rec), 4),
            "mean_precision@5": round(mean(fu_prec), 4),
            "mean_mrr": round(mean(fu_mrr), 4),
        },
        "deltas": {
            "token_reduction_pct": round(
                (1 - mean(fr_tokens) / max(mean(fu_tokens), 1)) * 100, 2),
            "latency_reduction_pct": round(
                (1 - mean(fr_lat) / max(mean(fu_lat), 1)) * 100, 2),
            "recall_delta": round(mean(fr_rec) - mean(fu_rec), 4),
            "precision_delta": round(mean(fr_prec) - mean(fu_prec), 4),
            "mrr_delta": round(mean(fr_mrr) - mean(fu_mrr), 4),
        },
    }

    logger.info(
        f"实验1 完成: FrugalRAG token={mean(fr_tokens):.0f} (full={mean(fu_tokens):.0f}), "
        f"latency={mean(fr_lat):.0f}ms (full={mean(fu_lat):.0f}ms), "
        f"recall@5={mean(fr_rec):.3f} (full={mean(fu_rec):.3f}), "
        f"precision@5={mean(fr_prec):.3f} (full={mean(fu_prec):.3f})"
    )

    return {"per_query": per_query, "summary": summary}


# ============================================================
# 实验2: NeuralMixer vs 加权投票
# ============================================================

# 6 个 Agent（与 gomarl_mixer.py 一致）
AGENT_NAMES = ["teacher", "quizmaster", "media_designer",
               "extension", "ppt_designer", "code_practice"]

# Agent 基础权重（与 gomarl_mixer.py _base_weights 一致）
BASE_WEIGHTS = {
    "teacher": 1.0,
    "quizmaster": 0.9,
    "media_designer": 0.85,
    "extension": 0.8,
    "ppt_designer": 0.8,
    "code_practice": 0.85,
}

# Agent 专长映射（用于合成数据：每个题型的"专家"agent）
AGENT_SPECIALTY = {
    "concept":      ["teacher", "extension", "ppt_designer"],   # 概念题
    "calculation":  ["quizmaster", "teacher"],                  # 计算题
    "algorithm":    ["code_practice", "quizmaster"],            # 算法题
    "diagram":      ["media_designer", "teacher"],              # 图示题
    "comparison":   ["extension", "teacher"],                  # 对比题
    "summary":      ["ppt_designer", "teacher"],               # 总结题
}

# 30 道弱标注题（4 选 1，含正确答案 + 题型）
QUESTIONS = [
    {"id": "q01", "type": "concept",     "stem": "进程的三种基本状态是?",                      "options": 4, "answer": 0},
    {"id": "q02", "type": "concept",     "stem": "下列关于虚拟内存的描述正确的是?",            "options": 4, "answer": 1},
    {"id": "q03", "type": "calculation", "stem": "一个LRU页面置换序列的缺页次数是?",          "options": 4, "answer": 2},
    {"id": "q04", "type": "calculation", "stem": "银行家算法中安全序列的数量是?",             "options": 4, "answer": 0},
    {"id": "q05", "type": "algorithm",   "stem": "快速排序第一趟划分后的结果是?",             "options": 4, "answer": 3},
    {"id": "q06", "type": "algorithm",   "stem": "二叉树前序遍历的输出序列是?",               "options": 4, "answer": 1},
    {"id": "q07", "type": "diagram",     "stem": "OSI模型中数据封装的正确顺序是?",            "options": 4, "answer": 2},
    {"id": "q08", "type": "diagram",     "stem": "TCP三次握手的状态转换正确的是?",            "options": 4, "answer": 0},
    {"id": "q09", "type": "comparison",  "stem": "TCP与UDP的主要区别不包括?",                 "options": 4, "answer": 1},
    {"id": "q10", "type": "comparison",  "stem": "栈和队列的本质区别是?",                     "options": 4, "answer": 2},
    {"id": "q11", "type": "summary",     "stem": "操作系统的四大核心功能是?",                 "options": 4, "answer": 0},
    {"id": "q12", "type": "summary",     "stem": "计算机网络分层模型的优势是?",               "options": 4, "answer": 3},
    {"id": "q13", "type": "concept",     "stem": "死锁的四个必要条件是?",                     "options": 4, "answer": 1},
    {"id": "q14", "type": "calculation", "stem": "Cache命中率计算，给定访问序列的结果是?",     "options": 4, "answer": 2},
    {"id": "q15", "type": "algorithm",   "stem": "Dijkstra算法求最短路径的结果是?",           "options": 4, "answer": 0},
    {"id": "q16", "type": "algorithm",   "stem": "哈希表线性探测冲突后的最终位置是?",         "options": 4, "answer": 3},
    {"id": "q17", "type": "diagram",     "stem": "IPv4数据报首部的正确结构是?",               "options": 4, "answer": 1},
    {"id": "q18", "type": "comparison",  "stem": "组合逻辑与微程序控制器的对比正确的是?",     "options": 4, "answer": 2},
    {"id": "q19", "type": "concept",     "stem": "文件系统目录结构的作用是?",                 "options": 4, "answer": 0},
    {"id": "q20", "type": "calculation", "stem": "浮点数加减运算的结果是?",                   "options": 4, "answer": 1},
    {"id": "q21", "type": "summary",     "stem": "数据结构中逻辑结构的四大类型是?",           "options": 4, "answer": 2},
    {"id": "q22", "type": "algorithm",   "stem": "BFS遍历图的输出序列是?",                   "options": 4, "answer": 3},
    {"id": "q23", "type": "diagram",     "stem": "指令执行的数据通路正确的是?",               "options": 4, "answer": 0},
    {"id": "q24", "type": "comparison",  "stem": "中断与DMA方式的对比正确的是?",              "options": 4, "answer": 1},
    {"id": "q25", "type": "concept",     "stem": "CSMA/CD协议的核心特征是?",                 "options": 4, "answer": 2},
    {"id": "q26", "type": "calculation", "stem": "PV操作后信号量的值是?",                     "options": 4, "answer": 3},
    {"id": "q27", "type": "summary",     "stem": "计算机网络的拓扑结构包括?",                 "options": 4, "answer": 0},
    {"id": "q28", "type": "algorithm",   "stem": "归并排序的时间复杂度是?",                  "options": 4, "answer": 1},
    {"id": "q29", "type": "diagram",     "stem": "虚拟内存页表的结构正确的是?",               "options": 4, "answer": 2},
    {"id": "q30", "type": "comparison",  "stem": "顺序存储与链式存储的对比正确的是?",         "options": 4, "answer": 3},
]


def synthesize_agent_answers(question: dict, rng: random.Random) -> list[dict]:
    """为单题合成 6 个 agent 的作答（答案选项 + 置信度 + 内容）

    专家 agent: 80% 概率答对，置信度 0.80-0.95
    非专家 agent: 45% 概率答对，置信度 0.45-0.70
    """
    qtype = question["type"]
    correct = question["answer"]
    n_options = question["options"]
    experts = set(AGENT_SPECIALTY.get(qtype, ["teacher"]))

    results = []
    for name in AGENT_NAMES:
        is_expert = name in experts
        if is_expert:
            p_correct = 0.80
            conf_lo, conf_hi = 0.80, 0.95
        else:
            p_correct = 0.45
            conf_lo, conf_hi = 0.45, 0.70

        if rng.random() < p_correct:
            ans = correct
        else:
            # 错误答案：从非正确选项中随机选
            wrong = [o for o in range(n_options) if o != correct]
            ans = rng.choice(wrong)

        conf = rng.uniform(conf_lo, conf_hi)
        # 合成简短内容（用于 E5 编码）
        content = f"[{name}] 题目:{question['stem'][:30]}.. 答案选项:{ans} 置信度:{conf:.2f} 专业:{is_expert}"
        # 质量评分（1-10）：专家 7-9，非专家 4-7
        score = (rng.uniform(7.0, 9.0) if is_expert else rng.uniform(4.0, 7.0))
        results.append({
            "agent_name": name,
            "content": content,
            "score": round(score, 2),
            "answer": ans,
            "confidence": round(conf, 3),
        })
    return results


def neural_mixer_aggregate(mixer_net, torch_module, agent_results: list[dict]) -> dict:
    """NeuralMixer 聚合：返回 (final_answer, consensus_score, weighted_scores)

    用 E5 编码 agent content → 喂入 GroupMixerNet → 取 w1_attn 注意力权重最高的 agent 的答案
    （w1_attn 是网络内部学到的 agent 重要性投影，与训练目标一致）
    """
    n = len(agent_results)
    texts = [r["content"][:2000] for r in agent_results]
    embs = np.array(embed_batch(texts), dtype=np.float32)
    scores = np.array([r["score"] for r in agent_results], dtype=np.float32)

    with torch_module.no_grad():
        cs, w1, sd = mixer_net(
            torch_module.from_numpy(scores),
            torch_module.from_numpy(embs),
        )
        # 复用网络内部的 w1_attn 注意力权重（与 forward 中一致）
        w1_attn_weights = mixer_net.w1_attn(w1).squeeze(-1)
        w1_attn_weights = torch_module.softmax(w1_attn_weights, dim=0)

    consensus_score = float(cs.item())
    attn_np = w1_attn_weights.cpu().numpy()
    if attn_np.sum() <= 0:
        attn_np = np.ones(n) / n

    # 用 attention × agent_score 作为最终加权分（与网络 forward 中 weighted_scores 一致）
    final_weights = attn_np * scores
    best_idx = int(np.argmax(final_weights))
    final_answer = agent_results[best_idx]["answer"]

    weighted_scores = {
        r["agent_name"]: float(final_weights[i])
        for i, r in enumerate(agent_results)
    }

    return {
        "final_answer": final_answer,
        "consensus_score": round(consensus_score, 4),
        "weighted_scores": {k: round(v, 4) for k, v in weighted_scores.items()},
        "selected_agent": agent_results[best_idx]["agent_name"],
        "attention_weights": {r["agent_name"]: round(float(attn_np[i]), 4)
                              for i, r in enumerate(agent_results)},
        "sd_loss": round(float(sd.item()), 4),
    }


def weighted_voting_aggregate(agent_results: list[dict]) -> dict:
    """加权投票基线: 用 base_weight * confidence 选 agent"""
    weighted = []
    for r in agent_results:
        bw = BASE_WEIGHTS.get(r["agent_name"], 0.8)
        w = bw * r["confidence"]
        weighted.append((r["agent_name"], w, r["answer"], r["score"]))

    best = max(weighted, key=lambda x: x[1])
    return {
        "final_answer": best[2],
        "consensus_score": round(best[1] * best[3], 4),
        "selected_agent": best[0],
        "weighted_scores": {
            r["agent_name"]: round(BASE_WEIGHTS.get(r["agent_name"], 0.8) * r["confidence"], 4)
            for r in agent_results
        },
    }


def load_neural_mixer_net(embed_dim: int = 768):
    """加载训练后的 GroupMixerNet（768 维与训练权重一致）"""
    from engines.gomarl_mixer import _ensure_torch, GroupMixerNet
    import engines.gomarl_mixer as _gm

    torch, _, _ = _ensure_torch()
    if torch is None or _gm.GroupMixerNet is None:
        raise RuntimeError("PyTorch / GroupMixerNet 不可用")

    net = _gm.GroupMixerNet(n_agents=6, embed_dim=embed_dim, hidden_dim=64)
    weights_path = PROJECT_ROOT / "models" / "neural_mixer_trained.pt"
    if not weights_path.exists():
        raise RuntimeError(f"权重文件不存在: {weights_path}")

    sd = torch.load(str(weights_path), map_location="cpu", weights_only=True)
    model_dict = net.state_dict()
    matched = {k: v for k, v in sd.items()
               if k in model_dict and v.shape == model_dict[k].shape}
    if not matched:
        raise RuntimeError("训练权重与模型结构完全不匹配")
    model_dict.update(matched)
    net.load_state_dict(model_dict)
    net.eval()
    n_matched = len(matched)
    n_total = len(model_dict)
    logger.info(f"NeuralMixer 权重加载: {n_matched}/{n_total} 参数匹配 (embed_dim={embed_dim})")
    return net, torch, n_matched, n_total


def run_experiment2(n_trials: int = 3) -> dict:
    """实验2主流程"""
    logger.info("=== 实验2: NeuralMixer vs 加权投票 ===")

    # 加载 NeuralMixer（768 维与训练权重一致）
    mixer_net, torch, n_matched, n_total = load_neural_mixer_net(embed_dim=768)

    # 预热 embedder
    logger.info("预热嵌入模型...")
    _ = embed_batch(["预热"] * 6)

    rng = random.Random(RANDOM_SEED)

    per_question = []
    neural_answers_all = []   # 跨所有 trial 的 NeuralMixer 答案
    voting_answers_all = []   # 跨所有 trial 的 WeightedVoting 答案
    truth_all = []            # 跨所有 trial 的 ground truth

    for qi, q in enumerate(QUESTIONS):
        truth = q["answer"]
        trials = []
        for t in range(n_trials):
            agents = synthesize_agent_answers(q, rng)

            t0 = time.perf_counter()
            nm = neural_mixer_aggregate(mixer_net, torch, agents)
            nm_lat = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            wv = weighted_voting_aggregate(agents)
            wv_lat = (time.perf_counter() - t0) * 1000

            trials.append({
                "trial": t,
                "neural_mixer": {**nm, "latency_ms": round(nm_lat, 2),
                                 "correct": nm["final_answer"] == truth},
                "weighted_voting": {**wv, "latency_ms": round(wv_lat, 2),
                                    "correct": wv["final_answer"] == truth},
                "ground_truth": truth,
                "agents": [{"agent_name": a["agent_name"], "answer": a["answer"],
                            "confidence": a["confidence"], "score": a["score"]}
                           for a in agents],
            })

            neural_answers_all.append(nm["final_answer"])
            voting_answers_all.append(wv["final_answer"])
            truth_all.append(truth)

        per_question.append({
            "id": q["id"],
            "type": q["type"],
            "stem": q["stem"],
            "ground_truth": truth,
            "trials": trials,
        })

        if (qi + 1) % 10 == 0:
            logger.info(f"  实验2 进度: {qi+1}/{len(QUESTIONS)}")

    # ── 汇总指标 ──
    n_total_obs = len(neural_answers_all)

    # 准确率
    nm_correct = sum(1 for a, t in zip(neural_answers_all, truth_all) if a == t)
    wv_correct = sum(1 for a, t in zip(voting_answers_all, truth_all) if a == t)
    nm_acc = nm_correct / n_total_obs
    wv_acc = wv_correct / n_total_obs

    # Cohen's Kappa
    try:
        kappa_nm_vs_wv = float(cohen_kappa_score(neural_answers_all, voting_answers_all))
    except Exception as e:
        logger.warning(f"Kappa(NM vs WV) 计算失败: {e}")
        kappa_nm_vs_wv = 0.0
    try:
        kappa_nm_vs_truth = float(cohen_kappa_score(neural_answers_all, truth_all))
    except Exception as e:
        logger.warning(f"Kappa(NM vs Truth) 计算失败: {e}")
        kappa_nm_vs_truth = 0.0
    try:
        kappa_wv_vs_truth = float(cohen_kappa_score(voting_answers_all, truth_all))
    except Exception as e:
        logger.warning(f"Kappa(WV vs Truth) 计算失败: {e}")
        kappa_wv_vs_truth = 0.0

    # 延迟
    nm_lats = [tr["neural_mixer"]["latency_ms"] for pq in per_question for tr in pq["trials"]]
    wv_lats = [tr["weighted_voting"]["latency_ms"] for pq in per_question for tr in pq["trials"]]
    nm_consen = [tr["neural_mixer"]["consensus_score"] for pq in per_question for tr in pq["trials"]]
    wv_consen = [tr["weighted_voting"]["consensus_score"] for pq in per_question for tr in pq["trials"]]

    summary = {
        "n_questions": len(QUESTIONS),
        "n_trials_per_question": n_trials,
        "n_observations": n_total_obs,
        "neural_mixer": {
            "accuracy": round(nm_acc, 4),
            "mean_latency_ms": round(mean(nm_lats), 2),
            "median_latency_ms": round(median(nm_lats), 2),
            "mean_consensus_score": round(mean(nm_consen), 4),
            "std_consensus_score": round(
                float(np.std(nm_consen)) if nm_consen else 0.0, 4),
            "weights_matched": f"{n_matched}/{n_total}",
        },
        "weighted_voting": {
            "accuracy": round(wv_acc, 4),
            "mean_latency_ms": round(mean(wv_lats), 2),
            "median_latency_ms": round(median(wv_lats), 2),
            "mean_consensus_score": round(mean(wv_consen), 4),
            "std_consensus_score": round(
                float(np.std(wv_consen)) if wv_consen else 0.0, 4),
        },
        "cohens_kappa": {
            "neural_vs_voting": round(kappa_nm_vs_wv, 4),
            "neural_vs_truth": round(kappa_nm_vs_truth, 4),
            "voting_vs_truth": round(kappa_wv_vs_truth, 4),
        },
        "deltas": {
            "accuracy_delta": round(nm_acc - wv_acc, 4),
            "latency_overhead_ms": round(mean(nm_lats) - mean(wv_lats), 2),
        },
    }

    logger.info(
        f"实验2 完成: NeuralMixer acc={nm_acc:.3f} (voting={wv_acc:.3f}), "
        f"Kappa(NM↔WV)={kappa_nm_vs_wv:.3f}, "
        f"Kappa(NM↔Truth)={kappa_nm_vs_truth:.3f}, "
        f"Kappa(WV↔Truth)={kappa_wv_vs_truth:.3f}"
    )

    return {"per_question": per_question, "summary": summary}


# ============================================================
# 绘图
# ============================================================

def plot_fig_cost(exp1: dict, out_path: Path):
    """实验1: 成本/延迟对比柱状图"""
    s = exp1["summary"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    methods = ["FrugalRAG", "全量检索"]
    colors = ["#2E86AB", "#A23B72"]

    # 子图1: 平均 token
    ax = axes[0]
    tokens = [s["frugalrag"]["mean_tokens"], s["full_retrieval"]["mean_tokens"]]
    bars = ax.bar(methods, tokens, color=colors, width=0.5)
    ax.set_ylabel("平均返回 token 数")
    ax.set_title("检索成本 (token/查询)")
    for b, v in zip(bars, tokens):
        ax.text(b.get_x() + b.get_width() / 2, v + max(tokens) * 0.01,
                f"{v:.0f}", ha="center", va="bottom", fontsize=11)
    ax.grid(axis="y", alpha=0.3)

    # 子图2: 平均延迟
    ax = axes[1]
    lats = [s["frugalrag"]["mean_latency_ms"], s["full_retrieval"]["mean_latency_ms"]]
    bars = ax.bar(methods, lats, color=colors, width=0.5)
    ax.set_ylabel("平均端到端延迟 (ms)")
    ax.set_title("检索延迟 (ms/查询)")
    for b, v in zip(bars, lats):
        ax.text(b.get_x() + b.get_width() / 2, v + max(lats) * 0.01,
                f"{v:.1f}", ha="center", va="bottom", fontsize=11)
    ax.grid(axis="y", alpha=0.3)

    # 子图3: Recall@5 / Precision@5 / MRR
    ax = axes[2]
    metrics = ["Recall@5", "Precision@5", "MRR"]
    fr_vals = [s["frugalrag"]["mean_recall@5"], s["frugalrag"]["mean_precision@5"],
               s["frugalrag"]["mean_mrr"]]
    fu_vals = [s["full_retrieval"]["mean_recall@5"], s["full_retrieval"]["mean_precision@5"],
               s["full_retrieval"]["mean_mrr"]]
    x = np.arange(len(metrics))
    w = 0.35
    ax.bar(x - w / 2, fr_vals, w, label="FrugalRAG", color=colors[0])
    ax.bar(x + w / 2, fu_vals, w, label="全量检索", color=colors[1])
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylabel("指标值")
    ax.set_title("检索质量 (Recall@5 / Precision@5 / MRR)")
    ax.set_ylim(0, 1.05)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    delta = s["deltas"]
    fig.suptitle(
        f"实验1: FrugalRAG vs 全量检索  |  "
        f"token↓{delta['token_reduction_pct']}%  "
        f"延迟↓{delta['latency_reduction_pct']}%  "
        f"Recall@5 Δ={delta['recall_delta']:+.3f}",
        fontsize=12)
    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"图表已保存: {out_path}")


def plot_fig_mixer(exp2: dict, out_path: Path):
    """实验2: NeuralMixer vs 加权投票"""
    s = exp2["summary"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    methods = ["NeuralMixer", "加权投票"]
    colors = ["#2E86AB", "#A23B72"]

    # 子图1: 准确率
    ax = axes[0]
    accs = [s["neural_mixer"]["accuracy"], s["weighted_voting"]["accuracy"]]
    bars = ax.bar(methods, accs, color=colors, width=0.5)
    ax.set_ylabel("Top-1 准确率")
    ax.set_title("聚合准确率 (vs 弱标注)")
    ax.set_ylim(0, 1.05)
    for b, v in zip(bars, accs):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.01,
                f"{v:.3f}", ha="center", va="bottom", fontsize=11)
    ax.grid(axis="y", alpha=0.3)

    # 子图2: Cohen's Kappa
    ax = axes[1]
    kappas = s["cohens_kappa"]
    k_labels = ["NM vs 投票", "NM vs 真值", "投票 vs 真值"]
    k_vals = [kappas["neural_vs_voting"], kappas["neural_vs_truth"],
              kappas["voting_vs_truth"]]
    bars = ax.bar(k_labels, k_vals, color=["#F18F01", "#2E86AB", "#A23B72"], width=0.5)
    ax.set_ylabel("Cohen's Kappa")
    ax.set_title("聚合一致性 (Cohen's Kappa)")
    ax.set_ylim(-0.1, 1.0)
    ax.axhline(y=0.61, color="green", linestyle="--", alpha=0.5, label="实质性一致(0.61)")
    ax.axhline(y=0.41, color="orange", linestyle="--", alpha=0.5, label="中等一致(0.41)")
    for b, v in zip(bars, k_vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.01,
                f"{v:.3f}", ha="center", va="bottom", fontsize=11)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    # 子图3: 延迟
    ax = axes[2]
    nm_lat = s["neural_mixer"]["mean_latency_ms"]
    wv_lat = s["weighted_voting"]["mean_latency_ms"]
    bars = ax.bar(methods, [nm_lat, wv_lat], color=colors, width=0.5)
    ax.set_ylabel("平均聚合延迟 (ms)")
    ax.set_title("聚合延迟 (ms/题)")
    for b, v in zip(bars, [nm_lat, wv_lat]):
        ax.text(b.get_x() + b.get_width() / 2, v + max(nm_lat, wv_lat) * 0.01,
                f"{v:.2f}", ha="center", va="bottom", fontsize=11)
    ax.grid(axis="y", alpha=0.3)

    delta = s["deltas"]
    fig.suptitle(
        f"实验2: NeuralMixer vs 加权投票  |  "
        f"准确率 Δ={delta['accuracy_delta']:+.3f}  "
        f"Kappa(NM vs 投票)={kappas['neural_vs_voting']:.3f}",
        fontsize=12)
    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"图表已保存: {out_path}")


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 70)
    print("MARS-408 Benchmark")
    print("=" * 70)

    # 中文字体（matplotlib 中文支持）
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # 加载查询集
    queries_path = Path(__file__).parent / "queries.json"
    with open(queries_path, "r", encoding="utf-8") as f:
        q_data = json.load(f)
    queries = q_data["queries"]
    print(f"加载查询集: {len(queries)} 条 (来自 {queries_path.name})")

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # ── 实验1 ──
    t0 = time.perf_counter()
    exp1 = run_experiment1(queries)
    exp1_elapsed = time.perf_counter() - t0
    print(f"\n[实验1] 耗时 {exp1_elapsed:.1f}s")
    s1 = exp1["summary"]
    print(f"  FrugalRAG : token={s1['frugalrag']['mean_tokens']:.0f}  "
          f"延迟={s1['frugalrag']['mean_latency_ms']:.1f}ms  "
          f"Recall@5={s1['frugalrag']['mean_recall@5']:.3f}  "
          f"Precision@5={s1['frugalrag']['mean_precision@5']:.3f}  "
          f"MRR={s1['frugalrag']['mean_mrr']:.3f}")
    print(f"  全量检索  : token={s1['full_retrieval']['mean_tokens']:.0f}  "
          f"延迟={s1['full_retrieval']['mean_latency_ms']:.1f}ms  "
          f"Recall@5={s1['full_retrieval']['mean_recall@5']:.3f}  "
          f"Precision@5={s1['full_retrieval']['mean_precision@5']:.3f}  "
          f"MRR={s1['full_retrieval']['mean_mrr']:.3f}")
    d1 = s1["deltas"]
    print(f"  Δ: token↓{d1['token_reduction_pct']}%  "
          f"延迟↓{d1['latency_reduction_pct']}%  "
          f"Recall@5 Δ={d1['recall_delta']:+.3f}  "
          f"Precision@5 Δ={d1['precision_delta']:+.3f}  "
          f"MRR Δ={d1['mrr_delta']:+.3f}")

    # ── 实验2 ──
    t0 = time.perf_counter()
    exp2 = run_experiment2(n_trials=3)
    exp2_elapsed = time.perf_counter() - t0
    print(f"\n[实验2] 耗时 {exp2_elapsed:.1f}s")
    s2 = exp2["summary"]
    print(f"  NeuralMixer: acc={s2['neural_mixer']['accuracy']:.3f}  "
          f"延迟={s2['neural_mixer']['mean_latency_ms']:.2f}ms  "
          f"权重匹配={s2['neural_mixer']['weights_matched']}")
    print(f"  加权投票   : acc={s2['weighted_voting']['accuracy']:.3f}  "
          f"延迟={s2['weighted_voting']['mean_latency_ms']:.2f}ms")
    k = s2["cohens_kappa"]
    print(f"  Cohen's Kappa: NM↔投票={k['neural_vs_voting']:.3f}  "
          f"NM↔真值={k['neural_vs_truth']:.3f}  "
          f"投票↔真值={k['voting_vs_truth']:.3f}")
    d2 = s2["deltas"]
    print(f"  Δ: 准确率 Δ={d2['accuracy_delta']:+.3f}  "
          f"延迟开销={d2['latency_overhead_ms']:.2f}ms")

    # ── 保存 JSON ──
    today = date.today().isoformat()
    json_path = results_dir / f"benchmark_{today}.json"
    output = {
        "meta": {
            "benchmark": "MARS-408",
            "version": "1.0",
            "date": today,
            "top_k": TOP_K,
            "kb_chunks": exp1["summary"]["kb_chunks"],
            "random_seed": RANDOM_SEED,
            "env": {
                "python": sys.version.split()[0],
                "torch": _get_torch_version(),
                "numpy": np.__version__,
            },
        },
        "experiment1": exp1,
        "experiment2": exp2,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[保存] JSON → {json_path}")

    # ── 保存图 ──
    fig_cost_path = results_dir / "fig_cost.png"
    fig_mixer_path = results_dir / "fig_mixer.png"
    plot_fig_cost(exp1, fig_cost_path)
    plot_fig_mixer(exp2, fig_mixer_path)
    print(f"[保存] 图  → {fig_cost_path}")
    print(f"[保存] 图  → {fig_mixer_path}")

    print("\n" + "=" * 70)
    print("Benchmark 完成")
    print("=" * 70)


def _get_torch_version() -> str:
    try:
        import torch
        return torch.__version__
    except Exception:
        return "unavailable"


if __name__ == "__main__":
    main()
