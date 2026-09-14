"""阶段2 收尾取证：评审权重 3-seed 对比的「公平口径 + 预算扫描」。

存在动机（两条，均已实测复现）：
  ① 欠训练伪影：`experiments/eval_review_mappo.py`（角色 C 产物）默认
     `--ppo-episodes 60`，且第 180 行调用 `train_ppo` 时不传 `batch_episodes`。
     自 d55387e 起 `batch_episodes` 默认 48 ⇒ 60//48 = **1 次梯度更新**。
     用它得到的 "RL 低于 uniform" 不能作为结论。
  ② 口径不公平：该脚本对 baseline `rule` 直接调用 `_rule_action_idx(feats)`，
     **绕过了生产 `decide_review_weight` 内的 `_block_skip` 纪律护栏**，
     于是 rule 臂可以白拿 skip 省 token（实测 skip 率 0.135、连发 2），
     与攻坚令阶段 3 验收项「skip 连发 >=2 发生率为 0」冲突。

本脚本不改 C 的文件（C 负责），而是以生产语义独立复算：
  - 对四个方案**统一施加**与生产同源的护栏（rule 臂显式施加；rl/supervised
    经 `select_action` 内部已施加，不重复施加）；
  - 显式传 `batch_episodes`，并把真实 `n_updates` 落盘，杜绝再次被静默饿死；
  - 预算三点扫描，证明结论随预算变化（预算即结论决定性超参）。

指标定义与 C 的 `run_episode` 逐项同源，便于与其表格直接对照。
诚信：所有数字来自真实 torch 运行并落盘；不落盘不对外引用。
"""
import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
sys.path.insert(0, str(ROOT))

import torch as _torch  # noqa: E402

_torch.set_num_threads(1)
try:
    _torch.use_deterministic_algorithms(True)
except Exception:  # pragma: no cover
    pass

from engines.review_policy import (  # noqa: E402
    ACTION_TOKENS,
    REVIEW_ACTIONS,
    REVIEW_MIN_REVIEW,
    SKIP_STREAK_LIMIT,
    ReviewEnv,
    ReviewWeightPolicy,
    _rule_action_idx,
)

SEEDS = [7, 42, 2026]
EVAL_EPISODES = 30
HORIZON = 6
WARMUP_STEPS = 300

# (label, ppo_episodes, batch_episodes) —— batch 显式传，避免被默认值静默改变语义
# 真实更新次数以 train_ppo 上报的 n_updates 为准（label 不写死，防止陈述与实测不符）
BUDGETS = [
    ("默认60ep(batch48)", 60, 48),
    ("中档1200ep(batch48)", 1200, 48),
    ("标准3000ep(batch48)", 3000, 48),
]

OUT_DIR = Path(__file__).resolve().parent.parent / "experiments" / "results"

# ── 精准评审口径：引用**环境原生语义**，不硬编码阈值 ──────────────
# `ReviewEnv.step` 内定义：precision = (consistency >= 0.5) or (action != 4)。
# C 的 `eval_review_mappo.py` 第 111 行硬编码 `thr = 75.0 if idx==4 else 60.0`
# （旧 0-100 量纲），而 d55387e 已把 consistency 改为 0-1 量纲 ⇒ 该阈值永不满足，
# 实测四臂 precision_rate 全部退化为 0.000。属跨角色口径漂移，此处改为单一真值源。
ENV_CONS_RANGE = (0.0, 1.0)
ENV_PRECISION_THRESHOLD = 0.5


def _check_scale(v):
    """量纲哨兵：环境量纲一旦再次变更即显式失败，杜绝静默漂移。"""
    lo, hi = ENV_CONS_RANGE
    if not (lo <= v <= hi):
        raise AssertionError(
            f"ReviewEnv.consistency={v} 超出约定量纲 {ENV_CONS_RANGE}；"
            "环境量纲已变更，本脚本的 precision 口径需同步复核（不得静默继续）")


def guard(idx, feats, skip_streak, reviews_done):
    """生产同源纪律护栏（`decide_review_weight._block_skip` 的等价复刻）。

    必须在「第 2 次连发发生前」拦截（>= LIMIT-1），否则连发 2 次已发生。
    """
    if idx == 4 and (reviews_done < REVIEW_MIN_REVIEW
                     or skip_streak >= SKIP_STREAK_LIMIT - 1):
        return 0 if (feats and len(feats) > 1 and feats[1] >= 0.6) else 3
    return idx


