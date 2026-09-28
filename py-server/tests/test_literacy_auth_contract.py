# ============================================================
# 职业素养测评 —— 鉴权契约测试（2026-09-28 收紧后）
#
# 背景：本模块是对照实验（教改/国创赛）的原始数据入口。收紧前三个数据端点
# 零鉴权，未登录即可：
#   (a) 枚举学号（=user_id=学号后 4 位）读任意学生的六维报告 —— IDOR；
#   (b) 只填班级名即拿到全班 user_id + user_name + 逐人各维度明细；
#   (c) 以任意学生身份写入/覆盖其前后测记录。
# 研究原始数据可被第三方读且可被改，动摇的是研究结论本身，不只是接口。
#
# 本文件把收紧后的契约钉死，防止「某次重构把依赖悄悄摘掉」而无人发现：
#   /questions     公开（只读题库，无学生数据）
#   /submit        需登录（get_current_user）
#   /report/{uid}  本人 / 教师 / 管理员（require_self_or_teacher）
#   /class-report  教师 / 管理员（require_teacher_or_demo_open，演示开关可放宽）
#
# 为什么单列一个文件：契约断言与业务断言（分档计分、聚合口径）关注点不同，
# 混在一个文件里时，收紧鉴权会让业务断言被 401 短路成「假通过」而不易察觉。
# ============================================================

import os
import sqlite3

import pytest

# 与 test_literacy_assessment.py 指向同一测试库（同进程内 env 只有一个值，
# 若两处硬写不同路径，写入与断言会静默错位）。
os.environ.setdefault(
    "NETLEARN_LITERACY_DB",
    os.path.join(os.path.dirname(__file__), "_test_literacy.db"),
)

# 契约涉及演示放宽开关的边界，每个用例都从「开关关闭」起步，避免相互污染。
_DEMO_SWITCH = "NETLEARN_DEMO_TEACHER_OPEN"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_db(monkeypatch):
    """清空测试数据；并把演示放宽开关重置为未设置（monkeypatch 自动还原）。"""
    monkeypatch.delenv(_DEMO_SWITCH, raising=False)
    db = os.environ["NETLEARN_LITERACY_DB"]
    if os.path.exists(db):
        conn = sqlite3.connect(db)
        conn.execute("DELETE FROM literacy_attempts")
        conn.commit()
        conn.close()
    yield


@pytest.fixture(autouse=True)
def _real_auth(no_mock_auth):
    """本模块全用例都在「真实鉴权」下运行。

    tests/conftest.py 的 mock_auth（autouse）会把 get_current_user 顶成一个 admin 假用户，
    使所有请求无条件通过鉴权。若不禁用它，本文件断言 401/403 会全部失败；
    更危险的是，一旦断言被改写成「期望 200」，它会永远绿着 ——
    完全测不到「依赖是否真的挂在路由上」。

    故显式关闭该替身（项目既有 opt-out fixture，见
    tests/test_api_contract_comprehensive.py 的同类用法）。
    本文件用 HTTP 层断言而非直接调用依赖函数，正是因为要证明「挂载」这件事本身。
    """
    yield


def _h(uid: str, role: str = "student") -> dict:
    """构造 Bearer 头；uid 即 token sub。"""
    from shared.auth import create_token
    return {"Authorization": f"Bearer {create_token(uid, role=role)}"}


def _submit_body(user_id: str = "", class_name: str = "契约班") -> dict:
    return {"phase": "pre", "class_name": class_name, "user_name": "契约同学",
            "user_id": user_id, "answers": [{"qid": i, "option_index": 0} for i in range(1, 11)]}


# ------------------------------------------------------------
# /questions：刻意公开
# ------------------------------------------------------------
class TestQuestionsStaysPublic:
    def test_readable_without_credentials(self, client):
        """题库必须无凭据可读（学生答题页要在拿到题目之前可用）。"""
        assert client.get("/api/literacy/questions").status_code == 200


