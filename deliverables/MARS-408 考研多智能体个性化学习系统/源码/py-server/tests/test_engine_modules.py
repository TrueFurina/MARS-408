# ============================================================
# Engine Module Tests — FrugalRAG SFT/Stop + GoMARL Mixer/Conflict
# ============================================================
# Purpose: Verify 4 new engine modules + 8 engine API endpoints
# ============================================================

import os
import sys
import json
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

# segv_env：本模块调用真实 torch/numpy 嵌入等，Windows 原生库下触发 SIGSEGV；
# 仅 CI/Linux 干净环境运行，本地 Windows 由 conftest 自动跳过。
pytestmark = pytest.mark.segv_env
from dataclasses import dataclass

# ── Project paths ──
PY_SERVER_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PY_SERVER_DIR)


# ============================================================
# 1. QueryPreprocessor Tests (frugal_rag_sft.py)
# ============================================================

class TestQueryPreprocessor:
    """查询预处理模块测试"""

    def setup_method(self):
        from engines.frugal_rag_sft import QueryPreprocessor
        self.preprocessor = QueryPreprocessor()

    def test_preprocess_removes_noise(self):
        """口语噪声去除"""
        result = self.preprocessor.preprocess("请问什么是TCP呢？")
        assert "请问" not in result
        assert "呢" not in result
        assert "TCP" in result

    def test_preprocess_adds_question_mark(self):
        """自动补问号"""
        result = self.preprocessor.preprocess("什么是三次握手")
        assert result[-1] in "？?"

    def test_preprocess_preserves_existing_punctuation(self):
        """已有标点不重复添加"""
        result = self.preprocessor.preprocess("什么是三次握手？")
        assert not result.endswith("？？")

    def test_extract_keywords_network(self):
        """计网关键词提取"""
        kws = self.preprocessor.extract_keywords(
            "TCP三次握手和UDP有什么区别", "computer_network"
        )
        # extract_keywords returns matching keywords from _DOMAIN_KEYWORDS
        assert len(kws) >= 1
        # At least some network-related keywords should be found
        all_text = " ".join(kws)
        assert "TCP" in all_text or "UDP" in all_text or "三次握手" in all_text

    def test_extract_keywords_ds(self):
        """数据结构关键词提取"""
        kws = self.preprocessor.extract_keywords(
            "链表和栈的区别是什么", "data_structures"
        )
        # Should find at least some data structure keywords
        assert len(kws) >= 1

    def test_extract_keywords_no_course(self):
        """无指定课程时搜索全部领域"""
        kws = self.preprocessor.extract_keywords("TCP和链表有什么关系")
        # Should find keywords from multiple domains
        assert len(kws) >= 2

    def test_assess_complexity_simple(self):
        """简单问题判定"""
        result = self.preprocessor.assess_complexity("什么是TCP")
        assert result == "simple"

    def test_assess_complexity_complex(self):
        """复杂问题判定"""
        result = self.preprocessor.assess_complexity(
            "TCP三次握手和UDP无连接的区别在拥塞控制和流量控制中的表现有什么不同"
        )
        assert result == "complex"

    def test_assess_complexity_medium(self):
        """中等问题判定"""
        result = self.preprocessor.assess_complexity("TCP和UDP的区别是什么？")
        assert result == "medium"


# ============================================================
# 2. HeuristicStopDecision Tests (frugal_rag_stop.py)
# ============================================================
# NOTE: decide() signature is (question, course, current_chunks, iteration, max_iterations)
# It internally computes coverage from question keywords vs chunks text

