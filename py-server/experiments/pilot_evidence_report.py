# -*- coding: utf-8 -*-
"""成效证据链 · 取证工具（拼图③）：从真实数据库生成"可不可以引用"的裁决。

为什么需要它
--------------------------------------------------------------------------
本仓库的开发环境里躺着 946 条 `career_sessions` 记录 —— 但它们来自**测试夹具**
（297 个班中 194 个 0 学生、99 个恰好 3 人；11 个 user_id 全是 test_/smoke_/e2e_ 前缀）。
若有人顺手引用「946 场实训」当作使用规模或成效，就是**虚假宣称**，触碰本项目
「发生型证据不可造假」红线。

所以本工具把这条红线**代码化**：只读扫描数据库，按一组**可审计的结构性判据**给出裁决 ——
数据够不够格叫"成效证据"。不够格时它会明确输出「❌ 不构成成效证据」并逐条列出未满足项，
从机制上堵住"拿开发数据当成果"的口子。

判据（`MIN_PILOT`，可审计、可讨论，不是黑箱）
--------------------------------------------------------------------------
1. `real_users`：**排除已知测试账号**后的独立用户数 ≥ 5
2. `finished_sessions`：已完成的实训场次 ≥ 10
3. `max_bound_class`：至少一个班里**已绑定 ≥ 3 名非测试学生**
4. `finished_with_task`：**由教师任务发起**（task_id 非空）且已完成的场次 ≥ 5

用法
--------------------------------------------------------------------------
    python experiments/pilot_evidence_report.py                    # 默认 data/pg_fallback.db
    python experiments/pilot_evidence_report.py --db <path> --out <report.md>

退出码：0 = 满足最低条件；1 = 不构成成效证据（这是**正常结果**，不是错误）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

# 已知的测试/开发账号前缀（career 域）。新增测试夹具时请一并登记，
# 否则它们会被当成"真实用户"，把裁决撑成假阳性。
TEST_ACCOUNT_PREFIXES = (
    "test_", "test_user", "smoke_", "smoke-", "e2e_", "u_test", "u_e2e",
    "baseline_", "journey_", "probe_", "pilot_demo", "tmp_", "demo_check",
)
# 形如 u_<16位hex> 的匿名账号：多为程序生成的测试/冒烟用户（人工注册通常不用这种名字）
_ANON_RE = re.compile(r"^u_[0-9a-f]{16}$")

MIN_PILOT = {
    "real_users": 5,
    "finished_sessions": 10,
    "max_bound_class": 3,
    "finished_with_task": 5,
}


def is_test_account(uid) -> bool:
    """判断 user_id 是否属于已知测试/开发账号（保守：拿不准的一律按测试处理）。"""
    s = str(uid or "")
    if not s:
        return True
    if any(s.startswith(p) for p in TEST_ACCOUNT_PREFIXES):
        return True
    return bool(_ANON_RE.match(s))


def _rows(con, sql, params=()):
    try:
        return con.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


def collect(db_path: str) -> dict:
    """只读收集统计。表不存在时按 0 处理（不抛异常，便于在空库上运行）。"""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        sessions = _rows(con, "SELECT user_id, task_id, status FROM career_sessions")
        bound = _rows(con, "SELECT class_id, user_id FROM career_class_students "
                           "WHERE user_id IS NOT NULL AND user_id <> ''")
        classes = _rows(con, "SELECT id FROM career_classes")
    finally:
        con.close()

    all_users = {s[0] for s in sessions if s[0]}
    real_users = {u for u in all_users if not is_test_account(u)}

    finished = [s for s in sessions if s[2] == "finished"]
    finished_real = [s for s in finished if not is_test_account(s[0])]
    finished_with_task = [s for s in finished if s[1]]

    # 每个班里"已绑定的非测试学生"数
    per_class: dict = {}
    for cid, uid in bound:
        if is_test_account(uid):
            continue
        per_class[cid] = per_class.get(cid, 0) + 1
    max_bound_class = max(per_class.values()) if per_class else 0

    return {
        "db": os.path.abspath(db_path),
        "sessions_total": len(sessions),
        "sessions_finished": len(finished),
        "sessions_finished_real": len(finished_real),
        "sessions_finished_with_task": len(finished_with_task),
        "distinct_users_all": len(all_users),
        "distinct_users_real": len(real_users),
        "test_accounts_sample": sorted(all_users - real_users)[:8],
        "classes_total": len(classes),
        "classes_with_bound_students": len(per_class),
        "max_bound_class": max_bound_class,
    }


def verdict(stats: dict) -> tuple[bool, list[str]]:
    """按 MIN_PILOT 逐条裁决。返回 (是否达标, 未满足项说明)。"""
    failing = []
    if stats["distinct_users_real"] < MIN_PILOT["real_users"]:
        failing.append(
            f"真实用户数 {stats['distinct_users_real']} < {MIN_PILOT['real_users']}"
            f"（排除测试账号后；当前全部账号样本：{stats['test_accounts_sample']}）")
    if stats["sessions_finished"] < MIN_PILOT["finished_sessions"]:
        failing.append(
            f"已完成场次 {stats['sessions_finished']} < {MIN_PILOT['finished_sessions']}")
    if stats["max_bound_class"] < MIN_PILOT["max_bound_class"]:
        failing.append(
            f"单个班最多已绑定非测试学生 {stats['max_bound_class']} < {MIN_PILOT['max_bound_class']}")
    if stats["sessions_finished_with_task"] < MIN_PILOT["finished_with_task"]:
        failing.append(
            f"教师任务发起且完成的场次 {stats['sessions_finished_with_task']}"
            f" < {MIN_PILOT['finished_with_task']}")
    return (not failing), failing


def render(stats: dict, ok: bool, failing: list[str]) -> str:
    L = ["# 成效证据状态（自动生成，勿手改）", ""]
    L.append(f"- 数据源：`{stats['db']}`")
    L.append(f"- 判据：{json.dumps(MIN_PILOT, ensure_ascii=False)}（见脚本 docstring，可审计）")
    L.append("")
    L.append("## 裁决")
    L.append("")
    if ok:
        L.append(f"✅ **满足最低条件** —— 可作为**探索性**成效证据引用。")
        L.append("")
        L.append(f"样本量须如实标注：真实用户 N={stats['distinct_users_real']}，"
                 f"完成实训 {stats['sessions_finished']} 场。")
        L.append("**仍禁止**：显著性宣称、因果推断、与对照组的比较（本工具不产生对照组）。")
    else:
        L.append("❌ **不构成成效证据** —— 当前数据**不得**作为使用规模或教学成效引用。")
        L.append("")
        L.append("未满足项：")
        for f in failing:
            L.append(f"- {f}")
        L.append("")
        L.append("> 诚实口径：现有记录全部来自开发/测试/基线跑批，**不是真实用户试用**。"
                 "对外表述应为「尚未开展真实试用」，而非引用这些条数。")
    L.append("")
    L.append("## 原始统计")
    L.append("")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    for k in ("sessions_total", "sessions_finished", "sessions_finished_real",
              "sessions_finished_with_task", "distinct_users_all", "distinct_users_real",
              "classes_total", "classes_with_bound_students", "max_bound_class"):
        L.append(f"| {k} | {stats[k]} |")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "pg_fallback.db"))
    ap.add_argument("--out", help="markdown 输出路径（缺省打印到 stdout）")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"数据库不存在：{args.db}", file=sys.stderr)
        return 1
    stats = collect(args.db)
    ok, failing = verdict(stats)
    text = render(stats, ok, failing)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已落盘：{args.out}")
    else:
        print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
