# -*- coding: utf-8 -*-
"""diag_rule_upgrade — 把解析阈值 f2≈0.675 折进生产规则的**候选方案实测**

背景
----
报告 `docs/三元评审权重MAPPO-环境根因与真实效果报告-2026-09-14.md` 建议 1：
**优先把解析阈值折进规则**（零训练、可审计、与 RL 同级）。但"折法"有多种，
本脚本在**采纳前**用同一口径实测选定 —— 避免"未验证就改生产"。

口径（与报告严格一致）
--------------------
  - 240 条真实形态上下文：`generate_samples(240, Random(20260914))`（报告同一集合）。
  - 有效分由生产 `weighted_consistency_score` 复算；**全臂经模块级 `discipline_gate`**
    （单一真值源，见 review_policy.discipline_gate）。
  - 判据：逐样本配对 t（vs 现行规则）+ 捕获率（相对 oracle 头寸）。

候选（**待选实验实现**；2026-09-14 已采纳 B_binary 折进生产，见
`review_policy.RULE_EVIDENCE_HONEST` / `RULE_F2_BINARY`；本脚本保留为采纳证据）
  uniform   : 三端等权（现状基线）
  rule_old  : 原级联 `_rule_action_idx_legacy`（consistency ≥ 0.6 一票定 honest）
  rule_new  : **已折进阈值的生产默认** `_rule_action_idx`
  A_thr675  : 原级联，**仅**把证据门槛 0.6 → 0.675（最小侵入 —— 实测被否证）
  B_binary  : 纯二分支 f2 > 0.675 → honest，否则 consensus（**已采纳**）
  C_three   : f2 > 0.675 → honest；elif 批评信噪比高 → critic；否则 consensus
  D_band    : 同 C，但 critic 支路仅在 f2 ∈ [0.60, 0.675) 启用（"证据够但不够强"区）
  oracle    : 全信息上界（不动）

只读：本脚本不改任何产品代码，只落盘一份对比 JSON。
用法：cd py-server && PYTHONPATH=. .venv/Scripts/python.exe experiments/diag_rule_upgrade.py
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.quality_gate import weighted_consistency_score  # noqa: E402
from engines.review_env_calibrated import discipline_gate  # noqa: E402
from engines.review_policy import (  # noqa: E402
    REVIEW_ACTIONS,
    _rule_action_idx,
    _rule_action_idx_legacy,
    _weights_of,
    review_state_features,
    review_weight_schema,
)
from run_shadow_probe import generate_samples  # noqa: E402

N = 240
DATA_SEED = 20260914
GEN_SEED = 313131
THR = 0.675          # 解析推导（Δ_eff 期望交点 s_h≈67.5 分），非在评估集上拟合
BAND_LO = 0.60       # 现行门槛，作为"证据够但不够强"区下沿
OUT = Path("experiments/results/diag_rule_upgrade.json")


# ────────────────────────────────────────────────────────────
# 候选实现（待选；选定后迁入生产并删除此处）
# ────────────────────────────────────────────────────────────

def cand_A_thr675(f: list) -> int:
    """现行级联，仅把证据门槛 0.6 → 0.675。"""
    if not f or len(f) < 12:
        return 3
    consistency, status, disagree = f[1], f[3], f[5]
    valid_c, invalid_c = f[6], f[7]
    cost_ratio = f[9]
    if consistency >= 0.75 and cost_ratio >= 0.6:
        return 4
    if consistency >= THR:
        return 0
    if (valid_c - invalid_c) >= 0.25:
        return 1
    if status <= 0.1 and disagree <= 0.35:
        return 2
    return 3


def cand_B_binary(f: list) -> int:
    """纯二分支：f2 > 0.675 → honest，否则 consensus。"""
    if not f or len(f) < 2:
        return 3
    return 0 if f[1] > THR else 2


def cand_C_three(f: list) -> int:
    """三段：f2>thr → honest；elif 批评信噪比高 → critic；否则 consensus。"""
    if not f or len(f) < 8:
        return 3
    if f[1] > THR:
        return 0
    if (f[6] - f[7]) >= 0.25:
        return 1
    return 2


def cand_D_band(f: list) -> int:
    """三段但 critic 支路限带：f2 ∈ [0.60, 0.675) 才允许 critic。"""
    if not f or len(f) < 8:
        return 3
    if f[1] > THR:
        return 0
    if BAND_LO <= f[1] and (f[6] - f[7]) >= 0.25:
        return 1
    return 2


CANDIDATES = {
    "A_thr675": cand_A_thr675,
    "B_binary": cand_B_binary,
    "C_three": cand_C_three,
    "D_band": cand_D_band,
}


# ────────────────────────────────────────────────────────────
# 评估
# ────────────────────────────────────────────────────────────

def _contexts(seed: int):
    rng = random.Random(seed)
    samples = generate_samples(N, rng)
    feats = [
        review_state_features(
            evidence=s["evidence"], critic=s["critic"], consensus=s["consensus"],
            state=s["state"], mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"],
        )
        for s in samples
    ]
    return samples, feats


def _eff(sample, idx: int) -> float:
    return weighted_consistency_score(
        sample["evidence"], sample["consensus"],
        review_weight_schema(_weights_of(idx)))[0]


def _oracle_idx(sample) -> int:
    """纪律门下的真实最优动作（skip 在评测口径被禁，故只在 0..3 中取）。"""
    cands = [(_eff(sample, a), a) for a in range(4)]
    return max(cands)[1]


def _gated(f, idx: int) -> int:
    """全臂统一过生产纪律门（单一真值源）。评测口径 reviews_done=0 ⇒ 恒禁 skip。"""
    return discipline_gate(idx, f, 0, 0)


def evaluate(seed: int) -> dict:
    samples, feats = _contexts(seed)

    arms = {name: [] for name in ("uniform", "rule_old", "rule_new", "oracle", *CANDIDATES)}
    act_dist = {name: Counter() for name in ("rule_old", "rule_new", *CANDIDATES)}

    for s, f in zip(samples, feats):
        arms["uniform"].append(_eff(s, 3))
        for name, fn in (("rule_old", _rule_action_idx_legacy),
                         ("rule_new", _rule_action_idx), *CANDIDATES.items()):
            idx = _gated(f, fn(f))
            arms[name].append(_eff(s, idx))
            act_dist[name][idx] += 1
        arms["oracle"].append(_eff(s, _oracle_idx(s)))

    uni = statistics.mean(arms["uniform"])
    ora = statistics.mean(arms["oracle"])
    headroom = ora - uni
    rule_old = statistics.mean(arms["rule_old"])

    out = {
        "seed": seed,
        "n": N,
        "headroom": round(headroom, 3),
        "arms": {},
    }
    for name in ("uniform", "rule_old", "rule_new", *CANDIDATES, "oracle"):
        vals = arms[name]
        d_rule = [x - y for x, y in zip(vals, arms["rule_old"])]
        mr = statistics.mean(d_rule)
        sr = statistics.pstdev(d_rule)
        tr = mr / (sr / len(d_rule) ** 0.5) if sr > 0 else float("inf")
        out["arms"][name] = {
            "mean_eff": round(statistics.mean(vals), 3),
            "delta_vs_uniform": round(statistics.mean(vals) - uni, 3),
            "capture_pct": round(100 * (statistics.mean(vals) - uni) / headroom, 1),
            "delta_vs_rule_old": round(mr, 3),
            "t_vs_rule_old": round(tr, 2),
            "pct_improve_vs_rule_old": round(
                100 * sum(1 for x in d_rule if x > 0) / len(d_rule), 1),
        }
        if name in act_dist:
            out["arms"][name]["action_dist"] = {
                REVIEW_ACTIONS[k]: v for k, v in sorted(act_dist[name].items())}
    return out


def _report(tag: str, res: dict) -> None:
    print(f"\n{'=' * 96}")
    print(f"评估集 = {tag} (seed={res['seed']}, n={res['n']})   "
          f"oracle 头寸 = {res['headroom']:+.3f}")
    print(f"{'=' * 96}")
    print(f"{'arm':<10s} {'mean_eff':>9s} {'Δ vs uni':>9s} {'capture':>8s} "
          f"{'Δ vs rule':>10s} {'t':>7s} {'改善样本%':>9s}")
    for name, a in res["arms"].items():
        print(f"{name:<10s} {a['mean_eff']:9.3f} {a['delta_vs_uniform']:+9.3f} "
              f"{a['capture_pct']:7.1f}% {a['delta_vs_rule_old']:+10.3f} "
              f"{a['t_vs_rule_old']:+7.2f} {a['pct_improve_vs_rule_old']:8.1f}%")
    print("\n动作分布（候选 vs 现行规则）:")
    for name in ("rule_old", "rule_new", *CANDIDATES):
        if "action_dist" in res["arms"][name]:
            print(f"  {name:<10s} {res['arms'][name]['action_dist']}")


def main() -> None:
    print("=" * 96)
    print("diag_rule_upgrade — 解析阈值折进规则：候选方案实测（采纳前把关）")
    print("=" * 96)
    print(f"阈值 THR={THR}（解析推导，非拟合）；全臂过同一纪律门 discipline_gate；"
          f"reviews_done=0 ⇒ skip 恒被禁。")

    results = {"meta": {"threshold": THR, "band_lo": BAND_LO,
                        "main_seed": DATA_SEED, "gen_seed": GEN_SEED, "n": N},
               "main": None, "gen": None}

    r_main = evaluate(DATA_SEED)
    _report("主评估集（报告同源）", r_main)
    results["main"] = r_main

    r_gen = evaluate(GEN_SEED)
    _report("独立泛化评估集（防过拟合）", r_gen)
    results["gen"] = r_gen

    print(f"\n{'=' * 96}")
    print("判读要点")
    print(f"{'=' * 96}")
    for tag, r in (("主集", r_main), ("泛化", r_gen)):
        ranked = sorted(CANDIDATES,
                        key=lambda k: -r["arms"][k]["mean_eff"])
        best = ranked[0]
        b = r["arms"][best]
        print(f"  [{tag}] 最优候选 = {best}  mean={b['mean_eff']:.3f}  "
              f"Δrule={b['delta_vs_rule_old']:+.3f} (t={b['t_vs_rule_old']:+.2f})  "
              f"capture={b['capture_pct']:.1f}%")
    print("  两集同时最优且 Δrule 显著为正的候选才可采纳（单集最优可能是过拟合）。")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已落盘: {OUT}")


if __name__ == "__main__":
    main()
