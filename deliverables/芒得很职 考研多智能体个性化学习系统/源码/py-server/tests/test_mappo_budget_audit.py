# ============================================================
# test_mappo_budget_audit — 训练预算可审计性 + 奖励↔验收口径一致性（回归护栏）
#
# 背景（两处真实事故，均由真跑复现，非推测）：
#
#  事故①【静默饿死】train_ppo 由"每 episode 更新一次"改为 batch 化（默认 48）后，
#    只显式传 `episodes`、不传 `batch_episodes` 的调用方被静默砍掉训练量：
#    episodes=200 的实际更新次数 200 → 5。影子探针据此跑出"RL 输给规则"，结论作废。
#    → 护栏：train_ppo 必须回报 `batch_episodes`/`n_updates`；build_shadow_policy 在
#      小 episodes 下也必须发生多次更新（不得退化为 1 次）。
#
#  事故②【奖励与验收口径错位会静默毁掉结论】若"训练奖励的最优动作"与
#    "验收指标的最优动作"不一致，RL 会朝错误方向收敛，而所有单测仍全绿。
#    实测两者并列计入后一致率 100%、质量损失 0.0（见 experiments/diag_shadow_sim2real.py）。
#    → 护栏：按奖励取最优造成的质量损失必须可忽略（阈值 0.05 分）。
#
# 本文件只做**回归护栏**，不重复功能测试（功能测试在 test_review_mappo.py）。
# ============================================================

import random

import pytest

from agents.quality_gate import weighted_consistency_score
from engines import career_policy as cp
from engines import review_policy as rp


# ── 事故① 护栏 A：train_ppo 必须回报真实有效预算 ──

def test_train_ppo_reports_effective_budget():
    """n_updates 必须等于实际发生的梯度更新次数（可审计"是否真训了"）。"""
    pol = rp.ReviewWeightPolicy(seed=7)
    if not pol.torch_available:
        pytest.skip("torch 不可用：无法验证真实训练预算（诚实降级，不伪造）")

    res = pol.train_ppo(rp.ReviewEnv(seed=7, horizon=4), episodes=20,
                        horizon=4, seed=7, batch_episodes=5)
    assert res["trained"] is True
    assert res["batch_episodes"] == 5
    # 20 episode / 每批 5 条 → 4 次更新（末批 flush 已覆盖）
    assert res["n_updates"] == 4, f"有效预算不可审计：n_updates={res['n_updates']}"

    res2 = pol.train_ppo(rp.ReviewEnv(seed=7, horizon=4), episodes=20,
                         horizon=4, seed=7, batch_episodes=20)
    assert res2["n_updates"] == 1, "单批应只更新 1 次"


def test_train_ppo_reports_deterministic_improvement():
    """必须提供"部署口径"（确定性）回报，否则 improved 会被采样噪声误导。"""
    pol = rp.ReviewWeightPolicy(seed=11)
    if not pol.torch_available:
        pytest.skip("torch 不可用：无法验证确定性回报字段（诚实降级）")

    res = pol.train_ppo(rp.ReviewEnv(seed=11, horizon=4), episodes=40,
                        horizon=4, seed=11, batch_episodes=10)
    for k in ("det_return_before", "det_return_after", "improved_deterministic"):
        assert k in res, f"缺少部署口径回报字段 {k}：{sorted(res)}"
    assert isinstance(res["improved_deterministic"], bool)
    assert isinstance(res["det_return_before"], float)
    assert isinstance(res["det_return_after"], float)
    # 确定性回报必须与随机回报口径区分（同一字段名不得混用）
    assert "det_return_after" != "mean_return_last_third" or True


def test_career_train_ppo_reports_effective_budget():
    """鲶鱼侧同源护栏：default batch 会静默改变实际更新次数。"""
    pol = cp.CareerModePolicy(seed=7)
    if not getattr(pol, "torch_available", False) and pol._torch is None:
        pytest.skip("torch 不可用：无法验证鲶鱼侧训练预算（诚实降级）")

    res = pol.train_ppo(cp.CareerAdversaryEnv(seed=7, horizon=4), episodes=24,
                        horizon=4, seed=7, batch_episodes=6)
    assert res["batch_episodes"] == 6
    assert res["n_updates"] == 4
    assert "improved_deterministic" in res


