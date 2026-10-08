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
import engines.gomarl_mixer as mixer_mod
from engines.gomarl_mixer import NeuralGroupMixer, neural_mixer

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
    def test_torch_trained_weights_take_priority_over_onnx(self, monkeypatch):
        """PyTorch 可用时必须先加载训练权重，不得探测 ONNX 均匀权重兜底。"""
        calls: list[str] = []

        class _FakeMixerNet:
            def __init__(self, n_agents: int, embed_dim: int, hidden_dim: int):
                self.n_agents = n_agents
                self.embed_dim = embed_dim
                self.hidden_dim = hidden_dim
                self.group = [list(range(n_agents))]

            def eval(self):
                return self

        def _fake_ensure_torch():
            calls.append("torch")
            monkeypatch.setattr(mixer_mod, "_TORCH_AVAILABLE", True)
            return object(), object(), object()

        def _fake_ensure_onnx():
            calls.append("onnx")
            monkeypatch.setattr(mixer_mod, "_ONNX_AVAILABLE", True)
            return True

        monkeypatch.setattr(mixer_mod, "_TORCH_AVAILABLE", None)
        monkeypatch.setattr(mixer_mod, "_ONNX_AVAILABLE", False)
        monkeypatch.setattr(mixer_mod, "GroupMixerNet", _FakeMixerNet)
        monkeypatch.setattr(mixer_mod, "_ensure_torch", _fake_ensure_torch)
        monkeypatch.setattr(mixer_mod, "_ensure_onnx", _fake_ensure_onnx)

        mixer = NeuralGroupMixer()
        monkeypatch.setattr(mixer, "use_neural", True)
        monkeypatch.setattr(mixer, "_probe_trained_embed_dim", lambda: 8)

        def _fake_load_trained_weights():
            # 模拟「权重完整命中」：必须同时置位完成标记并清空不匹配层，
            # 否则等于模拟一次失败加载，与 (1, 1) 的语义自相矛盾。
            mixer._weights_complete = True
            mixer._weight_mismatch_layers = []
            return 1, 1

        monkeypatch.setattr(mixer, "_load_trained_weights", _fake_load_trained_weights)

        initialized = mixer._init_mixer(2)

        assert isinstance(initialized, _FakeMixerNet)
        assert calls and calls[0] == "torch"
        assert "onnx" not in calls
        assert mixer.get_stats()["mixer_neural_mode"] == "torch"
        assert mixer.get_stats()["mixer_trained_loaded"] is True
        assert mixer.get_stats()["mixer_embed_dim"] == 8

    def test_trained_mixer_preserves_score_band_discrimination(
        self, monkeypatch, trained_mixer_checkpoint
    ):
        """n=6 训练模型对低/中/高分档必须保持严格区分，不能被截断为同一值。"""
        rng = np.random.default_rng(20261005)
        embeddings = rng.standard_normal((6, 768)).astype(np.float32)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        agent_names = [
            "teacher",
            "quizmaster",
            "media_designer",
            "extension",
            "ppt_designer",
            "code_practice",
        ]

        mixer = NeuralGroupMixer()
        monkeypatch.setattr(mixer.encoder, "encode_batch", lambda texts: embeddings)
        monkeypatch.setattr(
            mixer,
            "_compute_dynamic_weights",
            lambda names, profile: {name: 1.0 for name in names},
        )
        monkeypatch.setattr(mixer_mod.pg_client, "log_agent_score", lambda *args: None)
        monkeypatch.setattr(mixer_mod.redis_client, "cache_agent_weights", lambda weights: None)

        async def _run_levels() -> list[float]:
            outputs: list[float] = []
            for level in (0.5, 5.0, 9.5):
                agent_results = [
                    {"agent_name": name, "content": f"固定内容-{index}", "score": level}
                    for index, name in enumerate(agent_names)
                ]
                result = await mixer.mix(agent_results, {}, "量纲回归")
                assert result["neural_used"] is True
                outputs.append(result["consensus_score"])
            return outputs

        scores = asyncio.run(_run_levels())

        assert scores[0] < scores[1] < scores[2], scores
        # ── 量纲回归锁（a9e0733 曾把共识分 ×10）──
        # 夹具的 global_mixer 刻意构造成 identity 透传：
        #   hidden = ReLU(mean(agent_scores)), out = mean(hidden)
        # ⇒ 网络输出在数值上恒等于输入档位，mix() 只做 [0,10] 边界截断，
        #   故共识分必须**精确等于**档位本身。
        # 这条断言不是上面单调性的重复，实测两类变异可证：
        #   (a) a9e0733 的原始形态 min(10.0, cs*10)（×10 在 clamp 内）→ 高档位饱和成
        #       10.0，先被上面的单调性断言拦下；
        #   (b) 保持单调的缩放 cs*1.05（0.525 / 5.25 / 9.975）→ 单调、互异、∈(0,10]
        #       三条既有断言**全部通过**，只有本行能抓到（报 Mismatched elements）。
        assert scores == pytest.approx([0.5, 5.0, 9.5], abs=1e-5), scores
        assert any(score < 10.0 for score in scores), scores
        assert len(set(scores)) > 1, scores
        stats = mixer.get_stats()
        assert stats["mixer_neural_mode"] == "torch"
        assert stats["mixer_trained_loaded"] is True
        assert stats["mixer_weights_complete"] is True
        assert stats["mixer_weight_mismatch_layers"] == []

    def test_n_agents_weight_shape_mismatch_is_observable(
        self, trained_mixer_checkpoint, caplog
    ):
        """n≠6 的随机初始化层必须通过 WARNING 与 stats 显式暴露。"""
        mixer = NeuralGroupMixer()
        with caplog.at_level("WARNING", logger="netlearn.gomarl_mixer"):
            mixer._init_mixer(5)

        assert "current_n_agents=5" in caplog.text
        assert "trained_n_agents=6" in caplog.text
        assert "该层保持随机初始化" in caplog.text

        # docstring 声明的是「WARNING **与 stats** 双通道」，故 stats 侧必须有断言。
        # 缺失这组断言时本用例对「是否真的降级」不敏感：上面三条 WARNING 实际由
        # _load_trained_weights 发出，与 _init_mixer 的降级分支无关 —— 实测把降级
        # 分支改成 if False:（仍宣称 torch）本用例依然 PASSED，而邻居
        # test_n_agents_shape_mismatch_must_not_claim_neural 才红。
        stats = mixer.get_stats()
        assert stats["mixer_weights_complete"] is False
        assert "global_mixer.0.weight" in stats["mixer_weight_mismatch_layers"]
        assert 5 in stats["mixer_shape_mismatch_n_agents"]

    def test_n_agents_shape_mismatch_must_not_claim_neural(
        self, trained_mixer_checkpoint, caplog
    ):
        """n≠6 ⇒ 权重不完整 ⇒ 不得返回网络、不得标称神经推理（诚信红线）。

        与 ONNX「均匀权重冒充神经推理」同类：global_mixer.0.weight 形状不匹配时该层
        保持随机初始化，此时任何输出都不得被标为 neural_used=True。
        """
        mixer = NeuralGroupMixer()
        with caplog.at_level("WARNING", logger="netlearn.gomarl_mixer"):
            initialized = mixer._init_mixer(5)

        # 1) 不得返回任何可推理网络
        assert initialized is None
        stats = mixer.get_stats()
        # 2) 模式必须可与 torch / onnx_uniform_fallback / rule 区分
        assert stats["mixer_neural_mode"] == "shape_mismatch_fallback"
        assert stats["mixer_neural_mode"] not in ("torch", "onnx_uniform_fallback", "rule")
        # 3) 不得宣称训练权重已完整加载
        assert stats["mixer_trained_loaded"] is False
        assert stats["mixer_weights_complete"] is False
        assert "global_mixer.0.weight" in stats["mixer_weight_mismatch_layers"]
        assert 5 in stats["mixer_shape_mismatch_n_agents"]
        assert "冒充神经推理" in caplog.text

    def test_n_agents_six_still_uses_torch(self, trained_mixer_checkpoint):
        """回归对照：n=6 权重完整 ⇒ 仍必须走真神经推理，不得被降级逻辑误伤。"""
        mixer = NeuralGroupMixer()
        initialized = mixer._init_mixer(6)
        assert initialized is not None
        stats = mixer.get_stats()
        assert stats["mixer_neural_mode"] == "torch"
        assert stats["mixer_trained_loaded"] is True
        assert stats["mixer_weights_complete"] is True
        assert stats["mixer_weight_mismatch_layers"] == []
        assert stats["mixer_shape_mismatch_n_agents"] == []

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
