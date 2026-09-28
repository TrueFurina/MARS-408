# tests/test_review_shadow_probe.py — 影子探针（角色 C）最小验证
#
# 验证点：
#   1. observe 结构完整、能复算真实有效分差；
#   2. observe 无副作用（不修改传入的 evidence/consensus/state/critic）；
#   3. 纪律：reviews_done=0 时影子策略绝不选 skip（动作 != 4）；
#   4. 影子与基线对比链路不抛异常、delta 数值自洽。
#
# torch 不可用 → 整文件跳过（影子退化为规则等价，非探针验证目标）。

import copy

import pytest

# 真训 PPO 路径需要 torch；不可用则整文件跳过。
#
# ⚠️ Windows 本机的「torch 不可用」是以 **OSError(WinError 1114 动态链接库初始化失败)**
#    暴露的，而 **不是** ImportError；pytest.importorskip() 默认只捕获 ImportError，
#    于是它会升级成「收集期 ERROR」——后果有二：
#      ① 整轮 pytest 退出码恒为非 0，无法用退出码判定成败（历史上只能忽略本文件重跑）；
#      ② 本文件 6 条用例在 Windows 收集 0 条、在 Linux 收集 6 条，
#         「用例总数」这一对外数字变成**环境依赖**，本地无法复算权威值。
#    这里显式把 OSError 一并纳入后才降级为 skip。
#    注意边界：只放行 ImportError/OSError 两种「依赖缺失」信号，
#    其它异常照常抛出，绝不把代码错误伪装成 skip（否则该用例会假绿）。
try:
    import torch

    _TORCH_IMPORT_ERROR = None
except (ImportError, OSError) as exc:  # noqa: E402  (Windows: DLL 加载失败是 OSError)
    torch = None
    _TORCH_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

# 用 pytestmark 而非模块级 pytest.skip()：
#   模块级 skip 只产出 **1 个 skipped item**，而 Linux 会收集 **6 个** —— 两边用例总数不一致，
#   「对外用例总数」这类元统计依旧无法在本地复算。改成 pytestmark 后，6 条用例在任何环境下
#   都被收集，Windows 上逐条 skip、Linux 上照常执行，总数恒定。
pytestmark = pytest.mark.skipif(
    _TORCH_IMPORT_ERROR is not None,
    reason=f"torch 不可用（{_TORCH_IMPORT_ERROR}）：影子退化为规则等价，跳过本文件全部用例",
)

from engines.review_shadow_probe import (  # noqa: E402
    HEURISTIC_F2_THRESHOLD,
    build_shadow_policy,
    observe,
    summarize,
)

_SEED = 7
_EVIDENCE = {"consistency_score": 72.0, "coverage": 4, "expected_coverage": 5}
_CRITIC = {"confidence": 0.7, "valid_count": 3, "invalid_count": 1}
_CONSENSUS = {"status": "conflict", "confidence_score": 0.6, "overall_score": 55.0, "disagreement": 0.5}
_STATE = {"gate_retry_count": 0, "token_budget": 4000, "tokens_used": 1200,
          "last_consistency": 65.0, "disagreement": 0.4}


@pytest.fixture(scope="module")
def shadow_policies():
    torch.set_num_threads(1)
    try:
        torch.use_deterministic_algorithms(True)
    except Exception:
        pass
    p = build_shadow_policy(_SEED, warmup_steps=40, ppo_episodes=8, horizon=6)
    assert p.torch_available and p._trained
    return [p]


def test_observe_structure_and_deltas(shadow_policies):
    rec = observe(_EVIDENCE, _CONSENSUS, _STATE, shadow_policies, critic=_CRITIC,
                  skip_streak=0, reviews_done=0)
    for k in ("features", "signals", "baseline", "shadow", "delta"):
        assert k in rec
    for k in ("uniform", "rule", "mappo_current"):
        assert k in rec["baseline"]
    # 影子有效分应等于各 seed 均值（此处 1 seed）
    assert rec["shadow"]["per_seed_effective"][0] == rec["shadow"]["effective"]
    # delta 自洽：vs uniform 应等于 影子有效分 − uniform 有效分
    uni_eff = rec["baseline"]["uniform"]["effective"]
    assert abs(rec["delta"]["shadow_vs_uniform_effective"] - (rec["shadow"]["effective"] - uni_eff)) < 1e-6


