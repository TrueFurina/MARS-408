# ============================================================
# T1 基础层离线单测（兼容默认 -m 档：not system and not requires_milvus and not slow）
#
# 覆盖：
#   1. config 默认 lite + feature flag 读取（algorithm_version / features_frugalrag / features_gomarl）
#   2. Evidence / EvidenceChain / ArgumentChain 序列化（pydantic）
#   3. factory 在 lite 下返回规则版（委托 engines.frugal_rag / engines.gomarl）
#   4. factory 在 real 分支返回清晰标注的 stub（NotImplementedError）
#   5. resolve_version 支持 session 灰度覆盖 + 非法值回退 lite
#
# 不依赖真实模型 / 密钥 / 网络 / Milvus；全部为纯 Python 逻辑，可离线跑进默认档。
# ============================================================

import config
from engines.algorithm_factory import (
    AlgorithmFactory,
    LiteConsensus,
    LiteRetriever,
    RealConsensusStub,
    RealRetrieverStub,
    get_consensus,
    get_reward,
    get_retriever,
)
from engines.evidence.schema import (
    ArgumentChain,
    ChainEdge,
    ChainNode,
    Evidence,
    EvidenceCard,
    EvidenceChain,
)


# ── 1. config 默认 lite + flag 读取 ──


def test_default_algorithm_version_is_lite():
    # 仓库默认保护软件杯稳定：version 缺失或显式 "lite" 均解析为 lite（向后兼容）
    assert config.algorithm_version() == "lite"
    assert config.features_frugalrag() is False
    assert config.features_gomarl() is False


def test_algorithm_version_resolves_real(monkeypatch):
    monkeypatch.setattr(
        config,
        "get_algorithm_config",
        lambda: {"version": "real", "features": {"frugalrag": True, "gomarl": True}},
    )
    assert config.algorithm_version() == "real"
    assert config.features_frugalrag() is True
    assert config.features_gomarl() is True


def test_algorithm_version_backward_compatible(monkeypatch):
    # 旧代码读不到 algorithm 段 → 默认 lite，不抛异常
    monkeypatch.setattr(config, "get_algorithm_config", lambda: {})
    assert config.algorithm_version() == "lite"
    assert config.features_frugalrag() is False
    assert config.features_gomarl() is False


def test_get_algorithm_config_shape():
    cfg = config.get_algorithm_config()
    assert "version" in cfg
    assert "features" in cfg
    assert set(cfg["features"].keys()) >= {"frugalrag", "gomarl"}


# ── 2. Evidence / EvidenceChain / ArgumentChain 序列化 ──


def test_evidence_serialization_roundtrip():
    ev = Evidence(
        group_id="G408-001",
        snippet="TCP 三次握手保证可靠连接。",
        credibility=0.85,
        source_agent="Teacher",
        version="lite",
        source_type="rule",
    )
    d = ev.to_dict()
    assert d["group_id"] == "G408-001"
    assert 0.0 <= d["credibility"] <= 1.0
    assert d["version"] == "lite"
    # 反序列化
    ev2 = Evidence.from_dict(d)
    assert ev2.evidence_id == ev.evidence_id
    assert ev2.snippet == ev.snippet


def test_evidence_credibility_clamped():
    import pytest

    with pytest.raises(Exception):
        Evidence(credibility=1.5)


def test_evidence_defaults_and_rule_prototype():
    ev = Evidence()
    assert ev.version == "lite"
    assert ev.source_type == "rule"
    ev.mark_rule_prototype()
    assert ev.version == "lite" and ev.source_type == "rule"


def test_evidence_chain_container():
    chain = EvidenceChain(version="lite")
    chain.add(Evidence(group_id="G1", snippet="a", source_agent="Teacher", credibility=0.7))
    chain.add(Evidence(group_id="G1", snippet="b", source_agent="QuizMaster", credibility=0.6))
    assert len(chain.evidences) == 2
    d = chain.to_dict()
    assert len(d["evidences"]) == 2
    chain2 = EvidenceChain.from_dict(d)
    assert chain2.evidences[0].snippet == "a"


def test_argument_chain_forward_structure():
    # T3 EvidenceConsensus 将消费 ArgumentChain；此处仅验证容器与序列化
    ac = ArgumentChain(version="lite")
    n1 = ac.add_evidence_node("Teacher", credibility=0.8)
    n2 = ac.add_consensus_node(0.75)
    ac.add_edge(n1.node_id, n2.node_id, relation="supports")
    d = ac.to_dict()
    assert len(d["nodes"]) == 2 and len(d["edges"]) == 1
    assert d["edges"][0]["relation"] == "supports"


