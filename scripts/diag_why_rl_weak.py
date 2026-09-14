"""诊断：为什么 RL < 规则？逐步打印动作序列与奖励分量。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
sys.path.insert(0, str(ROOT))

from engines import review_policy as rp
from engines import career_policy as cp

NAMES = rp.REVIEW_ACTIONS


def trace_review(mode, seed=42):
    env = rp.ReviewEnv(seed=seed, horizon=6)
    feats = env.reset()
    seq, rewards = [], []
    for t in range(6):
        if mode == "uniform":
            idx = 3
        elif mode == "rule":
            idx = rp._rule_action_idx(feats)
        else:  # policy
            idx, _ = mode.select_action(feats, deterministic=True)
        true_best = env._true_best()
        feats, r, done = env.step(idx)
        seq.append((t + 1, NAMES[idx], NAMES[true_best], round(r, 3)))
        rewards.append(r)
        if done:
            break
    return seq, sum(rewards)


print("=" * 78)
print("[Review] 逐步轨迹：动作 / 环境真最优 / 奖励")
print("=" * 78)

# warmup-only（不跑 PPO）
p_warm = rp.ReviewWeightPolicy(seed=42)
p_warm.warmup_with_rules(rp.ReviewEnv(seed=42, horizon=6), steps=400, seed=42)
# warmup + PPO
p_ppo = rp.ReviewWeightPolicy(seed=42)
p_ppo.warmup_with_rules(rp.ReviewEnv(seed=42, horizon=6), steps=400, seed=42)
ppo = p_ppo.train_ppo(rp.ReviewEnv(seed=42, horizon=6), episodes=120, horizon=6, seed=42)

for label, mode in [("uniform", "uniform"), ("rule", "rule"),
                    ("warmup-only", p_warm), ("warmup+PPO", p_ppo)]:
    seq, total = trace_review(mode, seed=42)
    print(f"\n{label}: 总回报={total:+.3f} 均值={total/6:+.4f}")
    for t, a, best, r in seq:
        mark = "  " if a == best else "!!"
        print(f"   {mark} t={t} 选={a:<14} 真最优={best:<14} r={r:+.3f}")

print(f"\nPPO improved={ppo['improved']}  前1/3={ppo['mean_return_first_third']:+.3f} "
      f"后1/3={ppo['mean_return_last_third']:+.3f}")

print("\n" + "=" * 78)
print("[Review] 训练后 actor 的动作偏好（各状态下的 argmax）")
print("=" * 78)
import torch
env = rp.ReviewEnv(seed=42, horizon=6)
feats = env.reset()
for t in range(6):
    x = torch.tensor([feats], dtype=torch.float32)
    with torch.no_grad():
        probs = p_ppo._actor(x)[0].tolist()
    print(f"  t={t+1} consistency={feats[1]:.3f} true_best={NAMES[env._true_best()]:<14} "
          f"probs={[round(p,3) for p in probs]}")
    feats, _r, _d = env.step(3)  # 用 balanced 推进以观察后续上下文

print("\n" + "=" * 78)
print("[Career] 逐步轨迹：模式 / 奖励")
print("=" * 78)
CNAMES = cp.CAREER_ACTIONS
for label in ["uniform(normal)", "rule"]:
    env = cp.CareerAdversaryEnv(seed=42, horizon=8)
    feats = env.reset()
    total = 0.0
    rows = []
    for t in range(8):
        idx = 0 if label.startswith("uniform") else cp._rule_action_idx(feats)
        feats, r, done = env.step(idx)
        rows.append((t + 1, CNAMES[idx], round(feats[1], 3), round(r, 4)))
        total += r
        if done:
            break
    print(f"\n{label}: 总={total:+.4f} 均值={total/8:+.4f}")
    for t, m, d, r in rows:
        print(f"   t={t} mode={m:<11} density={d:.3f} r={r:+.4f}")
