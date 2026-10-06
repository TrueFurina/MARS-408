"""单一真值源护栏：纪律门 / 精准判定 / 奖励分项**只能有一份实现**。

为什么专门为"是否只有一份实现"写测试
------------------------------------
本项目已实际发生"多份复制静默漂移"事故：同一条纪律规则同时存在于

  (a) `review_policy.ReviewWeightPolicy.select_action` 内的闭包 `_block_skip`
  (b) `review_policy.evaluate_policy` 内的闭包 `_apply_discipline`
  (c) `engines/review_env_calibrated.discipline_gate`（逐字复刻）

生产侧修 (a) 的差一时，(b)(c) 不会跟着改。代价已经出现过：测评脚本因绕开护栏而报出
`discipline_ok=False / max_skip_streak=2` 的**假警报**，把"脚本口径错误"误诊为"策略违规"。

"对拍测试"（断言两份实现行为一致）只能**事后**发现漂移；对函数对象做**同一性断言**能让
漂移**根本无法发生**。故本文件对同一性、量纲、分项自洽三类不变量做硬断言。
"""

import pytest

from engines import review_policy as rp


# ────────────────────────────────────────────────────────────
# 1. 同一性：调用点必须指向同一个函数对象
# ────────────────────────────────────────────────────────────

def test_discipline_gate_is_single_source_object():
    """生产 / 校准环境 / 影子探针三处的纪律门必须是**同一对象**。

    变异体（在 calibrated 或 probe 里重新 `def` 一份实现）会让本用例失败。
    """
    from engines import review_env_calibrated as rc
    from engines.review_shadow_probe import discipline_gate as probe_gate

    assert rc.discipline_gate is rp.discipline_gate, \
        "review_env_calibrated 又出现了本模块自己的纪律门复刻体"
    assert probe_gate is rp.discipline_gate, \
        "影子探针转发到的不是生产纪律门"


def test_select_action_uses_module_level_gate(monkeypatch):
    """`select_action` 必须走模块级 `discipline_gate`（不得内联第三份实现）。

    做法：把 `rp.discipline_gate` 替换成一个"把 skip 改为 balanced 并打标记"的探针，
    若 select_action 未调用它，则动作不会被改写 ⇒ 用例失败。
    """
    calls = []

    def _spy(idx, features, skip_streak=0, reviews_done=0):
        calls.append((idx, skip_streak, reviews_done))
        return 3 if idx == 4 else idx

    monkeypatch.setattr(rp, "discipline_gate", _spy)
    p = rp.ReviewWeightPolicy(seed=7)
    feats = [0.5] * rp.STATE_DIM
    # torch 不可用/未训练时会走规则分支，同样必须经过护栏
    idx, src = p.select_action(feats, deterministic=True, skip_streak=0, reviews_done=0)
    assert calls, "select_action 未调用模块级 discipline_gate（疑似内联了自己的实现）"
    assert src in ("rule", "mappo", "rule_fallback")


def test_evaluate_policy_applies_gate_uniformly():
    """`evaluate_policy` 对规则臂也要施加护栏 —— 否则规则版靠 skip 省成本而虚高。"""
    env = rp.ReviewEnv(seed=7, horizon=8)
    out = rp.evaluate_policy("rule", env, horizon=8)
    assert out["max_skip_streak"] < rp.SKIP_STREAK_LIMIT, \
        f"规则臂出现连发 {out['max_skip_streak']} ≥ {rp.SKIP_STREAK_LIMIT}，护栏未生效"
    assert out["discipline_violation"] is False


# ────────────────────────────────────────────────────────────
# 2. 纪律门语义（差一回归）
# ────────────────────────────────────────────────────────────

def _feats(consistency: float) -> list:
    f = [0.5] * rp.STATE_DIM
    f[1] = consistency
    return f


@pytest.mark.parametrize("skip_streak,reviews_done,consistency,expect", [
    # 第 1 次 skip（streak=0）但真实评审次数不足 → 禁止 skip
    (0, 0, 0.8, 0),     # 证据强 → 压回 trust_honest
    (0, 0, 0.3, 3),     # 证据弱 → 压回 balanced
    # 连发已达 1 次（下一次就是第 2 次连发）→ 必须拦下（差一回归的守卫）
    (1, 5, 0.8, 0),
    (1, 5, 0.3, 3),
    # 评审次数够、且尚未连发 → 放行 skip
    (0, 5, 0.8, 4),
    (0, 2, 0.8, 4),
    # 非 skip 动作原样放行
    (0, 0, 0.8, 1),
    (1, 0, 0.3, 2),
])
def test_discipline_gate_semantics(skip_streak, reviews_done, consistency, expect):
    got = rp.discipline_gate(4 if expect in (0, 3, 4) else expect,
                             _feats(consistency), skip_streak, reviews_done)
    if expect in (0, 3, 4):
        assert got == expect
    else:
        assert got == expect  # 非 skip 动作不应被改写


