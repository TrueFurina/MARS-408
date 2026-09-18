# -*- coding: utf-8 -*-
"""tune_shadow_budget — 校准环境训练预算横扫（评估基准严格对齐影子探针的真实上下文）

为什么需要这个脚本
------------------
`diag_calib_alignment.py` 的 R3 诊断出：校准环境的 RL 在**低证据自评区（f2 ≤ 0.675）**
有 49/121 次退回 `balanced`（该动作真实增益恒为 0）——即"**学到了方向、未学到锐度**"。
同一诊断已排除两个替代解释：

  1. 奖励设计错位？→ 已排除。env 内 reward-argmax 与 quality-argmax 精确一致率 98.5%，
     不一致的 6 例 quality 损失为 0（并列）。token 成本项（REWARD_W["cost"]=0.15）不构成偏置。
  2. 状态可观测性不足？→ 部分成立（s_c/s_k 不在状态内），但单特征阈值已能吃到 60% 头寸，
     故当前 49.7% 的差距**主要是优化问题**，不是信息上限。

⇒ 本脚本只在**优化维度**上横扫，回答"给定同一环境与同一信息，训练能不能把锐度练出来"。

评估基准（与报告完全一致，避免口径漂移）
------------------------------------------
  - 主评估集：`generate_samples(240, Random(20260914))` —— 影子探针与报告的同一 240 条真实形态上下文。
  - 泛化评估集：`generate_samples(240, Random(<另一 seed>))` —— 防"扫到主评估集上过拟合的配置"。
  - 捕获率 capture = (mean_eff(policy) − mean_eff(uniform)) / (mean_eff(oracle) − mean_eff(uniform))。
  - 参照臂：rule（已过纪律门）、heuristic_f2（解析阈值，无拟合）在**同一集合**上实算。

只读：本脚本不改任何产品代码，只训练影子策略并落盘一份配置对比 JSON。
用法：cd py-server && PYTHONPATH=. .venv/Scripts/python.exe experiments/tune_shadow_budget.py
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.quality_gate import weighted_consistency_score  # noqa: E402
from engines.review_env_calibrated import CalibratedReviewEnv, discipline_gate  # noqa: E402
from engines.review_policy import (  # noqa: E402
    UNIFORM_WEIGHTS,
    _rule_action_idx,
    _weights_of,
    review_state_features,
    review_weight_schema,
)
from engines.review_shadow_probe import (  # noqa: E402
    build_shadow_policy,
    heuristic_action_idx,
)
from run_shadow_probe import generate_samples  # noqa: E402

MAIN_SEED = 20260914          # 与报告/探针同一评估集
GEN_SEED = 313131             # 独立泛化评估集
N_EVAL = 240
OUT = Path("experiments/results/tune_shadow_budget.json")


def _contexts(seed: int):
    rng = random.Random(seed)
    samples = generate_samples(N_EVAL, rng)
    feats = [
        review_state_features(
            evidence=s["evidence"], critic=s["critic"], consensus=s["consensus"],
            state=s["state"], mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"],
        )
        for s in samples
    ]
    return samples, feats


def _eff(sample, idx: int) -> float:
    return weighted_consistency_score(sample["evidence"], sample["consensus"],
                                      review_weight_schema(_weights_of(idx)))[0]


def _baselines(samples, feats) -> dict:
    uni = [_eff(s, 3) for s in samples]
    m_uni = statistics.mean(uni)
    orc = [max(_eff(s, a) for a in range(4)) for s in samples]
    m_orc = statistics.mean(orc)
    rule = [_eff(s, discipline_gate(_rule_action_idx(f), f, 0, 0))
            for s, f in zip(samples, feats)]
    heur = [_eff(s, heuristic_action_idx(f)) for s, f in zip(samples, feats)]
    return {"uniform": m_uni, "oracle": m_orc, "headroom": m_orc - m_uni,
            "rule": statistics.mean(rule), "heuristic_f2": statistics.mean(heur),
            "rule_capture_pct": round(100 * (statistics.mean(rule) - m_uni) / (m_orc - m_uni), 1),
            "heuristic_capture_pct": round(100 * (statistics.mean(heur) - m_uni) / (m_orc - m_uni), 1)}


def _evaluate(policy, samples, feats, m_uni, headroom):
    effs, bal_low, low_n = [], 0, 0
    for s, f in zip(samples, feats):
        idx, _src = policy.select_action(f, deterministic=True, skip_streak=0, reviews_done=0)
        idx = discipline_gate(idx, f, 0, 0)
        effs.append(_eff(s, idx))
        if f[1] <= 0.675:
            low_n += 1
            bal_low += (idx == 3)
    m = statistics.mean(effs)
    return {"mean_eff": round(m, 3), "delta_vs_uniform": round(m - m_uni, 3),
            "capture_pct": round(100 * (m - m_uni) / headroom, 1),
            "balanced_retreat_low_f2_pct": round(100 * bal_low / max(1, low_n), 1)}


def main() -> None:
    main_samples, main_feats = _contexts(MAIN_SEED)
    gen_samples, gen_feats = _contexts(GEN_SEED)
    b_main = _baselines(main_samples, main_feats)
    b_gen = _baselines(gen_samples, gen_feats)

    print("=" * 92)
    print("tune_shadow_budget —— 校准环境训练预算横扫（评估=真实上下文，与报告同口径）")
    print("=" * 92)
    for tag, b in (("主评估集(seed=%d)" % MAIN_SEED, b_main), ("泛化集(seed=%d)" % GEN_SEED, b_gen)):
        print(f"[{tag}] uniform={b['uniform']:.3f} oracle={b['oracle']:.3f} 头寸={b['headroom']:+.3f} | "
              f"rule={b['rule']:.3f}({b['rule_capture_pct']}%) "
              f"heuristic_f2={b['heuristic_f2']:.3f}({b['heuristic_capture_pct']}%)")

    # 横扫配置：(名称, horizon, episodes, warmup, lr, epochs, batch)
    # horizon=1 表示"纯上下文赌博机"（本问题本质是 contextual bandit，
    # 每步上下文独立重采样 ⇒ 32 步 episode 只引入 GAE 偏差与方差）。
    configs = [
        ("hz=1  ep=3000  wu=600 lr=3e-4 e4", 1, 3000, 600, 3e-4, 4, 0),
        ("hz=1  ep=10000 wu=600 lr=3e-4 e4", 1, 10000, 600, 3e-4, 4, 0),
        ("hz=1  ep=10000 wu=600 lr=1e-3 e4", 1, 10000, 600, 1e-3, 4, 0),
        ("hz=8  ep=10000 wu=600 lr=3e-4 e4", 8, 10000, 600, 3e-4, 4, 0),
        ("hz=32 ep=10000 wu=600 lr=3e-4 e4", 32, 10000, 600, 3e-4, 4, 0),
        ("hz=32 ep=3000  wu=600 lr=3e-4 e8", 32, 3000, 600, 3e-4, 8, 0),
        ("hz=1  ep=3000  wu=600 lr=3e-4 e4 b128", 1, 3000, 600, 3e-4, 4, 128),
        ("hz=32 ep=10000 wu=600 lr=1e-3 e8", 32, 10000, 600, 1e-3, 8, 0),
    ]

    rows = []
    for name, hz, ep, wu, lr, epo, batch in configs:
        t0 = time.time()
        p = build_shadow_policy(7, warmup_steps=wu, ppo_episodes=ep, horizon=hz,
                                env_factory=lambda sd, h: CalibratedReviewEnv(seed=sd, horizon=h),
                                lr=lr, epochs=epo, batch_episodes=(batch or None))
        ev_main = _evaluate(p, main_samples, main_feats, b_main["uniform"], b_main["headroom"])
        ev_gen = _evaluate(p, gen_samples, gen_feats, b_gen["uniform"], b_gen["headroom"])
        row = {"config": name, "horizon": hz, "episodes": ep, "warmup": wu, "lr": lr,
               "epochs": epo, "batch_episodes": batch or "auto",
               "main": ev_main, "gen": ev_gen, "seconds": round(time.time() - t0, 1)}
        rows.append(row)
        print(f"  {name:<38s} main: eff={ev_main['mean_eff']:.3f} "
              f"Δ={ev_main['delta_vs_uniform']:+.3f} cap={ev_main['capture_pct']:5.1f}% "
              f"躺平率={ev_main['balanced_retreat_low_f2_pct']:5.1f}% | "
              f"gen: cap={ev_gen['capture_pct']:5.1f}% | {row['seconds']:.0f}s")

    rows.sort(key=lambda r: -r["main"]["capture_pct"])
    print("\n按主评估集捕获率排序：")
    for r in rows:
        print(f"  {r['config']:<38s} main={r['main']['capture_pct']:5.1f}%  "
              f"gen={r['gen']['capture_pct']:5.1f}%  "
              f"躺平率={r['main']['balanced_retreat_low_f2_pct']:5.1f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({
            "meta": {
                "source": "tune_shadow_budget.py (read-only; 只训练影子策略)",
                "eval_main_seed": MAIN_SEED, "eval_gen_seed": GEN_SEED, "n_eval": N_EVAL,
                "note": "捕获率 = (策略−uniform)/(oracle−uniform)；躺平率 = 低 f2 区选 balanced 的占比。"
                        "参照线：rule/heuristic_f2 的捕获率见 baselines。",
            },
            "baselines": {"main": b_main, "gen": b_gen},
            "rows": rows,
        }, fh, ensure_ascii=False, indent=2)
    print(f"\n落盘：{OUT}")
    print(f"参照线：主评估集 rule={b_main['rule_capture_pct']}%  "
          f"heuristic_f2={b_main['heuristic_capture_pct']}%")
    print("判读：只有 main 与 gen 双高（且 > heuristic 参照线）的配置才是真改善；"
          "main 高 gen 低 = 过拟合到主评估集。")


if __name__ == "__main__":
    main()
