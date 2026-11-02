# ============================================================
# Wave B 针对性运行时验证 — SRE 阻塞项（纯函数级 pytest）
# Author: Edward (QA Engineer)  |  team: software-residual-fixes
# ============================================================
# 隔离策略：同 Wave A/B 安全测试（禁止启动后端 / import main / 触发 E5 / pymilvus）。
#   - metrics.py / logging_config.py 仅用标准库 + fastapi，可直接独立加载，无需 db 桩。
#   - migrations/runner.py 顶层 `from db.pg_client import pg_client`，
#     故 stub db.pg_client 提供 pg_client 单例（is_enabled=False 默认）后再独立加载。
#   - 运行加 --noconftest。
# 覆盖：4) metrics.render_prometheus  5) logging_config.JSONFormatter
#       6) migrations.runner.run_migrations（无 DB 跳过 + SQL 执行/幂等）
# ============================================================

import os
import sys
import types
import json
import logging
import importlib.util

_PY_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PY_SERVER not in sys.path:
    sys.path.insert(0, _PY_SERVER)


# ── 隔离桩：仅 stub db.pg_client 子模块（runner.py 顶层 import）──
# 关键：父包 db 始终真实，故同会话其它测试 import db.llm_provider / db.redis_client
# 不受影响；只桩 pg_client 子模块后再独立加载 runner，加载完即还原，零污染。
_ORIG_SUB = {}


def _stub_sub(name, mod):
    if name not in _ORIG_SUB:
        _ORIG_SUB[name] = sys.modules.get(name)
    sys.modules[name] = mod


_db_pg = types.ModuleType("db.pg_client")


class _PgDisabled:
    """桩：数据库未启用（is_enabled=False）。"""
    is_enabled = False


_db_pg.pg_client = _PgDisabled()
_stub_sub("db.pg_client", _db_pg)


def _load_standalone(module_name: str, rel_path: str):
    """按文件直接加载模块，绕过 api 包的 __init__ 重型依赖链。"""
    full = os.path.join(_PY_SERVER, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, full)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


metrics = _load_standalone("waveb_metrics", "shared/metrics.py")
logging_config = _load_standalone("waveb_logging_config", "shared/logging_config.py")
runner = _load_standalone("waveb_runner", "db/migrations/runner.py")

# ── 还原 pg_client 子模块桩（父包 db 始终真实，metrics/logging_config/runner 已独立名缓存）──
for _n, _orig in _ORIG_SUB.items():
    if _orig is None:
        sys.modules.pop(_n, None)
    else:
        sys.modules[_n] = _orig


# ============================================================
# 4) metrics.render_prometheus — D5 /metrics 文本格式
# ============================================================

def _reset_metrics():
    metrics._request_total.clear()
    metrics._request_errors.clear()
    metrics._latency_sum.clear()
    metrics._latency_count.clear()
    metrics._hist.clear()
    metrics._in_flight = 0


