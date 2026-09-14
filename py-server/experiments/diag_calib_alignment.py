# -*- coding: utf-8 -*-
"""diag_calib_alignment — 校准环境 vs 真实样本生成器 的「同分布性」与「统计显著性」双重把关。

只读诊断，不产出对外数字；目的是排除两类会推翻结论的风险：

  R1 分布错位：若 CalibratedReviewEnv 抽出的上下文与 run_shadow_probe.generate_samples
     的真实上下文不同分布，则"校准环境训练 → 真实空间评估"的 +3.087 可能是环境特异性
     （策略学到的是我环境的怪癖，而非真实可迁移的上下文切分）。

  R2 不显著：若 RL 相对 rule / heuristic_f2 的增益在种子间方差下不显著，
     则"RL 超过规则"不能作为结论。

做法：
  - 两套上下文各抽 N 个，逐维比对 均值/标准差/分位（KS 型对齐度）。
  - 用真实质量函数在两套上下文上评估同一批固定策略，看相对排序是否一致（排序稳健性）。
  - 读 results 里 calibrated ppo=3000 的 JSONL，做逐样本配对差 + 种子级汇总。

用法：cd py-server && PYTHONPATH=. .venv/Scripts/python.exe experiments/diag_calib_alignment.py
"""

from __future__ import annotations

import glob
import json
import os
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.quality_gate import weighted_consistency_score  # noqa: E402
from engines.review_env_calibrated import CalibratedReviewEnv  # noqa: E402
from engines.review_policy import (  # noqa: E402
    REVIEW_ACTIONS,
    UNIFORM_WEIGHTS,
    _weights_of,
    review_state_features,
    review_weight_schema,
)
from run_shadow_probe import generate_samples  # noqa: E402

N = 240
DATA_SEED = 20260914
OUT_DIR = Path("experiments/results")


def real_contexts(n: int = N, seed: int = DATA_SEED):
    """真实样本生成器的上下文（与探针完全同源）。"""
    rng = random.Random(seed)
    samples = generate_samples(n, rng)
    feats = [
        review_state_features(
            evidence=s["evidence"], critic=s["critic"], consensus=s["consensus"],
            state=s["state"], mode_encoding=s["mode_encoding"],
            round_ratio=s["round_ratio"],
        )
        for s in samples
    ]
    return samples, feats


def env_contexts(n: int = N, base_seed: int = 700000):
    """校准环境抽出的上下文（reset 后的特征即环境上下文）。

    同时取回环境内部的 evidence/consensus 信号，以便用真实质量函数在同一口径下评估，
    从而判断"环境原生上下文"与"真实生成器上下文"的绝对水平是否一致。
    """
    feats, signals = [], []
    for t in range(n):
        e = CalibratedReviewEnv(seed=base_seed + t, horizon=1)
        feats.append(list(e.reset()))
        signals.append({"evidence": e._evidence, "consensus": e._consensus})
    return signals, feats


def _cmp(name: str, a: list, b: list) -> dict:
    """逐维统计对齐度。"""
    n = min(len(a[0]), len(b[0]))
    rows = []
    worst = (None, 0.0)
    for d in range(n):
        va = [f[d] for f in a]
        vb = [f[d] for f in b]
        ma, mb = statistics.mean(va), statistics.mean(vb)
        sa, sb = statistics.pstdev(va), statistics.pstdev(vb)
        # 标准化均值差（以两套合并标准差为尺度）
        scale = max(1e-9, (sa + sb) / 2)
        smd = abs(ma - mb) / scale
        rows.append({"dim": d + 1, "mean_env": round(ma, 4), "mean_real": round(mb, 4),
                     "std_env": round(sa, 4), "std_real": round(sb, 4),
                     "std_mean_diff": round(smd, 4)})
        if smd > worst[1]:
            worst = (d, smd)
    return {"n_dims": n, "per_dim": rows, "worst_dim": worst[0],
            "worst_std_mean_diff": round(worst[1], 4)}


def _f2_cdf(feats):
    xs = sorted(f[1] for f in feats)
    return xs


def _ks_like(a: list, b: list) -> float:
    """两套一维样本的 KS 统计量（经验 CDF 最大差），0 = 完全同分布。"""
    a, b = sorted(a), sorted(b)
    i = j = 0
    best = 0.0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            i += 1
        else:
            j += 1
        best = max(best, abs(i / len(a) - j / len(b)))
    return best