def test_discipline_gate_blocks_before_second_consecutive_skip():
    """核心不变量：`skip_streak == LIMIT-1` 时必须已拦截。

    变异体（把 `SKIP_STREAK_LIMIT - 1` 改回 `SKIP_STREAK_LIMIT`）会让本用例失败 ——
    那正是历史上放行"连发 2 次"的差一缺陷。
    """
    f = _feats(0.3)
    assert rp.discipline_gate(4, f, rp.SKIP_STREAK_LIMIT - 1, 99) == 3, \
        "连发第 2 次前未拦截（差一缺陷回归）"
    assert rp.discipline_gate(4, f, rp.SKIP_STREAK_LIMIT - 2, 99) == 4, \
        "尚未连发却拦下了 skip（过度拦截）"


# ────────────────────────────────────────────────────────────
# 3. 精准判定：同源 + 量纲哨兵
# ────────────────────────────────────────────────────────────

def test_review_precision_semantics():
    assert rp.review_precision(0.9, 4) is True      # 优质产物放行 → 正确
    assert rp.review_precision(0.9, 3) is True
    assert rp.review_precision(0.3, 3) is True      # 低质但真实评审过 → 算拦住
    assert rp.review_precision(0.3, 4) is False     # 低质且 skip → 漏检重罚
    assert rp.review_precision(0.5, 4) is True      # 阈值含等号


def test_review_env_exposes_native_precision():
    """`env.last_precision` 必须等于模块级 `review_precision` 的判定（不得各自一套）。"""
    for seed in (7, 42, 2026):
        for action in (0, 1, 2, 3, 4):
            e = rp.ReviewEnv(seed=seed, horizon=8)
            e.reset()
            assert e.last_precision is None, "reset 后应清空 last_precision"
            c_before = e.consistency           # step 会抬升 consistency，判定用的是**旧值**
            e.step(action)
            assert e.last_precision == rp.review_precision(c_before, action), \
                f"seed={seed} action={action}: 环境原生 precision 与 review_precision 不一致"


def test_consistency_scale_is_unit_interval():
    """量纲哨兵：`consistency` 必须落在 [0, 1]。

    历史事故：量纲由 0-100 改为 0-1 时无人察觉，评测脚本里硬编码的阈值 60/75 遂使
    精准率恒为 0（而全部单测仍绿）。退回 0-100 量纲会让本用例失败。
    """
    e = rp.ReviewEnv(seed=12345, horizon=4, noisy=True)
    seen_max = 0.0
    for _ in range(300):
        e.reset()
        assert 0.0 <= e.consistency <= 1.0, f"consistency={e.consistency} 越出单位区间"
        seen_max = max(seen_max, e.consistency)
    assert seen_max > 0.5, "采样区间异常：300 次采样从未超过 0.5"


# ────────────────────────────────────────────────────────────
# 4. 奖励分项自洽（审计依赖它，必须与总数一致）
# ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tokens", [0.0, 900.0, 2500.0, -5.0])
@pytest.mark.parametrize("precision", [True, False])
@pytest.mark.parametrize("skip_streak", [0, 1, 2, 3])
def test_review_reward_components_sum_to_total(tokens, precision, skip_streak):
    comp = rp.review_reward(0.0, 3.0, precision, tokens, skip_streak=skip_streak,
                            return_components=True)
    parts = sum(comp[k] for k in ("gate", "precision", "cost", "discipline"))
    assert comp["total"] == pytest.approx(parts, abs=1e-12)
    # 不开分项时必须与分项总数一致（后向兼容）
    assert rp.review_reward(0.0, 3.0, precision, tokens,
                            skip_streak=skip_streak) == pytest.approx(comp["total"])


def test_discipline_term_only_activates_at_limit():
    """discipline 分项是"违规才激活"型：达 LIMIT 前恒为 0，达 LIMIT 后为负。"""
    at_before = rp.review_reward(0.0, 0.0, True, 0.0,
                                 skip_streak=rp.SKIP_STREAK_LIMIT - 1,
                                 return_components=True)["discipline"]
    at_limit = rp.review_reward(0.0, 0.0, True, 0.0,
                                skip_streak=rp.SKIP_STREAK_LIMIT,
                                return_components=True)["discipline"]
    assert at_before == 0.0
    assert at_limit < 0.0


def test_gain_of_matches_internal_gain_without_advancing():
    """`gain_of` 必须与内部 `_gain` 一致，且**不推进**环境状态。"""
    e = rp.ReviewEnv(seed=7, horizon=6)
    e.reset()
    before = (e.consistency, e.step_count)
    for a in range(len(rp.REVIEW_ACTIONS)):
        assert e.gain_of(a) == e._gain(a)
    assert (e.consistency, e.step_count) == before, "gain_of 意外推进了环境状态"
