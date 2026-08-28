#!/usr/bin/env python3
"""独立评测 v2 训练模型在 benchmark 实验2 上的 Top-1 准确率。

不修改 benchmark.py / benchmark_exp2_only.py，不触碰锁定权重
models/neural_mixer_trained.pt。仅复用题目集与评测逻辑，验证
"v2 降 loss 是否真实提升准确率"。

用法:
  cd py-server
  HUGGINGFACE_OFFLINE=1 python experiments/eval_v2_model.py models/neural_mixer_v2_tuned_2026-08-17.pt
"""
import sys, time, random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from sklearn.metrics import cohen_kappa_score

# 复用 benchmark 的实验2组件（题目/合成/聚合）
sys.path.insert(0, str(PROJECT_ROOT / "experiments"))
from benchmark import (
    QUESTIONS, AGENT_NAMES, BASE_WEIGHTS, AGENT_SPECIALTY,
    synthesize_agent_answers, neural_mixer_aggregate, weighted_voting_aggregate,
    RANDOM_SEED, mean, median,
)
from db.embedder import embed_batch


def load_model(custom_path: Path):
    """复刻 load_neural_mixer_net 的加载逻辑，但用自定义路径。"""
    from engines.gomarl_mixer import _ensure_torch, GroupMixerNet
    import engines.gomarl_mixer as _gm

    torch, _, _ = _ensure_torch()
    if torch is None or _gm.GroupMixerNet is None:
        raise RuntimeError("PyTorch / GroupMixerNet 不可用")

    net = _gm.GroupMixerNet(n_agents=6, embed_dim=768, hidden_dim=64)
    if not custom_path.exists():
        raise RuntimeError(f"权重文件不存在: {custom_path}")

    sd = torch.load(str(custom_path), map_location="cpu", weights_only=True)
    model_dict = net.state_dict()
    matched = {k: v for k, v in sd.items()
               if k in model_dict and v.shape == model_dict[k].shape}
    if not matched:
        raise RuntimeError("训练权重与模型结构完全不匹配")
    model_dict.update(matched)
    net.load_state_dict(model_dict)
    net.eval()
    logger_info = f"加载 {custom_path.name}: {len(matched)}/{len(model_dict)} 参数匹配"
    return net, torch, len(matched), len(model_dict), logger_info


def evaluate(mixer_net, torch, n_trials=3):
    # 预热
    _ = embed_batch(["预热"] * 6)
    rng = random.Random(RANDOM_SEED)
    neural_answers_all, voting_answers_all, truth_all = [], [], []

    for qi, q in enumerate(QUESTIONS):
        truth = q["answer"]
        for t in range(n_trials):
            agents = synthesize_agent_answers(q, rng)
            nm = neural_mixer_aggregate(mixer_net, torch, agents)
            wv = weighted_voting_aggregate(agents)
            neural_answers_all.append(nm["final_answer"])
            voting_answers_all.append(wv["final_answer"])
            truth_all.append(truth)

    n = len(neural_answers_all)
    nm_acc = sum(1 for a, t in zip(neural_answers_all, truth_all) if a == t) / n
    wv_acc = sum(1 for a, t in zip(voting_answers_all, truth_all) if a == t) / n
    k_nm_wv = float(cohen_kappa_score(neural_answers_all, voting_answers_all))
    k_nm_tr = float(cohen_kappa_score(neural_answers_all, truth_all))
    k_wv_tr = float(cohen_kappa_score(voting_answers_all, truth_all))
    return {
        "nm_acc": nm_acc, "wv_acc": wv_acc,
        "delta_abs": nm_acc - wv_acc,
        "delta_rel": (nm_acc - wv_acc) / wv_acc * 100 if wv_acc > 0 else 0,
        "k_nm_wv": k_nm_wv, "k_nm_tr": k_nm_tr, "k_wv_tr": k_wv_tr,
    }


def main():
    model_arg = sys.argv[1] if len(sys.argv) > 1 else "models/neural_mixer_v2_tuned_2026-08-17.pt"
    custom_path = PROJECT_ROOT / model_arg
    print("=" * 70)
    print(f"独立评测 v2 模型: {custom_path.name}")
    print(f"题目数: {len(QUESTIONS)}, 每题 3 轮, 共 {len(QUESTIONS)*3} 观测")
    print("=" * 70)

    net, torch, n_matched, n_total, info = load_model(custom_path)
    print(info)

    t0 = time.perf_counter()
    r = evaluate(net, torch, n_trials=3)
    elapsed = time.perf_counter() - t0

    print(f"\n耗时 {elapsed:.1f}s")
    print(f"{'='*70}")
    print(f"v2 模型在实验2 上的结果")
    print(f"{'='*70}")
    print(f"NeuralMixer Top-1 : {r['nm_acc']:.4f}")
    print(f"加权投票 Top-1    : {r['wv_acc']:.4f}")
    print(f"绝对提升 (pp)     : +{r['delta_abs']*100:.1f}pp")
    print(f"相对提升 (%)      : +{r['delta_rel']:.1f}%")
    print(f"Kappa(NM↔真值)    : {r['k_nm_tr']:.4f}")
    print(f"Kappa(NM↔投票)    : {r['k_nm_wv']:.4f}")
    print(f"Kappa(投票↔真值)  : {r['k_wv_tr']:.4f}")
    print(f"{'='*70}")
    print(f"\n对照锁定基准 (neural_mixer_trained.pt 7-11版):")
    print(f"  NeuralMixer Top-1 = 0.8333, +6.7pp/+8.7% vs 投票, Kappa=0.776")
    if r['nm_acc'] > 0.8333 + 1e-9:
        print(f"  ✅ v2 准确率高于锁定基准 (+{(r['nm_acc']-0.8333)*100:.1f}pp)")
    else:
        print(f"  ⚠️ v2 准确率未超过锁定基准 (差 {(r['nm_acc']-0.8333)*100:+.1f}pp) — 符合诚实预期(合成标签天花板)")


if __name__ == "__main__":
    main()
