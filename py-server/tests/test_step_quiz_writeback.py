"""P2 闭环拓展 — 步骤化答题完成时回写语义掌握度（使 adaptive 对真实用户生效）。

运行：
    cd py-server && python tests/test_step_quiz_writeback.py
或：
    cd py-server && python -m pytest tests/test_step_quiz_writeback.py -q
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from api.quiz import StepAnswerRequest, submit_step_answer


def test_writeback_called_on_finish():
    # 完成 step_tcp_1 的最后一步（共 3 步，索引 0/1/2），答错
    with patch("services.memory_service.record_quiz_result") as mock_rec:
        res = asyncio.run(
            submit_step_answer(
                "step_tcp_1",
                StepAnswerRequest(question_id="step_tcp_1", step_index=2, answer="wrong"),
                {"user_id": "u_wb_test"},
            )
        )
        assert res.finished is True
        assert mock_rec.called, "完成时必须回写语义掌握度"
        args = mock_rec.call_args.args
        kwargs = mock_rec.call_args.kwargs
        assert args[0] == "u_wb_test"
        assert args[1] == "computer_network", "topic 应为题目 subject（课程级）"
        assert kwargs.get("correct") is False, "答错时 correct 应为 False"


def test_no_writeback_before_finish():
    # 仅完成第一步（非最后一步），不应回写掌握度
    with patch("services.memory_service.record_quiz_result") as mock_rec:
        res = asyncio.run(
            submit_step_answer(
                "step_tcp_1",
                StepAnswerRequest(question_id="step_tcp_1", step_index=0, answer="wrong"),
                {"user_id": "u_wb_test"},
            )
        )
        assert res.finished is False
        assert not mock_rec.called, "未完成时不应回写掌握度"


if __name__ == "__main__":
    test_writeback_called_on_finish()
    test_no_writeback_before_finish()
    print("ALL step-quiz writeback tests PASSED")
