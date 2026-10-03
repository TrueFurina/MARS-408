"""
verify_mixer_before_after.py — 大创真版「小样本前后测」

目的：证明 train_mixer_real.py 训出来的 GroupMixerNet **真的学到了东西**，
而非随机初始化或退化映射。在「同一组小样本多智能体作答」上对比三种状态：

  - BEFORE (随机初始化 GroupMixerNet，未加载训练权重)  ← 训练前
  - AFTER  (加载 neural_mixer_trained.pt 的训练权重)    ← 训练后
  - RULE   (规则加权投票基线，无神经网络)               ← 朴素对照

指标（全部在 12 道跨四科小样本 × 多 trial 上聚合）：
  - 答案准确率：final_answer == ground_truth 的比例
  - 共识分均值：consensus_score 的均值（训练后应在 [0,10] 且随输入变化，非退化常数）
  - sd_loss 均值：相似度-多样性损失（衡量网络是否捕获 embedding 多样性）
  - 注意力-质量相关性：每样本 attention_weight 与 agent oracle 质量分(score) 的 Pearson，
    平均；训练后若 > 随机，说明网络学到了「给高质量 agent 更高权重」
  - 选中 agent 的平均 oracle 质量：argmax(attention) 对应 agent 的 score 均值

诚实边界：train_mixer_real.py 是弱监督自标注，不保证 QA 准确率超过规则基线；
若准确率持平，则如实报告，并强调「结构感知共识 + 动态组划分」才是训练带来的真实增量。
"""
import os
import sys
import json
import random
import logging
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch
import engines.gomarl_mixer as _gm
from engines.gomarl_mixer import neural_mixer, _ensure_torch

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("before_after")

# ── 与 benchmark.py 一致的 Agent 配置（小样本子集，覆盖 6 题型 / 四科）──
AGENT_NAMES = ["teacher", "quizmaster", "media_designer",
               "extension", "ppt_designer", "code_practice"]
AGENT_SPECIALTY = {
    "concept":     ["teacher", "extension", "ppt_designer"],
    "calculation": ["quizmaster", "teacher"],
    "algorithm":   ["code_practice", "quizmaster"],
    "diagram":     ["media_designer", "teacher"],
    "comparison":  ["extension", "teacher"],
    "summary":     ["ppt_designer", "teacher"],
}
BASE_WEIGHTS = {"teacher": 1.0, "quizmaster": 0.9, "media_designer": 0.85,
                "extension": 0.8, "ppt_designer": 0.8, "code_practice": 0.85}

# 12 道小样本（stem/answer 取自 benchmark.QUESTIONS，保证 ground truth 正确）
QUESTIONS = [
    {"id": "q01", "type": "concept",     "stem": "进程的三种基本状态是?",            "options": 4, "answer": 0},
    {"id": "q02", "type": "concept",     "stem": "下列关于虚拟内存的描述正确的是?",  "options": 4, "answer": 1},
    {"id": "q03", "type": "calculation", "stem": "一个LRU页面置换序列的缺页次数是?", "options": 4, "answer": 2},
    {"id": "q05", "type": "algorithm",   "stem": "快速排序第一趟划分后的结果是?",    "options": 4, "answer": 3},
    {"id": "q08", "type": "diagram",     "stem": "TCP三次握手的状态转换正确的是?",   "options": 4, "answer": 0},
    {"id": "q10", "type": "comparison",   "stem": "栈和队列的本质区别是?",            "options": 4, "answer": 2},
    {"id": "q13", "type": "concept",     "stem": "死锁的四个必要条件是?",            "options": 4, "answer": 1},
    {"id": "q16", "type": "algorithm",   "stem": "哈希表线性探测冲突后的最终位置是?", "options": 4, "answer": 3},
    {"id": "q21", "type": "summary",     "stem": "数据结构中逻辑结构的四大类型是?",  "options": 4, "answer": 2},
    {"id": "q24", "type": "comparison",   "stem": "中断与DMA方式的对比正确的是?",     "options": 4, "answer": 1},
    {"id": "q28", "type": "algorithm",   "stem": "归并排序的时间复杂度是?",          "options": 4, "answer": 1},
    {"id": "q30", "type": "comparison",   "stem": "顺序存储与链式存储的对比正确的是?", "options": 4, "answer": 3},
]


def synthesize_agent_answers(question, rng):
    qtype = question["type"]
    correct = question["answer"]
    n_options = question["options"]
    experts = set(AGENT_SPECIALTY.get(qtype, ["teacher"]))
    results = []
    for name in AGENT_NAMES:
        is_expert = name in experts
        p_correct, (lo, hi) = (0.80, (0.80, 0.95)) if is_expert else (0.45, (0.45, 0.70))
        ans = correct if rng.random() < p_correct else rng.choice(
            [o for o in range(n_options) if o != correct])
        conf = rng.uniform(lo, hi)
        content = f"[{name}] 题目:{question['stem'][:30]}.. 答案选项:{ans} 置信度:{conf:.2f} 专业:{is_expert}"
        score = rng.uniform(7.0, 9.0) if is_expert else rng.uniform(4.0, 7.0)
        results.append({"agent_name": name, "content": content,
                        "score": round(score, 2), "answer": ans, "confidence": round(conf, 3)})
    return results


def embed(texts):
    return np.asarray(neural_mixer.encoder.encode_batch(texts), dtype=np.float32)


