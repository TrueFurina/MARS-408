# ============================================================
# run_shadow_probe — 三元评审权重 MAPPO 影子探针驱动脚本（角色 C · 看效果）
#
# 用法：
#   PYTHONPATH=. .venv/Scripts/python.exe experiments/run_shadow_probe.py \
#       --samples 240 --seeds 7,42,2026 --warmup-steps 300 --ppo-episodes 50 --horizon 6 \
#       --out experiments/results
#
# 行为：
#   1. 多 seed 预训影子策略（真 PPO，确定性播种）
#   2. 生成贴近真实的评审上下文样本（evidence/consensus/state/critic 字段真实形态）
#   3. 对每条样本跑 observe() 旁路观测，落盘 JSONL + summary JSON
#   4. 打印效果快照（真实复算，不编造）
#
# 不变式：仅观测不干预；真实决策链路不受任何影响。
# ============================================================

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.review_shadow_probe import (  # noqa: E402
    build_shadow_policy,
    observe,
    summarize,
)


def generate_samples(n: int, rng: random.Random) -> list[dict]:
    """生成贴近真实的评审上下文样本（字段形态与线上一致）。"""
    samples = []
    for i in range(n):
        status = rng.choice(["pass", "conflict", "none"])
        has_overall = (status != "none") and (rng.random() < 0.8)
        samples.append({
            "id": i,
            "evidence": {
                "consistency_score": round(rng.uniform(30, 100), 1),
                "coverage": rng.randint(0, 8),
                "expected_coverage": max(1, rng.randint(2, 8)),
            },
            "critic": {
                "confidence": round(rng.uniform(0.2, 0.95), 3),
                "valid_count": rng.randint(0, 5),
                "invalid_count": rng.randint(0, 5),
            },
            "consensus": {
                "status": status,
                "confidence_score": round(rng.uniform(0.3, 0.95), 3),
                "overall_score": round(rng.uniform(40, 95), 1) if has_overall else None,
                "disagreement": round(rng.uniform(0.0, 1.0), 3),
            },
            "state": {
                "gate_retry_count": rng.randint(0, 3),
                "token_budget": rng.choice([2000, 4000]),
                "tokens_used": 0.0,
                "last_consistency": round(rng.uniform(30, 100), 1),
                "disagreement": round(rng.uniform(0.0, 1.0), 3),
            },
            "mode_encoding": round(rng.uniform(0.0, 1.0), 3),
            "round_ratio": round(rng.uniform(0.0, 1.0), 3),
        })
        # tokens_used 与 budget 相关
        budget = samples[-1]["state"]["token_budget"]
        samples[-1]["state"]["tokens_used"] = round(rng.uniform(0, budget), 1)
    return samples


def main():
    ap = argparse.ArgumentParser(description="三元评审权重 MAPPO 影子探针（仅观测）")
    ap.add_argument("--samples", type=int, default=240)
    ap.add_argument("--seeds", type=str, default="7,42,2026")
    ap.add_argument("--warmup-steps", type=int, default=300)
    ap.add_argument("--ppo-episodes", type=int, default=3000,
                    help="PPO 训练 episode 数。默认 3000（batch 48 → 约 62 次梯度更新）："
                         "实测更新次数是结论决定性超参——5 次更新时影子 68.445 输给规则 68.948，"
                         "63 次更新时影子 69.896 胜规则；旧默认 50 会把影子静默饿死")
    ap.add_argument("--ppo-batch", type=int, default=0,
                    help="PPO 每次更新的轨迹条数；0=按 episodes 自动推导（min(48, episodes//10)）")
    ap.add_argument("--horizon", type=int, default=32)
    ap.add_argument("--data-seed", type=int, default=20260914)
    ap.add_argument("--env", type=str, default="calibrated", choices=["legacy", "calibrated"],
                    help="影子策略的训练环境：legacy=原 ReviewEnv（合成阶梯）；"
                         "calibrated=校准环境（奖励=生产同款真实增益，balanced 恒 0）")
    ap.add_argument("--out", type=str, default="experiments/results")
    ap.add_argument("--no-train", action="store_true",
                    help="跳过 PPO 训练，影子退化为规则等价（快速自检用）")
    args = ap.parse_args()

    seed_list = [int(s) for s in args.seeds.split(",") if s.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    env_factory = None
    if args.env == "calibrated":
        from engines.review_env_calibrated import CalibratedReviewEnv
        env_factory = lambda sd, hz: CalibratedReviewEnv(seed=sd, horizon=hz)  # noqa: E731

    print(f"[shadow] 预训影子策略 seeds={seed_list} env={args.env} "
          f"(warmup={args.warmup_steps}, ppo={args.ppo_episodes}, "
          f"batch={args.ppo_batch or 'auto'}, horizon={args.horizon}) ...")
    shadow_policies = []
    n_updates = []
    for sd in seed_list:
        if args.no_train:
            from engines.review_policy import ReviewWeightPolicy
            try:
                import torch
                torch.set_num_threads(1)
            except Exception:
                pass
            p = ReviewWeightPolicy(seed=sd)
        else:
            p = (build_shadow_policy(sd, args.warmup_steps, args.ppo_episodes,
                                     args.horizon, env_factory=env_factory)
                 if args.ppo_batch <= 0 else
                 build_shadow_policy(sd, args.warmup_steps, args.ppo_episodes,
                                     args.horizon, env_factory=env_factory,
                                     batch_episodes=args.ppo_batch))
        _st = getattr(p, "_last_train_stats", {}) or {}
        n_updates.append(_st.get("n_updates"))
        trained = getattr(p, "_trained", False)
        torch_ok = getattr(p, "torch_available", False)
        print(f"  seed={sd}: torch_available={torch_ok} trained={trained} "
              f"n_updates={_st.get('n_updates')} batch={_st.get('batch_episodes')}")
        shadow_policies.append(p)

    rng = random.Random(args.data_seed)
    samples = generate_samples(args.samples, rng)
    print(f"[shadow] 生成 {len(samples)} 条真实形态样本，开始旁路观测 ...")

    records = []
    for s in samples:
        rec = observe(
            evidence=s["evidence"], consensus=s["consensus"], state=s["state"],
            critic=s["critic"], shadow_policies=shadow_policies,
            skip_streak=0, reviews_done=0,
            mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"])
        rec["sample_id"] = s["id"]
        records.append(rec)

    summary = summarize(records)
    summary["meta"] = {
        "source": "run_shadow_probe.py (shadow observer, read-only)",
        "generated_at": ts,
        "n_samples": args.samples,
        "shadow_seeds": seed_list,
        "warmup_steps": args.warmup_steps,
        "ppo_episodes": args.ppo_episodes,
        "horizon": args.horizon,
        "data_seed": args.data_seed,
        "train_env": args.env,
        # 有效训练预算必须落盘：否则"RL 输给规则"的结论无法区分
        # "方法不行"与"根本没训够"。
        "ppo_batch_episodes": args.ppo_batch or "auto",
        "n_updates_per_seed": n_updates,
        "note": "delta = 影子有效分 − 基线有效分；正=相对基线质量提升（真实 weighted_consistency_score 复算）",
    }

    jsonl_path = out_dir / f"review_shadow_{ts}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary_path = out_dir / f"review_shadow_summary_{ts}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n================= 影子探针效果快照 =================")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("===================================================")
    print(f"[shadow] JSONL : {jsonl_path}")
    print(f"[shadow] 汇总 : {summary_path}")


if __name__ == "__main__":
    main()
