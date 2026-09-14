# tests/test_review_env_calibrated.py — 校准版评审环境（角色 C）验证
#
# 验证点（对齐 experiments/diag_review_headroom.py 的实测结论）：
#   1. 接口与回顾环境一致（reset/step/horizon，12 维特征）；
#   2. **核心不变式：balanced(动作3) 的真实增益恒为 0** —— 奖励对动作 3 与上下文无关，
#      杜绝"躺平白拿分"（原环境把它赋 3.0/5.0 = 近优，是 PPO 塌缩的根因）；
#   3. 存在可学梯度：动作 2 平均优于动作 3 优于动作 0；
#   4. 上下文确实重要：oracle 平均增益显著高于最优恒定动作；
#   5. 口径纪律：skip(动作4) 在本口径不可用 → 恒定负奖励，不会被策略白嫖；
#   6. 同 seed 逐位可复现；
#   7. discipline_gate 与生产 select_action 的 _block_skip 语义一致。

import pytest

from agents.quality_gate import weighted_consistency_score
from engines.review_env_calibrated import (
    CalibratedReviewEnv,
    discipline_gate,
    oracle_action,
)
from engines.review_policy import (
    REVIEW_MIN_REVIEW,
    SKIP_STREAK_LIMIT,
    STATE_DIM,
    UNIFORM_WEIGHTS,
    _weights_of,
    review_weight_schema,
)

_N_TRIALS = 300


def _fresh(seed, horizon=1):
    e = CalibratedReviewEnv(seed=seed, horizon=horizon)
    e.reset()
    return e


def test_context_distribution_mirrors_real_generator():
    """上下文分布必须与真实样本生成器同分布（防回归到"恒定量"）。

    历史缺陷：f12(round_ratio) 曾由 step_count/horizon 推导 ⇒ horizon=1 时恒 1.0
    （std=0），而真实上下文为 uniform(0,1)（实测 0.49±0.29）⇒ 策略在评测时遇到
    分布外输入，虚高 RL 增益约 0.37 分。此处锁定 f11(shift 前为 mode_encoding) 与
    f12 均为非退化随机量。
    """
    import statistics
    f11 = [CalibratedReviewEnv(seed=900000 + t, horizon=1).reset()[10] for t in range(120)]
    f12 = [CalibratedReviewEnv(seed=900000 + t, horizon=1).reset()[11] for t in range(120)]
    for name, vals in (("f11(mode_encoding)", f11), ("f12(round_ratio)", f12)):
        assert statistics.pstdev(vals) > 0.15, f"{name} 退化：std={statistics.pstdev(vals):.4f}"
        assert 0.35 < statistics.mean(vals) < 0.65, f"{name} 均值偏离 uniform：{statistics.mean(vals):.3f}"


def test_interface_and_feature_dim():
    e = CalibratedReviewEnv(seed=1, horizon=6)
    f = e.reset()
    assert len(f) == STATE_DIM
    assert all(isinstance(x, float) for x in f)
    assert all(0.0 <= x <= 1.0 for x in f)
    f2, r, done = e.step(3)
    assert len(f2) == STATE_DIM
    assert isinstance(r, float)
    assert done is False
    # horizon 处 done
    for _ in range(5):
        _f, _r, done = e.step(3)
    assert done is True


def test_feature_f2_carries_evidence_consistency():
    """f2 必须与生产语义一致（evidence.consistency_score / 100）——最优动作就靠它。"""
    for s in (1, 2, 3, 99):
        e = _fresh(s)
        assert abs(e._features()[1] - e._evidence["consistency_score"] / 100.0) < 1e-6


def test_balanced_has_zero_gain_invariant():
    """核心不变式：balanced 的相对增益恒为 0 ⇒ 奖励对上下文恒定（无免费午餐）。

    原环境给 balanced 赋 3.0（最优 5.0 的 60%），策略因此学会躺平；
    本环境 balanced 增益严格为 0，只有按上下文选对才有正增益。
    """
    rew = []
    for t in range(_N_TRIALS):
        e = _fresh(10000 + t)
        base, _ = weighted_consistency_score(e._evidence, e._consensus, dict(UNIFORM_WEIGHTS))
        eff, _ = weighted_consistency_score(e._evidence, e._consensus,
                                            review_weight_schema(_weights_of(3)))
        assert abs(eff - base) < 1e-9, "balanced 的相对增益必须恒为 0"
        _f, r, _d = e.step(3)
        rew.append(r)
    # 奖励方差为 0（delta=0 且成本固定）→ 策略无法靠"恒定 balanced"获得波动收益
    assert max(rew) - min(rew) < 1e-9


def test_skip_is_unavailable_and_penalized():
    """口径纪律：reviews_done=0 时 discipline_gate 恒禁 skip → 环境给恒定负奖励。"""
    for t in range(50):
        e = _fresh(20000 + t)
        _f, r, _d = e.step(4)
        assert r == pytest.approx(-1.0)


def test_gradient_exists_between_actions():
    """可学梯度：trust_consensus > balanced > trust_honest。

    用**配对比较**（同一上下文下比各动作的相对增益）——上下文随机性被消掉，
    估计量方差远小于独立抽样，少量样本即可稳定判定。
    """
    acc = {a: 0.0 for a in range(4)}
    for t in range(_N_TRIALS):
        e = _fresh(30000 + t)
        base = weighted_consistency_score(e._evidence, e._consensus, dict(UNIFORM_WEIGHTS))[0]
        for a in range(4):
            acc[a] += weighted_consistency_score(
                e._evidence, e._consensus, review_weight_schema(_weights_of(a)))[0] - base
    m = {a: acc[a] / _N_TRIALS for a in range(4)}
    assert m[2] > m[3] > m[0], f"动作梯度不成立: {m}"