def neural_mixer_aggregate(net, agent_results):
    n = len(agent_results)
    texts = [r["content"][:2000] for r in agent_results]
    embs = embed(texts)
    scores = np.array([r["score"] for r in agent_results], dtype=np.float32)
    with torch.no_grad():
        cs, w1, sd = net(torch.from_numpy(scores), torch.from_numpy(embs))
        attn = net.w1_attn(w1).squeeze(-1)
        attn = torch.softmax(attn, dim=0)
    consensus_score = float(cs.item())
    attn_np = attn.cpu().numpy()
    if attn_np.sum() <= 0:
        attn_np = np.ones(n) / n
    final_weights = attn_np * scores
    best_idx = int(np.argmax(final_weights))
    attention = {r["agent_name"]: float(attn_np[i]) for i, r in enumerate(agent_results)}
    return {
        "final_answer": agent_results[best_idx]["answer"],
        "consensus_score": consensus_score,
        "sd_loss": float(sd.item()),
        "attention": attention,
        "selected_agent": agent_results[best_idx]["agent_name"],
    }


def weighted_voting_aggregate(agent_results):
    best = max(agent_results, key=lambda r: BASE_WEIGHTS.get(r["agent_name"], 0.8) * r["confidence"])
    return {"final_answer": best["answer"], "selected_agent": best["agent_name"]}


def build_trained_net():
    GroupMixerNet = _gm.GroupMixerNet
    net = GroupMixerNet(n_agents=6, embed_dim=768, hidden_dim=64)
    wpath = PROJECT_ROOT / "models" / "neural_mixer_trained.pt"
    sd = torch.load(str(wpath), map_location="cpu", weights_only=True)
    md = net.state_dict()
    matched = {k: v for k, v in sd.items() if k in md and v.shape == md[k].shape}
    md.update(matched)
    net.load_state_dict(md)
    net.eval()
    return net, len(matched), len(md)


def build_random_net():
    GroupMixerNet = _gm.GroupMixerNet
    net = GroupMixerNet(n_agents=6, embed_dim=768, hidden_dim=64)
    net.eval()
    return net


def pearson(x, y):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def main():
    _ensure_torch()
    net_after, n_match, n_total = build_trained_net()
    net_before = build_random_net()
    print(f"[i] 训练权重匹配: {n_match}/{n_total}")
    print(f"[i] 预热 E5 编码器...")
    _ = embed(["warmup"] * 6)

    rng = random.Random(20260903)
    N_TRIALS = 8

    acc_b = acc_a = acc_r = 0
    n_total_samples = 0
    cons_b, cons_a, sd_b, sd_a = [], [], [], []
    corr_b, corr_a = [], []
    selq_b, selq_a = [], []  # 选中 agent 的平均 oracle 质量

    per_question = []
    for q in QUESTIONS:
        truth = q["answer"]
        for t in range(N_TRIALS):
            agents = synthesize_agent_answers(q, rng)
            scores = [a["score"] for a in agents]

            before = neural_mixer_aggregate(net_before, agents)
            after = neural_mixer_aggregate(net_after, agents)
            wv = weighted_voting_aggregate(agents)

            acc_b += (before["final_answer"] == truth)
            acc_a += (after["final_answer"] == truth)
            acc_r += (wv["final_answer"] == truth)
            n_total_samples += 1

            cons_b.append(before["consensus_score"])
            cons_a.append(after["consensus_score"])
            sd_b.append(before["sd_loss"])
            sd_a.append(after["sd_loss"])

            cb = pearson(list(before["attention"].values()), scores)
            ca = pearson(list(after["attention"].values()), scores)
            if cb is not None: corr_b.append(cb)
            if ca is not None: corr_a.append(ca)

            # 选中 agent 的 oracle 质量
            sb = before["attention"]
            sa = after["attention"]
            selq_b.append(scores[agents.index(next(a for a in agents if a["agent_name"] == before["selected_agent"]))])
            selq_a.append(scores[agents.index(next(a for a in agents if a["agent_name"] == after["selected_agent"]))])

        per_question.append({"id": q["id"], "type": q["type"], "stem": q["stem"], "answer": truth})

    def pct(x): return round(100.0 * x / n_total_samples, 2)

    summary = {
        "n_questions": len(QUESTIONS),
        "n_trials_per_q": N_TRIALS,
        "n_samples": n_total_samples,
        "accuracy_before_random": pct(acc_b),
        "accuracy_after_trained": pct(acc_a),
        "accuracy_rule_weighted_voting": pct(acc_r),
        "mean_consensus_before": round(float(np.mean(cons_b)), 4),
        "mean_consensus_after": round(float(np.mean(cons_a)), 4),
        "std_consensus_before": round(float(np.std(cons_b)), 4),
        "std_consensus_after": round(float(np.std(cons_a)), 4),
        "mean_sd_loss_before": round(float(np.mean(sd_b)), 4),
        "mean_sd_loss_after": round(float(np.mean(sd_a)), 4),
        "mean_attn_quality_pearson_before": round(float(np.mean(corr_b)), 4),
        "mean_attn_quality_pearson_after": round(float(np.mean(corr_a)), 4),
        "mean_selected_agent_quality_before": round(float(np.mean(selq_b)), 4),
        "mean_selected_agent_quality_after": round(float(np.mean(selq_a)), 4),
        "weights_matched": f"{n_match}/{n_total}",
    }

    out = {
        "generated_at": "2026-09-03",
        "experiment": "mixer_before_after (random-init vs trained vs rule)",
        "summary": summary,
        "per_question": per_question,
    }
    out_path = PROJECT_ROOT / "experiments" / "results" / "mixer_before_after_2026-09-03.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("\n=== 小样本前后测结果 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\n[落盘] {out_path}")
    return summary


if __name__ == "__main__":
    main()
