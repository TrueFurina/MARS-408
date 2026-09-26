# ============================================================
# 职业素养测评 —— user_id 解析优先级回归测试
# 覆盖：请求体 user_id（学号后4位）> Bearer token sub > demo 兜底
# 这是课堂防覆盖的关键逻辑（并发试测曾因 token 优先而互相覆盖）。
#
# 注意：本文件**不**导入 main / 不使用 TestClient，避免触发 main 生命周期里的
# F6 单写者锁（import_worker 起锁）导致用例全 ERROR。
# ============================================================

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest

# 与同目录其他 literacy 测试一致的测试库隔离（本文件全程 mock _get_conn，不会真正落盘）
os.environ.setdefault(
    "NETLEARN_LITERACY_DB",
    os.path.join(os.path.dirname(__file__), "_test_literacy_uid.db"),
)

from api.literacy_assessment import (  # noqa: E402
    LiteracySubmitRequest,
    QUESTION_BANK,
    _resolve_submitter_uid,
    submit_literacy,
)


class TestResolveSubmitterUid:
    """_resolve_submitter_uid 纯函数：4 类优先级用例。"""

    def test_body_priority_over_token(self):
        # 同时给 body user_id 与 Bearer token —— body 必须胜出
        req = LiteracySubmitRequest(user_id="stu-003", answers=[])
        assert _resolve_submitter_uid(req, "Bearer tok-abc") == "stu-003"

    def test_empty_body_falls_back_to_token_sub(self):
        req = LiteracySubmitRequest(user_id="", answers=[])
        with patch("shared.auth.verify_token", return_value={"sub": "tok-user"}):
            assert _resolve_submitter_uid(req, "Bearer tok-abc") == "tok-user"

    def test_empty_body_no_token_falls_back_to_demo(self):
        req = LiteracySubmitRequest(user_id="", answers=[])
        # 无 Authorization
        assert _resolve_submitter_uid(req, None) == "demo"
        # 有 Authorization 但 verify_token 抛错
        with patch("shared.auth.verify_token", side_effect=ValueError("bad")):
            assert _resolve_submitter_uid(req, "Bearer bad") == "demo"

    def test_classroom_scenario_body_overrides_demo_token(self):
        # 全班共用 demo 账号登录（token sub=demo），但各自提交学号后4位
        req = LiteracySubmitRequest(user_id="9001", answers=[])
        assert _resolve_submitter_uid(req, "Bearer demo") == "9001"


@pytest.mark.asyncio
async def test_submit_literacy_uses_body_uid_not_demo_token():
    """端到端确认：解析出的 body uid 真正写入 DELETE/INSERT（防 no-op / 解析被绕过回归）。
    token 为 demo 时绝不能用 demo 覆盖学号后4位。"""
    fake_conn = MagicMock()
    fake_lock = MagicMock()
    req = LiteracySubmitRequest(
        user_id="stu-003",
        user_name="张三",
        class_name="C1",
        phase="pre",
        answers=[{"qid": q["id"], "option_index": 0} for q in QUESTION_BANK],
    )
    with patch("api.literacy_assessment._get_conn", return_value=fake_conn), patch(
        "api.literacy_assessment._lock", fake_lock
    ):
        await submit_literacy(req, "Bearer demo")  # token=demo 不应覆盖 body

    delete_calls = [
        c
        for c in fake_conn.execute.call_args_list
        if c.args and "DELETE FROM literacy_attempts" in c.args[0]
    ]
    assert delete_calls, "expected DELETE FROM literacy_attempts executed"
    # 断言落库的 user_id 是 body 的 stu-003，而非 token 的 demo
    assert delete_calls[0].args[1] == ("stu-003", "pre")


@pytest.mark.asyncio
async def test_submit_literacy_uses_token_uid_when_body_empty():
    """body 为空时用 token sub 落库。"""
    fake_conn = MagicMock()
    fake_lock = MagicMock()
    req = LiteracySubmitRequest(
        user_id="",
        user_name="李四",
        class_name="C1",
        phase="post",
        answers=[{"qid": q["id"], "option_index": 1} for q in QUESTION_BANK],
    )
    with patch("api.literacy_assessment._get_conn", return_value=fake_conn), patch(
        "api.literacy_assessment._lock", fake_lock
    ), patch("shared.auth.verify_token", return_value={"sub": "tok-user"}):
        await submit_literacy(req, "Bearer tok-abc")

    delete_calls = [
        c
        for c in fake_conn.execute.call_args_list
        if c.args and "DELETE FROM literacy_attempts" in c.args[0]
    ]
    assert delete_calls, "expected DELETE FROM literacy_attempts executed"
    assert delete_calls[0].args[1] == ("tok-user", "post")


if __name__ == "__main__":
    asyncio.run(test_submit_literacy_uses_body_uid_not_demo_token())