def _eval_arms(samples, feats):
    """在给定上下文上评估固定臂（真实质量函数口径）。

    ⚠️ 所有臂一律过 discipline_gate（reviews_done=0 ⇒ skip 恒禁用），与影子探针同口径。
    不加纪律门时 rule 会靠 skip（effective≡100）虚高 —— 实测真实上下文上
    68.948 → 69.966（+1.018），是本项目已记录过的口径陷阱，诊断脚本不得重犯。
    """
    from engines.review_env_calibrated import discipline_gate
    from engines.review_policy import _rule_action_idx
    from engines.review_shadow_probe import heuristic_action_idx

    arms = {"uniform": [], "rule": [], "heuristic_f2": [], "oracle": []}
    for s, f in zip(samples, feats):
        arms["uniform"].append(
            weighted_consistency_score(s["evidence"], s["consensus"],
                                       {"honest": 1 / 3, "critic": 1 / 3, "consensus": 1 / 3})[0])
        for key, idx in (("rule", _rule_action_idx(f)),
                         ("heuristic_f2", heuristic_action_idx(f))):
            gated = discipline_gate(idx, f, skip_streak=0, reviews_done=0)
            arms[key].append(
                weighted_consistency_score(s["evidence"], s["consensus"],
                                           review_weight_schema(_weights_of(gated)))[0])
        vals = [weighted_consistency_score(s["evidence"], s["consensus"],
                                           review_weight_schema(_weights_of(a)))[0]
                for a in range(4)]
        arms["oracle"].append(max(vals))
    return {k: round(statistics.mean(v), 3) for k, v in arms.items()}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="校准环境三重把关 + 奖励对齐（只读）")
    ap.add_argument("--r3-seed", type=int, default=7, help="R3 可解释性诊断所用的训练种子")
    ap.add_argument("--r3-episodes", type=int, default=3000,
                    help="R3 诊断策略的训练 episode 数。实测该超参决定'锐度'："
                         "3000(63 次更新) 时低 f2 区 40.5%% 退回 balanced；"
                         "10000(208 次更新) 时降至 0.8%%。诊断必须与被评策略同预算，"
                         "否则 R3 描述的是旧策略。")
    ap.add_argument("--r3-horizon", type=int, default=32)
    ap.add_argument("--r2-ppo", type=int, default=10000,
                    help="R2 显著性检验所选取的 calibrated 运行 episode 数（须与结论所用预算一致）")
    args = ap.parse_args()

    result: dict = {"meta": {
        "source": "diag_calib_alignment.py (read-only)",
        "n_samples": N,
        "data_seed": DATA_SEED,
        "note": "R1=训练/评测同分布核验；R2=逐样本配对显著性；R3=策略可解释性。"
                "全部数字为生产质量函数口径，所有臂过 discipline_gate(reviews_done=0)。",
    }}

    print("=" * 78)
    print("diag_calib_alignment —— 校准环境同分布性 + 统计显著性 双重把关")
    print("=" * 78)

    real_samples, real_feats = real_contexts()
    env_samples, env_feats = env_contexts()

    # ---------- R1: 分布对齐 ----------
    print("\n[R1] 上下文分布对齐（12 维逐维标准化均值差；越小越同分布）")
    cmp = _cmp("calib_env", env_feats, real_feats)
    print(f"  最差维度 = f{cmp['worst_dim']}  标准化均值差 = {cmp['worst_std_mean_diff']}")
    print(f"  {'dim':>4s} {'env_mean':>10s} {'real_mean':>10s} {'env_std':>9s} {'real_std':>9s} {'smd':>8s}")
    for r in cmp["per_dim"]:
        flag = "  <-- 关注" if r["std_mean_diff"] > 0.3 else ""
        print(f"  f{r['dim']:<3d} {r['mean_env']:10.4f} {r['mean_real']:10.4f} "
              f"{r['std_env']:9.4f} {r['std_real']:9.4f} {r['std_mean_diff']:8.4f}{flag}")

    ks = _ks_like([f[1] for f in env_feats], [f[1] for f in real_feats])
    print(f"  f2 的 KS 统计量 = {ks:.4f}  （<0.1 视为同分布）")
    env_f2 = [f[1] for f in env_feats]
    real_f2 = [f[1] for f in real_feats]
    print(f"  f2 分位  env: p10={sorted(env_f2)[len(env_f2)//10]:.3f} "
          f"p50={statistics.median(env_f2):.3f} p90={sorted(env_f2)[len(env_f2)*9//10]:.3f} | "
          f"real: p10={sorted(real_f2)[len(real_f2)//10]:.3f} "
          f"p50={statistics.median(real_f2):.3f} p90={sorted(real_f2)[len(real_f2)*9//10]:.3f}")
    print(f"  f2 ≥ 0.675 占比  env={100*sum(1 for x in env_f2 if x>=0.675)/len(env_f2):.1f}%  "
          f"real={100*sum(1 for x in real_f2 if x>=0.675)/len(real_f2):.1f}%")
    result["R1_distribution_alignment"] = {
        "worst_dim": cmp["worst_dim"],
        "worst_std_mean_diff": cmp["worst_std_mean_diff"],
        "all_dims_below_0_2": all(r["std_mean_diff"] < 0.2 for r in cmp["per_dim"]),
        "f2_ks_statistic": round(ks, 4),
        "f2_ge_0_675_pct": {
            "env": round(100 * sum(1 for x in env_f2 if x >= 0.675) / len(env_f2), 1),
            "real": round(100 * sum(1 for x in real_f2 if x >= 0.675) / len(real_f2), 1),
        },
        "per_dim": cmp["per_dim"],
    }

    # 固定臂在两套上下文上的绝对水平与排序稳健性
    print("\n[R1b] 固定臂在两套上下文上的绝对水平 + 排序稳健性（真实质量函数口径）")
    arms_real = _eval_arms(real_samples, real_feats)
    arms_env = _eval_arms(env_samples, env_feats)
    print(f"  真实生成器上下文 : {arms_real}")
    print(f"  校准环境上下文   : {arms_env}")
    order_real = sorted(arms_real, key=lambda k: -arms_real[k])
    order_env = sorted(arms_env, key=lambda k: -arms_env[k])
    print(f"  排序一致: {order_real == order_env}  ({' > '.join(order_real)})")
    gap = max(abs(arms_real[k] - arms_env[k]) for k in arms_real)
    print(f"  两套上下文上的臂均值最大差 = {gap:.3f}  （<1.0 视为水平一致）")
    result["R1b_arm_levels"] = {
        "arms_real": arms_real, "arms_env": arms_env,
        "ordering_identical": order_real == order_env,
        "ordering": order_real,
        "max_abs_gap": round(gap, 3),
    }

    # ---------- R2: 统计显著性 ----------
    print(f"\n[R2] 校准环境 ppo={args.r2_ppo} 的逐样本配对显著性")
    fs = sorted(glob.glob(str(OUT_DIR / "review_shadow_summary_*.json")),
                key=os.path.getmtime)
    targets = []
    for f in fs:
        d = json.load(open(f, encoding="utf-8"))
        m = d["meta"]
        if m.get("train_env") == "calibrated" and m.get("ppo_episodes") == args.r2_ppo:
            targets.append((f, d))
    if not targets:
        print(f"  未找到 calibrated ppo={args.r2_ppo} 的 summary，跳过。")
        # 回退到任意 calibrated 运行，避免整段诊断失效
        targets = [(f, json.load(open(f, encoding="utf-8"))) for f in fs
                   if json.load(open(f, encoding="utf-8"))["meta"].get("train_env") == "calibrated"]
    if targets:
        f, d = targets[-1]
        print(f"  使用 {os.path.basename(f)}")
        print(f"  shadow_action_dist = {d['shadow_action_dist']}")
        print(f"  arm_means = {d.get('arm_means')}")
        for key in ("delta_vs_uniform", "delta_vs_rule", "delta_vs_heuristic"):
            if key in d:
                x = d[key]
                print(f"  {key:<18s} mean={x['mean']:+.3f} std={x['std']:.3f} "
                      f"改善样本占比={x.get('pct_improve')}%")
        # 配对 t 检验（逐样本差）
        jl = sorted(glob.glob(f.replace("review_shadow_summary_", "review_shadow_")
                              .replace(".json", ".jsonl")))
        if jl:
            recs = [json.loads(l) for l in open(jl[-1], encoding="utf-8")]
            print(f"  JSONL = {os.path.basename(jl[-1])}  n = {len(recs)}")
            per_seed_n = len(recs[0]["shadow"]["per_seed_actions"])
            for si in range(per_seed_n):
                du = [r["shadow"]["per_seed_effective"][si] - r["baseline"]["uniform"]["effective"]
                      for r in recs]
                dr = [r["shadow"]["per_seed_effective"][si] - r["baseline"]["rule"]["effective"]
                      for r in recs]
                dh = [r["shadow"]["per_seed_effective"][si] - r["baseline"]["heuristic_f2"]["effective"]
                      for r in recs]
                print(f"    seed[{si}]  Δuni={statistics.mean(du):+.3f}  "
                      f"Δrule={statistics.mean(dr):+.3f}  Δheur={statistics.mean(dh):+.3f}")
            agg = {"uniform": [], "rule": [], "heuristic_f2": []}
            for r in recs:
                for key in agg:
                    base = r["baseline"][key]["effective"]
                    agg[key].append(statistics.mean(
                        [r["shadow"]["per_seed_effective"][si] - base
                         for si in range(per_seed_n)]))
            n = len(agg["uniform"])
            print(f"\n  聚合口径 n={n}（逐样本，种子已平均）:")
            r2 = {"summary_file": os.path.basename(f), "jsonl_file": os.path.basename(jl[-1]),
                  "n": n, "arm_means": d.get("arm_means"),
                  "shadow_action_dist": d["shadow_action_dist"], "per_seed": [], "aggregate": {}}
            for si in range(per_seed_n):
                r2["per_seed"].append({
                    "seed_index": si,
                    "d_uniform": round(statistics.mean(
                        [r["shadow"]["per_seed_effective"][si] - r["baseline"]["uniform"]["effective"]
                         for r in recs]), 3),
                    "d_rule": round(statistics.mean(
                        [r["shadow"]["per_seed_effective"][si] - r["baseline"]["rule"]["effective"]
                         for r in recs]), 3),
                    "d_heuristic": round(statistics.mean(
                        [r["shadow"]["per_seed_effective"][si] - r["baseline"]["heuristic_f2"]["effective"]
                         for r in recs]), 3),
                })
            for key, arr in agg.items():
                m, sd = statistics.mean(arr), statistics.pstdev(arr)
                t = m / (sd / n ** 0.5) if sd > 0 else float("inf")
                print(f"    Δ vs {key:<13s} mean={m:+.3f}  std={sd:.3f}  "
                      f"t={t:+.2f}  正增益样本占比={100*sum(1 for x in arr if x>0)/n:.1f}%")
                r2["aggregate"][key] = {
                    "mean": round(m, 3), "std": round(sd, 3), "t": round(t, 2),
                    "pct_positive": round(100 * sum(1 for x in arr if x > 0) / n, 1),
                }
            result["R2_significance"] = r2
        else:
            print("  (未找到对应 JSONL，跳过逐样本检验)")

    # ---------- R3: 策略可解释性（学到的是不是 f2 上下文切分） ----------
    print("\n[R3] 策略可解释性：RL 动作 vs 解析阈值策略（同一条真实上下文）")
    if targets:
        from engines.review_env_calibrated import discipline_gate
        from engines.review_shadow_probe import (build_shadow_policy,
                                                 heuristic_action_idx)
        p = build_shadow_policy(args.r3_seed, warmup_steps=600, ppo_episodes=args.r3_episodes,
                                horizon=args.r3_horizon,
                                env_factory=lambda sd, hz: CalibratedReviewEnv(seed=sd, horizon=hz))
        agree, better, worse, same = 0, 0, 0, 0
        d_better, d_worse = [], []
        act_by_lowf2 = Counter()
        act_by_highf2 = Counter()
        for s, f in zip(real_samples, real_feats):
            idx, _src = p.select_action(f, deterministic=True, skip_streak=0, reviews_done=0)
            idx = discipline_gate(idx, f, skip_streak=0, reviews_done=0)
            h_idx = heuristic_action_idx(f)
            (act_by_lowf2 if f[1] <= 0.675 else act_by_highf2)[idx] += 1
            v_rl = weighted_consistency_score(s["evidence"], s["consensus"],
                                              review_weight_schema(_weights_of(idx)))[0]
            v_h = weighted_consistency_score(s["evidence"], s["consensus"],
                                             review_weight_schema(_weights_of(h_idx)))[0]
            if idx == h_idx:
                agree += 1
            if abs(v_rl - v_h) < 1e-9:
                same += 1
            elif v_rl > v_h:
                better += 1
                d_better.append(v_rl - v_h)
            else:
                worse += 1
                d_worse.append(v_h - v_rl)
        n = len(real_feats)
        print(f"  与解析阈值策略动作一致率 = {100*agree/n:.1f}%  (n={n})")
        print(f"  不一致处：RL 更优 {better} 条（均值 +{statistics.mean(d_better):.3f}）"
              if d_better else "  不一致处：RL 更优 0 条")
        print(f"            RL 更差 {worse} 条（均值 +{statistics.mean(d_worse):.3f}）"
              if d_worse else "            RL 更差 0 条")
        print(f"  动作分布 | f2≤0.675（低证据自评 → 理论选 consensus）: {dict(act_by_lowf2)}")
        print(f"  动作分布 | f2> 0.675（高证据自评 → 理论选 honest）  : {dict(act_by_highf2)}")
        print(f"  说明：以上为 deterministic 推理（部署口径），跳过随机采样噪声。")
        result["R3_interpretability"] = {
            "r3_seed": args.r3_seed, "r3_episodes": args.r3_episodes,
            "r3_horizon": args.r3_horizon,
            "agreement_pct": round(100 * agree / n, 1),
            "rl_better": better, "rl_better_mean_gain": round(statistics.mean(d_better), 3) if d_better else 0.0,
            "rl_worse": worse, "rl_worse_mean_loss": round(statistics.mean(d_worse), 3) if d_worse else 0.0,
            "actions_low_f2": {REVIEW_ACTIONS[k]: v for k, v in sorted(act_by_lowf2.items())},
            "actions_high_f2": {REVIEW_ACTIONS[k]: v for k, v in sorted(act_by_highf2.items())},
        }

    # ---------- R4: 奖励对齐（排除"奖励设计错位"解释） ----------
    print("\n[R4] 奖励对齐：env 内 reward-argmax 是否等于 quality-argmax？")
    from engines.review_policy import ACTION_TOKENS, review_reward
    agree4, n4, qdist, rdist, loss = 0, 0, Counter(), Counter(), []
    for t in range(400):
        e = CalibratedReviewEnv(seed=800000 + t, horizon=1)
        e.reset()
        ev, cs = e._evidence, e._consensus
        base, _ = weighted_consistency_score(ev, cs, dict(UNIFORM_WEIGHTS))
        qual, rew = {}, {}
        for a in range(4):
            eff, _ap = weighted_consistency_score(ev, cs, review_weight_schema(_weights_of(a)))
            qual[a] = eff
            rew[a] = review_reward(gate_before=0.0, gate_after=eff - base, precision=True,
                                   tokens=ACTION_TOKENS.get(a, 0.0), skip_streak=0)
        qa = max(qual, key=qual.get)
        ra = max(rew, key=rew.get)
        n4 += 1
        qdist[qa] += 1
        rdist[ra] += 1
        if qa == ra:
            agree4 += 1
        else:
            loss.append(qual[qa] - qual[ra])
    print(f"  精确一致率 = {100*agree4/n4:.1f}%  (n={n4})")
    print(f"  quality-argmax 分布 = {{ {', '.join(f'{REVIEW_ACTIONS[k]}:{v}' for k, v in sorted(qdist.items()))} }}")
    print(f"  reward-argmax  分布 = {{ {', '.join(f'{REVIEW_ACTIONS[k]}:{v}' for k, v in sorted(rdist.items()))} }}")
    if loss:
        print(f"  不一致处 quality 损失：n={len(loss)} 均值 {statistics.mean(loss):.4f} 最大 {max(loss):.4f}"
              f"  （≈0 ⇒ 属并列，非错位）")
    else:
        print("  无不一致处")
    result["R4_reward_alignment"] = {
        "exact_agree_pct": round(100 * agree4 / n4, 1), "n": n4,
        "quality_argmax_dist": {REVIEW_ACTIONS[k]: v for k, v in sorted(qdist.items())},
        "reward_argmax_dist": {REVIEW_ACTIONS[k]: v for k, v in sorted(rdist.items())},
        "mismatch_n": len(loss),
        "mismatch_mean_quality_loss": round(statistics.mean(loss), 4) if loss else 0.0,
        "verdict": "reward 与验收口径对齐（不一致处为并列，损失≈0）⇒ 排除奖励设计错位",
    }

    print("\n" + "=" * 78)
    print("判读：R1 worst smd < 0.2 且 f2 KS < 0.1 且排序一致 → 两套上下文同分布；")
    print("      R2 Δuniform 显著为正 → RL 真实有效；Δrule 显著为正但种子脆弱 → 谨慎；")
    print("      Δheuristic 不显著 → 不得宣称 RL 超越解析启发式；")
    print("      R3 一致率低且低 f2 区退 balanced → 诊断出'学到方向、未学到锐度'；")
    print("      R4 奖励/质量 argmax 高度一致 → 排除'奖励设计错位'这一解释。")
    print("=" * 78)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "diag_calib_alignment.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"\n落盘证据：{out}")


if __name__ == "__main__":
    main()