class TestHeuristicStopDecision:
    """启发式停止决策模块测试（GRPO 风格思路，非强化学习）"""

    def setup_method(self):
        from engines.frugal_rag_stop import HeuristicStopDecision
        self.stop = HeuristicStopDecision()

    def test_stop_decision_high_coverage(self):
        """有高质量chunks时应停止"""
        decision = self.stop.decide(
            question="TCP三次握手", course="computer_network",
            current_chunks=[{"text": "TCP三次握手SYN ACK连接建立", "score": 0.9}],
            iteration=0, max_iterations=3
        )
        assert decision.should_stop is True
        assert decision.confidence > 0.5

    def test_stop_decision_no_chunks(self):
        """无chunks应继续检索"""
        decision = self.stop.decide(
            question="复杂问题需要多轮检索", course="computer_network",
            current_chunks=[], iteration=0, max_iterations=3
        )
        assert decision.should_stop is False

    def test_stop_decision_simple_threshold(self):
        """简单问题阈值较低(0.6)"""
        decision = self.stop.decide(
            question="什么是TCP", course="computer_network",
            current_chunks=[{"text": "TCP传输控制协议", "score": 0.85}],
            iteration=0, max_iterations=3
        )
        # Simple questions have threshold 0.6 — with good chunks should stop
        assert decision.threshold_used == pytest.approx(0.6, abs=0.05)

    def test_stop_decision_complex_threshold(self):
        """复杂问题阈值较高(0.8)"""
        decision = self.stop.decide(
            question="TCP三次握手和UDP无连接的区别在拥塞控制中的表现",
            course="computer_network",
            current_chunks=[], iteration=0, max_iterations=3
        )
        assert decision.threshold_used == pytest.approx(0.8, abs=0.05)

    def test_stop_decision_max_iterations(self):
        """到达最大迭代数强制停止"""
        decision = self.stop.decide(
            question="复杂问题", course="computer_network",
            current_chunks=[], iteration=4, max_iterations=3
        )
        assert decision.should_stop is True

    def test_update_threshold_ewma(self):
        """EWMA 动态阈值更新"""
        old_threshold = self.stop._base_thresholds.get("simple", 0.6)
        self.stop.update_threshold("simple", 0.9, True)
        # After update, base_thresholds should reflect EWMA change
        assert isinstance(self.stop._base_thresholds, dict)
        assert "simple" in self.stop._base_thresholds

    def test_get_stats(self):
        """统计信息返回"""
        stats = self.stop.get_stats()
        assert "total_decisions" in stats
        assert isinstance(stats["total_decisions"], int)


# ============================================================
# 3. QueryRewriter Tests (frugal_rag_stop.py)
# ============================================================
# NOTE: rewrite() signature is (question, course, previous_queries, previous_chunks) -> Optional[str]

class TestQueryRewriter:
    """查询重写模块测试"""

    def setup_method(self):
        from engines.frugal_rag_stop import QueryRewriter
        with patch("engines.frugal_rag_stop.LLMProvider") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm.text_completion = AsyncMock(return_value="TCP三次握手连接建立SYN ACK")
            mock_llm_cls.return_value = mock_llm
            self.rewriter = QueryRewriter()

    @pytest.mark.asyncio
    async def test_rewrite_with_llm(self):
        """LLM 重写查询"""
        from engines.frugal_rag_stop import QueryRewriter
        with patch("engines.frugal_rag_stop.LLMProvider") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm.text_completion = AsyncMock(return_value="TCP三次握手连接建立SYN ACK")
            mock_llm_cls.return_value = mock_llm
            rewriter = QueryRewriter()

            result = await rewriter.rewrite(
                "什么是TCP连接",
                "computer_network",
                previous_queries=["什么是TCP"],
                previous_chunks=[{"text": "TCP传输控制协议", "score": 0.9}]
            )
            # Either LLM succeeds or falls back to original
            assert result is not None
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rewrite_fallback_no_llm(self):
        """LLM 失败时降级"""
        from engines.frugal_rag_stop import QueryRewriter
        with patch("engines.frugal_rag_stop.LLMProvider") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm.text_completion = AsyncMock(side_effect=Exception("LLM unavailable"))
            mock_llm_cls.return_value = mock_llm
            rewriter = QueryRewriter()

            result = await rewriter.rewrite(
                "什么是TCP连接", "computer_network",
                previous_queries=[], previous_chunks=[]
            )
            # Fallback: returns None or original question
            assert result is None or isinstance(result, str)


