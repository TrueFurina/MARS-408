# ============================================================
# tune_calibrated_env — 校准环境 PPO 训练配置小扫（用 held-out 真实上下文判优）
#
# 判据（唯一）：在 held-out 上下文上，策略相对 uniform 的真实增益能捕获 oracle 头寸的百分之几。
# 不参与任何对外数字；只为选出可复现的最佳训练配置。
#
# ⚠️ 重要修订（2026-09-14 晚）：
#   本轮早期横扫（episodes ≤ 800）走的是生产 `train_ppo` 的默认 `batch_episodes=48`，
#   于是 episodes=200/800 只对应 4/16 次参数更新 —— **等于没训**，当时的捕获率
#   （23%~42%）是欠训练产物，不能作为配置优劣依据。
#   现行 `build_shadow_policy` 会在 batch_episodes=None 时自动推导
#   `max(1, min(48, episodes // 10))`；最终结论以影子探针在**真实 240 样本**上的
#   实测为准（见 docs/三元评审权重MAPPO-环境根因与真实效果报告-2026-09-14.md）。
#   本脚本保留用于机制探索，重新横扫请显式传 episodes ≥ 1500 以进入有效训练区间。
# ============================================================

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.quality_gate import weighted_consistency_score  # noqa: E402
from engines.review_env_calibrated import CalibratedReviewEnv  # noqa: E402
from engines.review_policy import (  # noqa: E402
    _weights_of,
    review_weight_schema,
)
from engines.review_shadow_probe import build_shadow_policy  # noqa: E402

N_EVAL = 400


def _eval_set(base_seed: int = 990000):
    """held-out：400 条全新上下文（与训练/探针样本均不重叠）。"""
    out = []
    for i in range(N_EVAL):
        e = CalibratedReviewEnv(seed=base_seed + i, horizon=1)
        f = e.reset()
        out.append((f, e._evidence, e._consensus))
    return out


def _make_env_factory(hz):
    return lambda sd, _hz: CalibratedReviewEnv(seed=sd, horizon=hz)


def main():
    evalset = _eval_set()
    # 基线：uniform / oracle
    uni = [_eff(ev, cs, 3) for _f, ev, cs in evalset]
    orc = []
    for _f, ev, cs in evalset:
        orc.append(max(_eff(ev, cs, a) for a in range(4)))
    m_uni, m_orc = sum(uni) / len(uni), sum(orc) / len(orc)
    print(f"held-out n={N_EVAL}  uniform={m_uni:.3f}  oracle={m_orc:.3f}  头寸={m_orc - m_uni:+.3f}")

    configs = [
        ("hz=32 ep=200 wu=600 lr=1e-4 ep8", 32, 200, 600, 1e-4, 8),
        ("hz=32 ep=200 wu=600 lr=3e-4 ep8", 32, 200, 600, 3e-4, 8),
        ("hz=32 ep=200 wu=600 lr=1e-3 ep4", 32, 200, 600, 1e-3, 4),
        ("hz=32 ep=200 wu=1200 lr=3e-4 ep4", 32, 200, 1200, 3e-4, 4),
    ]
    for name, hz, ep, wu, lr, epo in configs:
        t0 = time.time()
        ms, caps = [], []
        for sd in (7, 42, 2026):
            p = build_shadow_policy(sd, warmup_steps=wu, ppo_episodes=ep, horizon=hz,
                                    env_factory=_make_env_factory(hz), lr=lr, epochs=epo)
            effs, match = [], 0
            for f, ev, cs in evalset:
                idx, _s = p.select_action(f, deterministic=True, skip_streak=0, reviews_done=0)
                effs.append(_eff(ev, cs, idx))
                best = max(range(4), key=lambda a: _eff(ev, cs, a))
                match += (idx == best)
            m = sum(effs) / len(effs)
            ms.append(m)
            caps.append((m - m_uni) / (m_orc - m_uni))
            print(f"  {name} seed={sd}: mean_eff={m:.3f} Δ={m - m_uni:+.3f} "
                  f"capture={100 * (m - m_uni) / (m_orc - m_uni):.1f}% "
                  f"oracle_match={100 * match / len(evalset):.1f}%")
        print(f"  ==> {name}: 平均 capture={100 * sum(caps) / len(caps):.1f}%  "
              f"({time.time() - t0:.0f}s)\n")


def _eff(evidence, consensus, action_idx):
    w = review_weight_schema(_weights_of(action_idx))
    e, _a = weighted_consistency_score(evidence, consensus, w)
    return e


if __name__ == "__main__":
    main()
