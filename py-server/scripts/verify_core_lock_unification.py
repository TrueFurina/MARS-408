# py-server/scripts/verify_core_lock_unification.py
# 架构评审 M-5（存储锁域统一）的可机验守门脚本。
#
# 为什么独立成脚本：本机 venv 缺 numpy，`import db.pg_client` 会被 db/__init__
# → milvus_client 拖垮。这里用 stub 包绕开 db/__init__，只加载 db/core.py 与
# db/pg_client.py，无需任何第三方依赖即可实证「连接/锁是否真由 db.core 发放」。
#
# 运行：
#   cd py-server && python scripts/verify_core_lock_unification.py
# 退出码：0=全部通过，1=存在失败项。
# 直接加载 db/core.py 与 db/pg_client.py，实证：
#   1. 多次 connect() 返回同一连接 + 同一把锁（修复前是每调用一次新建一套）
#   2. 连接/锁确实来自 db.core 注册表
#   3. 合规访问器可用；多线程并发写不再出现 "database is locked"
#   4. disconnect() 能注销并重连

import importlib.util
import os
import shutil
import sys
import tempfile
import threading
import types

ROOT = r"E:\Program\MARL\study-help-pro\py-server"
DB_DIR = os.path.join(ROOT, "db")

pkg = types.ModuleType("db")
pkg.__path__ = [DB_DIR]
sys.modules["db"] = pkg
cfg = types.ModuleType("config")
cfg.get_pg_config = lambda: {"enabled": False}
sys.modules["config"] = cfg


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


core = load("db.core", os.path.join(DB_DIR, "core.py"))
pg = load("db.pg_client", os.path.join(DB_DIR, "pg_client.py"))

tmpdir = tempfile.mkdtemp(prefix="m5_verify_")
tmpdb = os.path.join(tmpdir, "pg_fallback.db")
pg._FALLBACK_DIR = tmpdir
pg._FALLBACK_DB = tmpdb

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {extra}")


try:
    c1 = pg.PgClient()
    c2 = pg.PgClient()
    check("c1.connect() 回退成功", c1.connect() and c1.is_fallback)
    check("c2.connect() 再次调用", c2.connect())

    check("两个 client 共用同一连接", c1._conn is c2._conn)
    check("两个 client 共用同一把锁", c1._lock is c2._lock)
    check("连接来自 db.core 注册表", core._conns.get(tmpdb) is c1._conn)
    check("锁来自 db.core 按文件发放", c1._lock is core.get_lock_for(tmpdb))

    tables = {
        r[0]
        for r in c1.sqlite_execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    check(
        "新建连接时 init 回调已建表",
        {"agent_performance", "student_profiles", "student_behavior_events"} <= tables,
        sorted(tables),
    )

    c1.sqlite_execute(
        "INSERT INTO agent_performance (agent_name,score) VALUES (?,?)", ("probe", 1.0), commit=True
    )
    row = c2.sqlite_query_one("SELECT agent_name, score FROM agent_performance WHERE agent_name=?", ("probe",))
    check("合规访问器跨 client 可见写入", row is not None and dict(row)["score"] == 1.0, dict(row or {}))

    errs = []


    def worker(idx, client):
        try:
            for _ in range(50):
                client.sqlite_execute(
                    "INSERT INTO student_behavior_events (user_id,event_type) VALUES (?,?)",
                    (f"u{idx}", "click"),
                    commit=True,
                )
        except Exception as exc:  # noqa: BLE001
            errs.append(repr(exc))


    threads = [threading.Thread(target=worker, args=(i, c1 if i % 2 else c2)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = c1.sqlite_query_one("SELECT COUNT(*) AS c FROM student_behavior_events")[0]
    check("并发写零异常", not errs, errs[:2])
    check("并发写全部落库", total == 400, f"rows={total}")

    c1.disconnect()
    check("disconnect 已注销共享连接", core._conns.get(tmpdb) is None)
    check("disconnect 后 _enabled=False", not c1.is_enabled and c1._conn is None)
    check("重连成功", c1.connect() and c1.is_fallback)
    c1.sqlite_execute(
        "INSERT INTO agent_performance (agent_name,score) VALUES (?,?)", ("probe2", 2.0), commit=True
    )
    check(
        "重连后可正常写入",
        c1.sqlite_query_one("SELECT score FROM agent_performance WHERE agent_name=?", ("probe2",))[0] == 2.0,
    )
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURE")
sys.exit(0 if ok else 1)