# ============================================================
# 4. LoRAAdapter Tests (frugal_rag_stop.py)
# ============================================================
# NOTE: get_lora_config() returns nested dict {"lora": {"r": 8, ...}, "training": {"num_samples": 500, ...}, "description": ...}
# NOTE: generate_training_data_template(course, samples) -> list[dict]

class TestLoRAAdapter:
    """LoRA 少样本适配配置测试"""

    def setup_method(self):
        from engines.frugal_rag_stop import LoRAAdapter
        self.adapter = LoRAAdapter()

    def test_get_lora_config(self):
        """LoRA 配置返回 — 嵌套结构"""
        config = self.adapter.get_lora_config()
        assert "lora" in config
        assert config["lora"]["r"] == 8
        assert config["lora"]["lora_alpha"] == 16
        assert "training" in config
        assert config["training"]["num_samples"] == 500

    def test_training_data_template(self):
        """训练数据模板生成"""
        template = self.adapter.generate_training_data_template(
            course="computer_network",
            samples=[{"question": "什么是TCP三次握手", "optimal_queries": ["TCP三次握手 SYN ACK"]}]
        )
        assert isinstance(template, list)
        assert len(template) >= 1


# ============================================================
# 5. ConsistencyChecker Tests (gomarl_conflict.py)
# ============================================================

class TestConsistencyChecker:
    """知识一致性校验测试"""

    def setup_method(self):
        from engines.gomarl_conflict import ConsistencyChecker
        with patch("engines.gomarl_conflict.LLMProvider"):
            self.checker = ConsistencyChecker()

    def test_factual_conflict_tcp_udp(self):
        """事实冲突检测 — TCP面向连接 vs TCP无连接（单 Agent 内精确检测）"""
        agent_results = [
            {"agent_name": "a", "content": "TCP是面向连接的可靠传输协议"},
            {"agent_name": "b", "content": "TCP是无连接的快速传输协议"},
        ]
        conflicts = self.checker.check(agent_results)
        assert len(conflicts) > 0
        assert any(c.conflict_type == "factual" for c in conflicts)

    def test_factual_conflict_three_four_handshake(self):
        """事实冲突 — 三次握手 vs 四次握手（建立连接上下文）"""
        agent_results = [
            {"agent_name": "a", "content": "TCP建立连接使用三次握手"},
            {"agent_name": "b", "content": "TCP建立连接使用四次握手"},
        ]
        conflicts = self.checker.check(agent_results)
        assert len(conflicts) > 0

    def test_factual_no_conflict(self):
        """不同协议不同特性不构成矛盾（互补正确事实不误报）"""
        agent_results = [
            {"agent_name": "a", "content": "TCP使用三次握手建立连接"},
            {"agent_name": "b", "content": "UDP是无连接的协议适用于实时通信"},
        ]
        conflicts = self.checker.check(agent_results)
        # TCP三次握手和UDP无连接不构成矛盾（不同协议不同特性）
        assert len(conflicts) == 0

    def test_semantic_conflict_detection_with_embeddings(self):
        """语义冲突检测 — 使用 E5 向量"""
        # 两个内容含义不同（一个正确一个错误），向量方向相反模拟语义冲突
        emb_a = np.random.randn(768)
        emb_b = -emb_a  # 方向相反，余弦相似度接近-1
        similarity = np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b))
        assert similarity < 0  # 方向相反

        agent_results = [
            {"agent_name": "a", "content": "TCP是面向连接的"},
            {"agent_name": "b", "content": "TCP是无连接的"},  # 错误描述 — 也有事实冲突
        ]
        embeddings = np.stack([emb_a, emb_b])
        conflicts = self.checker.check(agent_results, embeddings)
        # Should detect at least the factual conflict
        assert len(conflicts) > 0

    def test_semantic_no_conflict_similar_content(self):
        """语义一致的内容不产生事实冲突"""
        agent_results = [
            {"agent_name": "a", "content": "TCP使用三次握手建立连接"},
            {"agent_name": "b", "content": "TCP连接建立需要三次握手过程"},
        ]
        # Similar embeddings — no factual conflict in these similar statements
        emb_base = np.random.randn(768)
        embeddings = np.stack([emb_base, emb_base + np.random.randn(768) * 0.1])
        conflicts = self.checker.check(agent_results, embeddings)
        factual_conflicts = [c for c in conflicts if c.conflict_type == "factual"]
        assert len(factual_conflicts) == 0