def run_episode(mode, policy, eseed):
    """与 C 的 eval_review_mappo.run_episode 指标逐项同源，但统一施加护栏。"""
    env = ReviewEnv(seed=eseed, horizon=HORIZON)
    feats = env.reset()
    q0 = env.consistency
    _check_scale(q0)

    total_r = tokens = 0.0
    skips = streak = max_streak = reviews_done = prec_hits = steps = 0

    for _ in range(HORIZON):
        if mode == "uniform":
            idx = 3                                   # 恒定均衡 = 灰度关闭现状
        elif mode == "rule":
            raw = _rule_action_idx(feats)
            idx = guard(raw, feats, streak, reviews_done)   # ← C 版缺这一步
        else:
            # rl / supervised：select_action 内部已施加护栏，不重复施加
            idx, _src = policy.select_action(
                feats, deterministic=True, skip_streak=streak, reviews_done=reviews_done)
        idx = int(idx)
        if not (0 <= idx < len(REVIEW_ACTIONS)):
            idx = 3

        if idx == 4:
            skips += 1
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
            reviews_done += 1
        tokens += float(ACTION_TOKENS.get(idx, 0.0))

        feats, r, done = env.step(idx)
        _check_scale(env.consistency)
        # 环境原生 precision 语义（见文件头说明）
        if env.consistency >= ENV_PRECISION_THRESHOLD or idx != 4:
            prec_hits += 1
        total_r += float(r)
        steps += 1
        if done:
            break

    return {
        "total_return": total_r,
        "mean_return": total_r / max(1, steps),
        "quality_gain": env.consistency - q0,
        "final_quality": env.consistency,
        "tokens": tokens,
        "skip_count": skips,
        "max_skip_streak": max_streak,
        "reviews_done": reviews_done,
        "precision_rate": prec_hits / max(1, steps),
        "steps": steps,
        "discipline_violation": max_streak >= SKIP_STREAK_LIMIT,
    }


def aggregate(eps):
    n = len(eps)
    steps = sum(e["steps"] for e in eps)
    return {
        "episodes": n,
        "mean_return": sum(e["total_return"] for e in eps) / max(1, n),
        "mean_quality_gain": sum(e["quality_gain"] for e in eps) / max(1, n),
        "mean_final_quality": sum(e["final_quality"] for e in eps) / max(1, n),
        "mean_tokens": sum(e["tokens"] for e in eps) / max(1, n),
        "skip_rate": sum(e["skip_count"] for e in eps) / max(1, steps),
        "precision_rate": sum(e["precision_rate"] * e["steps"] for e in eps) / max(1, steps),
        "max_skip_streak": max((e["max_skip_streak"] for e in eps), default=0),
        "discipline_violation_rate": sum(
            1 for e in eps if e["discipline_violation"]) / max(1, n),
    }


def build(kind, seed, ppo_episodes, batch_episodes):
    p = ReviewWeightPolicy(seed=seed)
    if not p.torch_available:
        return None, {"degraded": True, "kind": kind, "seed": seed}
    p.warmup_with_rules(ReviewEnv(seed=seed, horizon=HORIZON),
                        steps=WARMUP_STEPS, seed=seed)
    st = {"degraded": False, "kind": kind, "seed": seed}
    if kind == "rl":
        t = p.train_ppo(ReviewEnv(seed=seed, horizon=HORIZON), episodes=ppo_episodes,
                        horizon=HORIZON, seed=seed, batch_episodes=batch_episodes)
        st["n_updates"] = t.get("n_updates")
        st["episodes"] = t.get("episodes")
        st["improved"] = t.get("improved")
        st["improved_deterministic"] = t.get("improved_deterministic")
    return p, st


