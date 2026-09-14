"""真实跑验证：确认角色 B（评审权重）+ P3③（career 鲶鱼）的验收目标是否可达。

严格按设计文档定义的三方案与 seed：
  评审（攻坚令阶段 3）: A=RL / B=固定规则 / C=监督学习，seeds 1/42/2024
      验收：RL ≥ 规则 ≥ 监督（或诚实报告不成立）
      纪律：skip 连发 ≥2 发生率为 0
  鲶鱼（P3③ 设计文档验收表）: seeds 1/42/2024
      验收：RL 奖励 ≥ 规则；证据密度 ≥ 规则；成本 ≤ 规则×1.1；鲶鱼连压 >2 为 0

所有数字来自真实 torch 运行，落盘 JSON。torch 不可用 → 如实标注降级。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
sys.path.insert(0, str(ROOT))

import torch  # 确认 torch 可用

from engines import review_policy as rp
from engines import career_policy as cp

SEEDS = [1, 42, 2024]
EPISODES = 40          # 每方案评估 episode 数（上下文每 episode 重采样，需平均）
OUT_DIR = Path(__file__).resolve().parent.parent / "experiments" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ────────────────────────────────────────────────────────────
# 通用：多 episode 评估（返回回报 / 动作分布 / 纪律指标）
# ────────────────────────────────────────────────────────────
# 纪律护栏（三方案一视同仁）：直接复用生产**唯一实现**。
# 本脚本原先自行复刻了一份 —— 复刻体不会随生产修差一而同步，属同类缺陷，已清除。
# 保留 `_guard` 别名，使下方调用处无需改动。
_guard = rp.discipline_gate


def run_review_episodes(select_fn, seed, horizon=6, episodes=EPISODES):
    """select_fn(feats, skip_streak, reviews_done) -> idx（未含护栏，本函数统一施加）"""
    total, counts = 0.0, {n: 0 for n in rp.REVIEW_ACTIONS}
    max_streak, skips = 0, 0
    for i in range(episodes):
        env = rp.ReviewEnv(seed=seed * 100000 + i, horizon=horizon)
        feats = env.reset()
        streak, reviewed = 0, 0
        for _ in range(horizon):
            idx = _guard(select_fn(feats, streak, reviewed), feats, streak, reviewed)
            counts[rp.REVIEW_ACTIONS[idx]] += 1
            if idx == 4:
                skips += 1
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
                reviewed += 1
            feats, r, done = env.step(idx)
            total += r
            if done:
                break
    return {"mean_return": total / (episodes * horizon), "counts": counts,
            "max_skip_streak": max_streak, "skips": skips}


# ────────────────────────────────────────────────────────────
# 1. 评审：A=RL / B=规则 / C=监督，3-seed
# ────────────────────────────────────────────────────────────
def verify_review():
    print("=" * 78)
    print("[评审] A=RL vs B=固定规则 vs C=监督学习（严格按攻坚令阶段 3 定义）")
    print("=" * 78)
    rows = []
    for seed in SEEDS:
        # A: RL = warmup + PPO
        p_rl = rp.ReviewWeightPolicy(seed=seed)
        p_rl.warmup_with_rules(rp.ReviewEnv(seed=seed, horizon=6), steps=400, seed=seed)
        # 训练预算 = 扫参最稳档（3000 episodes / batch 48）；见 train_ppo docstring
        ppo = p_rl.train_ppo(rp.ReviewEnv(seed=seed, horizon=6), episodes=3000,
                             horizon=6, seed=seed, batch_episodes=48)
        a = run_review_episodes(
            lambda f, s, r: p_rl.select_action(
                f, deterministic=True, skip_streak=s, reviews_done=r)[0], seed)

        # C: 监督 = 仅 warmup（离线回归规则标签），不跑 PPO
        p_sup = rp.ReviewWeightPolicy(seed=seed)
        p_sup.warmup_with_rules(rp.ReviewEnv(seed=seed, horizon=6), steps=400, seed=seed)
        c = run_review_episodes(
            lambda f, s, r: p_sup.select_action(
                f, deterministic=True, skip_streak=s, reviews_done=r)[0], seed)

        # B: 固定规则
        b = run_review_episodes(lambda f, s, r: rp._rule_action_idx(f), seed)

        ok = a["mean_return"] >= b["mean_return"] and b["mean_return"] >= c["mean_return"]
        disc_ok = max(a["max_skip_streak"], b["max_skip_streak"],
                      c["max_skip_streak"]) < rp.SKIP_STREAK_LIMIT
        print(f"  seed={seed:>5}  A(RL)={a['mean_return']:+.4f}  B(规则)={b['mean_return']:+.4f}  "
              f"C(监督)={c['mean_return']:+.4f}  {'OK' if ok else 'FAIL'}  "
              f"纪律{'OK' if disc_ok else 'FAIL'}")
        print(f"              RL 动作={ {k: v for k, v in a['counts'].items() if v} }")
        print(f"              规则动作={ {k: v for k, v in b['counts'].items() if v} }")
        print(f"              max_skip_streak A/B/C="
              f"{a['max_skip_streak']}/{b['max_skip_streak']}/{c['max_skip_streak']}"
              f"  ppo_improved={ppo['improved']}")
        rows.append({
            "seed": seed,
            "rl": a["mean_return"], "rule": b["mean_return"], "supervised": c["mean_return"],
            "rl_ge_rule": a["mean_return"] >= b["mean_return"],
            "rule_ge_supervised": b["mean_return"] >= c["mean_return"],
            "reachable": ok, "discipline_ok": disc_ok,
            "rl_actions": a["counts"], "rule_actions": b["counts"],
            "max_skip_streak": {"rl": a["max_skip_streak"], "rule": b["max_skip_streak"],
                                "supervised": c["max_skip_streak"]},
            "ppo_improved": ppo["improved"],
        })
    all_ok = all(r["reachable"] for r in rows)
    print(f"  >>> 评审验收 RL≥规则≥监督: {'全部成立' if all_ok else '存在不成立'}")
    return {"task": "review", "seeds": SEEDS, "rows": rows, "reachable": all_ok}


# ────────────────────────────────────────────────────────────
# 2. 评审可复现性
# ────────────────────────────────────────────────────────────
def verify_reproducible():
    print("=" * 78)
    print("[可复现性] 同 seed 两次 warmup+PPO 回报曲线必须逐位一致")
    print("=" * 78)
    def run_once(seed):
        p = rp.ReviewWeightPolicy(seed=seed)
        p.warmup_with_rules(rp.ReviewEnv(seed=seed, horizon=6), steps=400, seed=seed)
        out = p.train_ppo(rp.ReviewEnv(seed=seed, horizon=6), episodes=60, horizon=6, seed=seed)
        return [round(x, 8) for x in out["returns"]]
    a, b = run_once(42), run_once(42)
    print(f"  seed=42 两次曲线一致: {a == b}")
    return {"task": "reproducible", "seed": 42, "identical": a == b}


# ────────────────────────────────────────────────────────────
# 3. 鲶鱼：A/B 对比（奖励 / 密度 / 成本 / 纪律）
# ────────────────────────────────────────────────────────────
def run_career_episodes(select_fn, seed, horizon=8, episodes=EPISODES):
    total_r, total_cost = 0.0, 0.0
    counts = {n: 0 for n in cp.CAREER_ACTIONS}
    final_density, max_streak = 0.0, 0
    for i in range(episodes):
        env = cp.CareerAdversaryEnv(seed=seed * 100000 + i, horizon=horizon)
        feats = env.reset()
        streak = 0
        for _ in range(horizon):
            idx = select_fn(feats, streak)
            mode = cp.CAREER_ACTIONS[idx]
            counts[mode] += 1
            total_cost += env.MODE_TOKENS[mode]
            streak = streak + 1 if mode == "catfish" else 0
            max_streak = max(max_streak, streak)
            feats, r, done = env.step(idx)
            total_r += r
            final_density += env.density / horizon   # 每步密度均值（非累加）
            if done:
                break
    n = episodes * horizon
    return {"mean_return": total_r / n, "mean_density": final_density / episodes,
            "mean_tokens": total_cost / n, "counts": counts, "max_catfish_streak": max_streak}


def verify_career():
    print("=" * 78)
    print("[鲶鱼] A=MAPPO vs B=规则版（奖励 / 证据密度 / 成本 / 纪律），3-seed")
    print("=" * 78)
    rows = []
    for seed in SEEDS:
        p = cp.CareerModePolicy(seed=seed)
        p.warmup_with_rules(cp.CareerAdversaryEnv(seed=seed, horizon=8), steps=400, seed=seed)
        ppo = p.train_ppo(cp.CareerAdversaryEnv(seed=seed, horizon=8), episodes=3000,
                          horizon=8, seed=seed, batch_episodes=48)

        def _rl_sel(feats, streak, _p=p):
            idx, _src = _p.select_action(feats, deterministic=True)
            if idx == 2 and feats[4] >= 1.0:  # 复刻 select_action 内纪律护栏
                idx = 0
            return idx

        a = run_career_episodes(_rl_sel, seed)
        b = run_career_episodes(lambda f, s: cp._rule_action_idx(f), seed)

        # C: 监督 = 仅 warmup（模仿规则），不跑 PPO —— 用于证明 A 的增益来自 PPO 而非模仿
        p_sup = cp.CareerModePolicy(seed=seed)
        p_sup.warmup_with_rules(cp.CareerAdversaryEnv(seed=seed, horizon=8), steps=400, seed=seed)

        def _sup_sel(feats, streak, _p=p_sup):
            idx, _src = _p.select_action(feats, deterministic=True)
            if idx == 2 and feats[4] >= 1.0:
                idx = 0
            return idx

        c = run_career_episodes(_sup_sel, seed)

        rew_ok = a["mean_return"] >= b["mean_return"]
        dens_ok = a["mean_density"] >= b["mean_density"]
        cost_ok = a["mean_tokens"] <= b["mean_tokens"] * 1.1
        disc_ok = a["max_catfish_streak"] <= cp.CATFISH_MAX_CONTINUE
        ok = rew_ok and dens_ok and cost_ok and disc_ok
        print(f"  seed={seed:>5}  奖励 A={a['mean_return']:+.5f} B={b['mean_return']:+.5f} "
              f"{'OK' if rew_ok else 'FAIL'} | 密度 A={a['mean_density']:.3f} "
              f"B={b['mean_density']:.3f} {'OK' if dens_ok else 'FAIL'} | 成本 "
              f"A={a['mean_tokens']:.0f} B={b['mean_tokens']:.0f} {'OK' if cost_ok else 'FAIL'}"
              f" | 连压 {a['max_catfish_streak']} {'OK' if disc_ok else 'FAIL'}")
        print(f"              A 动作={a['counts']}  B 动作={b['counts']}  "
              f"C(监督) 动作={c['counts']}  奖励C={c['mean_return']:+.5f}")
        rows.append({"seed": seed, "rl": a, "rule": b, "supervised": c, "reward_ok": rew_ok,
                     "density_ok": dens_ok, "cost_ok": cost_ok, "discipline_ok": disc_ok,
                     "supervised_reward": c["mean_return"],
                     "rl_beats_supervised": a["mean_return"] > c["mean_return"],
                     "reachable": ok})
    all_ok = all(r["reachable"] for r in rows)
    print(f"  >>> 鲶鱼验收: {'全部成立' if all_ok else '存在不成立'}")
    return {"task": "career", "seeds": SEEDS, "rows": rows, "reachable": all_ok}


def main():
    results = {}
    results["review"] = verify_review()
    results["reproducible"] = verify_reproducible()
    results["career"] = verify_career()

    overall = (results["review"]["reachable"] and results["reproducible"]["identical"]
               and results["career"]["reachable"])
    results["overall_reachable"] = overall
    print("=" * 78)
    print(f"总验收: {'ALL REACHABLE' if overall else 'SOME UNREACHABLE'}")
    print("=" * 78)

    out = OUT_DIR / "mappo_reachability_verify.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"落盘: {out}")
    return results


if __name__ == "__main__":
    main()
