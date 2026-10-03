# ============================================================
# sweep_shadow_budget — 影子策略训练预算扫描（判定"欠训练 or 真失败"）
#
# 为什么需要它（真实事件）：
#   角色B 把 train_ppo 从"每 episode 更新一次"改成 batch 化（默认 batch_episodes=48）后，
#   未显式传 batch_episodes 的调用方被**静默饿死**：影子探针 episodes=200 在旧语义下是
#   200 次梯度更新，改后变成 200//48 = 4 次。于是 2026-09-14 16:15 之后跑出的
#   "真实特征空间 RL 输给规则"（68.445 vs 68.948）混杂了"预算被砍 50 倍"这一人为因素，
#   不能直接当作 sim-to-real 结论。
#
#   本脚本固定其它一切条件，只扫【更新次数】，从而把两件事分开：
#     - 若 shadow 随更新次数上升并越过 rule → 是欠训练（工程问题，修预算即可）
#     - 若 shadow 在充分预算下仍低于 rule/heuristic → 是真实的策略学习失败（需换方法）
#
# 口径常量（与 diag_shadow_sim2real.json 同源、同 240 样本）：
#   uniform 66.809 / rule 68.948 / heuristic_f2 69.807 / oracle 72.275
#
# 用法：
#   NO_PROXY=127.0.0.1 .venv/Scripts/python.exe experiments/sweep_shadow_budget.py
# ============================================================

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import random  # noqa: E402

from engines.review_env_calibrated import CalibratedReviewEnv, discipline_gate  # noqa: E402
from engines.review_shadow_probe import (  # noqa: E402
    build_shadow_policy,
    heuristic_action_idx,
    observe,
    summarize,
)
from engines.review_policy import (  # noqa: E402
    REVIEW_ACTIONS,
    UNIFORM_WEIGHTS,
    _rule_action_idx,
    _weights_of,
    review_state_features,
    review_weight_schema,
)
from agents.quality_gate import weighted_consistency_score  # noqa: E402
from run_shadow_probe import generate_samples  # noqa: E402

SEEDS = [7, 42, 2026]
DATA_SEED = 20260914
N_SAMPLES = 240
HORIZON = 32
WARMUP = 600

# (label, episodes, batch_episodes)
BUDGETS = [
    ("pre-fix语义(200ep,逐ep更新)", 200, 1),
    ("当前默认(200ep,batch48)", 200, 48),
    ("中档(1200ep,batch48)", 1200, 48),
    ("标准档(3000ep,batch48)", 3000, 48),
]