def evaluate(policies, schemes):
    out = {}
    for scheme in schemes:
        cells = []
        for seed in SEEDS:
            pol = policies.get(f"{scheme}/seed={seed}")
            rng = random.Random(seed * 1000 + 17)      # 与 C 完全一致的评估种子派生
            eps = [run_episode(scheme, pol, rng.randint(1, 10 ** 6))
                   for _ in range(EVAL_EPISODES)]
            cells.append(aggregate(eps))
        n = len(cells)
        out[scheme] = {
            "mean_return": sum(c["mean_return"] for c in cells) / n,
            "mean_return_std": (sum((c["mean_return"] - sum(
                x["mean_return"] for x in cells) / n) ** 2 for c in cells) / n) ** 0.5,
            "mean_quality_gain": sum(c["mean_quality_gain"] for c in cells) / n,
            "mean_tokens": sum(c["mean_tokens"] for c in cells) / n,
            "skip_rate": sum(c["skip_rate"] for c in cells) / n,
            "precision_rate": sum(c["precision_rate"] for c in cells) / n,
            "max_skip_streak": max(c["max_skip_streak"] for c in cells),
            "discipline_violation_rate": sum(
                c["discipline_violation_rate"] for c in cells) / n,
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budgets", type=str, default=None,
                    help='形如 "60:48,3000:48"，缺省用内置三点')
    args = ap.parse_args()

    budgets = BUDGETS
    if args.budgets:
        budgets = []
        for part in args.budgets.split(","):
            e, b = part.split(":")
            budgets.append((f"{e}ep(batch{b})", int(e), int(b)))

    results = []
    for label, eps, batch in budgets:
        print("=" * 78)
        print(f"[预算扫描] {label}  episodes={eps} batch={batch} "
              f"⇒ 预期更新 {eps // batch} 次")
        print("=" * 78)
        policies, stats = {}, []
        for scheme in ("supervised", "rl"):
            for seed in SEEDS:
                p, st = build(scheme, seed, eps, batch)
                policies[f"{scheme}/seed={seed}"] = p
                stats.append(st)
        agg = evaluate(policies, ("uniform", "rule", "supervised", "rl"))
        rl_upd = [s.get("n_updates") for s in stats if s["kind"] == "rl"]

        print(f"{'方案':<12}{'回报':>10}{'质量增益':>10}{'token':>10}"
              f"{'skip率':>9}{'精准率':>9}{'连发':>6}")
        for s in ("uniform", "rule", "supervised", "rl"):
            a = agg[s]
            print(f"{s:<12}{a['mean_return']:>10.4f}{a['mean_quality_gain']:>10.3f}"
                  f"{a['mean_tokens']:>10.1f}{a['skip_rate']:>9.3f}"
                  f"{a['precision_rate']:>9.3f}{a['max_skip_streak']:>6}")
        rl, ru, rr, sup = (agg["rl"], agg["uniform"], agg["rule"], agg["supervised"])
        disc_ok = all(agg[s]["max_skip_streak"] < SKIP_STREAK_LIMIT
                      for s in ("uniform", "rule", "supervised", "rl"))
        print(f"  n_updates(RL)={rl_upd}  rl>=uniform:{rl['mean_return'] >= ru['mean_return']}  "
              f"rl>=rule:{rl['mean_return'] >= rr['mean_return']}  "
              f"rule>=supervised:{rr['mean_return'] >= sup['mean_return']}  "
              f"discipline_ok:{disc_ok}")
        results.append({
            "label": label, "ppo_episodes": eps, "batch_episodes": batch,
            "n_updates_per_seed": rl_upd,
            "schemes": agg,
            "rl_ge_uniform": rl["mean_return"] >= ru["mean_return"],
            "rl_ge_rule": rl["mean_return"] >= rr["mean_return"],
            "rule_ge_supervised": rr["mean_return"] >= sup["mean_return"],
            "discipline_ok": disc_ok,
            "train_stats": stats,
        })

    print("\n================= 预算扫描汇总（统一护栏口径）=================")
    print(f"{'预算':<24}{'更新':>8}{'rl':>10}{'uniform':>10}{'rule':>10}{'supervised':>12}")
    for r in results:
        s = r["schemes"]
        print(f"{r['label']:<24}{str(r['n_updates_per_seed']):>8}"
              f"{s['rl']['mean_return']:>10.4f}{s['uniform']['mean_return']:>10.4f}"
              f"{s['rule']['mean_return']:>10.4f}{s['supervised']['mean_return']:>12.4f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "review_mappo_stage2_wrapup.json"
    payload = {
        "experiment": "review_mappo_stage2_wrapup_budget_guard",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "why": "C 的 eval_review_mappo.py 默认预算在当前树上=1次更新，且 rule 臂绕过纪律护栏；本脚本以生产语义复算",
        "config": {"seeds": SEEDS, "eval_episodes": EVAL_EPISODES, "horizon": HORIZON,
                   "warmup_steps": WARMUP_STEPS, "guard": "统一施加（生产同源）"},
        "results": results,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n落盘: {out}")


if __name__ == "__main__":
    main()
