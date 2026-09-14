# -*- coding: utf-8 -*-
"""诊断脚本：在不改动业务代码的前提下，真实跑出当前（已播种）代码的基线数字，
确认两个核心问题：
  (1) review_policy: RL 是否真 < 均匀/规则基线（环境是否让"按上下文选档"无可学增益）
  (2) career_policy:  规则基线是否 100% normal（P3③ 鲶鱼机制阈值是否不可达）
"""
import json
import sys
from pathlib import Path

# 把 py-server 根目录加入 sys.path（pytest 通过 rootdir 自动加，直接跑脚本需手动加），
# 否则 `import config` 会解析到其它位置的同名模块（"unknown location"）。
_ROOT = Path(__file__).resolve().parent.parent / "py-server"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import torch  # 确认 torch 可用

from engines import review_policy as rp
from engines import career_policy as cp

SEEDS = [1, 42, 2024]
H = 6  # review horizon
CH = 8  # career horizon


def fixed_action_return(env_cls, action, seed, horizon):
    env = env_cls(seed=seed, horizon=horizon)
    s = env.reset()
    total = 0.0
    for _ in range(horizon):
        s, r, done = env.step(action)
        total += r
        if done:
            break
    return total


def review_eval(seed):
    """单个 seed 下三方案平均回报（无噪声固定便于比较：noisy=False）。"""
    env = rp.ReviewEnv(seed=seed, horizon=H, noisy=False)
    pol = rp.ReviewWeightPolicy(seed=seed)
    pol.warmup_with_rules(rp.ReviewEnv(seed=seed, noisy=False), steps=400, seed=seed)
    pol.train_ppo(rp.ReviewEnv(seed=seed, horizon=H, noisy=False), episodes=80, horizon=H, seed=seed)
    rl = rp.evaluate_policy(pol, rp.ReviewEnv(seed=seed, horizon=H, noisy=False), horizon=H)
    rule = rp.evaluate_policy("rule", rp.ReviewEnv(seed=seed, horizon=H, noisy=False), horizon=H)
    uni = rp.evaluate_policy("uniform", rp.ReviewEnv(seed=seed, horizon=H, noisy=False), horizon=H)
    return {"seed": seed, "rl": rl["mean_return"], "rule": rule["mean_return"],
            "uniform": uni["mean_return"],
            "rl_rule_gap_pct": 100 * (rl["mean_return"] - rule["mean_return"]) / max(1e-9, rule["mean_return"]),
            "rl_uni_gap_pct": 100 * (rl["mean_return"] - uni["mean_return"]) / max(1e-9, uni["mean_return"]),
            "rl_skip": rl["skip_count"], "rl_discipline_violation": rl["discipline_violation"]}


def fixed_action_table_review():
    print("=== [ReviewEnv] 固定动作全程回报（noisy=False, 各 seed 取 mean）===")
    table = {}
    for a in range(5):
        vals = [fixed_action_return(rp.ReviewEnv, a, s, H) for s in SEEDS]
        table[rp.REVIEW_ACTIONS[a]] = sum(vals) / len(vals)
    for k, v in sorted(table.items(), key=lambda x: -x[1]):
        print(f"  {k:14s} mean_return={v:+.4f}")
    return table


def career_rule_mode_distribution(seed):
    """规则基线单 seed 全轨迹模式分布 + 鲶鱼是否触发（streak>=CATFISH_MAX_CONTINUE）。"""
    env = cp.CareerAdversaryEnv(seed=seed, horizon=CH)
    s = env.reset()
    modes = []
    streak = 0
    catfish_activated = False
    for _ in range(CH):
        a = cp._rule_action_idx(s)
        mode = cp.CAREER_ACTIONS[a]
        modes.append(mode)
        streak = streak + 1 if mode == "catfish" else 0
        if streak >= cp.CATFISH_MAX_CONTINUE:
            catfish_activated = True
        s, _r, done = env.step(a)
        if done:
            break
    return modes, catfish_activated


def career_eval(seed):
    env = cp.CareerAdversaryEnv(seed=seed, horizon=CH)
    pol = cp.CareerModePolicy(seed=seed)
    pol.warmup_with_rules(cp.CareerAdversaryEnv(seed=seed), steps=400, seed=seed)
    # 简单 PPO 复用（career_policy 当前无 train_ppo，用规则预热即已 trained）
    total, catfish, streak = 0.0, 0, 0
    feats = env.reset()
    for _ in range(CH):
        a, _src = pol.select_action(feats, deterministic=True)
        mode = cp.CAREER_ACTIONS[a]
        streak = streak + 1 if mode == "catfish" else 0
        if mode == "catfish":
            catfish += 1
        feats, r, done = env.step(a)
        total += r
        if done:
            break
    return {"seed": seed, "total_return": total, "catfish_selected": catfish,
            "max_streak": streak, "catfish_activated": streak >= cp.CATFISH_MAX_CONTINUE}


print("torch:", torch.__version__)
print()
print("############ DIAGNOSIS 1: review_policy ############")
fa = fixed_action_table_review()
print()
rv = [review_eval(s) for s in SEEDS]
print("=== [Review] 3-seed RL vs rule vs uniform ===")
for r in rv:
    print(f"  seed={r['seed']:5d}  RL={r['rl']:+.4f}  rule={r['rule']:+.4f}  uniform={r['uniform']:+.4f}"
          f"  | RL-rule={r['rl_rule_gap_pct']:+.2f}%  RL-uni={r['rl_uni_gap_pct']:+.2f}%"
          f"  skip={r['rl_skip']} viol={r['rl_discipline_violation']}")
import statistics as st
print(f"  >>> mean RL-uni gap = {st.mean(r['rl_uni_gap_pct'] for r in rv):+.2f}%  "
      f"(目标：>0 即 RL 可达基线之上)")
print()
print("############ DIAGNOSIS 2: career_policy ############")
print("=== [Career] 规则基线各 seed 模式轨迹 + 鲶鱼阈值可达性 ===")
for s in SEEDS + [2025]:
    modes, activated = career_rule_mode_distribution(s)
    from collections import Counter
    c = Counter(modes)
    print(f"  seed={s:5d}  modes={modes}  dist={dict(c)}  catfish_activated={activated}")
print()
print("=== [Career] RL(warmup) 3-seed ===")
cv = [career_eval(s) for s in SEEDS]
for r in cv:
    print(f"  seed={r['seed']:5d}  return={r['total_return']:+.4f}  catfish_selected={r['catfish_selected']}"
          f"  max_streak={r['max_streak']}  activated={r['catfish_activated']}")

summary = {
    "review_fixed_action": fa,
    "review_3seed": rv,
    "career_rule_modes": {s: career_rule_mode_distribution(s)[0] for s in SEEDS + [2025]},
    "career_rl_3seed": cv,
}
out = Path("experiments/results/diag_current.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print("\n诊断结果落盘:", out)
