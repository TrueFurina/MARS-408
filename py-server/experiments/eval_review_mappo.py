# ============================================================
# eval_review_mappo — 三元评审权重 3-seed 对比实验（角色 C · 实验数据）
#
# 依据：docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md 阶段 3
#   - baseline A = 均匀权重（绝对基线，= 现状灰度关闭行为）
#   - baseline B = 固定规则（_rule_action_idx，现有规则因子）
#   - baseline C = 监督学习（warmup_with_rules：离线回归到规则决策标签，无 RL）
#   - 方案 D = RL（warmup 预热 + PPO 微调）
#   - 3-seed × 4 方案 × 指标：评审质量增益 / 成本(token) / 精准率 / skip 频次
#   - 纪律指标：skip 连发 ≥2 发生率必须为 0
#
# 独立可复算纪律：本脚本不复用 evaluate_policy 的单一 mean_return，
#   而是自行重跑环境并复算全部指标（与 review_reward 口径同源），便于交叉校验。
#
# 诚信约束：torch 不可用时如实标注 degraded，不伪造训练/评估结果；
#   所有数字落盘 experiments/results/review_mappo_eval_YYYYMMDD.json，不落盘不对外引用。
# ============================================================

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.review_policy import (  # noqa: E402
    ACTION_TOKENS,
    REVIEW_ACTIONS,
    SKIP_STREAK_LIMIT,
    REVIEW_MIN_REVIEW,
    ReviewEnv,
    ReviewWeightPolicy,
    _rule_action_idx,
)

# ── 复现性锁 ───────────────────────────────────────────────
# PPO 在 CPU 多线程下 torch.manual_seed 不保证跨进程逐位复现，
# 会导致"同 seed 两次跑动作分布不同"→ 报告与 JSON 漂移（已踩坑）。
# 锁定单线程 + 确定性算法，使 3-seed 实验可逐位复算。
import torch as _torch  # noqa: E402

_torch.set_num_threads(1)
try:
    _torch.use_deterministic_algorithms(True)
except Exception:  # pragma: no cover
    pass

SEEDS = [7, 42, 2026]
SCHEMES = ["uniform", "rule", "supervised", "rl"]
DEFAULT_EPISODES = 30
DEFAULT_HORIZON = 6


# ────────────────────────────────────────────────────────────
# 单 episode 指标采集（独立复算，不依赖 evaluate_policy）
# ────────────────────────────────────────────────────────────

def run_episode(mode: str, policy: Optional[ReviewWeightPolicy], seed: int,
                horizon: int) -> dict:
    """跑一个 episode，返回本 episode 的逐项指标。

    mode: "uniform" | "rule" | "supervised" | "rl"
      - uniform / rule 不需要网络；
      - supervised / rl 需要已构造并（可能）训练好的 policy 实例。
    """
    env = ReviewEnv(seed=seed, horizon=horizon)
    feats = env.reset()
    q0 = env.consistency  # 初始质量（50.0）

    total_r = 0.0
    tokens = 0.0
    skips = 0
    streak = 0
    max_streak = 0
    reviews_done = 0
    prec_hits = 0
    steps = 0

    for _ in range(horizon):
        if mode == "uniform":
            idx = 3
        elif mode == "rule":
            idx = _rule_action_idx(feats)
        elif mode.startswith("const:"):
            # 恒定动作消融：用于确定"最优恒定策略"上界（诊断用，非方案）
            idx = int(mode.split(":", 1)[1])
        else:
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
        after = env.consistency
        # 精准评审口径（与 ReviewEnv.step 内 precision 定义同源）
        thr = 75.0 if idx == 4 else 60.0
        if after >= thr:
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
        "precision_hits": prec_hits,
        "precision_rate": prec_hits / max(1, steps),
        "steps": steps,
        "discipline_violation": max_streak >= SKIP_STREAK_LIMIT,
    }


def aggregate(episodes: list[dict]) -> dict:
    n = len(episodes)
    total_steps = sum(e["steps"] for e in episodes)
    viol = sum(1 for e in episodes if e["discipline_violation"])
    return {
        "episodes": n,
        "mean_return": sum(e["total_return"] for e in episodes) / max(1, n),
        "mean_quality_gain": sum(e["quality_gain"] for e in episodes) / max(1, n),
        "mean_final_quality": sum(e["final_quality"] for e in episodes) / max(1, n),
        "mean_tokens": sum(e["tokens"] for e in episodes) / max(1, n),
        "skip_rate": sum(e["skip_count"] for e in episodes) / max(1, total_steps),
        "mean_skip_per_episode": sum(e["skip_count"] for e in episodes) / max(1, n),
        "precision_rate": sum(e["precision_hits"] for e in episodes) / max(1, total_steps),
        "max_skip_streak": max((e["max_skip_streak"] for e in episodes), default=0),
        "discipline_violation_rate": viol / max(1, n),
        "reviews_done_mean": sum(e["reviews_done"] for e in episodes) / max(1, n),
    }