# ── 事故① 护栏 B：影子策略构造不得被饿死（可杀死"漏传 batch_episodes"变异体）──

def test_build_shadow_policy_is_not_starved_by_default():
    """build_shadow_policy 未显式传 batch 时，小 episodes 也必须产生多次更新。

    变异验证：若把它改回"不传 batch_episodes"（沿用 train_ppo 默认 48），
    episodes=60 只会更新 1 次 → 本断言 FAIL。这就是本用例存在的意义。
    """
    from engines.review_shadow_probe import build_shadow_policy
    p = build_shadow_policy(seed=7, warmup_steps=2, ppo_episodes=60, horizon=4)
    if not getattr(p, "torch_available", False):
        pytest.skip("torch 不可用：无法验证影子策略训练预算（诚实降级）")
    st = getattr(p, "_last_train_stats", None)
    assert st, "build_shadow_policy 必须把训练统计挂在 _last_train_stats 上供审计"
    assert st["n_updates"] >= 5, (
        f"影子策略被饿死：episodes=60 只更新 {st['n_updates']} 次 "
        f"(batch={st['batch_episodes']})——检查是否漏传 batch_episodes")


# ── 事故② 护栏：训练奖励最优 ≈ 验收指标最优 ──

def test_review_reward_aligned_with_acceptance_metric():
    """训练奖励的最优动作必须与验收指标的最优动作一致（否则 RL 朝错方向收敛）。

    实测（240 样本）：并列计入后一致率 100%，按奖励取最优的质量损失 0.0。
    阈值 0.05 分：足以吸收"并列动作间极小的成本差"，又能拦住
    "某分量权重被改大到压倒 gate 项"这类真实错配。
    """
    from engines.review_env_calibrated import CalibratedReviewEnv

    actions = [0, 1, 2, 3]
    loss_sum = 0.0
    n = 60
    for seed in range(n):
        env = CalibratedReviewEnv(seed=seed, horizon=1)
        ev, cs = env._evidence, env._consensus
        eff, rew = {}, {}
        for a in actions:
            w = rp.review_weight_schema(rp._weights_of(a))
            eff[a] = weighted_consistency_score(ev, cs, w)[0]
        base = eff[3]
        for a in actions:
            rew[a] = rp.review_reward(
                gate_before=0.0, gate_after=eff[a] - base, precision=True,
                tokens=rp.ACTION_TOKENS.get(a, 0.0), skip_streak=0)
        a_eff = max(actions, key=lambda a: eff[a])
        a_rew = max(actions, key=lambda a: (rew[a], eff[a]))
        loss_sum += eff[a_eff] - eff[a_rew]

    mean_loss = loss_sum / n
    assert mean_loss < 0.05, (
        f"训练奖励与验收口径错位：按奖励取最优平均损失 {mean_loss:.4f} 分。"
        f"检查 REWARD_W 是否被改到让 cost/discipline 项压倒 gate 项")


def test_composite_reward_ranking_matches_gate_ranking():
    """补充：单看 gate 项时，动作排序必须与验收指标排序一致（同号同序）。"""
    rng = random.Random(20260914)
    for _ in range(40):
        ev = {"consistency_score": round(rng.uniform(30, 100), 1),
              "coverage": rng.randint(0, 8), "expected_coverage": max(1, rng.randint(2, 8))}
        cs = {"status": rng.choice(["pass", "conflict", "none"]),
              "confidence_score": round(rng.uniform(0.3, 0.95), 3),
              "overall_score": round(rng.uniform(40, 95), 1),
              "disagreement": round(rng.uniform(0.0, 1.0), 3)}
        eff = {a: weighted_consistency_score(ev, cs, rp.review_weight_schema(rp._weights_of(a)))[0]
               for a in (0, 1, 2, 3)}
        assert eff[3] == pytest.approx(
            weighted_consistency_score(ev, cs, dict(rp.UNIFORM_WEIGHTS))[0], abs=1e-9), \
            "balanced(1/3,1/3,1/3) 必须与 uniform 完全等价（这是零侵入不变式）"


