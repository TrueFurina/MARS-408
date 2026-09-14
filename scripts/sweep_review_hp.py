"""扫训练超参：找出能让 RL 稳定超过规则版的配置（固定上下文集，公平对比）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
sys.path.insert(0, str(ROOT))

from engines import review_policy as rp

NAMES = rp.REVIEW_ACTIONS
N_CTX, HORIZON = 400, 6


def collect_contexts(seed=2024, n=N_CTX):
    out = []
    for i in range(n):
        env = rp.ReviewEnv(seed=seed * 100000 + i, horizon=HORIZON)
        feats = env.reset()
        steps = []
        for _ in range(HORIZON):
            steps.append((list(feats), env._true_best()))
            feats, _r, _d = env.step(3)
        out.append(steps)
    return out


def payoff(action, best, consistency):
    if action == 4:
        gain = rp.REV_GAIN_SKIP
    elif action == best:
        gain = rp.REV_GAIN_MATCHED
    elif action == 3:
        gain = rp.REV_GAIN_BALANCED
    else:
        gain = rp.REV_GAIN_MISMATCH
    precision = True if consistency >= 0.5 else (action != 4)
    return rp.review_reward(0.0, float(gain), precision, rp.ACTION_TOKENS[action], 0)


def score(decide, ctxs):
    correct = total = 0
    ret = 0.0
    for steps in ctxs:
        for feats, best in steps:
            a = decide(feats)
            correct += 1 if a == best else 0
            total += 1
            ret += payoff(a, best, feats[1])
    return ret / total, correct / total


ctxs = collect_contexts()
rule_r, rule_a = score(lambda f: rp._rule_action_idx(f), ctxs)
bal_r, bal_a = score(lambda f: 3, ctxs)
print(f"参照: 规则={rule_r:+.4f}(acc {rule_a:.3f})  balanced-always={bal_r:+.4f}(acc {bal_a:.3f})")
print()
print(f"{'episodes':>9} {'batch':>6} {'lr':>8} {'epochs':>7} | "
      f"{'RL(s1)':>8} {'RL(s42)':>8} {'RL(s2024)':>9} | 全部>规则?")
print("-" * 78)

for episodes, batch, lr, epochs in [
    (400, 12, 3e-4, 4),
    (1500, 12, 3e-4, 4),
    (1500, 24, 1e-4, 6),
    (3000, 24, 1e-4, 6),
    (3000, 48, 3e-4, 4),
    (6000, 48, 1e-4, 4),
]:
    row = []
    for seed in (1, 42, 2024):
        p = rp.ReviewWeightPolicy(seed=seed, lr=lr)
        p.warmup_with_rules(rp.ReviewEnv(seed=seed, horizon=HORIZON), steps=400, seed=seed)
        p.train_ppo(rp.ReviewEnv(seed=seed, horizon=HORIZON), episodes=episodes,
                    horizon=HORIZON, seed=seed, epochs=epochs, batch_episodes=batch)
        r, a = score(lambda f, _p=p: _p.select_action(
            f, deterministic=True, skip_streak=0, reviews_done=9)[0], ctxs)
        row.append((r, a))
    ok = all(r > rule_r for r, _a in row)
    print(f"{episodes:>9} {batch:>6} {lr:>8} {epochs:>7} | "
          f"{row[0][0]:>+8.4f} {row[1][0]:>+8.4f} {row[2][0]:>+9.4f} | {ok}")
    print(f"{'':>9} {'':>6} {'':>8} {'':>7} | acc "
          f"{row[0][1]:>0.3f}   {row[1][1]:>0.3f}    {row[2][1]:>0.3f}")
