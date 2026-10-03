# ============================================================
# T1 基础层 — QA 补充边缘用例（独立复核）
#
# 不依赖真实模型 / 密钥 / 网络 / Milvus / torch / numpy。
# real 分支桩在调用入口即抛 NotImplementedError，绝不触发 engines 重依赖 import。
#
# 覆盖工程师 20 用例之外的边缘面：
#   - Evidence.version 非法/未知值被 pydantic 拒绝；real 为合法字面量（仅留给未来真版）
#   - resolve_version 对未知/空/非字符串 override 一律回退 lite
#   - EvidenceChain 空链 / 单节点 / add_many 往返
#   - ArgumentChain 空链 / 非法 relation 被拒 / conflict 节点
#   - AlgorithmFactory 实例级 lite↔real 路由；real 分支确实抛 NotImplementedError
#   - config.algorithm_version() 纯函数（默认 "lite"，可重复、不依赖副作用）
#   - Evidence / EvidenceChain from_dict 全字段往返一致
#   - EvidenceCard.to_payload() 结构合理性 + 诚实标记(version=lite)
# ============================================================

import pytest

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
    ChainNode,
    Evidence,
    EvidenceCard,
    EvidenceChain,
)


# ── 1. version 非法 / 未知值（诚信红线：字面量强制）──


def test_evidence_rejects_invalid_version():
    # 未知值必须被 pydantic Literal 拒绝，绝不静默接受
    with pytest.raises(Exception):
        Evidence(version="unknown")
    with pytest.raises(Exception):
        Evidence(version="REAL")
    with pytest.raises(Exception):
        Evidence(version="real ")


def test_evidence_accepts_real_as_valid_literal():
    # real 是合法字面量（供未来真版使用），仅允许 lite/real 二选一
    ev = Evidence(version="real", source_type="real")
    assert ev.version == "real"
    assert ev.source_type == "real"


def test_evidence_default_is_honest_lite():
    # 默认构造即 lite + rule，绝不可默认 real（诚信红线：禁止伪造发生型证据）
    ev = Evidence()
    assert ev.version == "lite"
    assert ev.source_type == "rule"
    assert ev.credibility == 0.0


def test_resolve_version_unknown_override_falls_back_lite():
    f = AlgorithmFactory({"version": "lite"})
    assert f.resolve_version("bogus-value") == "lite"
    assert f.resolve_version("") == "lite"
    assert f.resolve_version(123) == "lite"
    assert f.resolve_version(None) == "lite"


# ── 2. EvidenceChain 空链 / 单节点 / 批量 ──


def test_evidence_chain_empty_roundtrip():
    chain = EvidenceChain(version="lite")
    assert len(chain.evidences) == 0
    d = chain.to_dict()
    assert d["evidences"] == []
    chain2 = EvidenceChain.from_dict(d)
    assert chain2.evidences == []
    assert chain2.version == "lite"


def test_evidence_chain_single_node():
    chain = EvidenceChain(version="lite")
    chain.add(Evidence(group_id="G1", snippet="only", source_agent="Teacher", credibility=0.5))
    assert len(chain.evidences) == 1
    chain2 = EvidenceChain.from_dict(chain.to_dict())
    assert len(chain2.evidences) == 1
    assert chain2.evidences[0].snippet == "only"


def test_evidence_chain_add_many():
    chain = EvidenceChain()
    chain.add_many([Evidence(snippet="a"), Evidence(snippet="b")])
    assert len(chain.evidences) == 2


def test_evidencechain_full_roundtrip():
    chain = EvidenceChain(version="lite", conclusion="汇聚结论", consensus_score=0.8)
    chain.add_many([Evidence(snippet="a"), Evidence(snippet="b")])
    d = chain.to_dict()
    chain2 = EvidenceChain.from_dict(d)
    assert chain2.to_dict() == d


# ── 3. ArgumentChain 空链 / 非法 relation / conflict 节点 ──