# ────────────────────────────────────────────────────────────
# 策略构建
# ────────────────────────────────────────────────────────────

def build_policy(kind: str, seed: int, warmup_steps: int, ppo_episodes: int,
                 horizon: int) -> tuple[Optional[ReviewWeightPolicy], dict]:
    """构建 supervised / rl 策略，返回 (policy, train_stats)。

    torch 不可用 → 返回 (None, {"degraded": True, ...})，由调用方如实标注。
    """
    # 必须按 seed 分别播种：否则 ReviewWeightPolicy 默认 seed=42，
    # 3 个 RL 单元会训出同一份策略，"3-seed" 退化为同策略的 3 次评估。
    p = ReviewWeightPolicy(seed=seed)
    if not p.torch_available:
        return None, {"degraded": True, "reason": "torch 不可用", "kind": kind}

    stats: dict = {"degraded": False, "kind": kind, "seed": seed}
    w = p.warmup_with_rules(ReviewEnv(seed=seed, horizon=horizon),
                            steps=warmup_steps, seed=seed)
    stats["warmup"] = {
        "steps": w.get("steps"),
        "mean_loss": w.get("mean_loss"),
        "final_loss": w.get("final_loss"),
    }
    if kind == "rl":
        t = p.train_ppo(env=ReviewEnv(seed=seed, horizon=horizon),
                        episodes=ppo_episodes, horizon=horizon, seed=seed)
        stats["ppo"] = {
            "trained": t.get("trained"),
            "episodes": t.get("episodes"),
            "final_mean_return": t.get("final_mean_return"),
            "first_mean_return": t.get("first_mean_return"),
            "reason": t.get("reason"),
        }
    return p, stats


