# ============================================================
# 单元测试：M3 · MAPPO 权重灰度接线（flag-ON 消费路径）
#
# 背景：
# - config.py `use_mappo_policy` 自 baf16a7（2026-10-10）起为 True：
#   生产默认已激活，无 torch / 未训练时 fail-open 降级 EWMA 规则。
# - test_m3_mappo_policy.py::TestMixerMappoGrayscale 只钉了 **flag-OFF**
#   契约（mixer._use_mappo is False），且该文件在 Windows 被 conftest
#   collect_ignore（模块导入期 `_ensure_torch()` → 原生 torch SIGSEGV 风险）
#   ⇒ flag-ON 的消费路径（gomarl_mixer.py:886-901）**任何平台零覆盖**。
#   生产默认 ON 而路径无覆盖 = 「开关已翻、路径未验」，本文件补上。
#
# 覆盖契约（gomarl_mixer.py::_compute_dynamic_weights 尾部 MAPPO 块）：
#   1) 生产默认 flag=ON（防静默翻回）；
#   2) flag ON + 策略返回乘性因子 → 对应 Agent 权重被调整并重新归一化；
#   3) 策略返回 {}（规则未训练）→ 与 flag-OFF 完全等价（零影响）；
#   4) 策略抛异常 → fail-open 保持规则权重，不向调用方抛错；
#   5) 仅请求集合内的 Agent 名被调整（未知名被 `if k in weights` 过滤）；
#   6) 调整后执行第二次归一化（Σw == len(agents)）。
#
# Windows 安全（全程无 torch）：
# - engines.mappo_policy 用 PEP 562 惰性单例（模块级 __getattr__），
#   导入期零副作用；但首次访问 `mappo_policy` 属性会构造 MappoPolicy
#   → _ensure_torch() → import torch ⇒ 本机 segv 风险。故测试以
#   monkeypatch 预置模块全局 `_mappo_policy_singleton`（非 None 时
#   __getattr__ 原样返回它，永不触达构造），注入记录型假策略。
# - gomarl_mixer 模块级 `pg_client` 整体替换为替身（EWMA 历史支路返回 []），
#   权重仅由 _base_weights + 学生画像 + MAPPO 决定，可精确复算。
#
# 运行：python -m pytest tests/test_mixer_mappo_wiring.py -v
# ============================================================

import os
import sys
from types import SimpleNamespace

import pytest

# 确保 py-server 根目录在 sys.path，使 `from engines import ...` 可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.unit

import engines.gomarl_mixer as gm  # noqa: E402
import engines.mappo_policy as mp  # noqa: E402
from config import get_gomarl_config  # noqa: E402
from engines.gomarl_mixer import NeuralGroupMixer  # noqa: E402

AGENTS = ["teacher", "quizmaster"]
BEGINNER_PROFILE = {"level": "beginner"}  # 仅触发 teacher×1.15 画像支路（无 topic → 不走 teaching_rules）


class _FakeMappoPolicy:
    """记录型假策略：替身 engines.mappo_policy 的惰性单例。

    adjust: agent_weight_adjust 返回值（乘性因子表）；raises 非 None 时抛出。
    """

    def __init__(self, adjust=None, raises=None):
        self.adjust = {} if adjust is None else adjust
        self.raises = raises
        self.calls: list[dict] = []

    def agent_weight_adjust(self, profile, action=None):
        self.calls.append(profile)
        if self.raises is not None:
            raise self.raises
        return dict(self.adjust)


def _install_fake_policy(monkeypatch, adjust=None, raises=None) -> _FakeMappoPolicy:
    """把假策略注入 mappo_policy 惰性单例槽位（非 None ⇒ __getattr__ 直接返回）。"""
    fake = _FakeMappoPolicy(adjust=adjust, raises=raises)
    monkeypatch.setattr(mp, "_mappo_policy_singleton", fake)
    return fake


def _isolate_pg(monkeypatch):
    """替换 gomarl_mixer 模块级 pg_client：EWMA 历史支路恒空、写支路空操作。"""
    monkeypatch.setattr(gm, "pg_client", SimpleNamespace(
        get_agent_history=lambda name, window: [],
        log_agent_score=lambda *a, **k: None,
    ))


def _weights(mixer: NeuralGroupMixer, agents=AGENTS, profile=BEGINNER_PROFILE) -> dict:
    return mixer._compute_dynamic_weights(agents, profile)


# ════════════════════════════════════════════════════════════
# 1. 生产默认：flag=ON（激活不许被静默翻回）
# ════════════════════════════════════════════════════════════

def test_production_default_flag_is_on():
    """config.py 默认 use_mappo_policy=True（baf16a7 激活态）；mixer 据此置 _use_mappo。"""
    assert get_gomarl_config().get("use_mappo_policy") is True
    assert NeuralGroupMixer()._use_mappo is True


