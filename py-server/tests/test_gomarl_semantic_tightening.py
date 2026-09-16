# ============================================================
# 测试：GoMARL 语义级冲突检测「收紧」（C10）+ 接线（C3）
#
# 背景（docs/代码审查-核心引擎深度审查.md）：
#   C10 —— 旧 _check_semantic 仅凭 sim<0.3 就判冲突，会把"不同主题的
#          互补正确内容"误报为矛盾（假阳性极高）。
#   C3  —— 语义级检测此前在图管线（gomarl.py）与 API（engine.py）两条链
#          均不传 embeddings，从未真正执行。
# 本文件守护收紧后的三重门（长度 / 实体锚定 / 零向量）+ 接线（mix() 返回向量）。
# ============================================================

import asyncio

import numpy as np
import pytest

from engines.gomarl_conflict import ConsistencyChecker
from engines.gomarl_mixer import neural_mixer

pytestmark = pytest.mark.unit

_REPEAT = 8  # 越过 _SEMANTIC_MIN_LEN=100 的长度门


def _vec(*vals) -> np.ndarray:
    return np.array(vals, dtype=np.float32)


def _long(text: str, repeat: int = _REPEAT) -> str:
    return text * repeat


# ── C10：实体锚定 ──

class TestAnchorGate:
    def test_disjoint_for_different_topics(self):
        c = ConsistencyChecker()
        a = "TCP 通过三次握手建立连接。"
        b = "快速排序的平均时间复杂度是 O(n log n)。"
        assert c._shared_anchors(a, b) == set()

    def test_hit_for_same_entity(self):
        c = ConsistencyChecker()
        a = "TCP 三次握手建立连接。"
        b = "TCP 无需握手即可连接。"
        shared = c._shared_anchors(a, b)
        assert "tcp" in shared and "握手" in shared


# ── C10：三重门逐级短路 ──

class TestSemanticGates:
    def test_different_topics_low_sim_not_conflict(self):
        """核心防误报：不同主题 + 向量正交（sim=0）→ 不判冲突。"""
        c = ConsistencyChecker()
        a = _long("TCP 通过三次握手建立连接，确保收发能力就绪。")
        b = _long("快速排序平均时间复杂度为 O(n log n)，最坏 O(n^2)。")
        assert c._shared_anchors(a, b) == set()
        assert c._check_semantic(
            "teacher", "quizmaster", a, b, _vec(1, 0), _vec(0, 1)
        ) is None

    def test_same_topic_low_sim_flags(self):
        """同一实体（TCP/握手）+ 向量正交 → 判语义分歧。"""
        c = ConsistencyChecker()
        a = _long("TCP 通过三次握手建立连接。")
        b = _long("TCP 建立连接不需要任何握手。")
        got = c._check_semantic("teacher", "quizmaster", a, b, _vec(1, 0), _vec(0, 1))
        assert got is not None
        assert got.conflict_type == "semantic"
        assert "握手" in got.description or "tcp" in got.description.lower()

    def test_short_content_not_judged(self):
        c = ConsistencyChecker()
        assert c._check_semantic(
            "a", "b", "TCP 握手。", "TCP 握手不必要。", _vec(1, 0), _vec(0, 1)
        ) is None

    def test_zero_vector_not_judged(self):
        """E5 编码失败 → 零向量 → sim≈0 不得据此判冲突。"""
        c = ConsistencyChecker()
        a = _long("TCP 通过三次握手建立连接。")
        b = _long("TCP 建立连接不需要任何握手。")
        assert c._check_semantic("a", "b", a, b, _vec(0, 0), _vec(0, 0)) is None
        assert c._check_semantic(
            "a", "b", a, b, np.zeros(2, dtype=np.float32), _vec(1, 0)
        ) is None


# ── C10：check() 集成（embeddings 作为语义门） ──

class TestCheckIntegration:
    @staticmethod
    def _same_topic_results():
        return [
            {"agent_name": "teacher", "content": _long("TCP 通过三次握手建立连接。")},
            {"agent_name": "quizmaster", "content": _long("TCP 建立连接不需要任何握手。")},
        ]

    def test_with_embeddings_emits_semantic(self):
        c = ConsistencyChecker()
        embs = np.stack([_vec(1, 0), _vec(0, 1)])
        conflicts = c.check(self._same_topic_results(), embs)
        assert any(x.conflict_type == "semantic" for x in conflicts)

    def test_without_embeddings_no_semantic(self):
        c = ConsistencyChecker()
        conflicts = c.check(self._same_topic_results(), None)
        assert not any(x.conflict_type == "semantic" for x in conflicts)

    def test_different_topics_no_semantic(self):
        c = ConsistencyChecker()
        results = [
            {"agent_name": "teacher", "content": _long("TCP 通过三次握手建立连接。")},
            {"agent_name": "quizmaster", "content": _long("快速排序平均 O(n log n)。")},
        ]
        embs = np.stack([_vec(1, 0), _vec(0, 1)])
        conflicts = c.check(results, embs)
        assert not any(x.conflict_type == "semantic" for x in conflicts)


# ── C3：接线（mix() 返回 agent_embeddings） ──

class TestMixerWiring:
    def test_mix_returns_agent_embeddings(self, monkeypatch):
        fake = np.ones((2, 8), dtype=np.float32)
        monkeypatch.setattr(neural_mixer.encoder, "encode_batch", lambda texts: fake)
        monkeypatch.setattr(neural_mixer, "use_neural", False)
        out = asyncio.run(neural_mixer.mix(
            [{"agent_name": "teacher", "content": "x", "score": 5.0},
             {"agent_name": "quizmaster", "content": "y", "score": 6.0}],
            {}, "tcp",
        ))
        assert "agent_embeddings" in out
        assert out["agent_embeddings"].shape == (2, 8)

    def test_mix_empty_results_returns_none_for_get(self):
        """空输入早退分支不含该 key → 调用方 .get() 必须安全得到 None。"""
        out = asyncio.run(neural_mixer.mix([], {}, "tcp"))
        assert out.get("agent_embeddings") is None
