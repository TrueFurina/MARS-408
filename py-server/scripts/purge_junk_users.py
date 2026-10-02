"""清理 netlearn_users.db 中的测试/调试遗留用户（仅删垃圾，保留真实账号）。

设计原则（对齐项目"垃圾即删"约定，但**不**使用 DELETE FROM users 全表清空）：
- 明确白名单 KEEP = {admin, demo, teacher1}（运营/演示/教师账号，真实保留）。
- 其余全部判定为垃圾：journey_*/dbg_*/test*/af_* 等批量调试账号，以及
  probe_verify_001 / bugfix_tester / diag0902 / ability_probe_* / qauser_* 等单例探针账号。
- 本仓库 FK 未启用，故对每张含 user_id 的子表一并级联删除，避免孤儿行。

用法：
    python scripts/purge_junk_users.py            # 仅干跑，打印将被删除的账号与计数
    python scripts/purge_junk_users.py --apply    # 实际执行
"""
import argparse
import sqlite3

DB_PATH = r"E:\Program\MARL\study-help-pro\py-server\data\netlearn_users.db"
KEEP = {"admin", "demo", "teacher1"}

CHILD_TABLES = [
    "user_profiles",
    "user_quiz_history",
    "user_conversations",
    "profile_snapshots",
    "user_wrong_questions",
    "user_daily_plans",
    "memory_l1_working",
    "memory_l2_semantic",
    "memory_l3_episodic",
    "skill_ratings",
    "skill_usage_log",
    "skill_favorites",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际执行删除；不加则仅干跑")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("SELECT id, username, role FROM users")
    all_users = cur.fetchall()

    keep_ids = [uid for uid, name, role in all_users if name in KEEP]
    junk = [(uid, name, role) for uid, name, role in all_users if name not in KEEP]
    junk_ids = [uid for uid, _, _ in junk]

    print(f"[dry] 总用户数: {len(all_users)}")
    print(f"[dry] 保留账号({len(keep_ids)}): " + ", ".join(n for _, n, _ in all_users if n in KEEP))
    print(f"[dry] 将删除垃圾账号({len(junk)}):")
    for uid, name, role in junk:
        print(f"        - {name} ({role}) [id={uid}]")

    if not args.apply:
        print("\n⚠️ 干跑模式，未做任何修改。加 --apply 才真正删除。")
        return

    # 级联清理子表
    for t in CHILD_TABLES:
        ph = ",".join("?" * len(junk_ids))
        cur.execute(f"DELETE FROM {t} WHERE user_id IN ({ph})", junk_ids)
        print(f"[apply] {t}: 删除 {cur.rowcount} 行")

    cur.execute(f"DELETE FROM users WHERE id IN ({','.join('?' * len(junk_ids))})", junk_ids)
    print(f"[apply] users: 删除 {cur.rowcount} 行")

    con.commit()

    cur.execute("SELECT COUNT(*) FROM users")
    remaining = cur.fetchone()[0]
    print(f"\n✅ 完成。剩余用户数: {remaining}")
    cur.execute("SELECT username, role FROM users ORDER BY username")
    for name, role in cur.fetchall():
        print(f"        {name} ({role})")
    con.close()


if __name__ == "__main__":
    main()