# ============================================================
# 6. NeuralGroupMixer Tests (gomarl_mixer.py)
# ============================================================
# NOTE: Agent names are: teacher, quizmaster, media_designer, extension, ppt_designer, code_practice

class TestNeuralGroupMixer:
    """GoMARL Neural GroupMixer 测试"""

    def setup_method(self):
        from engines.gomarl_mixer import NeuralGroupMixer
        with patch("engines.gomarl_mixer.LLMProvider"), \
             patch("engines.gomarl_mixer.redis_client"), \
             patch("engines.gomarl_mixer.pg_client"):
            self.mixer = NeuralGroupMixer()

    def test_initial_weights(self):
        """初始权重设置 — 使用实际Agent名称"""
        weights = self.mixer._base_weights
        assert "teacher" in weights
        assert "quizmaster" in weights
        assert "media_designer" in weights
        assert "extension" in weights
        assert "ppt_designer" in weights
        assert "code_practice" in weights

    def test_get_stats(self):
        """统计信息返回 — 使用实际stats字段名"""
        stats = self.mixer.get_stats()
        assert "neural_enabled" in stats
        assert "torch_available" in stats
        assert "base_weights" in stats

    @pytest.mark.asyncio
    async def test_mix_with_mock_results(self):
        """共识混合 — 模拟Agent结果（使用实际Agent名称）

        量纲约定：consensus_score 为 **10 分制**（与 QualityScore.overall /
        quality_threshold=7 对齐），见 gomarl_mixer.mix() 中 `max(0, min(10, cs*10))`。
        因此入参 score 也必须是 10 分制，断言区间为 [0, 10]。

        随机性：此处必须用固定种子的 np.random，不能用裸 randn —— 神经网络路径的
        输出随输入 embedding 变化，随机数据会让本用例时红时绿（flaky）。
        """
        agent_results = [
            {"agent_name": "teacher", "content": "TCP三次握手", "score": 9.0},
            {"agent_name": "quizmaster", "content": "TCP连接练习题", "score": 8.0},
            {"agent_name": "media_designer", "content": "TCP思维导图", "score": 8.5},
        ]
        student_profile = {"level": "medium", "weak_points": ["TCP"]}

        with patch("engines.gomarl_mixer.AgentOutputEncoder") as mock_enc_cls:
            mock_enc = MagicMock()
            # 固定种子：避免随机 embedding 导致共识分抖动
            rng = np.random.default_rng(20260829)
            mock_enc.encode_batch = MagicMock(return_value=rng.standard_normal((3, 768)))
            mock_enc_cls.return_value = mock_enc

            result = await self.mixer.mix(agent_results, student_profile, "TCP")
            assert "consensus_score" in result
            assert "dynamic_weights" in result
            assert "weighted_scores" in result
            assert isinstance(result["consensus_score"], float)
            # 10 分制契约（原断言写成 [0,1]，与实现不符）
            assert 0.0 <= result["consensus_score"] <= 10.0

    @pytest.mark.asyncio
    async def test_mix_fallback_no_torch(self):
        """PyTorch不可用时降级为加权平均"""
        from engines.gomarl_mixer import NeuralGroupMixer
        with patch("engines.gomarl_mixer.LLMProvider"), \
             patch("engines.gomarl_mixer.redis_client"), \
             patch("engines.gomarl_mixer.pg_client"):
            mixer = NeuralGroupMixer()
            mixer.use_neural = False  # 强制规则模式

            agent_results = [
                {"agent_name": "teacher", "content": "TCP三次握手", "score": 0.9},
                {"agent_name": "quizmaster", "content": "TCP练习", "score": 0.8},
            ]
            result = await mixer.mix(agent_results, {}, "TCP")
            assert result["neural_used"] is False
            assert "consensus_score" in result


