# ============================================================
# diag_train_return_vs_eval — 解释"训练回报下降、真实质量上升"的矛盾
#
# 现象（真实数据，见 sweep_shadow_budget_20260914_163451.json）：
#   episodes=3000 batch=48（63 次更新）时：
#     训练回报  22.44→10.69 / 25.64→10.88 / 25.50→9.57   （首三分位→末三分位，**下降**）
#     真实质量  69.896 vs 规则 68.948、uniform 66.809    （**上升**，t=3.08）
#   train_ppo 的 `improved` 字段据此返回 False ⇒ 审计口径会把"策略变好"读成"PPO 没效果"。
#
# 待验证假设（唯一可疑项）：
#   CalibratedReviewEnv 对"被纪律门拒绝的 skip"给 −1.0 惩罚。warmup 后的策略是规则的
#   尖锐克隆（几乎不采样 skip），训练中概率质量向动作 4 扩散，每步期望被扣分
#   ⇒ 回报曲线被"采样噪声 + 无效 skip 惩罚"主导，与真实质量脱钩。
#
# 判据：同一批策略、同一环境分布，比较三种 rollout 的平均回报
#   (a) 随机采样（= train_ppo 口径）
#   (b) 确定性 argmax（= 部署口径）
#   (c) 随机采样但屏蔽动作 4（消除无效 skip 惩罚）
#   若 (b) 或 (c) 显著高于 (a) → 回报下降是采样/惩罚伪影，不是策略退化。
# ============================================================

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engines.review_env_calibrated import CalibratedReviewEnv  # noqa: E402
from engines.review_shadow_probe import build_shadow_policy  # noqa: E402

SEEDS = [7, 42, 2026]
BUDGETS = [(3000, 48), (200, 48)]
K_EPISODES = 150
EVAL_SEED = 909090


def _rollout(policy, horizon, mode, seed, k):
    """返回 (平均回报, 采样到动作4的步数占比)。"""
    torch = policy._torch
    env = CalibratedReviewEnv(seed=seed, horizon=horizon)
    total, n, n4 = 0.0, 0, 0
    for _ in range(k):
        s = env.reset()
        ep = 0.0
        for _t in range(horizon):
            x = torch.tensor([s], dtype=torch.float32)
            policy._actor.eval()
            with torch.no_grad():
                probs = policy._actor(x)[0]
            if mode == "deterministic":
                a = int(probs.argmax().item())
            elif mode == "stochastic_no_skip":
                p = probs.clone()
                p[4] = 0.0
                if float(p.sum()) <= 0:
                    p[3] = 1.0
                a = int(torch.multinomial(p / p.sum(), 1).item())
            else:  # stochastic（train_ppo 口径）
                a = int(torch.multinomial(probs, 1).item())
            if a == 4:
                n4 += 1
            n += 1
            s, r, done = env.step(a)
            ep += float(r)
            if done:
                break
        total += ep
    return total / k, (100.0 * n4 / n if n else 0.0)


def main():
    out = {"meta": {"source": "diag_train_return_vs_eval.py (read-only)",
                    "k_episodes": K_EPISODES, "eval_seed": EVAL_SEED,
                    "note": "同一策略、同一环境分布下的三种 rollout 口径对比"},
           "rows": []}

    for eps, batch in BUDGETS:
        for sd in SEEDS:
            p = build_shadow_policy(
                sd, warmup_steps=600, ppo_episodes=eps, horizon=32,
                env_factory=lambda s_, h_: CalibratedReviewEnv(seed=s_, horizon=h_),
                batch_episodes=batch)
            st = getattr(p, "_last_train_stats", {}) or {}
            rows = {}
            for mode in ("stochastic", "deterministic", "stochastic_no_skip"):
                ret, skip_pct = _rollout(p, 32, mode, EVAL_SEED + sd, K_EPISODES)
                rows[mode] = {"mean_return": round(ret, 3), "pct_steps_action4": round(skip_pct, 2)}
            rec = {
                "episodes": eps, "batch_episodes": batch, "seed": sd,
                "n_updates": st.get("n_updates"),
                "train_return_first_third": round(st.get("mean_return_first_third", float("nan")), 3),
                "train_return_last_third": round(st.get("mean_return_last_third", float("nan")), 3),
                "train_reported_improved": st.get("improved"),
                **rows,
            }
            rec["deterministic_minus_stochastic"] = round(
                rows["deterministic"]["mean_return"]
                - rows["stochastic"]["mean_return"], 3)
            out["rows"].append(rec)
            print(f"ep={eps} batch={batch} seed={sd} updates={rec['n_updates']} "
                  f"train_ret {rec['train_return_first_third']}→{rec['train_return_last_third']} "
                  f"(improved={rec['train_reported_improved']})")
            print(f"    rollout: stochastic={rows['stochastic']['mean_return']:8.3f} "
                  f"(P(skip-step)={rows['stochastic']['pct_steps_action4']:5.2f}%) "
                  f"deterministic={rows['deterministic']['mean_return']:8.3f} "
                  f"no_skip={rows['stochastic_no_skip']['mean_return']:8.3f}")

    # 汇总：预算档内取均值
    print("\n================= 汇总（3 seed 均值） =================")
    for eps, batch in BUDGETS:
        sub = [r for r in out["rows"] if r["episodes"] == eps and r["batch_episodes"] == batch]
        if not sub:
            continue
        def _m(k):
            return round(sum(r[k] for r in sub) / len(sub), 3)
        print(f"ep={eps} batch={batch} updates={sub[0]['n_updates']}: "
              f"train_ret {_m('train_return_first_third')}→{_m('train_return_last_third')} | "
              f"stochastic {_m2(sub, 'stochastic')} | "
              f"deterministic {_m2(sub, 'deterministic')} | "
              f"no_skip {_m2(sub, 'stochastic_no_skip')}")

    outp = Path(__file__).resolve().parent / "results" / "diag_train_return_vs_eval.json"
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[diag] -> {outp}")


def _m2(sub, mode):
    return round(sum(r[mode]["mean_return"] for r in sub) / len(sub), 3)


if __name__ == "__main__":
    main()
