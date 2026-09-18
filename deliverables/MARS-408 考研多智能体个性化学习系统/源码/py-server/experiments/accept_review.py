# -*- coding: utf-8 -*-
"""accept_review — 三元评审权重方案验收卡（单一入口，防口径漂移）

为什么需要它
------------
本项目此前反复吃亏于"数字随配置漂移"与"用欠训练结果下结论"：
  · episodes=200（仅 ~4 次更新）曾得出"RL 不如规则"；
  · episodes=3000（~63 次）得出"打平"；
  · episodes=10000（~208 次）得出"显著超规则但仍不及启发式"；
  · 最终发现**解析式**（`review_policy.analytic_review_action`）在 effective 口径下
    **可达 ≈100% 头寸**（零训练）。
⇒ 每次下结论都必须**同时**报告：(horizon, warmup, episodes, batch) 与参照基线集合。

验收判据（本卡自动判定）
------------------------
  A. **解析式未回归**：analytic 在独立泛化集上的 capture ≥ 95%
     （实测 99.7%；这是当前理论最优，若跌破说明恒等式/接线被破坏）
  B. **学习方案仍需超过规则**：给出 RL 的 capture（--with-rl 时实测；否则只标注参照）
  C. **若任何学习方案 ≥ 解析式** → 报警：说明"解析式是上界"的前提被破坏，必须复查
     （解析式在 effective 口径下是数学最优，不可能被超越；真被超越只会因为
      评估口径/样本生成器与打分函数不一致）

用法
----
  cd py-server && PYTHONPATH=. .venv/Scripts/python.exe experiments/accept_review.py
  （加 --with-rl --episodes 10000 --seeds 7,42,2026 则附带真训 RL 臂，耗时约 10 分钟/seed）
"""

from __future__ import annotations

import argparse
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
    RULE_MODE,
    _rule_action_idx,
    _rule_action_idx_legacy,
    _weights_of,
    analytic_review_action,
    review_state_features,
    review_weight_schema,
)
from run_shadow_probe import generate_samples  # noqa: E402

N = 240
MAIN_SEED = 20260914
GEN_SEED = 313131
NOISE = 0.03
OUT = Path("experiments/results/accept_review.json")


