"""诊断评审 RL 为何打不过规则：在同一批上下文上对比 各方案的动作正确率与平均奖励。

关键：把"上下文"与"方案"解耦 —— 固定一批 env 上下文，分别让
  oracle（选 env 真最优）/ balanced-always / 规则 / 监督(warmup) / RL(warmup+PPO)
决策，统计正确率与平均奖励，才能看出 RL 到底学到了什么。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
sys.path.insert(0, str(ROOT))

from engines import review_policy as rp

NAMES = rp.REVIEW_ACTIONS
N_CTX = 600
HORIZON = 6


def collect_contexts(seed=2024, n=N_CTX):
    """采集固定上下文（每 episode 一条），记录每步的观测与该步真最优。"""
    out = []
    for i in range(n):
        env = rp.ReviewEnv(seed=seed * 100000 + i, horizon=HORIZON)
        feats = env.reset()
        steps = []
        for _ in range(HORIZON):
            best = env._true_best()
            steps.append((list(feats), best))
            feats, _r, _d = env.step(3)  # 用 balanced 推进（推进与所选动作无关）
        out.append(steps)
    return out


def payoff(action, best, consistency):
    """单步奖励（复刻 env.step 的奖励计算）"""
    tokens = rp.ACTION_TOKENS[action]
    if action == 4:
        gain = rp.REV_GAIN_SKIP
    elif action == best:
        gain = rp.REV_GAIN_MATCHED
    elif action == 3:
        gain = rp.REV_GAIN_BALANCED
    else:
        gain = rp.REV_GAIN_MISMATCH
    precision = True if consistency >= 0.5 else (action != 4)
    return rp.review_reward(0.0, float(gain), precision, tokens, 0)


def evaluate(name, decide, ctxs):
    correct, total, ret, counts = 0, 0, 0.0, {n: 0 for n in NAMES}
    for steps in ctxs:
        for feats, best in steps:
            a = decide(feats)
            counts[NAMES[a]] += 1
            correct += 1 if a == best else 0
            total += 1
            ret += payoff(a, best, feats[1])
    # 真最优与恒 balanced 的参照
    return {"acc": correct / total, "mean_reward": ret / total, "counts": counts}


print("=" * 78)
print(f"[评审] 固定 {N_CTX} 条上下文 × {HORIZON} 步，同一批样本上横向对比")
print("=" * 78)

ctxs = collect_contexts()

# 参照：真最优
ref_best, ref_bal = 0.0, 0.0
n = 0
for steps in ctxs:
    for feats, best in steps:
        ref_best += payoff(best, best, feats[1])
        ref_bal += payoff(3, best, feats[1])
        n += 1
print(f"  参照上限 oracle(真最优)      奖励={ref_best / n:+.4f}  acc=1.000")
print(f"  参照     balanced-always     奖励={ref_bal / n:+.4f}  "
      f"acc={sum(1 for s in ctxs for f, b in s if b == 3) / n:.3f}")

results = {}
results["oracle"] = {"mean_reward": ref_best / n, "acc": 1.0}
results["balanced"] = {"mean_reward": ref_bal / n}

for label, decide in [("规则", lambda f: rp._rule_action_idx(f))]:
    r = evaluate(label, decide, ctxs)
    results[label] = r
    print(f"  B  {label:<24} 奖励={r['mean_reward']:+.4f}  acc={r['acc']:.3f}  "
          f"动作={ {k: v for k, v in r['counts'].items() if v} }")

for seed in (1, 42, 2024):
    p = rp.ReviewWeightPolicy(seed=seed)
    p.warmup_with_rules(rp.ReviewEnv(seed=seed, horizon=HORIZON), steps=400, seed=seed)
    r_sup = evaluate(f"监督(seed={seed})", lambda f, _p=p: _p.select_action(
        f, deterministic=True, skip_streak=0, reviews_done=9)[0], ctxs)
    p.train_ppo(rp.ReviewEnv(seed=seed, horizon=HORIZON), episodes=400,
                horizon=HORIZON, seed=seed)
    r_rl = evaluate(f"RL(seed={seed})", lambda f, _p=p: _p.select_action(
        f, deterministic=True, skip_streak=0, reviews_done=9)[0], ctxs)
    results[f"supervised_{seed}"] = r_sup
    results[f"rl_{seed}"] = r_rl
    print(f"  C  监督(seed={seed:<4})          奖励={r_sup['mean_reward']:+.4f}  "
          f"acc={r_sup['acc']:.3f}")
    print(f"  A  RL(seed={seed:<4})            奖励={r_rl['mean_reward']:+.4f}  "
          f"acc={r_rl['acc']:.3f}  动作={ {k: v for k, v in r_rl['counts'].items() if v} }")

print("\n" + "=" * 78)
print("[评审] 真最优档位的先验分布（环境实际要求的动作比例）")
print("=" * 78)
prior = {n: 0 for n in NAMES}
for steps in ctxs:
    for _f, b in steps:
        prior[NAMES[b]] += 1
tot = sum(prior.values())
for k, v in prior.items():
    print(f"  {k:<16} {v / tot:.3f}")
