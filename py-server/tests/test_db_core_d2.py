"""D2 回归测试：共享 SQLite 连接与锁（消除跨 store 并发写 database is locked）。

验证：
1. user_store 与 skill_store 复用**同一连接对象**与**同一把锁**（D2 核心修复）。
2. 多线程分别通过两个 store 并发写同一 netlearn_users.db，不抛 database is locked。
"""
import threading

import pytest

import db.core as core
import db.user_store as us
import db.skill_store as ss


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """把 core 的连接重定向到临时库，测试结束还原，避免污染真实 data/ 与跨测试串扰。"""
    orig_path = core.DB_PATH
    orig_conn = core._conn
    orig_us_init = us._initialized
    orig_ss_init = ss._initialized
    new_db = str(tmp_path / "netlearn_users.db")
    monkeypatch.setattr(core, "DB_PATH", new_db)
    core._conn = None
    us._initialized = False
    ss._initialized = False
    yield new_db
    core.DB_PATH = orig_path
    core._conn = orig_conn
    us._initialized = orig_us_init
    ss._initialized = orig_ss_init


def test_d2_shared_connection_and_lock(temp_db):
    """两 store 必须复用同一连接对象与同一把锁——否则并发写不互斥。"""
    assert us._get_conn() is ss._get_conn(), "D2 失败：user_store 与 skill_store 未共享同一连接"
    assert us._lock is ss._lock, "D2 失败：user_store 与 skill_store 未共享同一把锁"


def test_d2_concurrent_cross_store_writes_no_locked(temp_db):
    """30 个线程交替通过两 store 写同一库，断言无 database is locked / WAL 损坏。"""
    errors = []

    def worker(i: int):
        try:
            with us._lock:
                c1 = us._get_conn()
                c1.execute("CREATE TABLE IF NOT EXISTS tu(id INTEGER)")
                c1.execute("INSERT INTO tu VALUES (?)", (i,))
                c1.commit()
            with ss._lock:
                c2 = ss._get_conn()
                c2.execute("CREATE TABLE IF NOT EXISTS ts(id INTEGER)")
                c2.execute("INSERT INTO ts VALUES (?)", (i,))
                c2.commit()
        except Exception as e:  # noqa: BLE001 - 收集异常用于断言
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发跨 store 写异常（可能 database is locked）: {errors[:3]}"