def test_evidence_card_payload():
    card = EvidenceCard(
        version_tag="v1 规则原型",
        consensus_score=0.7,
        evidence=[Evidence(group_id="G1", snippet="x", credibility=0.7)],
        conclusion="规则版汇聚结论",
    )
    payload = card.to_payload()
    assert payload["version_tag"] == "v1 规则原型"
    assert payload["consensus_score"] == 0.7
    assert len(payload["evidence"]) == 1


# ── 3. factory lite 返回规则版（委托 engines）──


def test_factory_lite_returns_rule_backend():
    r = get_retriever(version="lite")
    assert isinstance(r, LiteRetriever)
    assert r.version_tag == "v1 规则原型"

    c = get_consensus(version="lite")
    assert isinstance(c, LiteConsensus)
    assert c.version_tag == "v1 规则原型"


def test_factory_default_reads_config_lite():
    # 默认不传 version → 读 config.algorithm.version（当前默认 lite）
    r = get_retriever()
    assert isinstance(r, LiteRetriever)


async def test_lite_retriever_delegates_to_frugal_rag(monkeypatch):
    # 验证 lite 分支确实委托现有规则版 engines.frugal_rag，不重写。
    # 注意：engines/__init__.py 把单例名 frugal_rag 带入 engines 命名空间，
    # 因此用 `from engines.frugal_rag import frugal_rag` 直接取单例再打桩。
    from engines.frugal_rag import frugal_rag as the_singleton

    fake = []

    async def _fake_retrieve(query, course=None, top_k=5, **kwargs):
        fake.append((query, course, top_k))
        return [{"text": "x", "score": 1.0}]

    monkeypatch.setattr(the_singleton, "retrieve", _fake_retrieve)
    r = get_retriever(version="lite")
    out = await r.retrieve("什么是 TCP", course="computer_network", top_k=3)
    assert out == [{"text": "x", "score": 1.0}]
    assert fake == [("什么是 TCP", "computer_network", 3)]


async def test_lite_consensus_delegates_to_gomarl(monkeypatch):
    import engines.gomarl as gm

    captured = {}

    async def _fake_eval(self, results, student_profile, topic, round_num=0, **kwargs):
        captured["topic"] = topic
        return "CONSENSUS_RESULT_STUB"

    monkeypatch.setattr(gm.GOMARLConsensus, "evaluate", _fake_eval)
    c = get_consensus(version="lite")
    res = await c.evaluate(results=[], student_profile={}, topic="子网划分")
    assert res == "CONSENSUS_RESULT_STUB"
    assert captured["topic"] == "子网划分"


# ── 4. factory real 分支 stub 行为 ──


def test_factory_real_returns_stub():
    r = get_retriever(version="real")
    assert isinstance(r, RealRetrieverStub)
    assert r.is_stub is True
    assert "T2" in r.version_tag

    c = get_consensus(version="real")
    assert isinstance(c, RealConsensusStub)
    assert c.is_stub is True
    assert "T3" in c.version_tag


def test_real_retriever_stub_raises():
    import pytest

    r = get_retriever(version="real")
    with pytest.raises(NotImplementedError):
        r.retrieve("q")


def test_real_consensus_stub_raises():
    import pytest

    c = get_consensus(version="real")
    with pytest.raises(NotImplementedError):
        c.evaluate([])


# ── 5. resolve_version session 灰度 + 回退 ──


def test_resolve_version_session_override():
    f = AlgorithmFactory({"version": "lite"})
    assert f.resolve_version("real") == "real"  # session 灰度覆盖全局 lite
    assert f.resolve_version("lite") == "lite"
    assert f.resolve_version(None) == "lite"  # 读 cfg
    assert f.resolve_version("bogus") == "lite"  # 非法值回退 lite


def test_resolve_version_global_real():
    f = AlgorithmFactory({"version": "real"})
    assert f.resolve_version(None) == "real"
    # 全局 real + session 强制 lite 仍可降级
    assert f.resolve_version("lite") == "lite"


def test_get_reward_lite_placeholder_and_real_stub():
    import pytest

    rw = get_reward(kind="generation", version="lite")
    assert rw.score({"x": 1}) == 0.0
    with pytest.raises(NotImplementedError):
        get_reward(kind="generation", version="real")
