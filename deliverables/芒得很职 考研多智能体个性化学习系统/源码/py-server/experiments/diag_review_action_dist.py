# ============================================================
# diag_review_action_dist — 评审权重策略动作分布诊断（角色 B · 训练侧诊断）
#
# 为什么需要它：docs/B-阶段2 报告中的"RL 动作分布 100% balanced"最初来自一次性
#   inline 命令，无法复算。凡对外引用的数字必须有可复算脚本 + 落盘 JSON。
#
# 它回答的问题：RL 到底学到了什么？
#   - 若分布集中在单一动作 → 策略退化为恒定动作，状态条件化未带来信息增益；
#   - 与"恒定动作消融上界"交叉验证：若退化动作恰是最优恒定动作，
#     则该环境下收益空间为 0，调参无效（见 review_mappo_ablation_*.json）。
#
# 诚信约束：torch 不可用时如实标注 degraded，不伪造分布；结果落盘
#   experiments/results/review_action_dist_YYYYMMDD.json，不落盘不对外引用。
# ============================================================

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.review_policy import (  # noqa: E402
    REVIEW_ACTIONS,
    ReviewEnv,
    ReviewWeightPolicy,
    _rule_action_idx,
)

RESULTS_DIR = _ROOT / "experiments" / "results"


def _dist_to_dict(counter: Counter, total: int) -> dict:
    return {
        REVIEW_ACTIONS[k]: round(v / total, 4)
        for k, v in sorted(counter.items())
    }


def collect(policy: ReviewWeightPolicy, env: ReviewEnv,
            episodes: int, horizon: int) -> dict:
    """在给定环境上统计 (RL, 规则) 两个决策方式的动作分布。"""
    rl_cnt: Counter = Counter()
    rule_cnt: Counter = Counter()
    for _ in range(episodes):
        s = env.reset()
        for _ in range(horizon):
            a, _src = policy.select_action(s, deterministic=True)
            rl_cnt[a] += 1
            rule_cnt[_rule_action_idx(s)] += 1
            s, _r, done = env.step(a)
            if done:
                break
    tot_rl = sum(rl_cnt.values()) or 1
    tot_rule = sum(rule_cnt.values()) or 1
    return {
        "rl": _dist_to_dict(rl_cnt, tot_rl),
        "rule": _dist_to_dict(rule_cnt, tot_rule),
        "samples": tot_rl,
        "rl_distinct_actions": len(rl_cnt),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="评审权重策略动作分布诊断")
    ap.add_argument("--train-seed", type=int, default=42,
                    help="策略训练 seed（warmup + PPO）")
    ap.add_argument("--eval-seed", type=int, default=999,
                    help="评估环境 seed（与训练 seed 不同，检验泛化而非记忆）")
    ap.add_argument("--episodes", type=int, default=30)
    ap.add_argument("--horizon", type=int, default=6)
    ap.add_argument("--warmup-steps", type=int, default=300)
    ap.add_argument("--ppo-episodes", type=int, default=60)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    policy = ReviewWeightPolicy()
    degraded = not policy.torch_available
    policy.warmup_with_rules(ReviewEnv(seed=args.train_seed),
                             steps=args.warmup_steps, seed=args.train_seed)
    policy.train_ppo(ReviewEnv(seed=args.train_seed),
                     episodes=args.ppo_episodes, seed=args.train_seed)

    env = ReviewEnv(seed=args.eval_seed, horizon=args.horizon)
    dist = collect(policy, env, args.episodes, args.horizon)

    top_action, top_share = max(dist["rl"].items(), key=lambda kv: kv[1])
    result = {
        "experiment": "review_action_dist",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "train_seed": args.train_seed,
            "eval_seed": args.eval_seed,
            "episodes": args.episodes,
            "horizon": args.horizon,
            "warmup_steps": args.warmup_steps,
            "ppo_episodes": args.ppo_episodes,
        },
        "degraded": degraded,
        "action_dist": dist,
        "verdict": {
            "rl_top_action": top_action,
            "rl_top_share": top_share,
            # 单一动作占比 >= 0.99 视为完全退化（RL 未利用状态信息）
            "rl_degenerated": bool(top_share >= 0.99),
        },
        "notes": [
            "degraded=True 表示 torch 不可用，分布来自规则层而非训练后网络，不可用于结论。",
            "rl 与 rule 分布需结合消融上界（review_mappo_ablation_*.json）一并解读。",
        ],
    }

    out = Path(args.out) if args.out else (
        RESULTS_DIR / f"review_action_dist_{datetime.now():%Y%m%d}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    print("=" * 78)
    print(f"评审权重动作分布诊断  train_seed={args.train_seed} "
          f"eval_seed={args.eval_seed} episodes={args.episodes}")
    print("=" * 78)
    print(f"  degraded            : {result['degraded']}")
    print(f"  RL   分布           : {dist['rl']}")
    print(f"  规则 分布           : {dist['rule']}")
    print(f"  RL top action       : {top_action} (share={top_share})")
    print(f"  rl_degenerated      : {result['verdict']['rl_degenerated']}")
    print("-" * 78)
    print(f"落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
