"""精细栅格：在可行区域内按"成本余量"排序，找最鲁棒参数（PPO 不会恰好停在解析最优点）。"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
sys.path.insert(0, str(ROOT))

from engines import career_policy as cp

ACTIONS = cp.CAREER_ACTIONS
HORIZON = 8
SEEDS = [1, 42, 2024, 7, 99, 555, 31337]


def greedy(T_cat, cap_cat, cap_esc, overload, pen):
    cp.CAREER_DELTA_CAP["catfish"] = cap_cat
    cp.CAREER_DELTA_CAP["escalating"] = cap_esc
    cp.CAREER_OVERLOAD = overload
    cp.CAREER_OVERLOAD_PENALTY = pen
    fracs, costs = [], []
    for seed in SEEDS:
        env = cp.CareerAdversaryEnv(seed=seed, horizon=HORIZON)
        env.noisy = False
        env.MODE_TOKENS = {"normal": 600.0, "escalating": 900.0, "catfish": T_cat}
        env.reset()
        counts = {n: 0 for n in ACTIONS}
        tok = 0.0
        for _ in range(HORIZON):
            best_a, best_r = 0, None
            for a in range(len(ACTIONS)):
                probe = copy.deepcopy(env)
                _f, r, _d = probe.step(a)
                if best_r is None or r > best_r + 1e-12:
                    best_a, best_r = a, r
            counts[ACTIONS[best_a]] += 1
            tok += env.MODE_TOKENS[ACTIONS[best_a]]
            env.step(best_a)
        fracs.append(counts["catfish"] / HORIZON)
        costs.append(tok / HORIZON)
    return sum(fracs) / len(fracs), sum(costs) / len(costs), max(fracs)


def rule_cost(T_cat):
    tok, n = 0.0, 0
    for seed in SEEDS:
        for i in range(10):
            env = cp.CareerAdversaryEnv(seed=seed * 100000 + i, horizon=HORIZON)
            env.MODE_TOKENS = {"normal": 600.0, "escalating": 900.0, "catfish": T_cat}
            feats = env.reset()
            for _ in range(HORIZON):
                idx = cp._rule_action_idx(feats)
                tok += env.MODE_TOKENS[ACTIONS[idx]]
                feats, _r, _d = env.step(idx)
                n += 1
    return tok / n


print("=" * 96)
print("按『成本余量』排序（越大越鲁棒）：cost_limit = 规则成本 × 1.1")
print("=" * 96)
print(f"{'T_cat':>6} {'cap_cat':>8} {'cap_esc':>8} {'ovl':>5} {'pen':>5} | "
      f"{'鲶鱼均值':>8} {'鲶鱼最大':>8} {'cost':>6} {'限':>6} {'余量':>6}")
print("-" * 96)

rows = []
for T_cat in (1100.0, 1200.0, 1300.0, 1400.0, 1500.0):
    limit = rule_cost(T_cat) * 1.1
    for cap_cat in (0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        for cap_esc in (0.70, 0.85):
            for ovl, pen in ((0.45, 0.10), (0.70, 0.08)):
                frac, cost, fmax = greedy(T_cat, cap_cat, cap_esc, ovl, pen)
                if frac <= 0:          # 机制未被使用 → 不合格，直接剔除
                    continue
                margin = limit - cost
                rows.append((margin, T_cat, cap_cat, cap_esc, ovl, pen, frac, fmax, cost, limit))

rows.sort(reverse=True)
for margin, T_cat, cap_cat, cap_esc, ovl, pen, frac, fmax, cost, limit in rows[:20]:
    ok = "  <== OK" if margin >= 0 else ""
    print(f"{T_cat:>6.0f} {cap_cat:>8} {cap_esc:>8} {ovl:>5} {pen:>5} | "
          f"{frac:>8.1%} {fmax:>8.1%} {cost:>6.0f} {limit:>6.0f} {margin:>+6.0f}{ok}")
if not rows:
    print("  无任何配置在『使用鲶鱼』的同时满足成本约束")
