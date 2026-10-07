# -*- coding: utf-8 -*-
"""career 分支测试 · 证据链「一页纸」导出端点（可溯源 · 诚信优先）

运行：python -m pytest tests/test_career_export_report.py -q

要点：
  · 端点返回 200 + text/html；
  · 真实证据原话必须出现在 HTML 中；
  · KB 原文溯源（chunk_ref）在链路中未落库 → 必须显式标注「溯源：待补全」，
    但绝不伪造 chunk 引用，且占位符不会被伪装成真实原话（不裹在「」内）；
  · 未知会话返回 404。
"""
import pytest

from fastapi.testclient import TestClient

from main import app
from services import career_service


DISTINCTIVE = "根因定位后对比三套方案并给出回滚预案与监控指标。"


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_session(client: TestClient) -> str:
    """最窄闭环：列表 → 启动 → 作答（含特征句）→ 强制结束出报告。"""
    sc = client.get("/api/career/scenarios").json()["scenarios"]
    assert sc, "需要有可用情景才能跑导出测试"
    sid = client.post(
        "/api/career/session/start",
        json={"scenario_id": sc[0]["id"], "max_turns": 4},
    ).json()["session_id"]
    # 提交两轮带真实内容的作答，让规则兜底评估把它们作为「原话溯源」引用
    ans1 = client.post(
        f"/api/career/session/{sid}/answer", json={"answer": DISTINCTIVE}
    )
    assert ans1.status_code == 200
    ans2 = client.post(
        f"/api/career/session/{sid}/answer",
        json={"answer": "我会先对齐目标，再拆解任务，并定期同步风险与进展。"},
    )
    assert ans2.status_code == 200
    end = client.post(f"/api/career/session/{sid}/end", json={"force": True})
    assert end.status_code == 200
    return sid


def test_export_report_returns_printable_html(client: TestClient):
    sid = _seed_session(client)
    resp = client.get(f"/api/career/session/{sid}/export-report")

    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    html = resp.text

    # 1) 真实证据原话必须出现（来自学生作答）
    assert DISTINCTIVE in html

    # 2) 诚信缺口必须显式标注：KB 原文溯源未落库 → 溯源：待补全
    assert "溯源：待补全" in html

    # 3) 绝不伪造 chunk 引用
    assert "chunk-" not in html

    # 4) 占位符不会被伪装成真实原话（真实原话裹在「」内，占位符不裹）
    assert "「溯源：待补全」" not in html

    # 4b) 来源 Agent 必须真实填充，旧的"待补全"占位已移除
    assert "CAREER_ASSESS(ECD六维)" in html
    assert "待补全（证据取自学生本轮作答）" not in html

    # 4c) 真实评分量表依据（BARS rubric）进入溯源；KB 原文溯源不适用已如实说明
    assert "情景期望行为" in html

    # 5) 报告结构完整：标题、六维溯源标签、对话还原
    assert "职业素养对抗实训" in html
    assert "原话溯源" in html and "KB 原文溯源" in html
    assert "完整对抗记录" in html


def test_export_report_404_for_unknown_session(client: TestClient):
    resp = client.get("/api/career/session/does-not-exist/export-report")
    assert resp.status_code == 404


def test_export_report_evidence_chain_has_real_tracing(client: TestClient):
    """证据链必须携带真实可溯源字段，且绝不伪造 KB/向量库来源（诚信红线）。

    验证 E-3 一页纸的真实溯源补全：
      · source_agent 非空（真实产出证据的 Agent）；
      · rubric_text 存在（情景种子 BARS 评分量表，规则/评分驱动）；
      · answer_snippet 存在（学生真实原话，取自 dialogue_turns）；
      · source_type == "rule"（本实训无 KB 检索，绝不可伪装成 retrieval）；
      · chunk_ref 不得是伪造的向量库 id（chunk-xxx）。
    """
    sid = _seed_session(client)
    report = career_service.get_report(sid)
    chain = report.get("evidence_chain") or []
    assert chain, "证据链不应为空"

    saw_source_agent = False
    saw_rubric = False
    saw_snippet = False
    seen_any_pte = False

    for item in chain:
        # 来源必须是 rule（规则/评分驱动），不得伪装成 retrieval
        assert item.get("source_type") == "rule", "source_type 必须为 rule，不得伪造 retrieval"

        # 不得出现伪造的向量库 chunk 引用（KB id 形如 chunk-xxx）
        chunk = item.get("chunk_ref", "") or ""
        assert not chunk.startswith("chunk-"), f"不得伪造 KB chunk 引用: {chunk}"

        if item.get("source_agent"):
            saw_source_agent = True
        if item.get("rubric_text"):
            saw_rubric = True
        if item.get("snippet"):
            saw_snippet = True

        # 逐轮证据若非空，必须带来学生真实原话片段（answer_snippet）
        pte = item.get("per_turn_evidence") or []
        if pte:
            seen_any_pte = True
        for h in pte:
            assert h.get("answer_snippet"), "逐轮证据应带来学生真实原话片段（answer_snippet）"

    assert saw_source_agent, "至少有一个维度带非空 source_agent"
    assert saw_rubric, "至少有一个维度带 BARS rubric_text"
    assert saw_snippet, "至少有一个维度带学生原话 snippet"
    # 本环境为规则兜底模式，评分维度应补全逐轮原话证据（answer_snippet）
    assert seen_any_pte, "至少应有维度的逐轮证据带来学生原话（answer_snippet）"
