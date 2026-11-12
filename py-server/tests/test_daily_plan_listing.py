"""daily plan 列表读取的回归测试（此前该路径零覆盖）。

锁两件事：
1. **功能**：`list_daily_plans` 返回的字段投影完整（含 tasks 反序列化与完成率计算）。
2. **N+1 不回归**：无论有多少条计划，整个调用**只允许 1 条 SQL**。

第 2 点是本文件的重点。原实现先 `SELECT id ...` 再对每一行 `SELECT * ... WHERE id=?`
回查：limit=30 时单次调用会多打 30 条 SQL，且逐条回查跑在 `_lock` 之外
（共享连接下存在并发隐患）。修复后合并为一次 `SELECT *`。
若有人把实现改回"先取 id 再回查"，本测试会立即失败。
"""
import db.core as core
import db.user_store as us


def _isolate(tmp_path, monkeypatch):
    """把 core 的连接重定向到临时库，避免污染 data/ 与跨测试串扰。"""
    orig_path = core.DB_PATH
    orig_conn = core._conn
    orig_init = us._initialized
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "netlearn_users.db"))
    core._conn = None
    us._initialized = False
    return orig_path, orig_conn, orig_init


def _restore(state):
    orig_path, orig_conn, orig_init = state
    core.DB_PATH = orig_path
    core._conn = orig_conn
    us._initialized = orig_init


class _CountingConn:
    """连接代理：统计 execute 次数，其余属性透传。"""

    def __init__(self, conn, counter):
        self._conn = conn
        self._counter = counter

    def execute(self, sql, *args, **kwargs):
        self._counter["n"] += 1
        return self._conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_list_daily_plans_returns_full_projection(tmp_path, monkeypatch):
    state = _isolate(tmp_path, monkeypatch)
    try:
        uid = us.create_user("dp_user", "Passw0rd!2026", "计划用户", role="student")["id"]
        dates = ["2026-11-01", "2026-11-02", "2026-11-03"]
        for d in dates:
            us.get_or_create_daily_plan(uid, plan_date=d)

        rows = us.list_daily_plans(uid, limit=30)

        assert len(rows) == len(dates)
        # 按 plan_date DESC 排序
        assert [r["plan_date"] for r in rows] == list(reversed(dates))
        for r in rows:
            assert set(r) == {
                "id",
                "plan_date",
                "tasks",
                "total_tasks",
                "completed_tasks",
                "completion_rate",
                "target_exam_date",
                "target_score",
            }
            assert isinstance(r["tasks"], list)
            # 完成率口径：completed/total*100，保留 1 位；total=0 时为 0
            expected = (
                round(r["completed_tasks"] / r["total_tasks"] * 100, 1)
                if r["total_tasks"] > 0
                else 0
            )
            assert r["completion_rate"] == expected
    finally:
        _restore(state)


def test_list_daily_plans_issues_single_query(tmp_path, monkeypatch):
    """N+1 回归锁：N 条计划也只能打 1 条 SQL。"""
    state = _isolate(tmp_path, monkeypatch)
    try:
        uid = us.create_user("dp_user2", "Passw0rd!2026", "计划用户2", role="student")["id"]
        for d in ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]:
            us.get_or_create_daily_plan(uid, plan_date=d)

        counter = {"n": 0}
        real_get = us._get_conn
        monkeypatch.setattr(us, "_get_conn", lambda: _CountingConn(real_get(), counter))

        rows = us.list_daily_plans(uid, limit=30)

        assert len(rows) == 4
        assert counter["n"] == 1, (
            f"list_daily_plans 对 {len(rows)} 条计划执行了 {counter['n']} 条 SQL，"
            "应为 1 条 —— 疑似 N+1 回查被改回来了（先 SELECT id 再逐条 SELECT *）"
        )
    finally:
        _restore(state)