# ------------------------------------------------------------
# /submit：需登录（防「匿名第三方篡改研究原始数据」）
# ------------------------------------------------------------
class TestSubmitRequiresLogin:
    def test_anonymous_rejected_401(self, client):
        r = client.post("/api/literacy/submit", json=_submit_body())
        assert r.status_code == 401

    def test_forged_token_rejected_401(self, client):
        r = client.post("/api/literacy/submit", json=_submit_body(),
                        headers={"Authorization": "Bearer forged.token.value"})
        assert r.status_code == 401

    def test_logged_in_accepted_200(self, client):
        r = client.post("/api/literacy/submit", json=_submit_body(), headers=_h("c-stu"))
        assert r.status_code == 200

    def test_body_uid_still_outranks_token(self, client):
        """加鉴权不得改变「请求体 user_id 优先」的课堂防覆盖语义。

        全班共用 demo 账号登录时 token sub 一律是 demo；若 token 优先，
        全班提交会互相覆盖（并发试测实锤过一次）。故记录必须落在 body 的学号上。
        """
        r = client.post("/api/literacy/submit", json=_submit_body(user_id="c-real"),
                        headers=_h("demo"))
        assert r.status_code == 200

        teacher = _h("c-teacher", role="teacher")
        own = client.get("/api/literacy/report/c-real", headers=teacher)
        assert own.status_code == 200, "记录必须落在请求体给出的学号名下"
        assert own.json()["user_id"] == "c-real"
        assert client.get("/api/literacy/report/demo", headers=teacher).status_code == 404, \
            "token 的 demo 名下不得产生记录"


# ------------------------------------------------------------
# /report/{user_id}：本人 / 教师 / 管理员
# ------------------------------------------------------------
class TestReportIsSelfScoped:
    @pytest.fixture(autouse=True)
    def _seed_own_record(self, client):
        client.post("/api/literacy/submit", json=_submit_body(), headers=_h("c-owner"))

    def test_anonymous_rejected_401(self, client):
        assert client.get("/api/literacy/report/c-owner").status_code == 401

    def test_owner_allowed_200(self, client):
        assert client.get("/api/literacy/report/c-owner", headers=_h("c-owner")).status_code == 200

    def test_other_student_rejected_403(self, client):
        """IDOR 关闸：另一名学生读他人报告必须 403。"""
        assert client.get("/api/literacy/report/c-owner",
                          headers=_h("c-intruder")).status_code == 403

    def test_teacher_allowed_200(self, client):
        assert client.get("/api/literacy/report/c-owner",
                          headers=_h("c-teacher", role="teacher")).status_code == 200

    def test_admin_allowed_200(self, client):
        assert client.get("/api/literacy/report/c-owner",
                          headers=_h("c-admin", role="admin")).status_code == 200

    def test_demo_switch_does_not_relax_personal_report(self, client, monkeypatch):
        """演示放宽开关**不得**作用于个人报告。

        该开关的用途是让 demo 账号预览教师仪表板；一旦它也放宽个人报告，
        演示环境里任何持 demo 账号者都能按学号枚举读取任意学生数据 ——
        等于把刚关掉的 IDOR 原样放回。本人自查不依赖该开关，故无需放宽。
        """
        monkeypatch.setenv(_DEMO_SWITCH, "1")
        assert client.get("/api/literacy/report/c-owner",
                          headers=_h("c-intruder")).status_code == 403


# ------------------------------------------------------------
# /class-report：教师 / 管理员（含演示放宽边界）
# ------------------------------------------------------------
class TestClassReportIsTeacherOnly:
    CLASS = "契约聚合班"

    @pytest.fixture(autouse=True)
    def _seed_class(self, client):
        client.post("/api/literacy/submit", json=_submit_body(class_name=self.CLASS),
                    headers=_h("c-owner"))

    def test_anonymous_rejected_401(self, client):
        assert client.post("/api/literacy/class-report",
                           json={"class_name": self.CLASS}).status_code == 401

    def test_student_rejected_403(self, client):
        """含姓名的全班明细不得对普通学生开放。"""
        assert client.post("/api/literacy/class-report", json={"class_name": self.CLASS},
                           headers=_h("c-owner")).status_code == 403

    def test_teacher_allowed_200(self, client):
        r = client.post("/api/literacy/class-report", json={"class_name": self.CLASS},
                        headers=_h("c-teacher", role="teacher"))
        assert r.status_code == 200
        assert r.json()["student_count"] == 1

    def test_demo_switch_relaxes_student(self, client, monkeypatch):
        """演示开关打开时，已登录的 demo 学生账号可预览教师报告（并写 [DEMO-RELAX] 审计）。"""
        monkeypatch.setenv(_DEMO_SWITCH, "1")
        r = client.post("/api/literacy/class-report", json={"class_name": self.CLASS},
                        headers=_h("c-owner"))
        assert r.status_code == 200

    def test_demo_switch_still_requires_login(self, client, monkeypatch):
        """放宽的只是角色，不是登录：无凭据仍须 401。"""
        monkeypatch.setenv(_DEMO_SWITCH, "1")
        assert client.post("/api/literacy/class-report",
                           json={"class_name": self.CLASS}).status_code == 401
