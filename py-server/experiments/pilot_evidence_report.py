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
5. `nonnumeric_candidates` == 0：不存在「既非已知夹具、也不像学号」的账号
   （阈值刻意**不写进** `MIN_PILOT` —— 它不是"够不够多"的量，而是布尔型可信度闸门）

第 5 条从哪来（2026-10-22 口径变更：认不出 ⇒ 算不可信）
--------------------------------------------------------------------------
前四条有一个共同的**假阳性通道**：它们只做「**排除**已知黑名单」，
凡没被识别出是夹具的账号，**一律被算作真实用户**。于是任何新引入的夹具命名
（无论有意还是顺手）都会自动抬高 `distinct_users_real` / `max_bound_class`，
把闸门推向绿色 —— 不需要任何人撒谎，只要换个前缀就够了。

实测本机 `data/pg_fallback.db`：139 个 distinct user_id 里被判「真实」的有 124 个，
而这 124 个**百分之百是夹具**（`stu_` 121 / `diag` 1 / `u_t` 1 / `u_a` 1）。
当时闸门只是**碰巧**停在第 4 条上（`max_bound_class` = 2 < 3）——一条结构性巧合。

第 5 条把口径反过来：**不能正面证明是学号 ⇒ 不作真实用户**。
黑名单照旧排除已知夹具（省事的那一层），新判据兜住所有**未知**命名习惯。
命中时本工具不仅判 ❌，还会**隐藏原始统计表**：表里那些条数才是会被顺手抄进材料的东西，
只写"勿引用"而把数字留在屏幕上，等于没拦。

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
    # 2026-10-21 计算机模拟演练（用户拍板「真实试点不可能，纯按计算机模拟来」）：
    # sim_ 前缀账号是脚本驱动的模拟学生，不是真实用户。不登记的话它们会把
    # distinct_users_real / max_bound_class 撑成假阳性 —— 那正是制造"试用已开展"
    # 假象的路径，与本闸门的存在目的相反。
    "sim_", "sim-",
    # 2026-10-22 取证闸口径加固：本机 data/pg_fallback.db 的 139 个 distinct user_id 中，
    # 有 124 个被误判成真实用户，它们百分之百是夹具 —— stu_ 前缀 121 个（career 路由/权限/
    # 越权测试造的学生账号，如 stu_outsider_*、stu_feature_x、stu_bad_phase、stu_join_only、
    # stu_no_name_p4）+ diag 1 个（诊断脚本账号）+ u_t / u_a 2 个（短匿名账号，由下方
    # _ANON_RE 放宽后覆盖）。这两类前缀此前从未登记，是本闸门当时最大的假阳性来源。
    "stu_", "diag",
)
# 形如 u_<小写字母数字短串> 的匿名账号：多为程序生成的测试/冒烟用户（人工注册通常不用这种名字）。
#
# 2026-10-22 放宽：原为 `^u_[0-9a-f]{16}$`（只认 16 位十六进制），本机库里真实存在的
# `u_t` / `u_a` 两个短匿名账号因此**漏网**，被计入 distinct_users_real。
# 放宽到 `^u_[0-9a-z]{1,32}$` 为什么是**安全方向**：本工具的既定哲学是
# "拿不准一律按测试处理"（见 is_test_account 的 docstring），把任何 `u_` 小串判为测试账号
# 落在**保守方向** —— 宁可漏判真实用户（低估成果），也不可把夹具算成真实用户（高估成果）；
# 前者只是"报告偏严"，后者是"发生型证据造假"，两者代价不对称。
# 代价（写在这里便于日后讨论）：若将来某真实试点确实用 `u_xxx` 给账号命名，需要**逐个显式**
# 登记到 TRUSTED_NON_NUMERIC 才能通过 —— 这道人工确认是刻意的，不是 bug。
_ANON_RE = re.compile(r"^u_[0-9a-z]{1,32}$")

# 正面核实的白名单逃生口：**默认空 = 无豁免**。
#
# 为什么需要它：黑名单 + 学号形态都是启发式，遇到合法但非纯数字的学号体系
# （如 S20240123、2024-CS-01）会被第 5 条判据误杀，届时把**确切账号**逐个登记在此处即可放行。
# 为什么**默认空**：默认空意味着「没有任何账号能靠名字蒙混过关」。每加一个都要求人工确认
# 其确为该校真实学号，否则白名单自身会变成新的假阳性通道 —— 那正是本次要堵的同一类问题。
TRUSTED_NON_NUMERIC: frozenset[str] = frozenset()

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


def _looks_like_student_id(uid) -> bool:
    """学号形态判定：纯数字。

    为什么用"纯数字"这么窄的口径：真实学号由学校学号体系生成，形态稳定，
    且与所有夹具命名空间（`stu_` / `test_` / `smoke_` / `e2e_` / `sim_` / `diag` / `u_` …）
    天然不重叠。窄口径换来的是**可预期的单向误判方向**：认错只可能是把真实用户漏掉（判严），
    不可能把夹具认成真实用户（判宽）。非数字学号体系请用 TRUSTED_NON_NUMERIC 显式登记。
    """
    return str(uid or "").isdigit()