def main():
    ap = argparse.ArgumentParser(description="影子策略训练预算扫描（判定欠训练 or 真失败）")
    ap.add_argument("--seeds", type=str, default=",".join(str(s) for s in SEEDS))
    ap.add_argument("--data-seed", type=int, default=DATA_SEED)
    ap.add_argument("--samples", type=int, default=N_SAMPLES)
    ap.add_argument("--horizon", type=int, default=HORIZON)
    ap.add_argument("--warmup-steps", type=int, default=WARMUP)
    ap.add_argument("--budgets", type=str, default="",
                    help="覆盖默认预算，格式 episodes:batch[,episodes:batch...]；"
                         "留空=跑内置 4 档")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    if args.budgets.strip():
        budgets = []
        for i, tok in enumerate(args.budgets.split(",")):
            e, b = tok.split(":")
            budgets.append((f"ep{e}x batch{b}", int(e), int(b)))
    else:
        budgets = BUDGETS

    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.data_seed)
    samples = generate_samples(args.samples, rng)

    # 基线臂（与预算无关，先算一次）
    # ⚠️ rule 必须过 discipline_gate：skip(4) 的 effective 恒 ≡100，是口径陷阱；
    #    未过门时 rule 会虚高约 +1.0 分，使"RL 是否胜过规则"的结论系统性偏移。
    base_eff, rule_eff, heur_eff = [], [], []
    for s in samples:
        ev, cs = s["evidence"], s["consensus"]
        u = weighted_consistency_score(ev, cs, dict(UNIFORM_WEIGHTS))[0]
        base_eff.append(u)
        feats = review_state_features(
            evidence=ev, critic=s["critic"], consensus=cs, state=s["state"],
            mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"])
        r_idx = discipline_gate(_rule_action_idx(feats), feats, 0, 0)
        rule_eff.append(weighted_consistency_score(
            ev, cs, review_weight_schema(_weights_of(r_idx)))[0])
        h_idx = heuristic_action_idx(feats)
        heur_eff.append(weighted_consistency_score(
            ev, cs, review_weight_schema(_weights_of(h_idx)))[0])

    def _m(xs):
        return round(sum(xs) / len(xs), 3)

    baselines = {"uniform": _m(base_eff), "rule": _m(rule_eff), "heuristic_f2": _m(heur_eff)}
    print(f"[sweep] 基线（{args.samples} 样本, data_seed={args.data_seed}）：{baselines}")

    results = []
    for label, eps, batch in budgets:
        print(f"\n[sweep] === {label} : episodes={eps} batch={batch} "
              f"→ 预期更新 {eps // batch} 次 ===")
        policies = []
        n_upd = []
        for sd in seeds:
            p = build_shadow_policy(
                sd, warmup_steps=args.warmup_steps, ppo_episodes=eps, horizon=args.horizon,
                env_factory=lambda s_, h_: CalibratedReviewEnv(seed=s_, horizon=h_),
                batch_episodes=batch)
            st = getattr(p, "_last_train_stats", {}) or {}
            n_upd.append(st.get("n_updates"))
            print(f"    seed={sd}: trained={getattr(p, '_trained', False)} "
                  f"n_updates={st.get('n_updates')} "
                  f"ret {st.get('mean_return_first_third', float('nan')):.4f}"
                  f"→{st.get('mean_return_last_third', float('nan')):.4f}")
            policies.append(p)

        recs = []
        for s in samples:
            r = observe(evidence=s["evidence"], consensus=s["consensus"], state=s["state"],
                        critic=s["critic"], shadow_policies=policies,
                        skip_streak=0, reviews_done=0,
                        mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"])
            recs.append(r)
        summ = summarize(recs)

        # ── 自校验：本地算的 rule 基线必须与 observe 内部的 rule 臂逐位一致 ──
        # 这条断言是补上来的：首版脚本对 rule 用**未过纪律门**的原始动作取分，
        # skip(4) 的 effective 恒 ≡100 使 rule 虚高到 69.966，与 observe 的 68.948 不符。
        # 自有基线一旦与观测臂口径不同，整张对比表都会系统性偏袒某一方。
        if results == [] and abs(summ["arm_means"]["rule"] - baselines["rule"]) > 1e-6:
            raise AssertionError(
                f"rule 基线口径不一致：本地 {baselines['rule']} vs observe 臂 "
                f"{summ['arm_means']['rule']} —— 检查是否漏了 discipline_gate")
        summ["meta"] = {"label": label, "episodes": eps, "batch_episodes": batch,
                        "n_updates_per_seed": n_upd, "seeds": seeds,
                        "horizon": args.horizon, "warmup_steps": args.warmup_steps,
                        "train_env": "calibrated", "n_samples": args.samples,
                        "data_seed": args.data_seed}
        results.append(summ)
        print(f"    → shadow={summ['arm_means']['shadow']} rule={summ['arm_means']['rule']} "
              f"heuristic={summ['arm_means']['heuristic_f2']} "
              f"Δrule={summ['delta_vs_rule']['mean']} "
              f"dist={ {REVIEW_ACTIONS[int(k)]: v for k, v in summ['shadow_action_dist'].items()} }")

    print("\n================= 预算扫描汇总 =================")
    print(f"{'预算':<28} {'更新次数':>8} {'shadow':>8} {'Δvs规则':>9} {'Δvs启发':>9} {'配对t':>7}")
    for r in results:
        m = r["meta"]
        nu = ",".join(str(x) for x in m["n_updates_per_seed"])
        # 配对显著性：Δ 的逐样本均值 / 标准误（同一批样本上三方案配对比较）
        n = r["n"]
        se = r["delta_vs_rule"]["std"] / (n ** 0.5) if n else float("nan")
        t = r["delta_vs_rule"]["mean"] / se if se else float("nan")
        print(f"{m['label']:<28} {nu:>8} {r['arm_means']['shadow']:>8} "
              f"{r['delta_vs_rule']['mean']:>9} {r['delta_vs_heuristic']['mean']:>9} "
              f"{t:>7.2f}")
    print(f"{'[基线] rule':<28} {'-':>8} {baselines['rule']:>8}")
    print(f"{'[基线] heuristic_f2':<28} {'-':>8} {baselines['heuristic_f2']:>8}")
    print(f"{'[基线] uniform':<28} {'-':>8} {baselines['uniform']:>8}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outp = out_dir / f"sweep_shadow_budget_{ts}.json"
    with open(outp, "w", encoding="utf-8") as f:
        json.dump({"baselines": baselines,
                   "config": {"seeds": seeds, "data_seed": args.data_seed,
                              "n_samples": args.samples, "horizon": args.horizon,
                              "warmup_steps": args.warmup_steps},
                   "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\n[sweep] -> {outp}")


if __name__ == "__main__":
    main()