# ────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="三元评审权重 3-seed 对比实验")
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    ap.add_argument("--episodes", type=int, default=DEFAULT_EPISODES,
                    help="每 (方案,seed) 评估 episode 数")
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--warmup-steps", type=int, default=300)
    ap.add_argument("--ppo-episodes", type=int, default=60)
    ap.add_argument("--ablation", action="store_true",
                    help="额外跑恒定动作消融，用于确定收益上界（诊断）")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    results = {
        "experiment": "review_mappo_3seed_comparison",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_order": "docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md 阶段 3",
        "config": {
            "seeds": args.seeds,
            "eval_episodes_per_cell": args.episodes,
            "horizon": args.horizon,
            "warmup_steps": args.warmup_steps,
            "ppo_episodes": args.ppo_episodes,
            "schemes": {
                "uniform": "均匀权重（绝对基线 = 灰度关闭现状）",
                "rule": "固定规则 _rule_action_idx（现有规则因子）",
                "supervised": "监督学习 warmup_with_rules（回归规则标签，无 RL）",
                "rl": "warmup 预热 + PPO 微调",
            },
            "discipline": {
                "skip_streak_limit": SKIP_STREAK_LIMIT,
                "review_min_review": REVIEW_MIN_REVIEW,
                "acceptance": "skip 连发 >= 2 发生率必须为 0",
            },
        },
        "per_cell": {},
        "train_stats": [],
        "aggregate_by_scheme": {},
        "degraded": False,
        "notes": [],
    }

    # 评估用 episode 的种子：与训练 seed 派生但独立，避免"自己考自己"
    for scheme in SCHEMES:
        for seed in args.seeds:
            policy = None
            train_stats = None
            if scheme in ("supervised", "rl"):
                policy, train_stats = build_policy(
                    scheme, seed, args.warmup_steps, args.ppo_episodes, args.horizon)
                results["train_stats"].append(train_stats)
                if policy is None:
                    results["degraded"] = True
                    results["notes"].append(
                        f"{scheme}/seed={seed}: torch 不可用，该单元无法评估（如实标注，不伪造）")
                    continue

            eps = []
            rng = random.Random(seed * 1000 + 17)
            for _ in range(args.episodes):
                eseed = rng.randint(1, 10**6)
                eps.append(run_episode(scheme, policy, eseed, args.horizon))

            agg = aggregate(eps)
            results["per_cell"][f"{scheme}/seed={seed}"] = {
                "scheme": scheme, "seed": seed, **agg}

    # 跨 seed 汇总
    for scheme in SCHEMES:
        cells = [v for k, v in results["per_cell"].items() if v["scheme"] == scheme]
        if not cells:
            continue
        n = len(cells)
        def avg(key):
            return sum(c[key] for c in cells) / n
        results["aggregate_by_scheme"][scheme] = {
            "seeds": [c["seed"] for c in cells],
            "mean_return": avg("mean_return"),
            "mean_return_std": (sum((c["mean_return"] - avg("mean_return")) ** 2
                                    for c in cells) / n) ** 0.5,
            "mean_quality_gain": avg("mean_quality_gain"),
            "mean_final_quality": avg("mean_final_quality"),
            "mean_tokens": avg("mean_tokens"),
            "skip_rate": avg("skip_rate"),
            "precision_rate": avg("precision_rate"),
            "max_skip_streak": max(c["max_skip_streak"] for c in cells),
            "discipline_violation_rate": avg("discipline_violation_rate"),
        }

    # 诊断：恒定动作消融（确定"最优恒定策略"上界，解释 RL 收益天花板）
    agg = results["aggregate_by_scheme"]
    if args.ablation:
        abl = {}
        for idx, name in enumerate(REVIEW_ACTIONS):
            cells = []
            for seed in args.seeds:
                rng = random.Random(seed * 1000 + 17)
                eps = [run_episode(f"const:{idx}", None, rng.randint(1, 10**6),
                                   args.horizon) for _ in range(args.episodes)]
                cells.append(aggregate(eps))
            n = len(cells)
            abl[f"{idx}:{name}"] = {
                "mean_return": sum(c["mean_return"] for c in cells) / n,
                "mean_quality_gain": sum(c["mean_quality_gain"] for c in cells) / n,
                "mean_tokens": sum(c["mean_tokens"] for c in cells) / n,
                "precision_rate": sum(c["precision_rate"] for c in cells) / n,
                "skip_rate": sum(c["skip_rate"] for c in cells) / n,
            }
        results["constant_action_ablation"] = abl
        best = max(abl.items(), key=lambda kv: kv[1]["mean_return"])
        results["notes"].append(
            f"诊断：最优恒定动作 = {best[0]}（回报 {best[1]['mean_return']:.4f}）；"
            f"该值即「恒定策略」上界，RL 若未超过它说明未学到上下文自适应增益")
        if "rl" in agg:
            verdict_rl_beats_const = agg["rl"]["mean_return"] >= best[1]["mean_return"]
            results["verdict_pre"] = {
                "rl_beats_best_constant": verdict_rl_beats_const,
                "best_constant": best[0],
                "best_constant_return": best[1]["mean_return"],
                "rl_return": agg["rl"]["mean_return"],
            }

    # 验收判定（攻坚令：RL ≥ 规则 ≥ 监督；纪律违规率为 0）
    agg = results["aggregate_by_scheme"]
    verdict = {"available_schemes": list(agg.keys())}
    # 并入诊断判定（恒定动作上界）
    verdict.update(results.pop("verdict_pre", {}))
    if "rl" in agg and "rule" in agg:
        verdict["rl_ge_rule"] = agg["rl"]["mean_return"] >= agg["rule"]["mean_return"]
        verdict["rl_vs_rule_gain_pct"] = (
            (agg["rl"]["mean_return"] - agg["rule"]["mean_return"])
            / abs(agg["rule"]["mean_return"]) * 100.0
            if agg["rule"]["mean_return"] else None)
    if "rule" in agg and "supervised" in agg:
        verdict["rule_ge_supervised"] = (
            agg["rule"]["mean_return"] >= agg["supervised"]["mean_return"])
    all_viol = [v["discipline_violation_rate"]
                for v in agg.values()]
    verdict["discipline_ok"] = all(v == 0.0 for v in all_viol)
    verdict["max_skip_streak_overall"] = max(
        (v["max_skip_streak"] for v in agg.values()), default=0)
    results["verdict"] = verdict

    if not verdict.get("discipline_ok"):
        results["notes"].append("警告：出现 skip 连发 ≥2 的纪律违规，需回查奖励/硬约束")

    out = args.out or str(
        _ROOT / "experiments" / "results"
        / f"review_mappo_eval_{datetime.now().strftime('%Y%m%d')}.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 控制台对比表
    print("=" * 92)
    print(f"三元评审权重 3-seed 对比   episodes/cell={args.episodes} horizon={args.horizon}")
    print("=" * 92)
    hdr = f"{'方案':<12}{'回报':>10}{'质量增益':>10}{'终态质量':>10}{'token':>10}{'skip率':>9}{'精准率':>9}{'连发':>6}"
    print(hdr)
    print("-" * 92)
    for scheme in SCHEMES:
        if scheme not in agg:
            print(f"{scheme:<12}{'(缺评估数据)':>10}")
            continue
        a = agg[scheme]
        print(f"{scheme:<12}{a['mean_return']:>10.4f}{a['mean_quality_gain']:>10.3f}"
              f"{a['mean_final_quality']:>10.2f}{a['mean_tokens']:>10.1f}"
              f"{a['skip_rate']:>9.3f}{a['precision_rate']:>9.3f}"
              f"{a['max_skip_streak']:>6}")
    if "constant_action_ablation" in results:
        print("\n--- 恒定动作消融（诊断：收益上界）---")
        for k, v in results["constant_action_ablation"].items():
            print(f"  {k:<22} 回报={v['mean_return']:>8.4f}  质量增益={v['mean_quality_gain']:>7.3f}"
                  f"  token={v['mean_tokens']:>7.1f}  skip率={v['skip_rate']:.3f}")
    print("-" * 92)
    for k, v in verdict.items():
        print(f"  {k}: {v}")
    print(f"\n落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