def looks_like_real_student(uid) -> bool:
    """正面核实：这个 user_id 能不能当作真实学生账号。

    判定 = 过了黑名单（不是任何已知夹具形态）**且**满足以下之一：
      * 形态像学号（纯数字，见 `_looks_like_student_id`）；
      * 已显式登记在白名单 `TRUSTED_NON_NUMERIC` 里。

    与 `is_test_account` 的区别（这是 2026-10-22 的核心口径变更，务必分清）：
      * `is_test_account` 是**黑名单**：认不出 ⇒ False ⇒ 下游统计把它算成"真实用户"；
      * 本函数是**正面核实**：认不出 ⇒ False ⇒ 算**不可信**。
    两者返回值同为 False，含义却相反。旧口径下"没被认出来"会自动成为真实用户，
    于是任何新出现的夹具命名都能单向抬高真实用户数 —— 那就是假阳性通道。
    本函数把它封住：凡不能正面证明是学号的，一律不作真实用户。
    """
    if is_test_account(uid):
        return False
    s = str(uid or "")
    return _looks_like_student_id(s) or s in TRUSTED_NON_NUMERIC


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

    # 正面核实的观察全集 = 会话 user_id ∪ 班级绑定 user_id。
    # 为什么把班级绑定也算进来：第 3 条判据（max_bound_class）读的就是绑定表，只核会话会漏掉
    # 「只在班里、还没开过场」的账号 —— 本机实测有 7 个这类账号（其中 2 个是新前缀夹具），
    # 它们同样能把「试用已开展」的假象撑起来。对本闸门这类红线，口径宁宽勿窄。
    bound_users = {u for _cid, u in bound if u}
    observed_users = all_users | bound_users
    blacklisted = {u for u in observed_users if is_test_account(u)}
    # 过了黑名单、还没做正面核实的全集（"认不出"的集中营，第 5 条判据的输入）
    real_candidates = sorted(observed_users - blacklisted, key=str)
    # 其中**不像学号**的：既非已知夹具、也证明不了是学号 ⇒ 数据源不可信
    nonnumeric_candidates = [u for u in real_candidates if not looks_like_real_student(u)]

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
        # 以下四项供第 5 条判据（数据源可信度）使用，语义见脚本 docstring：
        # 认不出 ⇒ 算不可信，而不是认不出 ⇒ 算真实。
        "real_candidates": real_candidates,
        "real_candidates_n": len(real_candidates),
        "nonnumeric_candidates": nonnumeric_candidates,
        "nonnumeric_candidates_n": len(nonnumeric_candidates),
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

    # 第 5 条：这条与上面四条不同，它不是"量够不够"，而是**数据源可信度**。
    # 只要存在一个账号既是黑名单以外的未知形态、又证明不了是学号，就说明这批数据
    # 的账号来源无法解释 ⇒ 整批明细不可对外引用（不是打折引用，是禁止引用）。
    #
    # 用 .get(...) 而非 [...]：第三方（旧版 collect / 手写 stats）可能不带这些键，
    # 缺键时按 0 处理 = 该条通过，交由前四条兜底，不会让调用方 KeyError 崩掉。
    nonnumeric_n = stats.get("nonnumeric_candidates_n", 0)
    if nonnumeric_n > 0:
        sample = list(stats.get("nonnumeric_candidates") or [])[:5]
        failing.append(
            f"有 {nonnumeric_n} 个账号既非已知测试夹具、也不像学号（样本：{sample}）"
            f" ⇒ 数据源不可信，**不得当作真实试用**")
    return (not failing), failing


def render(stats: dict, ok: bool, failing: list[str]) -> str:
    # 第 5 条判据是否命中。命中时**不打印任何可被抄数的明细**：
    # 只在文案里写"禁止引用"是不够的 —— 表格还在，就有人会抄走其中的行数/人数，
    # 而那正是本闸门唯一要拦的东西。所以这种情况下连条数本身都不出库。
    untrusted = stats.get("nonnumeric_candidates_n", 0) > 0
    L = ["# 成效证据状态（自动生成，勿手改）", ""]
    L.append(f"- 数据源：`{stats['db']}`")
    L.append(f"- 判据：{json.dumps(MIN_PILOT, ensure_ascii=False)}（见脚本 docstring，可审计）")
    L.append("")
    L.append("## 裁决")
    L.append("")
    if untrusted:
        L.append(f"🔴 **数据源不可信**：检出 {stats['nonnumeric_candidates_n']} 个账号"
                 f"既不在已知测试夹具名单里、也不像学号"
                 f"（样本：{(stats.get('nonnumeric_candidates') or [])[:5]}）。")
        L.append("")
        L.append("以下条数**禁止对外引用**，包括不可在材料里出现「N 场 / N 人」——"
                 "连「多少」都不许说；正确表述只有「尚未开展真实试用」。")
        L.append("")
        L.append("处置顺序：先查明这些账号的来源（多半是新引入的开发夹具），"
                 "确认是夹具则在 `TEST_ACCOUNT_PREFIXES` 登记；"
                 "确认是真实学号则逐个登记入 `TRUSTED_NON_NUMERIC`（默认空，需人工确认）。")
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
    if untrusted:
        # 明细整体隐藏：见 render 开头注释（可视化=可抄，可抄=会漏）。
        L.append("明细已隐藏，原因：数据源不可信")
    else:
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