def test_oracle_action_varies_and_beats_best_constant():
    """上下文确实重要：oracle 平均增益显著高于最优恒定动作（否则无可学空间）。"""
    base_acc, const_acc = 0.0, {a: 0.0 for a in range(4)}
    seen = set()
    for t in range(_N_TRIALS):
        e = _fresh(40000 + t)
        a_star = oracle_action(e)
        seen.add(a_star)
        vals = {a: weighted_consistency_score(
            e._evidence, e._consensus, review_weight_schema(_weights_of(a)))[0]
            for a in range(4)}
        base = vals[3]
        base_acc += vals[a_star] - base
        for a in range(4):
            const_acc[a] += vals[a] - base
    assert len(seen) >= 2, "oracle 动作应当随上下文变化（否则无可学信号）"
    best_const = max(const_acc.values()) / _N_TRIALS
    best_oracle = base_acc / _N_TRIALS
    assert best_oracle > best_const + 2.0, (
        f"上下文增益不足：oracle={best_oracle:.3f} vs 最优恒定={best_const:.3f}")


def test_reproducible_per_seed():
    a = CalibratedReviewEnv(seed=7, horizon=4)
    b = CalibratedReviewEnv(seed=7, horizon=4)
    fa, fb = a.reset(), b.reset()
    assert fa == fb
    for act in (0, 2, 3, 1):
        ra, rb = a.step(act), b.step(act)
        assert ra[0] == rb[0] and ra[1] == rb[1]


def test_discipline_gate_matches_production_semantics():
    """与 review_policy.select_action 内 _block_skip 语义一致（含已修的差一）。"""
    strong = [0.5, 0.9] + [0.0] * 10      # f2 = 0.9（证据强）
    weak = [0.5, 0.3] + [0.0] * 10        # f2 = 0.3
    # reviews_done < REVIEW_MIN_REVIEW → 禁 skip
    assert discipline_gate(4, strong, skip_streak=0, reviews_done=0) == 0
    assert discipline_gate(4, weak, skip_streak=0, reviews_done=0) == 3
    # skip 连发达上限 → 禁 skip
    assert discipline_gate(4, strong, skip_streak=SKIP_STREAK_LIMIT, reviews_done=9) == 0
    assert discipline_gate(4, weak, skip_streak=SKIP_STREAK_LIMIT, reviews_done=9) == 3
    # ⚠️ 差一修复：skip_streak 达到 SKIP_STREAK_LIMIT-1 就必须拦（否则第 1 次连发被放过，
    # 与验收"连发 ≥2 发生率为 0"冲突）
    assert discipline_gate(4, strong, skip_streak=SKIP_STREAK_LIMIT - 1, reviews_done=9) == 0
    assert discipline_gate(4, weak, skip_streak=SKIP_STREAK_LIMIT - 1, reviews_done=9) == 3
    # 非 skip 动作原样通过
    for a in (0, 1, 2, 3):
        assert discipline_gate(a, strong, 0, 0) == a
    # 条件满足时允许 skip（与生产一致：reviews_done 足够且未连发）
    assert discipline_gate(4, weak, skip_streak=0, reviews_done=REVIEW_MIN_REVIEW) == 4


def test_discipline_gate_equivalent_to_production_select_action():
    """对拍守护：本模块 discipline_gate 必须与真实生产 select_action 的门一致。

    _block_skip 是 select_action 内的闭包，无法直接 import，只能复刻；本测试用
    「未训练策略 → 走 rule 分支」的路径，构造 _rule_action_idx 必返 4 的特征，
    从而让生产端输出恰好等于 _block_skip(4)，与本模块 discipline_gate(4, ...) 对拍。
    生产若再改判据而此处未同步，本测试会失败。
    """
    from engines.review_policy import ReviewWeightPolicy, _rule_action_idx

    # f2=0.9（consistency≥0.75）且 f10=0.9（cost_ratio≥0.6）→ _rule_action_idx 必返 4
    feats = [0.5, 0.9, 0.5, 0.0, 0.0, 0.3, 0.6, 0.2, 0.5, 0.9, 0.5, 0.5]
    assert _rule_action_idx(feats) == 4

    p = ReviewWeightPolicy()          # 未训练 → select_action 走 rule 分支
    assert not p._trained
    for skip_streak in (0, 1, 2, 3):
        for reviews_done in (0, 1, 2, 3, 5):
            prod_idx, _src = p.select_action(
                feats, deterministic=True,
                skip_streak=skip_streak, reviews_done=reviews_done)
            mine = discipline_gate(4, feats, skip_streak, reviews_done)
            assert prod_idx == mine, (
                f"纪律门漂移 skip_streak={skip_streak} reviews_done={reviews_done}: "
                f"生产={prod_idx} 本地={mine}")

    # 注：gate 的"弱证据 → 压回 balanced(3)"支路**无法经 rule 路径对拍** ——
    # _rule_action_idx 仅在 consistency ≥ 0.75 时才返回 4，而此刻 f2 ≥ 0.6 必走强支路。
    # 该支路只在"策略自身输出 4 且 f2 < 0.6"时可达，已由
    # test_discipline_gate_matches_production_semantics 直接断言覆盖。
