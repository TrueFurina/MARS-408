# ============================================================
# 职业素养测评模块（对照实验载体）测试
# 覆盖：题库 / 分档计分 / 前后测 / 个人报告 / 班级聚合 / 边界与幂等
# ============================================================

import os
import sqlite3

import pytest

# 测试专用数据库（避免污染 data/literacy.db）
os.environ["NETLEARN_LITERACY_DB"] = os.path.join(os.path.dirname(__file__), "_test_literacy.db")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_db():
    """每个用例前清空测试数据（不删文件——Windows 下缓存连接句柄未释放，删文件会 PermissionError）。"""
    db = os.environ["NETLEARN_LITERACY_DB"]
    if os.path.exists(db):
        conn = sqlite3.connect(db)
        conn.execute("DELETE FROM literacy_attempts")
        conn.commit()
        conn.close()
    yield


def _full_answers(option_index=0):
    """全 10 题统一选同一档（直接从题库构造，不经 HTTP）。"""
    from api.literacy_assessment import QUESTION_BANK
    return [{"qid": q["id"], "option_index": option_index} for q in QUESTION_BANK]


# ------------------------------------------------------------
# 题库
# ------------------------------------------------------------
class TestQuestionBank:
    def test_questions_endpoint(self, client):
        r = client.get("/api/literacy/questions")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 10
        assert len(data["dimensions"]) == 6
        assert set(data["dimensions"]) == {"表达逻辑", "抗压应变", "方案拆解", "协作沟通", "技术汇报", "问题解决"}

    def test_every_question_has_four_options_and_dim(self, client):
        data = client.get("/api/literacy/questions").json()
        for q in data["questions"]:
            assert q["dim"] in data["dimensions"]
            assert len(q["options"]) in (2, 4)  # 判断题 2 项，单/多选 4 项
            assert q["stem"].strip()


# ------------------------------------------------------------
# 计分
# ------------------------------------------------------------
class TestScoring:
    def test_pre_best_answers_full_score(self, client):
        answers = _full_answers(0)  # 全选最优解 → 10 分档
        r = client.post("/api/literacy/submit", json={
            "phase": "pre", "class_name": "实验班", "user_name": "甲", "answers": answers})
        assert r.status_code == 200
        body = r.json()
        assert body["total_score"] == 100.0
        assert all(v == 100.0 for v in body["dim_scores"].values())

    def test_post_second_best_scores(self, client):
        answers = _full_answers(1)  # 次优解 → 7 分档；判断题 index1=1 分
        r = client.post("/api/literacy/submit", json={
            "phase": "post", "class_name": "实验班", "user_name": "甲", "answers": answers})
        body = r.json()
        # 维度均值×10 再跨维平均：表达/方案/协作/汇报/问题=70，抗压应变=(7+1)/2×10=40
        # total = (70×5+40)/6 = 65.0
        assert body["total_score"] == pytest.approx(65.0)

    def test_out_of_range_option_scores_zero(self):
        from api.literacy_assessment import _score_answer, QUESTION_BANK
        assert _score_answer(QUESTION_BANK[0], 99) == 0
        assert _score_answer(QUESTION_BANK[0], -1) == 0


# ------------------------------------------------------------
# 前后测与报告
# ------------------------------------------------------------
class TestReport:
    def test_pre_post_delta(self, client):
        uid = "stu-001"
        # 直接通过 API 提交两次（依赖 auth 依赖注入默认 demo 用户，用 monkeypatch 更稳）
        answers = _full_answers(0)
        client.post("/api/literacy/submit", json={
            "phase": "pre", "class_name": "实验班", "user_name": "甲", "answers": answers})
        answers2 = _full_answers(1)
        client.post("/api/literacy/submit", json={
            "phase": "post", "class_name": "实验班", "user_name": "甲", "answers": answers2})
        r = client.get(f"/api/literacy/report/{uid}")
        # demo 用户场景：user 依赖固定 demo
        if r.status_code == 404:
            r = client.get("/api/literacy/report/demo")
        assert r.status_code == 200
        rep = r.json()
        assert rep["pre"]["total"] == 100.0
        assert rep["post"]["total"] == pytest.approx(65.0)
        assert rep["delta"]["表达逻辑"] == pytest.approx(-30.0)

    def test_report_404_when_no_record(self, client):
        assert client.get("/api/literacy/report/nobody").status_code == 404


# ------------------------------------------------------------
# 班级聚合
# ------------------------------------------------------------
class TestClassReport:
    def test_class_aggregation(self, client):
        answers = _full_answers(0)
        client.post("/api/literacy/submit", json={
            "phase": "pre", "class_name": "聚合班", "user_name": "乙", "answers": answers})
        r = client.post("/api/literacy/class-report", json={"class_name": "聚合班"})
        assert r.status_code == 200
        body = r.json()
        assert body["student_count"] == 1
        assert body["class_avg"]["pre"]["表达逻辑"] == 100.0
        assert body["class_avg"]["post"]["表达逻辑"] is None  # 只有前测

    def test_class_report_404(self, client):
        assert client.post("/api/literacy/class-report", json={"class_name": "不存在"}).status_code == 404


# ------------------------------------------------------------
# 边界与幂等
# ------------------------------------------------------------
class TestEdgeCases:
    def test_invalid_phase_422(self, client):
        r = client.post("/api/literacy/submit", json={
            "phase": "mid", "class_name": "x", "user_name": "x", "answers": _full_answers()})
        assert r.status_code == 422

    def test_empty_answers_422(self, client):
        r = client.post("/api/literacy/submit", json={
            "phase": "pre", "class_name": "x", "user_name": "x", "answers": []})
        assert r.status_code == 422

    def test_unknown_qid_422(self, client):
        r = client.post("/api/literacy/submit", json={
            "phase": "pre", "class_name": "x", "user_name": "x",
            "answers": [{"qid": 999, "option_index": 0}]})
        assert r.status_code == 422

    def test_resubmit_same_phase_replaces(self, client):
        """同一 phase 重复提交应替换旧记录（不产生重复行）。"""
        a = _full_answers(0)
        client.post("/api/literacy/submit", json={
            "phase": "pre", "class_name": "幂等班", "user_name": "丙", "answers": a})
        client.post("/api/literacy/submit", json={
            "phase": "pre", "class_name": "幂等班", "user_name": "丙", "answers": a})
        db = os.environ["NETLEARN_LITERACY_DB"]
        conn = sqlite3.connect(db)
        n = conn.execute("SELECT COUNT(*) FROM literacy_attempts WHERE phase='pre'").fetchone()[0]
        conn.close()
        assert n == 1
