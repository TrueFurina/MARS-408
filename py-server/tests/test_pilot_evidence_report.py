# -*- coding: utf-8 -*-
"""守护：成效证据闸必须**双向**有效（既会拦下开发数据，也能放行真实试点）。

为什么这个测试重要
--------------------------------------------------------------------------
`experiments/pilot_evidence_report.py` 是一道"诚实闸"：它决定现有数据够不够格叫成效证据。
这类闸最坏的两个失效形态是：
  * **永远放行**（形同虚设 ⇒ 谁都敢引用开发数据当成果）；
  * **永远拦截**（真实试点跑完了还判不达标 ⇒ 团队会绕过它，闸就死了）。
所以本测试用两个合成分支把两侧都钉住，并加一次变异验证（把真实用户名换成 test_ 前缀应立刻翻红）。
"""
import importlib.util
import os
import sqlite3

import pytest

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "experiments", "pilot_evidence_report.py")
_spec = importlib.util.spec_from_file_location("pilot_evidence_report", _PATH)
per = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(per)


_DDL = """
CREATE TABLE career_classes (id TEXT PRIMARY KEY, student_count INTEGER DEFAULT 0);
CREATE TABLE career_sessions (id TEXT PRIMARY KEY, user_id TEXT, task_id TEXT, status TEXT);
CREATE TABLE career_class_students (class_id TEXT, user_id TEXT);
"""


def _make_db(path, classes=(), sessions=(), bound=()):
    con = sqlite3.connect(path)
    con.executescript(_DDL)
    con.executemany("INSERT INTO career_classes (id) VALUES (?)", [(c,) for c in classes])
    con.executemany("INSERT INTO career_sessions (id,user_id,task_id,status) VALUES (?,?,?,?)",
                    [(f"s{i}", u, t, st) for i, (u, t, st) in enumerate(sessions)])
    con.executemany("INSERT INTO career_class_students (class_id,user_id) VALUES (?,?)",
                    [(c, u) for c, u in bound])
    con.commit()
    con.close()


def test_empty_db_is_not_evidence(tmp_path):
    """空库（连表都没有）不得被判为达标——`_rows` 遇错返回空，不能把异常当通过。"""
    p = str(tmp_path / "empty.db")
    sqlite3.connect(p).close()
    stats = per.collect(p)
    ok, failing = per.verdict(stats)
    assert stats["sessions_total"] == 0
    assert ok is False
    assert any("真实用户数" in f for f in failing)


def test_dev_data_like_current_repo_is_rejected(tmp_path):
    """复刻仓库现状的形态（测试账号 + 空班）必须被拦下。"""
    p = str(tmp_path / "dev.db")
    _make_db(
        p,
        classes=("c1", "c2", "c3"),
        sessions=([("test_user_0001", None, "finished")] * 20
                  + [("smoke_user", None, "ongoing")] * 5),
        bound=[("c1", None), ("c2", None), ("c3", None)],
    )
    stats = per.collect(p)
    ok, failing = per.verdict(stats)
    assert stats["distinct_users_real"] == 0
    assert ok is False
    assert len(failing) >= 3  # 用户数 / 已完成场次 / 绑定学生 均不达标


def test_genuine_pilot_passes(tmp_path):
    """真实试点形态（多真实用户 + 一个班绑定多人 + 教师任务完成）应能通过。

    没有这条，闸可能退化成"永远返回不达标"，团队就会绕过它。
    """
    p = str(tmp_path / "pilot.db")
    users = [f"2023{i:04d}" for i in range(1, 7)]  # 像学号的真实用户名，非测试前缀
    _make_db(
        p,
        classes=("c1",),
        sessions=[(u, "task_1", "finished") for u in users for _ in range(2)]
                 + [(u, "task_1", "ongoing") for u in users[:2]],
        bound=[("c1", u) for u in users[:4]],
    )
    stats = per.collect(p)
    ok, failing = per.verdict(stats)
    assert stats["distinct_users_real"] == 6
    assert stats["sessions_finished_with_task"] == 12
    assert stats["max_bound_class"] == 4
    assert ok is True, f"真实试点形态应达标，未满足项：{failing}"


def test_mutation_rename_users_to_test_prefix_flips_verdict(tmp_path):
    """变异验证：把同一个"达标"库里的真实用户名改成 test_ 前缀 → 裁决必须立刻翻红。

    这证明判据真的在看"真实用户"，而不是被总数蒙混过去。
    """
    p = str(tmp_path / "mutant.db")
    users = [f"test_2023{i:04d}" for i in range(1, 7)]  # 只改名字前缀
    _make_db(
        p,
        classes=("c1",),
        sessions=[(u, "task_1", "finished") for u in users for _ in range(2)],
        bound=[("c1", u) for u in users[:4]],
    )
    stats = per.collect(p)
    ok, _ = per.verdict(stats)
    assert stats["sessions_total"] == 12, "记录数不变（排除的只是账号身份）"
    assert stats["distinct_users_real"] == 0
    assert ok is False, "测试账号前缀被换成 test_ 后，绝不能再判为达标"


@pytest.mark.parametrize("uid,expected", [
    ("test_user_0001", True), ("smoke_user", True), ("e2e_student", True),
    ("u_test", True), ("u_c14ded3ee34050ae", True), ("baseline_probe", True),
    ("2023001", False), ("zhangsan", False), ("", True), (None, True),
])
def test_is_test_account(uid, expected):
    assert per.is_test_account(uid) is expected