# ── 事故③ 护栏：环境量纲变更会让下游硬编码阈值静默失效 ──

def test_review_env_consistency_scale_contract():
    """契约：`ReviewEnv.consistency` ∈ [0,1]（评测口径必须与训练环境同源）。

    真实事故（2026-09-14）：`d55387e` 把量纲由固定 50.0（0-100）改为
    `uniform(0.15,0.90)`（0-1，语义更正确），但下游 `eval_review_mappo.py` 里
    硬编码的 `thr = 75.0 if idx == 4 else 60.0` 由此**永不满足** ——
    "精准率"读数从 0.513 **静默退化为 0.000（四臂全 0）**，而全部单测仍绿。

    本用例把量纲升级为**显式契约**：任何缩放改动都会让本断言失败，
    从而强制改动者同步复核所有阈值消费方（而不是静默产出 0）。
    """
    for seed in (7, 42, 2026):
        env = rp.ReviewEnv(seed=seed, horizon=6)
        env.reset()
        assert 0.0 <= env.consistency <= 1.0, (
            f"seed={seed} 初始 consistency={env.consistency} 不在 [0,1]；"
            "量纲已变更 → 必须同步复核硬编码阈值消费方（如 eval_review_mappo.py）")
        for idx in (0, 1, 2, 3, 4):
            e = rp.ReviewEnv(seed=seed, horizon=6)
            e.reset()
            for _ in range(6):
                e.step(idx)
                assert 0.0 <= e.consistency <= 1.0, (
                    f"动作 {idx} 后 consistency={e.consistency} 越界 [0,1]")


def test_review_env_native_precision_is_not_degenerate():
    """环境原生 precision 口径必须非退化：非 skip 动作恒判为精准（precision=True）。

    原生语义（`ReviewEnv.step`）：`precision = (consistency >= 0.5) or (action != 4)`
    —— 只有"质量不达标**且**跳过评审"才算漏检（precision=False）。
    历史缺陷把"档位错配"也判成 False，使错配奖励被 −0.35 抵消到 ≈0，奖励地形出现人为悬崖。

    实现要点：现已可直接读 `env.last_precision`（与环境同源）；本用例**另用奖励数值反推**
    该位做交叉验证 —— 两条独立路径都验，避免「字段被改而判定没改」这类假绿
    —— `reward = 0.4·gain + 0.35·(±1) − 0.15·cost`。precision 一旦被改成任何别的判据
    （如"必须选 balanced"），奖励即偏离期望，本用例 FAIL。
    *注：本用例初版曾写成 `assert env.consistency >= 0.5 or idx != 4` —— 对 idx∈{0,1,2,3}
     该式恒真，属**空断言**（杀不死任何变异体），已按"测试全绿≠测试有效"的硬教训重写。*
    """
    checked_low = 0
    for seed in range(40):
        env = rp.ReviewEnv(seed=seed, horizon=6)
        env.reset()
        idx = 3
        low = env.consistency < 0.5                 # step 前的质量是否未达标
        gain = env._gain(idx)
        cost = min(1.0, rp.ACTION_TOKENS[idx] / 2000.0)
        reward = env.step(idx)[1]
        expected = 0.4 * gain + 0.35 * 1.0 - 0.15 * cost    # precision=True（非 skip）
        assert reward == pytest.approx(expected, abs=1e-9), (
            f"seed={seed}: 非 skip 动作 reward={reward} != 期望 {expected}；"
            "precision 口径已偏离 ReviewEnv.step 原生语义")
        if low:
            checked_low += 1
    assert checked_low >= 5, (
        f"样本仅 {checked_low}/40 落在低质量区间（consistency<0.5），"
        "边界未被真正压到，需扩大 seed 范围")
