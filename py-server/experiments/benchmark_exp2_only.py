#!/usr/bin/env python3
"""只跑 benchmark 实验2: NeuralMixer vs 加权投票（不依赖向量库）

验证申报书数字可复现:
  - NeuralMixer Top-1 vs 加权投票 Top-1 (期望 +6.7pp 绝对 / +8.7% 相对)
  - Kappa(NM↔真值) (期望 0.776)

用法: cd py-server && HUGGINGFACE_OFFLINE=1 python experiments/benchmark_exp2_only.py
"""
import sys, json, logging, time, random
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from sklearn.metrics import cohen_kappa_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("benchmark_exp2")

# 复用 benchmark.py 的实验2组件
sys.path.insert(0, str(Path(__file__).parent))
from benchmark import (
    run_experiment2, QUESTIONS, AGENT_NAMES, BASE_WEIGHTS, AGENT_SPECIALTY,
    synthesize_agent_answers, neural_mixer_aggregate, weighted_voting_aggregate,
    load_neural_mixer_net, RANDOM_SEED, mean, median,
)
from db.embedder import embed_batch


def main():
    print("=" * 70)
    print("MARS-408 Benchmark — 实验2 only (NeuralMixer vs 加权投票)")
    print("=" * 70)
    print(f"题目数: {len(QUESTIONS)}, 每题 3 轮 trial, 共 {len(QUESTIONS)*3} 观测")
    print(f"权重文件: models/neural_mixer_trained.pt")
    print()

    t0 = time.perf_counter()
    exp2 = run_experiment2(n_trials=3)
    elapsed = time.perf_counter() - t0
    print(f"\n[实验2] 耗时 {elapsed:.1f}s")

    s = exp2["summary"]
    nm_acc = s["neural_mixer"]["accuracy"]
    wv_acc = s["weighted_voting"]["accuracy"]
    delta_abs = nm_acc - wv_acc  # 绝对提升 pp
    delta_rel = (nm_acc - wv_acc) / wv_acc * 100 if wv_acc > 0 else 0  # 相对提升 %
    k = s["cohens_kappa"]

    print(f"\n{'='*70}")
    print(f"核心指标对比 (申报书数字 vs 本次复现)")
    print(f"{'='*70}")
    print(f"{'指标':<28}{'申报书':<16}{'本次复现':<16}{'是否吻合'}")
    print(f"{'-'*70}")
    print(f"{'NeuralMixer Top-1':<28}{'0.8333':<16}{nm_acc:<16.4f}{'✅' if abs(nm_acc-0.8333)<0.05 else '⚠️'}")
    print(f"{'加权投票 Top-1':<28}{'0.7667':<16}{wv_acc:<16.4f}{'✅' if abs(wv_acc-0.7667)<0.05 else '⚠️'}")
    print(f"{'绝对提升 (pp)':<28}{'+6.7pp':<16}{f'+{delta_abs*100:.1f}pp':<16}{'✅' if abs(delta_abs-0.067)<0.03 else '⚠️'}")
    print(f"{'相对提升 (%)':<28}{'+8.7%':<16}{f'+{delta_rel:.1f}%':<16}{'✅' if abs(delta_rel-8.7)<3 else '⚠️'}")
    print(f"{'Kappa(NM↔真值)':<28}{'0.776':<16}{k['neural_vs_truth']:<16.4f}{'✅' if abs(k['neural_vs_truth']-0.776)<0.1 else '⚠️'}")
    print(f"{'Kappa(NM↔投票)':<28}{'—':<16}{k['neural_vs_voting']:<16.4f}{'—'}")
    print(f"{'Kappa(投票↔真值)':<28}{'—':<16}{k['voting_vs_truth']:<16.4f}{'—'}")
    print(f"{'权重匹配':<28}{'—':<16}{s['neural_mixer']['weights_matched']:<16}{'—'}")
    print(f"{'='*70}")

    # 保存 JSON
    results_dir = PROJECT_ROOT / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    json_path = results_dir / f"benchmark_exp2_reproduce_{today}.json"
    output = {
        "meta": {
            "benchmark": "MARS-408 exp2 only",
            "date": today,
            "random_seed": RANDOM_SEED,
            "n_questions": len(QUESTIONS),
            "n_trials": 3,
            "n_observations": len(QUESTIONS) * 3,
            "weights_file": "models/neural_mixer_trained.pt",
            "weights_matched": s["neural_mixer"]["weights_matched"],
        },
        "summary": s,
        "reproduce_check": {
            "申报书_NeuralMixer_Top1": 0.8333,
            "本次_NeuralMixer_Top1": nm_acc,
            "申报书_加权投票_Top1": 0.7667,
            "本次_加权投票_Top1": wv_acc,
            "申报书_绝对提升_pp": 6.7,
            "本次_绝对提升_pp": round(delta_abs * 100, 1),
            "申报书_相对提升_pct": 8.7,
            "本次_相对提升_pct": round(delta_rel, 1),
            "申报书_Kappa_NM_真值": 0.776,
            "本次_Kappa_NM_真值": k["neural_vs_truth"],
        },
        "per_question": exp2["per_question"],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[保存] JSON → {json_path}")

    # 诚实声明
    print(f"\n{'='*70}")
    print("诚实声明")
    print(f"{'='*70}")
    print("1. 本实验使用合成弱标注集(30题×3轮, 专家80%/非专家45%正确率)")
    print("2. NeuralMixer 权重为 7-11 旧版(首轮8-15真训因文件锁未保存成功)")
    print("3. 数字可复现性取决于随机种子(RANDOM_SEED=20260719)与权重文件")
    print("4. Track B-G1 真实标注集训练后, 数字应以真训结果为准")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
