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

    # 5) 报告结构完整：标题、六维溯源标签、对话还原
    assert "职业素养对抗实训" in html
    assert "原话溯源" in html and "KB 原文溯源" in html
    assert "完整对抗记录" in html


def test_export_report_404_for_unknown_session(client: TestClient):
    resp = client.get("/api/career/session/does-not-exist/export-report")
    assert resp.status_code == 404