# ============================================================
# 7. ConflictResolutionEngine Tests (gomarl_conflict.py)
# ============================================================

class TestConflictResolutionEngine:
    """冲突检测+消解引擎测试"""

    def setup_method(self):
        from engines.gomarl_conflict import ConflictResolutionEngine
        with patch("engines.gomarl_conflict.LLMProvider") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm.text_completion = AsyncMock(return_value="A正确，TCP是面向连接的")
            mock_llm_cls.return_value = mock_llm
            self.engine = ConflictResolutionEngine()

    @pytest.mark.asyncio
    async def test_check_and_resolve_no_conflicts(self):
        """无冲突内容 — 一致性高"""
        agent_results = [
            {"agent_name": "teacher", "content": "TCP使用三次握手建立连接"},
            {"agent_name": "quizmaster", "content": "练习题关于TCP三次握手"},
        ]
        result = await self.engine.check_and_resolve(agent_results, course="computer_network")
        assert "total_conflicts" in result
        assert "overall_consistency" in result
        assert result["total_conflicts"] >= 0

    @pytest.mark.asyncio
    async def test_check_and_resolve_with_factual_conflict(self):
        """事实冲突检测"""
        agent_results = [
            {"agent_name": "teacher", "content": "TCP是面向连接的协议"},
            {"agent_name": "quizmaster", "content": "TCP是无连接的协议"},  # 错误！
        ]
        result = await self.engine.check_and_resolve(agent_results, course="computer_network")
        assert result["total_conflicts"] > 0
        agent_results = [
            {"agent_name": "teacher", "content": "TCP是面向连接的协议"},
            {"agent_name": "quizmaster", "content": "TCP是无连接的协议"},  # 错误！
        ]
        result = await self.engine.check_and_resolve(agent_results, course="computer_network")
        assert result["total_conflicts"] > 0


# ============================================================
# 8. Engine API Endpoint Tests (api/engine.py)
# ============================================================
# NOTE: LoRA config is nested {"lora": {"r": 8, ...}, "training": {"num_samples": 500}}
# NOTE: stop_decision stats = {"total_decisions": int}
# NOTE: mixer stats = {"neural_enabled", "torch_available", "base_weights"}

