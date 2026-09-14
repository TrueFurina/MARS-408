"""栅格搜索 career 环境参数：使 reward 最优策略同时满足文档验收表三条约束。

约束（P3③ 设计文档验收表）：
  RL 奖励 ≥ 规则；证据密度 ≥ 规则；成本 ≤ 规则×1.1；鲶鱼连压 >2 为 0
另加：鲶鱼占比 > 0（机制必须真的被用到，否则"鲶鱼 MAPPO 化"名不副实）
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
sys.path.insert(0, str(ROOT))

from engines import career_policy as cp

ACTIONS = cp.CAREER_ACTIONS
HORIZON = 8
SEEDS = [1, 42, 2024, 7, 99, 555]


def greedy(T_cat, cap_cat, cap_esc, overload):
    """在给定参数下取逐步 argmax，返回 (鲶鱼占比, token/步, 奖励/步, 密度/步)"""
    cp.CAREER_DELTA_CAP["catfish"] = cap_cat
    cp.CAREER_DELTA_CAP["escalating"] = cap_esc
    cp.CAREER_OVERLOAD = overload
    fracs, costs, rets, dens = [], [], [], []
    for seed in SEEDS:
        env = cp.CareerAdversaryEnv(seed=seed, horizon=HORIZON)
        env.noisy = False
        env.MODE_TOKENS = {"normal": 600.0, "escalating": 900.0, "catfish": T_cat}
        env.reset()
        counts = {n: 0 for n in ACTIONS}
        tok = ret = dn = 0.0
        for _ in range(HORIZON):
            best_a, best_r = 0, None
            for a in range(len(ACTIONS)):
                probe = copy.deepcopy(env)
                _f, r, _d = probe.step(a)
                if best_r is None or r > best_r + 1e-12:
                    best_a, best_r = a, r
            counts[ACTIONS[best_a]] += 1
            tok += env.MODE_TOKENS[ACTIONS[best_a]]
            _f, r, _d = env.step(best_a)
            ret += r
            dn += env.density
        fracs.append(counts["catfish"] / HORIZON)
        costs.append(tok / HORIZON)
        rets.append(ret / HORIZON)
        dens.append(dn / HORIZON)
    return (sum(fracs) / len(fracs), sum(costs) / len(costs),
            sum(rets) / len(rets), sum(dens) / len(dens),
            max(fracs), min(fracs))


def rule_stats(T_cat):
    counts = {"normal": 0, "escalating": 0, "catfish": 0}
    tok = ret = dn = 0.0
    n = 0
    for seed in SEEDS:
        for i in range(10):
            env = cp.CareerAdversaryEnv(seed=seed * 100000 + i, horizon=HORIZON)
            env.MODE_TOKENS = {"normal": 600.0, "escalating": 900.0, "catfish": T_cat}
            feats = env.reset()
            for _ in range(HORIZON):
                idx = cp._rule_action_idx(feats)
                counts[ACTIONS[idx]] += 1
                tok += env.MODE_TOKENS[ACTIONS[idx]]
                feats, r, _d = env.step(idx)
                ret += r
                dn += env.density
                n += 1
    return counts, tok / n, ret / n, dn / n


print("=" * 92)
print("栅格搜索：T_cat × cap_catfish × cap_escalating")
print("=" * 92)
print(f"{'T_cat':>6} {'cap_cat':>8} {'cap_esc':>8} | {'鲶鱼占比':>9} {'cost':>6} | "
      f"{'限':>6} {'costOK':>7} {'rewOK':>6} {'densOK':>7} {'used':>5}")
print("-" * 92)

best = None
for T_cat in (1300.0, 1500.0, 1700.0, 1900.0):
    rc, rcost, rret, rdens = rule_stats(T_cat)
    limit = rcost * 1.1
    for cap_cat in (0.45, 0.55, 0.65):
        for cap_esc in (0.70, 0.85):
            frac, cost, ret, den, fmax, fmin = greedy(T_cat, cap_cat, cap_esc, 0.70)
            cost_ok = cost <= limit
            rew_ok = ret >= rret
            dens_ok = den >= rdens
            used = frac > 0.0
            ok = cost_ok and rew_ok and dens_ok and used
            flag = " <== OK" if ok else ""
            print(f"{T_cat:>6.0f} {cap_cat:>8} {cap_esc:>8} | {frac:>9.1%} {cost:>6.0f} | "
                  f"{limit:>6.0f} {str(cost_ok):>7} {str(rew_ok):>6} {str(dens_ok):>7} "
                  f"{str(used):>5}{flag}")
            if ok:
                score = (ret - rret) + (den - rdens) * 0.1 - abs(frac - 0.18)
                if best is None or score > best[0]:
                    best = (score, T_cat, cap_cat, cap_esc, frac, cost, ret, den)

print()
if best:
    _, T_cat, cap_cat, cap_esc, frac, cost, ret, den = best
    print(f"最优: T_cat={T_cat:.0f} cap_cat={cap_cat} cap_esc={cap_esc}")
    print(f"      鲶鱼占比={frac:.1%} cost={cost:.0f} 奖励={ret:+.5f} 密度={den:.3f}")
else:
    print("未找到同时满足全部约束的参数组合")
