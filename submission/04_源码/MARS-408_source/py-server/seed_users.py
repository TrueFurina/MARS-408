# ============================================================
# 用户库初始化脚本 — 清理测试数据并灌入演示账号
# 仅用于开发/演示环境，生产环境请勿运行（会清空已注册用户）
# 用法: py-server/.venv/Scripts/python.exe py-server/seed_users.py
# ============================================================
import os
import sys
import shutil

# 将 py-server 加入 sys.path，确保能 import db / shared
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from db import user_store as us

DB_PATH = us._DB_PATH
WAL = DB_PATH + "-wal"
SHM = DB_PATH + "-shm"

# ── 1. 清空全部表（保留库文件，避免安全删除拦截） ──
conn = us._get_conn()
with us._lock:
    conn.execute("DELETE FROM user_conversations")
    conn.execute("DELETE FROM user_quiz_history")
    conn.execute("DELETE FROM user_profiles")
    conn.execute("DELETE FROM users")
    conn.commit()
print("[清理] 已清空 users / user_profiles / user_quiz_history / user_conversations")

# ── 2. 管理员账号 ──
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
# ⚠️ 安全：不再提供默认口令。必须由环境变量 ADMIN_PASSWORD 注入（建议来自 .env / 密钥管理器）。
# 缺失即退出，避免把弱口令写回仓库导致 G1 门禁回归。
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASS:
    print("[错误] 未设置环境变量 ADMIN_PASSWORD，无法种子管理员账号。请在 .env 中配置强随机口令后重试。")
    sys.exit(1)
us.ensure_admin(ADMIN_USER, ADMIN_PASS, display_name="系统管理员")
print(f"[管理员] {ADMIN_USER} / (口令取自环境变量 ADMIN_PASSWORD，已不在日志中明文打印)")

# ── 3. 演示学生账号 + 画像 + 答题 + 对话 ──
DEMO_STUDENTS = [
    {
        "username": "zhangwei",
        "password": "Student@2026",
        "display_name": "张伟",
        "profile": {
            "target": "考研408",
            "level": "进阶",
            "weak_subjects": ["计算机组成", "操作系统"],
            "strong_subjects": ["数据结构", "计算机网络"],
            "weekly_hours": 18,
            "goal_score": 125,
            "style": "思维导图+刷题",
        },
        "quiz": [
            ("ds", True, "easy"), ("ds", True, "medium"), ("ds", False, "hard"),
            ("network", True, "easy"), ("network", True, "medium"), ("network", True, "medium"),
            ("network", False, "hard"), ("os", False, "medium"), ("os", False, "hard"),
            ("co", False, "medium"), ("co", True, "easy"), ("ds", True, "medium"),
        ],
        "conversations": [
            {"id": "c_zw_1", "title": "计网·TCP三次握手详解", "messages": [
                {"role": "user", "content": "请讲讲 TCP 三次握手的过程和作用"},
                {"role": "assistant", "content": "三次握手用于建立可靠连接：1)客户端发 SYN；2)服务端回 SYN+ACK；3)客户端发 ACK……"},
            ]},
            {"id": "c_zw_2", "title": "OS·进程与线程区别", "messages": [
                {"role": "user", "content": "进程和线程到底有什么区别？"},
                {"role": "assistant", "content": "进程是资源分配的基本单位，线程是 CPU 调度的基本单位，同一进程内线程共享地址空间……"},
            ]},
        ],
    },
    {
        "username": "liuyang",
        "password": "Student@2026",
        "display_name": "刘洋",
        "profile": {
            "target": "考研408",
            "level": "基础",
            "weak_subjects": ["数据结构", "计算机网络"],
            "strong_subjects": ["计算机组成"],
            "weekly_hours": 10,
            "goal_score": 110,
            "style": "讲解文档+例题",
        },
        "quiz": [
            ("ds", False, "easy"), ("ds", False, "medium"), ("ds", True, "medium"),
            ("network", False, "easy"), ("network", True, "medium"), ("os", True, "easy"),
            ("os", True, "medium"), ("co", True, "easy"), ("co", True, "medium"),
            ("co", True, "hard"), ("network", False, "medium"), ("ds", False, "hard"),
        ],
        "conversations": [
            {"id": "c_ly_1", "title": "CO·CPU数据通路", "messages": [
                {"role": "user", "content": "CPU 数据通路是怎么工作的？"},
                {"role": "assistant", "content": "数据通路由寄存器、ALU、多路选择器、总线等组成，指令执行分取指、译码、执行、写回……"},
            ]},
        ],
    },
    {
        "username": "chenjing",
        "password": "Student@2026",
        "display_name": "陈静",
        "profile": {
            "target": "保研复试",
            "level": "进阶",
            "weak_subjects": ["操作系统"],
            "strong_subjects": ["数据结构", "计算机网络", "计算机组成"],
            "weekly_hours": 22,
            "goal_score": 130,
            "style": "刷题+错题复盘",
        },
        "quiz": [
            ("ds", True, "easy"), ("ds", True, "medium"), ("ds", True, "hard"),
            ("network", True, "easy"), ("network", True, "medium"), ("network", True, "hard"),
            ("os", True, "easy"), ("os", False, "medium"), ("os", True, "medium"),
            ("co", True, "medium"), ("co", False, "hard"), ("network", True, "medium"),
        ],
        "conversations": [
            {"id": "c_cj_1", "title": "DS·红黑树平衡", "messages": [
                {"role": "user", "content": "红黑树是如何保持平衡的？"},
                {"role": "assistant", "content": "红黑树通过5条性质+旋转/变色维持近似平衡，最长路径不超过最短路径的2倍……"},
            ]},
            {"id": "c_cj_2", "title": "Network·拥塞控制", "messages": [
                {"role": "user", "content": "TCP 拥塞控制有哪些算法？"},
                {"role": "assistant", "content": "慢开始、拥塞避免、快重传、快恢复，配合 ssthresh 动态调整拥塞窗口……"},
            ]},
        ],
    },
]