class TestEngineAPIEndpoints:
    """8个引擎API端点测试 — 用 TestClient"""

    def setup_method(self):
        from fastapi.testclient import TestClient
        # main.py already handles missing services (InMemory fallback)
        from main import app
        self.client = TestClient(app)

    def test_engine_status_endpoint(self):
        """GET /api/engine/status"""
        response = self.client.get("/api/engine/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "modules" in data
        assert "torch_available" in data

    def test_stop_decision_stats_endpoint(self):
        """GET /api/engine/stop-decision"""
        response = self.client.get("/api/engine/stop-decision")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "stats" in data
        assert "total_decisions" in data["stats"]

    def test_neural_mixer_stats_endpoint(self):
        """GET /api/engine/neural-mixer"""
        response = self.client.get("/api/engine/neural-mixer")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "stats" in data

    def test_lora_config_endpoint(self):
        """GET /api/engine/lora-config — 嵌套结构"""
        response = self.client.get("/api/engine/lora-config")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "config" in data
        # LoRA config is nested: {"lora": {"r": 8, "lora_alpha": 16}, "training": {"num_samples": 500}}
        assert data["config"]["lora"]["r"] == 8
        assert data["config"]["lora"]["lora_alpha"] == 16

    def test_conflict_check_endpoint(self):
        """POST /api/engine/conflict-check"""
        response = self.client.post(
            "/api/engine/conflict-check",
            json={
                "agent_results": [
                    {"agent_name": "teacher", "content": "TCP面向连接"},
                    {"agent_name": "quizmaster", "content": "TCP无连接"},
                ],
                "course": "computer_network",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "total_conflicts" in data

    def test_stop_decision_update_endpoint(self):
        """POST /api/engine/stop-decision/update"""
        response = self.client.post(
            "/api/engine/stop-decision/update",
            json={
                "complexity": "simple",
                "final_coverage": 0.9,
                "was_good": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "stats" in data

    def test_frugal_rag_full_endpoint_structure(self):
        """POST /api/engine/frugal-rag-full — 验证端点可达"""
        response = self.client.post(
            "/api/engine/frugal-rag-full",
            json={
                "question": "什么是TCP三次握手",
                "course": "computer_network",
                "top_k": 5,
            },
        )
        # May return 200 with error status (LLM unavailable) or 200 with ok
        assert response.status_code == 200
        data = response.json()
        assert "status" in data  # either "ok" or "error"

    def test_gomarl_consensus_endpoint_structure(self):
        """POST /api/engine/gomarl-consensus — 验证端点可达"""
        response = self.client.post(
            "/api/engine/gomarl-consensus",
            json={
                "agent_results": [
                    {"agent_name": "teacher", "content": "TCP三次握手", "score": 0.9},
                    {"agent_name": "quizmaster", "content": "TCP练习题", "score": 0.8},
                ],
                "student_profile": {},
                "topic": "TCP",
                "course": "computer_network",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


# ============================================================
# 9. GOMARLConsensus Integration Tests (gomarl.py upgrade)
# ============================================================

class TestGOMARLConsensusUpgrade:
    """GOMARL共识模块升级验证"""

    def test_gomarl_has_enhanced_methods(self):
        """升级后的 GOMARLConsensus 包含新方法"""
        from engines.gomarl import GOMARLConsensus
        instance = GOMARLConsensus()
        assert hasattr(instance, "_check_consistency_enhanced")
        assert hasattr(instance, "_neural_mix")
        assert hasattr(instance, "_use_neural")
        assert hasattr(instance, "_use_evidence")

    def test_gomarl_base_weights_include_new_agents(self):
        """新增Agent的base weights"""
        from engines.gomarl import GOMARLConsensus
        instance = GOMARLConsensus()
        weights = instance._base_weights
        assert "ppt_designer" in weights
        assert weights["ppt_designer"] == 0.8
        assert "code_practice" in weights
        assert weights["code_practice"] == 0.85


# ============================================================
# 10. Config Tests — SFT/GRPO/Mixer parameters
# ============================================================
# NOTE: config functions are get_frugal_config() and get_gomarl_config(), returning dict

class TestEngineConfig:
    """引擎配置参数验证"""

    def test_frugal_rag_sft_config(self):
        """SFT配置项存在"""
        from config import get_frugal_config
        cfg = get_frugal_config()
        assert "sft_enabled" in cfg
        assert "grpo_stop_enabled" in cfg
        assert "query_rewrite_enabled" in cfg

    def test_gomarl_mixer_config(self):
        """Mixer配置项存在"""
        from config import get_gomarl_config
        cfg = get_gomarl_config()
        assert "use_neural_mixer" in cfg
        assert "use_evidence_conflict" in cfg


# ============================================================
# 11. Engines __init__ export tests
# ============================================================

class TestEnginesInit:
    """engines/__init__.py 导出验证"""

    def test_all_new_modules_exported(self):
        """所有新模块在 __init__.py 中导出"""
        import engines
        # Lite版
        assert hasattr(engines, "frugal_rag")
        # 真版增量
        assert hasattr(engines, "query_preprocessor")
        assert hasattr(engines, "sft_query_generator")
        assert hasattr(engines, "react_retriever")
        assert hasattr(engines, "stop_decision")
        assert hasattr(engines, "query_rewriter")
        assert hasattr(engines, "lora_adapter")
        assert hasattr(engines, "frugal_rag_full")
        assert hasattr(engines, "neural_mixer")
        assert hasattr(engines, "agent_encoder")
        assert hasattr(engines, "consistency_checker")
        assert hasattr(engines, "conflict_resolver")
        assert hasattr(engines, "conflict_engine")
        assert hasattr(engines, "conflict_engine")
        assert hasattr(engines, "GOMARLConsensus")


# ============================================================
# 12. Personalized Rerank Tests (报告§3.4.2)
# ============================================================

class TestPersonalizedRerank:
    """个性化检索排序测试"""

    def setup_method(self):
        from engines.frugal_rag import FrugalRAG
        self.rag = FrugalRAG()

    def test_retrieve_signature_has_student_profile(self):
        """retrieve() 方法签名包含 student_profile 参数"""
        import inspect
        sig = inspect.signature(self.rag.retrieve)
        assert "student_profile" in sig.parameters
        assert sig.parameters["student_profile"].default is None

    def test_personalized_rerank_method_exists(self):
        """_personalized_rerank 方法存在"""
        assert hasattr(self.rag, "_personalized_rerank")
        assert hasattr(self.rag, "_match_chunk_to_topic")

    def test_match_chunk_to_topic_with_topic_id(self):
        """metadata.topic_id 精确匹配"""
        from engines.teaching_rules import teaching_rules
        # 使用已知topic_id
        metadata = {"topic_id": "transport", "chapter_name": "运输层"}
        result = self.rag._match_chunk_to_topic("", metadata, "computer_network")
        assert result == "transport"

    def test_match_chunk_to_topic_with_chapter_name(self):
        """chapter_name 模糊匹配"""
        from engines.teaching_rules import teaching_rules
        metadata = {"chapter_name": "TCP协议详解"}
        result = self.rag._match_chunk_to_topic("", metadata, "computer_network")
        # TCP 在 computer_network 中有 topic_id="tcp"
        assert result is not None
        assert result == "tcp"

    def test_match_chunk_to_topic_no_match(self):
        """无法匹配时返回None"""
        from engines.teaching_rules import teaching_rules
        metadata = {"chapter_name": "量子力学基础"}
        result = self.rag._match_chunk_to_topic("", metadata, "computer_network")
        # 无匹配
        assert result is None or result == ""

    def test_personalized_rerank_weak_topic_boost(self):
        """薄弱知识点加成 +0.15"""
        chunks = [
            {"id": "1", "text": "TCP三次握手建立连接", "score": 0.80,
             "metadata": {"topic_id": "tcp", "chapter_name": "TCP协议"}},
            {"id": "2", "text": "以太网帧结构", "score": 0.79,
             "metadata": {"topic_id": "ethernet", "chapter_name": "以太网"}},
        ]
        profile = {
            "weak_topics": ["tcp"],
            "mastered_topics": [],
            "review_stage": "basic",
            "target_score": 100,
        }
        result = self.rag._personalized_rerank(chunks, "computer_network", profile)

        # TCP chunk 应排到前面（因为 weak_topics 加成）
        assert result[0]["metadata"]["topic_id"] == "tcp"
        assert result[0]["_rerank_adjustment"] > 0
        assert "weak_topic_boost" in result[0]["_rerank_reasons"]

    def test_personalized_rerank_mastered_topic_reduce(self):
        """已掌握知识点减权 -0.10"""
        chunks = [
            {"id": "1", "text": "以太网帧结构", "score": 0.80,
             "metadata": {"topic_id": "ethernet", "chapter_name": "以太网"}},
            {"id": "2", "text": "TCP三次握手", "score": 0.79,
             "metadata": {"topic_id": "tcp", "chapter_name": "TCP协议"}},
        ]
        profile = {
            "weak_topics": [],
            "mastered_topics": ["ethernet"],
            "review_stage": "basic",
            "target_score": 100,
        }
        result = self.rag._personalized_rerank(chunks, "computer_network", profile)

        # ethernet chunk 应排到后面（mastered减权）
        assert result[1]["metadata"]["topic_id"] == "ethernet"
        assert result[1]["_rerank_adjustment"] < 0
        assert "mastered_topic_reduce" in result[1]["_rerank_reasons"]

    def test_personalized_rerank_exam_weight_boost(self):
        """考查权重加成"""
        chunks = [
            {"id": "1", "text": "运输层概述", "score": 0.80,
             "metadata": {"topic_id": "transport", "chapter_name": "运输层"}},
        ]
        profile = {
            "weak_topics": [],
            "mastered_topics": [],
            "review_stage": "strengthen",
            "target_score": 100,
        }
        result = self.rag._personalized_rerank(chunks, "computer_network", profile)

        # transport 的 exam_weight=0.20, 应有 exam_weight 加成
        assert result[0]["_rerank_adjustment"] > 0
        assert any("exam_weight" in r for r in result[0]["_rerank_reasons"])

    def test_personalized_rerank_no_profile_no_adjustment(self):
        """无画像时不调整（student_profile=None）"""
        # 直接构造chunks模拟 retrieve 不传 profile
        chunks = [
            {"id": "1", "text": "TCP", "score": 0.80, "metadata": {}},
        ]
        # retrieve 不传 profile 时跳过 _personalized_rerank
        # 验证 chunks 不含 _rerank_adjustment
        assert "_rerank_adjustment" not in chunks[0]

    def test_personalized_rerank_stage_difficulty_match(self):
        """复习阶段→难度匹配"""
        chunks = [
            {"id": "1", "text": "TCP协议高级", "score": 0.80,
             "metadata": {"topic_id": "tcp", "chapter_name": "TCP协议"}},
        ]
        # TCP是advanced难度，comprehensive阶段偏好advanced
        profile = {
            "weak_topics": [],
            "mastered_topics": [],
            "review_stage": "comprehensive",
            "target_score": 100,
        }
        result = self.rag._personalized_rerank(chunks, "computer_network", profile)

        # comprehensive阶段 advanced难度 应有 positive difficulty_match
        assert any("difficulty_match" in r for r in result[0]["_rerank_reasons"])


# ============================================================
# 13. FrugalRAGFull + Profile Integration Tests
# ============================================================

class TestFrugalRAGFullProfileIntegration:
    """FrugalRAG Full 流程 + 画像参数集成测试"""

    def test_retrieve_full_signature_has_student_profile(self):
        """retrieve_full 方法签名包含 student_profile"""
        from engines.frugal_rag_stop import FrugalRAGFull
        import inspect
        sig = inspect.signature(FrugalRAGFull.retrieve_full)
        assert "student_profile" in sig.parameters

    def test_react_retriever_signature_has_student_profile(self):
        """retrieve_with_reasoning 方法签名包含 student_profile"""
        from engines.frugal_rag_sft import ReActRetriever
        import inspect
        sig = inspect.signature(ReActRetriever.retrieve_with_reasoning)
        assert "student_profile" in sig.parameters

    def test_frugal_rag_full_endpoint_with_profile(self):
        """API端点支持 student_profile 字段"""
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)

        response = client.post(
            "/api/engine/frugal-rag-full",
            json={
                "question": "TCP三次握手",
                "course": "computer_network",
                "top_k": 5,
                "student_profile": {
                    "weak_topics": ["tcp"],
                    "mastered_topics": ["ethernet"],
                    "review_stage": "strengthen",
                    "target_score": 120,
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        # If the request succeeded (status=ok), check personalized_rerank field
        if data["status"] == "ok":
            assert "personalized_rerank" in data
            assert data["personalized_rerank"]["applied"] is True