def test_argument_chain_empty_roundtrip():
    ac = ArgumentChain(version="lite")
    d = ac.to_dict()
    assert d["nodes"] == [] and d["edges"] == []
    ac2 = ArgumentChain.from_dict(d)
    assert ac2.nodes == [] and ac2.edges == []


def test_argument_chain_edge_invalid_relation_rejected():
    # relation 限制为 supports/conflicts/resolves，非法值必须被拒
    ac = ArgumentChain()
    with pytest.raises(Exception):
        ac.add_edge("n1", "n2", relation="not_a_relation")


def test_argument_chain_conflict_node():
    ac = ArgumentChain()
    n = ac.add_conflict_node(label="冲突点")
    assert isinstance(n, ChainNode)
    assert n.kind == "conflict"
    assert n.label == "冲突点"
    assert len(ac.nodes) == 1


# ── 4. AlgorithmFactory 实例级路由 + real 分支确实抛 NotImplementedError ──


def test_factory_instance_lite_real_routing():
    f = AlgorithmFactory()
    assert isinstance(f.get_retriever("lite"), LiteRetriever)
    assert isinstance(f.get_retriever("real"), RealRetrieverStub)
    assert isinstance(f.get_consensus("lite"), LiteConsensus)
    assert isinstance(f.get_consensus("real"), RealConsensusStub)


def test_factory_real_retriever_raises_on_call():
    r = get_retriever(version="real")
    assert type(r).__name__ == "RealRetrieverStub"
    assert r.is_stub is True
    with pytest.raises(NotImplementedError):
        r.retrieve("q")


def test_factory_real_consensus_raises_on_call():
    c = get_consensus(version="real")
    assert type(c).__name__ == "RealConsensusStub"
    assert c.is_stub is True
    with pytest.raises(NotImplementedError):
        c.evaluate([])


def test_factory_real_reward_raises():
    with pytest.raises(NotImplementedError):
        get_reward(version="real")
    with pytest.raises(NotImplementedError):
        AlgorithmFactory().get_reward(version="real")


def test_resolve_version_reads_config_real(monkeypatch):
    # 工厂应读取 config.algorithm_version()；config=real 时返回 real
    monkeypatch.setattr(
        config,
        "get_algorithm_config",
        lambda: {"version": "real", "features": {"frugalrag": True, "gomarl": True}},
    )
    f = AlgorithmFactory()
    assert f.resolve_version(None) == "real"


# ── 5. config.algorithm_version() 纯函数检查 ──


def test_config_algorithm_version_pure_function():
    v1 = config.algorithm_version()
    v2 = config.algorithm_version()
    assert v1 == v2 == "lite"  # 默认 lite，可重复、确定性
    assert isinstance(v1, str)
    assert v1 in ("lite", "real")
    assert config.features_frugalrag() is False
    assert config.features_gomarl() is False


# ── 6. Evidence.from_dict 全字段往返一致 ──


def test_evidence_from_dict_roundtrip_consistent():
    ev = Evidence(
        group_id="G408-002",
        snippet="OS 分页减少外部碎片。",
        credibility=0.9,
        source_agent="QuizMaster",
        version="lite",
        source_type="rule",
        chunk_ref="chunk-42",
        metadata={"hit_rate": 0.8},
    )
    d = ev.to_dict()
    ev2 = Evidence.from_dict(d)
    assert ev2.to_dict() == d  # 全字段往返一致


# ── 7. EvidenceCard.to_payload() 结构与诚实标记 ──


def test_evidence_card_payload_structure():
    card = EvidenceCard(
        version_tag="v1 规则原型",
        consensus_score=0.75,
        evidence=[Evidence(group_id="G1", snippet="x", credibility=0.7)],
        conclusion="规则版汇聚结论",
    )
    payload = card.to_payload()
    assert set(payload.keys()) >= {
        "version_tag",
        "consensus_score",
        "evidence",
        "conclusion",
        "created_at",
    }
    assert payload["version_tag"] == "v1 规则原型"
    assert payload["consensus_score"] == 0.75
    assert len(payload["evidence"]) == 1
    # 诚实标记：规则版证据默认 version=lite
    assert payload["evidence"][0]["version"] == "lite"