def test_observe_no_side_effects(shadow_policies):
    ev = copy.deepcopy(_EVIDENCE)
    co = copy.deepcopy(_CONSENSUS)
    st = copy.deepcopy(_STATE)
    cr = copy.deepcopy(_CRITIC)
    observe(ev, co, st, shadow_policies, critic=cr, skip_streak=0, reviews_done=0)
    assert ev == _EVIDENCE
    assert co == _CONSENSUS
    assert st == _STATE
    assert cr == _CRITIC


def test_shadow_never_skips_when_reviews_low(shadow_policies):
    # reviews_done=0 < REVIEW_MIN_REVIEW(2) → 纪律硬约束禁止 skip（动作 4）
    rec = observe(_EVIDENCE, _CONSENSUS, _STATE, shadow_policies, critic=_CRITIC,
                  skip_streak=0, reviews_done=0)
    assert rec["shadow"]["action"] != 4
    # 同样验证 skip_streak 高时也压回
    rec2 = observe(_EVIDENCE, _CONSENSUS, _STATE, shadow_policies, critic=_CRITIC,
                   skip_streak=3, reviews_done=2)
    assert rec2["shadow"]["action"] != 4


def test_summarize_runs_on_records(shadow_policies):
    recs = [observe(_EVIDENCE, _CONSENSUS, _STATE, shadow_policies, critic=_CRITIC)
            for _ in range(5)]
    s = summarize(recs)
    assert s["n"] == 5
    assert "delta_vs_uniform" in s
    assert "shadow_action_dist" in s


def test_heuristic_arm_present_and_thresholded(shadow_policies):
    """第 4 对照臂：单特征理论阈值启发式（解析推导，非拟合 → 无泄漏）。"""
    rec = observe(_EVIDENCE, _CONSENSUS, _STATE, shadow_policies, critic=_CRITIC)
    h = rec["baseline"]["heuristic_f2"]
    assert h["action"] in (0, 2)
    assert h["action"] == (0 if rec["features"][1] > HEURISTIC_F2_THRESHOLD else 2)
    s = summarize([rec])
    assert "arm_means" in s and "heuristic_f2" in s["arm_means"]
    assert "heuristic_action_dist" in s
    assert "delta_vs_heuristic" in s


def test_rule_arm_is_discipline_gated(shadow_policies):
    """回归：rule 臂必须与 mappo/shadow 走**同一纪律门**。

    旧版探针对 rule 未加纪律门 → rule 可自由 skip（skip ⇒ effective ≡ 100）
    → rule 被虚高约 +1.0 分，是"rule 优于影子"的伪结论来源。
    """
    ev = {"consistency_score": 95.0, "coverage": 5, "expected_coverage": 5}
    co = {"status": "pass", "confidence_score": 0.9, "overall_score": 92.0, "disagreement": 0.2}
    st = {"gate_retry_count": 0, "token_budget": 4000, "tokens_used": 3800,
          "last_consistency": 90.0, "disagreement": 0.2}
    from engines.review_policy import _rule_action_idx, review_state_features

    feats = review_state_features(evidence=ev, critic=_CRITIC, consensus=co, state=st)
    assert _rule_action_idx(feats) == 4, "前置条件：未加纪律门时规则会选择 skip"

    rec = observe(ev, co, st, shadow_policies, critic=_CRITIC,
                  skip_streak=0, reviews_done=0)
    assert rec["baseline"]["rule"]["action"] == 0, "纪律门应把 skip 压回 trust_honest"
    assert rec["baseline"]["rule"]["action"] != 4

