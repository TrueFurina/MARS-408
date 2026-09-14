"""解析 reward 最优策略：在无噪声环境下逐步取 argmax 动作，统计鲶鱼占比与 token 成本。

目的：判定"成本 ≤ 规则版×1.1"未达标是 **reward 本身与约束冲突**，还是 **PPO 欠收敛**。
  - 若 reward 最优策略的鲶鱼占比就 > 允许上限 → 必须调成本参数（reward 与约束冲突）
  - 若 reward 最优策略成本达标，而 PPO 不达标 → 问题是训练（加预算 / 降方差）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
sys.path.insert(0, str(ROOT))

import copy
from engines import career_policy as cp

ACTIONS = cp.CAREER_ACTIONS


def one_step_reward(env, action_idx):
    """在不污染原 env 的前提下，测该动作的一步奖励"""
    probe = copy.deepcopy(env)
    _f, r, _d = probe.step(action_idx)
    return r


def greedy_rollout(seed=1, horizon=8):
    env = cp.CareerAdversaryEnv(seed=seed, horizon=horizon)
    env.noisy = False          # 去掉噪声，取确定性最优
    env.reset()
    counts = {n: 0 for n in ACTIONS}
    tokens = 0.0
    total_r = 0.0
    for _ in range(horizon):
        best_a, best_r = 0, None
        for a in range(len(ACTIONS)):
            r = one_step_reward(env, a)
            if best_r is None or r > best_r + 1e-12:
                best_a, best_r = a, r
        counts[ACTIONS[best_a]] += 1
        tokens += env.MODE_TOKENS[ACTIONS[best_a]]
        _f, r, done = env.step(best_a)
        total_r += r
        if done:
            break
    return counts, tokens / horizon, total_r / horizon


print("=" * 78)
print("[解析] reward 最优（逐步 argmax）策略的行为")
print("=" * 78)
all_cat, all_cost = [], []
for seed in (1, 42, 2024, 7, 99):
    counts, cost, ret = greedy_rollout(seed)
    frac = counts["catfish"] / sum(counts.values())
    all_cat.append(frac)
    all_cost.append(cost)
    print(f"  seed={seed:>4}  动作={counts}  鲶鱼占比={frac:.1%}  平均token={cost:.0f}  "
          f"平均奖励={ret:+.5f}")

print()
print("=" * 78)
print("[对比] 规则版成本与允许上限")
print("=" * 78)
rule_counts = {"normal": 0, "escalating": 0, "catfish": 0}
rule_tokens = 0.0
N = 40
for i in range(N):
    env = cp.CareerAdversaryEnv(seed=1 * 100000 + i, horizon=8)
    feats = env.reset()
    for _ in range(8):
        idx = cp._rule_action_idx(feats)
        rule_counts[ACTIONS[idx]] += 1
        rule_tokens += env.MODE_TOKENS[ACTIONS[idx]]
        feats, _r, done = env.step(idx)
        if done:
            break
rule_cost = rule_tokens / (N * 8)
print(f"  规则版: 动作={rule_counts}  平均token={rule_cost:.0f}  上限(×1.1)={rule_cost * 1.1:.0f}")
print()
print(f"  reward 最优平均 token = {sum(all_cost) / len(all_cost):.0f}  "
      f"→ {'达标' if sum(all_cost) / len(all_cost) <= rule_cost * 1.1 else '不达标（reward 与约束冲突）'}")
print(f"  reward 最优平均鲶鱼占比 = {sum(all_cat) / len(all_cat):.1%}")
print(f"  MODE_TOKENS = {cp.CareerAdversaryEnv.MODE_TOKENS}")