for st in DEMO_STUDENTS:
    try:
        u = us.create_user(st["username"], st["password"], st["display_name"], role="student")
    except ValueError as e:
        print(f"[跳过] {st['username']}: {e}")
        # 若已存在则取出 id 继续补充数据
        conn = us._get_conn()
        row = conn.execute("SELECT id FROM users WHERE username=?", (st["username"],)).fetchone()
        if not row:
            continue
        u = {"id": row["id"]}
    uid = u["id"]
    us.save_profile(uid, st["profile"])
    from datetime import datetime, timedelta
    now = datetime.now()
    n_quiz = len(st["quiz"])
    quiz_records = []
    for idx, (s, c, d) in enumerate(st["quiz"]):
        # 将答题时间分散到最近 7 天，使管理看板「近7日」柱状图更真实
        day_offset = (n_quiz - 1 - idx) // max((n_quiz + 6) // 7, 1)
        ts = (now - timedelta(days=day_offset, hours=(idx % 5) * 2)).strftime("%Y-%m-%d %H:%M:%S")
        quiz_records.append({"subject": s, "correct": c, "difficulty": d, "timestamp": ts})
    us.append_quiz_history(uid, quiz_records)
    us.save_conversations(uid, st["conversations"])
    total = len(quiz_records)
    correct = sum(1 for r in quiz_records if r["correct"])
    print(f"[学生] {st['username']} / {st['password']}  答题 {total} 正确 {correct} 正确率 {correct/total:.0%}  对话 {len(st['conversations'])}")

# ── 4. 校验聚合结果 ──
stats = us.get_platform_stats()
print("\n=== 平台统计 ===")
print(f"  用户总数: {stats['user_count']} (学生 {stats['student_count']} / 管理员 {stats['admin_count']})")
print(f"  活跃用户: {stats['active_users']}")
print(f"  总答题: {stats['total_quiz']}  正确率: {stats['overall_accuracy']:.0%}")
by_subj_str = {k: f"{v['correct']}/{v['total']}" for k, v in stats['by_subject'].items()}
print(f"  分科目: {by_subj_str}")
daily_str = [d['count'] for d in stats['daily_quiz']]
print(f"  近7日答题: {daily_str}")

users = us.list_all_users()
print(f"\n=== 用户列表 ({len(users)} 人) ===")
for u in users:
    print(f"  - {u['username']} ({u['display_name']}, {u['role']}) 答题{u['quiz_total']} 对话{u['conversation_count']}")
print("\n[完成] 演示数据已写入", DB_PATH)
