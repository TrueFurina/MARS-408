# -*- coding: utf-8 -*-
"""班级看板覆盖率说明（coverage_note）回归 —— REA #9「不报分母的比率等于营销」

背景：教师端看板此前只给「完成率 0%」这类比率，不给分母构成。
2026-10-20 教师端全流程 E2E 撞到过：学生凭任务码加入后只绑定花名册行、
不产生会话，教师看到「参与 0/3」会误判成"没人来"，实际是"进来了还没开练"。
joined_count 落地后仍缺一句话把「谁没被算进比率」说出来，本测试钉住它。

三条契约：
  1. coverage_note 必须出现，且同时含分母人数与「尚未加入」人数；
  2. 名册为空时不得输出看似有效的比率说明，必须明说是占位；
  3. 导出的一页纸 HTML 必须带覆盖率横幅，且与 API 返回的字符串同源
     （报告与看板说同一句话，不允许各算一套）。
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from main import app
    return TestClient(app)


def _new_class(client, name: str):
    return client.post("/api/career/classes", json={"class_name": name}).json()


def test_coverage_note_names_denominator_and_unjoined(client):
    cls = _new_class(client, "覆盖率班A")
    cid = cls["class_id"]
    client.post(f"/api/career/classes/{cid}/students", json={"roster": "01 甲\n02 乙\n03 丙"})

    dash = client.get(f"/api/career/classes/{cid}/dashboard").json()
    note = dash["summary"]["coverage_note"]
    assert note, "coverage_note 不得为空"
    assert "名册 3 人" in note, f"分母必须写明，实测：{note}"
    assert "3 人尚未加入" in note, f"未加入人数必须写明，实测：{note}"
    assert "0 人有可评分结果" in note


def test_coverage_note_marks_empty_roster_as_placeholder(client):
    cls = _new_class(client, "覆盖率空班")
    cid = cls["class_id"]
    dash = client.get(f"/api/career/classes/{cid}/dashboard").json()
    note = dash["summary"]["coverage_note"]
    assert "名册为空" in note, f"空名册必须明说比率不成立，实测：{note}"
    # 0% 仍是 0%：不得为了让文案好看而改数字，只允许把数字的语义说清楚
    assert dash["summary"]["completion_rate"] == 0.0


def test_export_report_banner_is_same_string_as_api(client):
    cls = _new_class(client, "覆盖率导出班")
    cid = cls["class_id"]
    client.post(f"/api/career/classes/{cid}/students", json={"roster": "01 甲\n02 乙"})

    dash = client.get(f"/api/career/classes/{cid}/dashboard").json()
    note = dash["summary"]["coverage_note"]
    html = client.get(f"/api/career/classes/{cid}/export-report").text
    assert "覆盖率：" in html, "一页纸必须带覆盖率横幅"
    # 同源校验：API 那句原文必须整段出现在 HTML 里（只差 HTML 转义，本用例无特殊字符）
    assert note in html, "一页纸的覆盖率说明必须与 API 返回同源，不得各算一套"
