"""QMIX 必须使用 target mixing network（2026-11-02）。

标准 QMIX 的 TD 目标要用**慢更新**的 target mixer 计算。旧实现的目标里用的是
在线 ``mixing_net`` / ``mixing_bias``，而 target Q 网络是单独一份、定期同步的
—— 混合器漏了目标副本。后果：目标随在线混合器的梯度一起漂移，训练不稳定且
目标有偏。

本测试在 torch 不可用时 skip（本机 torch 为坏装：``shm.dll`` 缺失，项目自己的
``_ensure_torch`` 会把这种失败吞成 None）。
"""
import pytest

from engines.marl_dqn import _ensure_torch

_torch = _ensure_torch()
pytestmark = pytest.mark.skipif(_torch is None, reason="torch 不可用（未安装或 DLL 坏装）")


def _make_qmix():
    from engines.marl_dqn import QMIXLearner

    return QMIXLearner(state_dim=8, hidden=16, mix_hidden=8, seed=1)


def test_qmix_has_target_mixing_networks():
    m = _make_qmix()
    assert hasattr(m, "target_mixing_net")
    assert hasattr(m, "target_mixing_bias")
    for p1, p2 in zip(m.target_mixing_net.parameters(), m.mixing_net.parameters()):
        assert _torch.equal(p1, p2), "初始时 target mixer 应等于在线 mixer"


def test_qmix_target_mixer_synced_on_target_update():
    m = _make_qmix()
    m.target_update_every = 1
    m.batch_size = 2
    # 人为改在线混合器，确认 target 同步会覆盖回来
    with _torch.no_grad():
        for p in m.mixing_net.parameters():
            p.add_(0.1)
    for _ in range(4):
        m.remember([0.0] * 8, {0: 0, 1: 0, 2: 0}, 1.0, [0.0] * 8, False)
    m.train_step_once()
    for p1, p2 in zip(m.target_mixing_net.parameters(), m.mixing_net.parameters()):
        assert _torch.equal(p1, p2), "target mixer 未随 target 同步更新"