def _contexts(seed: int):
    rng = random.Random(seed)
    samples = generate_samples(N, rng)
    feats = [review_state_features(
        evidence=s["evidence"], critic=s["critic"], consensus=s["consensus"],
        state=s["state"], mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"])
        for s in samples]
    return samples, feats


def _eff(sample, idx: int) -> float:
    return weighted_consistency_score(
        sample["evidence"], sample["consensus"],
        review_weight_schema(_weights_of(idx)))[0]


def _noisy_consensus(consensus: dict, rng: random.Random) -> dict:
    co = dict(consensus)
    for key, lo, hi in (("confidence_score", 0.0, 1.0), ("overall_score", 0.0, 100.0)):
        try:
            v = float(co.get(key))
        except (TypeError, ValueError):
            continue
        span = (hi - lo) * NOISE
        co[key] = max(lo, min(hi, v + rng.uniform(-span, span)))
    return co


def _deterministic_arms(samples, feats, noisy: bool = False):
    """全部确定性臂（含解析式），一律过同一纪律门。"""
    rng = random.Random(4242)
    arms = {"uniform": [], "rule_old": [], "rule_new": [], "analytic": []}
    for s, f in zip(samples, feats):
        co = _noisy_consensus(s["consensus"], rng) if noisy else s["consensus"]
        raw = {
            "rule_old": _rule_action_idx_legacy(f),
            "rule_new": _rule_action_idx(f),
            "analytic": analytic_review_action(s["evidence"], co),
        }
        arms["uniform"].append(_eff(s, 3))
        for k, a in raw.items():
            arms[k].append(_eff(s, discipline_gate(a, f, 0, 0)))
    return arms


def _stats(arms, ref: str = "uniform"):
    base = statistics.mean(arms[ref])
    values = {k: statistics.mean(v) for k, v in arms.items()}
    headroom = values["oracle"] - values["uniform"] if "oracle" in values else None
    return values, base, headroom


def _oracle_values(samples) -> list:
    return [max(_eff(s, a) for a in range(4)) for s in samples]


def _report(tag: str, samples, feats, noisy: bool = False) -> dict:
    arms = _deterministic_arms(samples, feats, noisy=noisy)
    arms["oracle"] = _oracle_values(samples)
    uni = statistics.mean(arms["uniform"])
    ora = statistics.mean(arms["oracle"])
    headroom = ora - uni
    print(f"\n{'=' * 92}")
    print(f"评估集 = {tag}   n={len(samples)}   uniform={uni:.3f}  oracle={ora:.3f}  "
          f"头寸={headroom:+.3f}{'   [观测加噪 ±3%]' if noisy else ''}")
    print(f"{'=' * 92}")
    print(f"{'arm':<10s} {'mean_eff':>9s} {'Δ vs uni':>9s} {'capture':>8s} {'Δ vs rule_new':>14s}")
    out = {"uniform": round(uni, 3), "oracle": round(ora, 3), "headroom": round(headroom, 3), "arms": {}}
    rule_new_m = statistics.mean(arms["rule_new"])
    for name, vals in arms.items():
        m = statistics.mean(vals)
        row = {"mean_eff": round(m, 3),
               "delta_vs_uniform": round(m - uni, 3),
               "capture_pct": round(100 * (m - uni) / headroom, 1),
               "delta_vs_rule_new": round(m - rule_new_m, 3)}
        out["arms"][name] = row
        print(f"{name:<10s} {m:9.3f} {m - uni:+9.3f} {100*(m-uni)/headroom:7.1f}% "
              f"{m - rule_new_m:+14.3f}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-rl", action="store_true", help="附带真训 RL 臂（慢）")
    ap.add_argument("--episodes", type=int, default=10000)
    ap.add_argument("--horizon", type=int, default=32)
    ap.add_argument("--warmup-steps", type=int, default=600)
    ap.add_argument("--seeds", type=str, default="7,42,2026")
    args = ap.parse_args()

    print("=" * 92)
    print("accept_review — 三元评审权重方案验收卡")
    print("=" * 92)
    print(f"RULE_MODE = {RULE_MODE}（analytic = 解析最优档位，零训练；实测占 effective 口径上界）")
    print(f"判据：A) 解析式 capture ≥ 95%（防接线/恒等式回归）；"
          f"B) 学习方案须超过 rule_new；C) 学得比解析式高 → 报警（口径不一致）")

    samples_main, feats_main = _contexts(MAIN_SEED)
    samples_gen, feats_gen = _contexts(GEN_SEED)

    result = {"meta": {"rule_mode": RULE_MODE, "n": N, "main_seed": MAIN_SEED,
                       "gen_seed": GEN_SEED, "noise": NOISE,
                       "episodes": args.episodes if args.with_rl else None,
                       "horizon": args.horizon if args.with_rl else None,
                       "warmup_steps": args.warmup_steps if args.with_rl else None},
              "main": None, "gen": None, "gen_noisy": None, "rl": None, "verdict": {}}

    result["main"] = _report("主评估集（报告同源）", samples_main, feats_main)
    result["gen"] = _report("独立泛化评估集", samples_gen, feats_gen)
    result["gen_noisy"] = _report("独立泛化评估集", samples_gen, feats_gen, noisy=True)

    if args.with_rl:
        from engines.review_shadow_probe import build_shadow_policy
        seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
        print(f"\n{'-' * 92}\nRL 臂：h={args.horizon} wu={args.warmup_steps} "
              f"ep={args.episodes} seeds={seeds}（约 10 分钟/seed，CPU）\n{'-' * 92}")
        rl_val = {}
        for sd in seeds:
            t0 = time.time()
            p = build_shadow_policy(
                sd, warmup_steps=args.warmup_steps, ppo_episodes=args.episodes,
                horizon=args.horizon,
                env_factory=lambda s, hz: CalibratedReviewEnv(seed=s, horizon=hz))
            vals, ref_uni, ref_rule = [], statistics.mean(
                [_eff(s, 3) for s in samples_gen]), None
            rule_vals = []
            for s, f in zip(samples_gen, feats_gen):
                idx, _src = p.select_action(f, deterministic=True, skip_streak=0, reviews_done=0)
                vals.append(_eff(s, discipline_gate(idx, f, 0, 0)))
                rule_vals.append(_eff(s, discipline_gate(_rule_action_idx(f), f, 0, 0)))
            m = statistics.mean(vals)
            ref_rule = statistics.mean(rule_vals)
            rl_val[sd] = {"mean_eff": round(m, 3), "delta_vs_rule_new": round(m - ref_rule, 3),
                          "secs": round(time.time() - t0, 1)}
            print(f"  seed={sd}: mean={m:.3f}  Δ vs rule_new={m - ref_rule:+.3f}  "
                  f"({rl_val[sd]['secs']}s)")
        result["rl"] = rl_val

    # ── 验收判定 ──
    v = {}
    for tag, key in (("主集", "main"), ("泛化集", "gen"), ("泛化集(加噪)", "gen_noisy")):
        v[f"analytic_capture_{key}"] = result[key]["arms"]["analytic"]["capture_pct"]
    v["A_analytic_not_regressed"] = min(
        v["analytic_capture_main"], v["analytic_capture_gen"],
        v["analytic_capture_gen_noisy"]) >= 95.0
    if result["rl"]:
        best_rl = max(x["delta_vs_rule_new"] for x in result["rl"].values())
        v["best_rl_delta_vs_rule_new"] = best_rl
        v["B_rl_beats_rule_new"] = best_rl > 0
        analytic_gen = result["gen"]["arms"]["analytic"]["mean_eff"]
        v["C_rl_not_above_analytic"] = all(
            x["mean_eff"] <= analytic_gen + 1e-9 for x in result["rl"].values())
    v["PASS"] = bool(v["A_analytic_not_regressed"]) and all(
        v.get(k, True) for k in ("B_rl_beats_rule_new", "C_rl_not_above_analytic"))
    result["verdict"] = v

    print(f"\n{'=' * 92}\n验收判定\n{'=' * 92}")
    for k, val in v.items():
        print(f"  {k}: {val}")
    print("\n判读：")
    print("  · A 通过 ⇒ 解析式仍处理论最优位置（effective 口径下的可达上界）；")
    print("  · C 通过 ⇒ 无学习方案超越解析式 ⇒ **部署优先级应为解析式 > RL**；")
    print("  · RL 的价值仅体现在解析式无法使用的场景（字段缺失 / 目标非 effective / 强噪声）。")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已落盘: {OUT}")


if __name__ == "__main__":
    main()
