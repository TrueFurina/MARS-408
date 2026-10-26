# -*- coding: utf-8 -*-
"""守护：成效证据闸必须**双向**有效（既会拦下开发数据，也能放行真实试点）。

为什么这个测试重要
--------------------------------------------------------------------------
`experiments/pilot_evidence_report.py` 是一道"诚实闸"：它决定现有数据够不够格叫成效证据。
这类闸最坏的两个失效形态是：
  * **永远放行**（形同虚设 ⇒ 谁都敢引用开发数据当成果）；
  * **永远拦截**（真实试点跑完了还判不达标 ⇒ 团队会绕过它，闸就死了）。
所以本测试用两个合成分支把两侧都钉住，并加一次变异验证（把真实用户名换成 test_ 前缀应立刻翻红）。

本仓库已经发生过一次具体形态：本机 `data/pg_fallback.db` 里 139 个 distinct
user_id 曾被判出 **124 个"真实用户"**，而它们百分之百是夹具（`stu_` 121 / `diag` 1 /
`u_t` 1 / `u_a` 1）——只因黑名单未登记这些前缀。该通道已于 2026-10-22 用「黑名单 +
正面核实」两层封住（详见实现文件 docstring），本文件后半部分的用例守护这条新红线。
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


# ============================================================================
# 2026-10-22 加固后的守护：正向核实（认不出 ⇒ 算不可信）
#
# 这些用例存在的理由：旧的 `is_test_account` 是**黑名单**，返回值 False 意味着
# "没被认出来是夹具"，下游却把它当成"是真实用户" —— 于是任何新夹具换个前缀就能抬高
# 真实用户数。`looks_like_real_student()` 把这个方向翻过来：不能正面证明是学号 ⇒ 不可信。
# 下面三组用例分别从「堵住」「放行」「白名单逃生口」三个方向把它钉死，缺任何一个方向
# 本闸门都可能退化成"永远红"（团队会绕过它，闸就死了）。
# ============================================================================

def _untrusted_db(tmp_path, users):
    """造一个**前四条判据全部达标**的库，但账号形态既非已知夹具、也不像学号。

    关键点：它不是随便一个坏库 —— 用户数 / 完成场次 / 任务发起场次 / 班级绑定人数
    四条全部过关，**只有第 5 条能拦住它**。这样本用例同时也是第 5 条的变异探针：
    一旦有人把该判据改成恒假，本库立刻假绿，测试转红。
    """
    p = str(tmp_path / "untrusted.db")
    _make_db(
        p,
        classes=("c1",),
        sessions=[(u, "task_1" if k < 2 else None, "finished") for u in users for k in range(3)],
        bound=[("c1", u) for u in users[:3]],
    )
    return p


_UNKNOWN_USERS = ["2024A01", "2024A02", "2024A03", "2024A04", "2024A05"]


def test_unrecognized_accounts_block_evidence_and_hide_stats(tmp_path):
    """「既非已知夹具、也不像学号」的账号 ⇒ 判红，且**不打印任何可抄的条数**。

    为什么连表格都要隐藏：这些数字一旦出现在屏幕上，就会被顺手抄进材料；
    只写一句"勿引用"而把 918 / 1830 之类留在屏幕上，等于没拦。
    """
    p = _untrusted_db(tmp_path, _UNKNOWN_USERS)
    stats = per.collect(p)
    ok, failing = per.verdict(stats)

    # 前四条判据此处**全部达标**（证明拦住它的确实只有第 5 条）
    assert stats["distinct_users_real"] == 5
    assert stats["sessions_finished"] == 15
    assert stats["sessions_finished_with_task"] == 10
    assert stats["max_bound_class"] == 3

    assert stats["real_candidates_n"] == 5
    assert stats["nonnumeric_candidates_n"] == 5
    assert ok is False
    assert any("数据源不可信" in f and "不得当作真实试用" in f for f in failing)

    text = per.render(stats, ok, failing)
    assert "🔴" in text
    assert "禁止对外引用" in text
    assert "明细已隐藏" in text
    assert "| sessions_total |" not in text, "数据源不可信时不得再打印可被抄走的条数"


def test_trusted_source_still_prints_raw_stats(tmp_path):
    """可信数据源（纯数学号）必须照常打印统计表 —— 防止隐藏逻辑被写反/写糊。

    与上一条互为反例：只测"该隐藏时隐藏"会漏掉"不该隐藏时也隐藏"这种反向失效。
    """
    p = str(tmp_path / "trusted.db")
    users = [f"2023{i:04d}" for i in range(1, 7)]
    _make_db(
        p,
        classes=("c1",),
        sessions=[(u, "task_1", "finished") for u in users for _ in range(2)],
        bound=[("c1", u) for u in users[:4]],
    )
    stats = per.collect(p)
    ok, failing = per.verdict(stats)
    assert ok is True, f"纯数学号须能穿透全部过滤，未满足项：{failing}"
    assert stats["nonnumeric_candidates_n"] == 0
    text = per.render(stats, ok, failing)
    assert "明细已隐藏" not in text
    assert "| sessions_total |" in text


def test_trusted_whitelist_rescues_non_numeric_accounts(tmp_path, monkeypatch):
    """非数学号体系必须有逃生口（TRUSTED_NON_NUMERIC），否则第 5 条会焊死闸门。

    白名单默认空 = 无豁免；这里用 monkeypatch 逐个显式登记，验证"人工确认后可放行"。
    """
    p = _untrusted_db(tmp_path, _UNKNOWN_USERS)
    monkeypatch.setattr(per, "TRUSTED_NON_NUMERIC", frozenset(_UNKNOWN_USERS))
    stats = per.collect(p)
    ok, failing = per.verdict(stats)
    assert stats["nonnumeric_candidates_n"] == 0
    assert ok is True, f"已显式登记白名单的账号应放行，未满足项：{failing}"
    assert "🔴" not in per.render(stats, ok, failing)


@pytest.mark.parametrize("uid,expected", [
    ("2023001", True),      # 纯数学号：正面核实通过
    ("2024A01", False),     # 混合形态：认不出 ⇒ 不可信（不是"算真实"）
    ("zhangsan", False),    # 拼音用户名：同上
    ("stu_feature_x", False), ("stu_outsider_021b1a", False),
    ("diag", False), ("u_t", False), ("u_a", False),
    ("test_user_0001", False), ("u_c14ded3ee34050ae", False),
    ("", False), (None, False),
])
def test_looks_like_real_student(uid, expected):
    """`looks_like_real_student` 与 `is_test_account` 同为 False 但含义相反，此处逐态钉住。"""
    assert per.looks_like_real_student(uid) is expected


@pytest.mark.parametrize("uid", ["stu_outsider_021b1a", "stu_feature_x", "stu_bad_phase",
                                 "stu_join_only", "stu_no_name_p4", "diag", "u_t", "u_a"])
def test_repo_fixture_accounts_are_no_longer_real(uid):
    """本机库实际存在的夹具真名，永不得被当成真实用户 —— 不论由哪一层判掉。

    2026-10-22 方案 A 修订：原断言 `is_test_account(uid) is True`（黑名单口径）守护的是**已被否决**
    的做法 —— stu_* / diag 现已刻意不登记黑名单、留给第 5 条判据去抓并隐藏明细（见实现文件元组末尾
    注释）。故改为断言结果不变量 `looks_like_real_student(uid) is False`；u_t / u_a 仍由放宽后的
    `_ANON_RE` 判掉，最后一行一并钉住两者的分工。
    """
    assert per.looks_like_real_student(uid) is False
    assert per.is_test_account(uid) is (uid in ("u_t", "u_a"))
