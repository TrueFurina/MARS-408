# tests/test_review_rule_upgrade.py — 规则折进解析阈值的守护测试（2026-09-14 采纳）
#
# 背景：`experiments/diag_rule_upgrade.py` 实测**否证**了"问题在阈值位置"的假设 ——
#   仅把级联门槛 0.6 → 0.675（其余不变）：主集 −0.033 (t=−0.27) / 泛化 −0.133 (t=−1.02)。
#   真因是低证据区**回落到 balanced**（其真实增益恒 0，240 样本中 0 次最优）。
#   采纳的折法 = 阈值二分支：f2 > 0.675 → trust_honest，否则 trust_consensus。
#   实测收益：主集 +0.859 (t=+3.27) / 泛化 +1.032 (t=+2.87)，capture 39.1%→54.8%。
#
# 本文件守护四件事：
#   1. 默认走新二分支（含阈值边界方向）；
#   2. **skip 前置支路保留** —— 生产的成本控制能力不被"折进"破坏（纪律门另行拦截连发）；
#   3. 回退开关 `RULE_F2_BINARY=False` 仍能回到原级联；
#   4. 折进后的真实有效分确实高于原级联（防未来无意回退到弱规则）。

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))

import engines.review_policy as rp  # noqa: E402
from agents.quality_gate import weighted_consistency_score  # noqa: E402
from engines.review_env_calibrated import discipline_gate  # noqa: E402
from engines.review_policy import (  # noqa: E402
    _weights_of,
    review_state_features,
    review_weight_schema,
)
from run_shadow_probe import generate_samples  # noqa: E402

THR = rp.RULE_EVIDENCE_HONEST
N = 240
DATA_SEED = 20260914


def _feats(f2: float, cost: float = 0.1, status: float = 0.5,
           disagree: float = 0.5, valid: float = 0.2, invalid: float = 0.2) -> list:
    f = [0.5] * 12
    f[1], f[3], f[5], f[6], f[7], f[9] = f2, status, disagree, valid, invalid, cost
    return f


# ── 1. 默认 = 阈值二分支 ──

def test_default_is_binary_threshold():
    assert rp.RULE_F2_BINARY is True, "默认必须已折进阈值（实测收益 +0.859/+1.032）"
    assert rp._rule_action_idx(_feats(0.80)) == 0, "强证据 → trust_honest"
    assert rp._rule_action_idx(_feats(0.50)) == 2, "弱证据 → trust_consensus（不再 balanced 兜底）"


def test_threshold_boundary_is_strict_greater():
    """方向纪律：f2 > THR → honest；f2 == THR → consensus（解析推导为严格不等式）。"""
    assert rp._rule_action_idx(_feats(THR + 0.001)) == 0
    assert rp._rule_action_idx(_feats(THR)) == 2


def test_balanced_no_longer_reachable_by_default():
    """核心回归：真实增益恒 0 的 balanced 不得再作为确定性规则的输出。

    （旧级联在低证据区兜底到 balanced —— 这正是 capture 只有 39.1% 的成因。）
    """
    outs = {rp._rule_action_idx(_feats(f2)) for f2 in (0.0, 0.3, 0.5, 0.6, 0.67, 0.675, 0.9)}
    assert 3 not in outs, f"默认规则不应再输出 balanced，实际输出集 = {outs}"


# ── 2. skip 前置支路必须保留（生产成本控制能力）──

def test_skip_precondition_preserved():
    assert rp._rule_action_idx(_feats(0.90, cost=0.9)) == 4, "成本高压 + 质量达标 → 允许 skip"
    assert rp._rule_action_idx(_feats(0.90, cost=0.1)) == 0, "质量达标但成本不高 → 不 skip"
    assert rp._rule_action_idx(_feats(0.50, cost=0.9)) == 2, "成本高但质量未达标 → 不 skip"


# ── 3. 回退开关与 legacy 保留 ──

def test_legacy_rollback_switch(monkeypatch):
    monkeypatch.setattr(rp, "RULE_F2_BINARY", False)
    assert rp._rule_action_idx(_feats(0.45)) == 3, "回退后应恢复原级联的 balanced 兜底"
    assert rp._rule_action_idx(_feats(0.80)) == 0


def test_legacy_preserved_for_history():
    """legacy 原级联必须仍正确（不参与默认路径，但历史数字需可复现到当时实现）。"""
    assert rp._rule_action_idx_legacy(_feats(0.45)) == 3
    assert rp._rule_action_idx_legacy(_feats(0.80)) == 0
    assert rp._rule_action_idx_legacy(_feats(0.90, cost=0.9)) == 4
    assert rp._rule_action_idx_legacy(_feats(0.45, valid=0.5, invalid=0.1)) == 1, "批评信噪比高 → critic"
    assert rp._rule_action_idx_legacy(
        _feats(0.45, status=0.0, disagree=0.2)) == 2, "共识 pass 且分歧低 → consensus"


# ── 4. 折叠后的真实有效分必须确实更高（防无意回退）──

def _mean_eff(samples, idxs) -> float:
    tot = 0.0
    for s, i in zip(samples, idxs):
        tot += weighted_consistency_score(
            s["evidence"], s["consensus"], review_weight_schema(_weights_of(i)))[0]
    return tot / len(samples)


@pytest.fixture(scope="module")
def real_contexts():
    rng = random.Random(DATA_SEED)
    samples = generate_samples(N, rng)
    feats = [
        review_state_features(
            evidence=s["evidence"], critic=s["critic"], consensus=s["consensus"],
            state=s["state"], mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"],
        )
        for s in samples
    ]
    return samples, feats


def test_folded_rule_beats_legacy_on_real_contexts(real_contexts):
    samples, feats = real_contexts
    new_idx = [discipline_gate(rp._rule_action_idx(f), f, 0, 0) for f in feats]
    old_idx = [discipline_gate(rp._rule_action_idx_legacy(f), f, 0, 0) for f in feats]
    uni = _mean_eff(samples, [3] * len(samples))
    new_m, old_m = _mean_eff(samples, new_idx), _mean_eff(samples, old_idx)

    assert new_m > uni + 2.5, f"折进版应明显优于均匀：{new_m:.3f} vs {uni:.3f}"
    assert new_m > old_m + 0.5, (
        f"折进版应显著优于原级联（实测 +0.859）：new={new_m:.3f} old={old_m:.3f}")


def test_rule_is_deterministic_and_discipline_gated(real_contexts):
    """确定性（同输入同输出）+ 全臂过同一纪律门（不得绕开护栏）。"""
    _, feats = real_contexts
    for f in feats[:40]:
        a1, a2 = rp._rule_action_idx(f), rp._rule_action_idx(f)
        assert a1 == a2
        assert discipline_gate(a1, f, 0, 0) != 4, "reviews_done=0 ⇒ skip 必被纪律门压回"