# ════════════════════════════════════════════════════════════
# 2. flag-ON 消费路径：调整 / 零影响 / fail-open / 过滤 / 归一化
# ════════════════════════════════════════════════════════════

def test_flag_on_applies_policy_adjustment(monkeypatch):
    """flag ON + 策略返回 {"teacher": 1.5} → teacher 权重被抬高（相对份额严格上升）。"""
    _isolate_pg(monkeypatch)
    monkeypatch.setitem(get_gomarl_config(), "use_mappo_policy", False)
    baseline = _weights(NeuralGroupMixer())  # flag-OFF 基线

    monkeypatch.setitem(get_gomarl_config(), "use_mappo_policy", True)
    fake = _install_fake_policy(monkeypatch, adjust={"teacher": 1.5})
    adjusted = _weights(NeuralGroupMixer())

    # 策略确实被调用，且收到学生画像（透传契约）
    assert fake.calls == [BEGINNER_PROFILE]
    # teacher 相对 quizmaster 的份额严格上升（1.5× 乘子 + 重归一化不变量）
    assert adjusted["teacher"] / adjusted["quizmaster"] > baseline["teacher"] / baseline["quizmaster"]
    assert adjusted["teacher"] > baseline["teacher"]


def test_flag_on_empty_adjust_is_zero_impact(monkeypatch):
    """策略返回 {}（规则未训练）→ 与 flag-OFF 基线逐位相等（零影响契约）。"""
    _isolate_pg(monkeypatch)
    monkeypatch.setitem(get_gomarl_config(), "use_mappo_policy", False)
    baseline = _weights(NeuralGroupMixer())

    monkeypatch.setitem(get_gomarl_config(), "use_mappo_policy", True)
    _install_fake_policy(monkeypatch, adjust={})
    assert _weights(NeuralGroupMixer()) == baseline


def test_flag_on_policy_failure_keeps_rule_weights(monkeypatch):
    """策略抛异常 → fail-open：保持规则权重，不向调用方抛错。"""
    _isolate_pg(monkeypatch)
    monkeypatch.setitem(get_gomarl_config(), "use_mappo_policy", False)
    baseline = _weights(NeuralGroupMixer())

    monkeypatch.setitem(get_gomarl_config(), "use_mappo_policy", True)
    _install_fake_policy(monkeypatch, raises=RuntimeError("policy boom"))
    assert _weights(NeuralGroupMixer()) == baseline


def test_flag_on_filters_unknown_agent_names(monkeypatch):
    """仅请求集合内的 Agent 名被调整；未知名被 `if k in weights` 过滤（不 KeyError）。

    精确值钉死：base(teacher=1.0/quizmaster=0.9) ×beginner画像(teacher×1.15)
    ×MAPPO(teacher×1.5) 后重归一化（Σ==2）——过滤失效的变异会先乘 teacher
    再对 ghost KeyError 被 fail-open 吞掉（份额断言仍绿），只有精确值能抓住。
    """
    _isolate_pg(monkeypatch)
    monkeypatch.setitem(get_gomarl_config(), "use_mappo_policy", True)
    _install_fake_policy(monkeypatch, adjust={"teacher": 1.5, "ghost_agent": 3.0})
    weights = _weights(NeuralGroupMixer(), agents=["teacher", "quizmaster"])
    assert set(weights) == {"teacher", "quizmaster"}, "不得引入未请求的 Agent"
    assert weights["teacher"] == pytest.approx(1.314285714285714)
    assert weights["quizmaster"] == pytest.approx(0.6857142857142857)


def test_flag_on_renormalizes_after_adjustment(monkeypatch):
    """调整后执行第二次归一化：Σw == len(agents)（乘子不破坏总量不变式）。

    精确值钉死：teacher 1.0×1.15×1.5=1.725 / quizmaster 0.9×0.5=0.45 /
    media_designer 0.85（beginner 画像不触达）→ Σ=3.025 → 各 ÷3.025×3。
    """
    _isolate_pg(monkeypatch)
    monkeypatch.setitem(get_gomarl_config(), "use_mappo_policy", True)
    _install_fake_policy(monkeypatch, adjust={"teacher": 1.5, "quizmaster": 0.5})
    agents = ["teacher", "quizmaster", "media_designer"]
    weights = _weights(NeuralGroupMixer(), agents=agents)
    assert set(weights) == set(agents)
    assert abs(sum(weights.values()) - len(agents)) < 1e-9
    assert weights["teacher"] == pytest.approx(1.7107438016528924)
    assert weights["quizmaster"] == pytest.approx(0.44628099173553726)
    assert weights["media_designer"] == pytest.approx(0.8429752066115703)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