class TestPrometheusRender:
    def test_output_is_text_and_has_key_metrics(self):
        _reset_metrics()
        metrics.record_request("/api/test", 200, 0.05)
        out = metrics.render_prometheus()
        assert isinstance(out, str)
        assert "http_requests_total" in out
        assert "http_requests_in_flight" in out
        assert "http_request_errors_total" in out
        assert "http_request_duration_seconds" in out

    def test_counter_and_gauge_format(self):
        _reset_metrics()
        metrics.record_request("/x", 200, 0.1)
        metrics.record_request("/x", 200, 0.3)
        metrics.inc_inflight(2)
        out = metrics.render_prometheus()
        lines = out.strip().splitlines()
        # 计数器行格式：metric{labels} value
        total_lines = [l for l in lines if l.startswith("http_requests_total{")]
        assert any('path="/x"' in l and l.rstrip().endswith(" 2") for l in total_lines)
        assert "http_requests_in_flight 2" in out
        # 耗时累加行存在
        assert "http_request_duration_seconds_sum" in out
        assert "http_request_duration_seconds_count" in out

    def test_5xx_recorded_as_errors(self):
        _reset_metrics()
        metrics.record_request("/err", 500, 0.2)
        out = metrics.render_prometheus()
        assert 'http_request_errors_total{path="/err"} 1' in out

    def test_in_flight_never_negative(self):
        _reset_metrics()
        metrics.inc_inflight(-5)
        assert metrics._in_flight == 0
        out = metrics.render_prometheus()
        assert "http_requests_in_flight 0" in out

    def test_percentile_estimate_present_and_sane(self):
        _reset_metrics()
        for _ in range(90):
            metrics.record_request("/api/x", 200, 0.1)
        for _ in range(9):
            metrics.record_request("/api/x", 200, 1.0)
        metrics.record_request("/api/x", 200, 5.0)
        out = metrics.render_prometheus()
        p95 = [l for l in out.splitlines()
               if l.startswith('http_request_duration_seconds_p95{path="/api/x"}')]
        p99 = [l for l in out.splitlines()
               if l.startswith('http_request_duration_seconds_p99{path="/api/x"}')]
        assert p95 and p99, "必须暴露 p95/p99 分位数"
        p95_val = float(p95[0].split()[-1])
        p99_val = float(p99[0].split()[-1])

        # 断言**精度**而非算法快照（旧写法钉死 p99==1.0，改分桶就失配，
        # 且锁的是实现行为而不是「算得准不准」）。真值直接由样本求。
        samples = sorted([0.1] * 90 + [1.0] * 9 + [5.0])

        import math as _math

        def _truth(q: float) -> float:
            # nearest-rank：与估算器 target=q*total 的语义一致（第 ceil(qn) 个样本）
            rank = max(1, _math.ceil(q * len(samples)))
            return samples[rank - 1]

        for name, est, q in (("p95", p95_val, 0.95), ("p99", p99_val, 0.99)):
            true = _truth(q)
            err = abs(est - true) / true
            assert err <= 0.15, f"{name} 偏差 {err * 100:.1f}% 超 15%：est={est} true={true}"

    def test_percentile_accuracy_on_skewed_distribution(self):
        """偏态分布下 p99 偏差须 ≤10% —— 旧分桶实测 +43%，本用例是它的回归护栏。"""
        import math
        import random as _random

        _reset_metrics()
        rng = _random.Random(42)
        vals = [max(0.001, rng.lognormvariate(math.log(0.2), 0.8)) for _ in range(20000)]
        for v in vals:
            metrics.record_request("/api/skew", 200, v)

        out = metrics.render_prometheus()
        line = [
            l
            for l in out.splitlines()
            if l.startswith('http_request_duration_seconds_p99{path="/api/skew"}')
        ]
        assert line, "偏态分布路径也必须暴露 p99"
        est = float(line[0].split()[-1])

        ordered = sorted(vals)
        true = ordered[max(1, math.ceil(0.99 * len(ordered))) - 1]
        err = abs(est - true) / true
        assert err <= 0.10, (
            f"p99 偏差 {err * 100:.1f}% 超 10%（est={est:.3f}s true={true:.3f}s）"
            "—— 检查 _LATENCY_BUCKETS 是否又被放稀"
        )

    def test_percentile_skips_inf_tail(self):
        _reset_metrics()
        for _ in range(10):
            metrics.record_request("/api/slow", 200, 40.0)  # 全落 +Inf 桶(>30s)
        out = metrics.render_prometheus()
        assert 'http_request_duration_seconds_p95{path="/api/slow"}' not in out
        assert 'http_request_duration_seconds_p99{path="/api/slow"}' not in out


# ============================================================
# 5) logging_config.JSONFormatter — D11 结构化日志
# ============================================================

class TestJSONFormatter:
    def test_format_contains_required_keys(self):
        fmt = logging_config.JSONFormatter()
        record = logging.LogRecord(
            name="netlearn.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        s = fmt.format(record)
        data = json.loads(s)  # 必须是合法 JSON
        assert "ts" in data
        assert data["level"] == "INFO"
        assert data["logger"] == "netlearn.test"
        assert data["msg"] == "hello world"

    def test_exc_info_included(self):
        fmt = logging_config.JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys as _sys
            exc = _sys.exc_info()
        record = logging.LogRecord(
            name="netlearn.err",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=exc,
        )
        data = json.loads(fmt.format(record))
        assert "exc" in data
        assert "boom" in data["exc"]


# ============================================================
# 6) migrations.runner.run_migrations — D6 幂等 + 无 DB 跳过
# ============================================================

class TestRunMigrations:
    def test_no_db_skips_silently(self):
        # pg_client.is_enabled=False（桩默认）-> 直接返回 0，不抛异常
        assert runner.run_migrations() == 0

    def test_executes_sql_and_records_version(self, monkeypatch, tmp_path):
        vers = tmp_path / "versions"
        vers.mkdir()
        (vers / "0001_init_metrics.sql").write_text(
            "CREATE TABLE IF NOT EXISTS metrics (id INT);", encoding="utf-8"
        )
        monkeypatch.setattr(runner, "_VERSIONS_DIR", str(vers))
        monkeypatch.setattr(runner, "_APPLIED_FILE", str(vers / "applied.json"))

        executed = []

        class FakePg:
            is_enabled = True
            _conn = None

            def migrate_exec(self, sql):
                executed.append(sql)

        monkeypatch.setattr(runner, "pg_client", FakePg())

        n = runner.run_migrations()
        assert n == 1
        assert executed and "CREATE TABLE" in executed[0]

        data = json.loads((vers / "applied.json").read_text(encoding="utf-8"))
        assert "0001" in data["versions"]

    def test_idempotent_second_run_applies_nothing(self, monkeypatch, tmp_path):
        vers = tmp_path / "versions"
        vers.mkdir()
        (vers / "0002_seed.sql").write_text(
            "CREATE TABLE IF NOT EXISTS seed (id INT);", encoding="utf-8"
        )
        monkeypatch.setattr(runner, "_VERSIONS_DIR", str(vers))
        monkeypatch.setattr(runner, "_APPLIED_FILE", str(vers / "applied.json"))

        class FakePg:
            is_enabled = True
            _conn = None

            def migrate_exec(self, sql):
                pass

        monkeypatch.setattr(runner, "pg_client", FakePg())

        assert runner.run_migrations() == 1   # 首次应用 1 个
        assert runner.run_migrations() == 0   # 已记录 -> 幂等跳过
