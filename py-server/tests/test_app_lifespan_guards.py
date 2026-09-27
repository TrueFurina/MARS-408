# -*- coding: utf-8 -*-
"""app/lifespan.py 守卫与降级分支单测（M-4 拆分后新增，此前仅 57% 覆盖）

覆盖重点不是行数，而是这些**出事才有用**的分支：
  - ADR-007 单写者硬约束（workers>1 必须拒绝启动）
  - 生产环境管理员口令校验（缺失/过短必须 fail-fast）
  - PG / Redis 连接超时与失败的降级（不得阻塞启动）
  - 生产环境跳过演示账户播种
  - 会话产物生命周期清理（>7 天）
  - lifespan 启动→关闭完整周期（含连接释放）
全部用替身注入，不触碰真实数据库 / 不写真实 sessions 目录。
"""

import asyncio
import os
import sys
import time

import pytest

import app.lifespan as L


async def _noop(*args, **kwargs):
    return None


class TestSingleWorkerGuard:
    """ADR-007：后端必须单写者，workers>1 直接拒绝启动。"""

    def test_default_single_worker_passes(self, monkeypatch):
        monkeypatch.delenv("UVICORN_WORKERS", raising=False)
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.setattr(sys, "argv", ["main.py"])
        L._assert_single_worker()

    def test_env_workers_gt_one_raises(self, monkeypatch):
        monkeypatch.setenv("UVICORN_WORKERS", "2")
        monkeypatch.setattr(sys, "argv", ["main.py"])
        with pytest.raises(RuntimeError, match="ADR-007"):
            L._assert_single_worker()

    def test_web_concurrency_env_also_checked(self, monkeypatch):
        monkeypatch.delenv("UVICORN_WORKERS", raising=False)
        monkeypatch.setenv("WEB_CONCURRENCY", "4")
        monkeypatch.setattr(sys, "argv", ["main.py"])
        with pytest.raises(RuntimeError, match="ADR-007"):
            L._assert_single_worker()

    def test_cli_workers_gt_one_raises(self, monkeypatch):
        monkeypatch.delenv("UVICORN_WORKERS", raising=False)
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.setattr(sys, "argv", ["main.py", "--workers", "4"])
        with pytest.raises(RuntimeError, match="workers数量=4"):
            L._assert_single_worker()

    def test_cli_workers_non_integer_falls_back_to_default(self, monkeypatch):
        monkeypatch.delenv("UVICORN_WORKERS", raising=False)
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.setattr(sys, "argv", ["main.py", "--workers", "abc"])
        L._assert_single_worker()

    def test_cli_workers_one_passes(self, monkeypatch):
        monkeypatch.delenv("UVICORN_WORKERS", raising=False)
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.setattr(sys, "argv", ["main.py", "--workers", "1"])
        L._assert_single_worker()


class TestInitAdmin:
    """F-004：生产环境口令必须显式且足够强。"""

    async def test_production_without_password_fails_fast(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "production")
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            await L._init_admin()

    async def test_production_short_password_fails_fast(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "production")
        monkeypatch.setenv("ADMIN_PASSWORD", "short-pwd")
        with pytest.raises(RuntimeError, match="长度必须"):
            await L._init_admin()

    async def test_production_strong_password_calls_ensure_admin(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "production")
        monkeypatch.setenv("ADMIN_PASSWORD", "x" * 20)
        import services.user_service as us
        seen = {}
        monkeypatch.setattr(us, "ensure_admin", lambda u, p, **k: seen.update(u=u, p=p))
        await L._init_admin()
        assert seen["p"] == "x" * 20

    async def test_development_generates_random_password(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "development")
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        import services.user_service as us
        seen = {}
        monkeypatch.setattr(us, "ensure_admin", lambda u, p, **k: seen.update(p=p))
        await L._init_admin()
        assert len(seen["p"]) >= 16, "临时口令必须足够长"

    async def test_ensure_admin_failure_is_non_blocking(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "development")
        monkeypatch.setenv("ADMIN_PASSWORD", "y" * 20)
        import services.user_service as us

        def boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(us, "ensure_admin", boom)
        await L._init_admin()


class TestComponentDegradation:
    """PG / Redis 不可用时必须降级，不得阻塞启动。"""

    async def test_pg_timeout_marks_disabled(self, monkeypatch):
        async def fake_wait_for(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError()

        monkeypatch.setattr(L.asyncio, "wait_for", fake_wait_for)
        await L._init_pg()
        assert L.pg_client._enabled is False

    async def test_pg_exception_is_swallowed(self, monkeypatch):
        def boom():
            raise RuntimeError("no pg")

        monkeypatch.setattr(L.pg_client, "connect", boom)
        await L._init_pg()

    async def test_redis_timeout_marks_disabled(self, monkeypatch):
        async def fake_wait_for(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError()

        monkeypatch.setattr(L.asyncio, "wait_for", fake_wait_for)
        await L._init_redis()
        assert L.redis_client._enabled is False

    async def test_redis_not_enabled_is_tolerated(self, monkeypatch):
        monkeypatch.setattr(L.redis_client, "connect", lambda: False)
        await L._init_redis()

    async def test_redis_exception_is_swallowed(self, monkeypatch):
        def boom():
            raise RuntimeError("no redis")

        monkeypatch.setattr(L.redis_client, "connect", boom)
        await L._init_redis()

    async def test_migrations_failure_does_not_block_startup(self, monkeypatch):
        import db.migrations as migrations

        def boom():
            raise RuntimeError("migration exploded")

        monkeypatch.setattr(migrations, "run_migrations", boom)
        await L._run_migrations()

    async def test_migrations_success_path(self, monkeypatch):
        import db.migrations as migrations
        monkeypatch.setattr(migrations, "run_migrations", lambda: 2)
        await L._run_migrations()


class TestSeedAndCredentialChecks:
    async def test_demo_seed_skipped_in_production(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "production")
        import services.user_service as us
        called = {"n": 0}
        monkeypatch.setattr(us, "authenticate", lambda *a, **k: called.update(n=1))
        await L._seed_demo_data()
        assert called["n"] == 0, "生产环境不得触碰演示账户"

    async def test_demo_seed_failure_is_non_blocking(self, monkeypatch):
        monkeypatch.setenv("NETLEARN_ENV", "development")
        import services.user_service as us

        def boom(*a, **k):
            raise RuntimeError("seed exploded")

        monkeypatch.setattr(us, "authenticate", boom)
        await L._seed_demo_data()

    async def test_llm_credentials_absent_logs_guidance(self, monkeypatch, caplog):
        import config
        monkeypatch.setattr(config, "load_config", lambda: {})
        with caplog.at_level("WARNING"):
            await L._check_llm_credentials()
        assert any("demo 模式" in r.message for r in caplog.records)

    async def test_llm_credentials_present_stays_quiet(self, monkeypatch, caplog):
        import config
        monkeypatch.setattr(
            config, "load_config", lambda: {"deepseek": {"api_key": "sk-x"}}
        )
        with caplog.at_level("WARNING"):
            await L._check_llm_credentials()
        assert not [r for r in caplog.records if "demo 模式" in r.message]

    async def test_llm_credential_check_failure_is_non_blocking(self, monkeypatch):
        import config

        def boom():
            raise RuntimeError("config broken")

        monkeypatch.setattr(config, "load_config", boom)
        await L._check_llm_credentials()


class TestArtifactLifecycleLoop:
    """会话产物生命周期：>7 天清理；同时跑一次 L3 记忆清理。"""

    async def test_sweep_removes_expired_files_and_empty_dirs(self, monkeypatch, tmp_path):
        fake_app_dir = tmp_path / "app"
        fake_app_dir.mkdir()
        monkeypatch.setattr(L, "__file__", str(fake_app_dir / "lifespan.py"))

        user_dir = tmp_path / "sessions" / "u1"
        user_dir.mkdir(parents=True)
        expired = user_dir / "old.png"
        expired.write_bytes(b"x")
        fresh = user_dir / "new.png"
        fresh.write_bytes(b"y")
        stale_ts = time.time() - 8 * 86400
        os.utime(expired, (stale_ts, stale_ts))

        empty_dir = tmp_path / "sessions" / "u2"
        empty_dir.mkdir()

        import db.memory_store as memory_store
        monkeypatch.setattr(memory_store, "prune_episodes", lambda retention_days=90: 3)

        calls = {"n": 0}

        async def fake_sleep(_seconds):
            calls["n"] += 1
            if calls["n"] > 1:
                raise asyncio.CancelledError()

        monkeypatch.setattr(L.asyncio, "sleep", fake_sleep)
        with pytest.raises(asyncio.CancelledError):
            await L._artifact_lifecycle_loop()

        assert not expired.exists(), ">7 天的文件应被清理"
        assert fresh.exists(), "未过期文件必须保留"
        assert not empty_dir.exists(), "空用户目录应被回收"

    async def test_sweep_survives_missing_sessions_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(L, "__file__", str(tmp_path / "app" / "lifespan.py"))

        async def fake_sleep(_seconds):
            raise asyncio.CancelledError()

        monkeypatch.setattr(L.asyncio, "sleep", fake_sleep)
        with pytest.raises(asyncio.CancelledError):
            await L._artifact_lifecycle_loop()


class TestLifespanFullCycle:
    """启动 → yield → 关闭全流程（外部依赖全部替身化，不连真实服务）。"""

    async def _stub_everything(self, monkeypatch):
        import shared.auth as auth
        monkeypatch.setattr(auth, "resolve_auth_secret", lambda: "s" * 40)

        monkeypatch.setattr(L.vector_db, "connect", lambda: True)
        monkeypatch.setattr(L.vector_db, "count", lambda name: 999)  # >=500 → 不触发教材导入
        # 注意：disconnect 是**同步**方法，替身必须同步，否则会留下未 await 的 coroutine
        monkeypatch.setattr(L.vector_db, "disconnect", lambda: None)
        monkeypatch.setattr(L.pg_client, "disconnect", lambda: None)
        monkeypatch.setattr(L.redis_client, "disconnect", lambda: None)

        for name in (
            "_init_pg", "_init_redis", "_init_admin",
            "_run_migrations", "_seed_demo_data", "_check_llm_credentials",
            "_artifact_lifecycle_loop",
        ):
            monkeypatch.setattr(L, name, _noop)
        monkeypatch.setattr(L, "_assert_single_worker", lambda: None)

        import services.import_worker as iw
        monkeypatch.setattr(iw.import_worker, "start", _noop)
        monkeypatch.setattr(iw.import_worker, "stop", _noop)

        import db.llm_provider as llm_provider
        monkeypatch.setattr(llm_provider, "_close_http_clients", _noop)

    async def test_full_cycle_without_textbook_import(self, monkeypatch):
        await self._stub_everything(monkeypatch)
        async with L.lifespan(app=None):
            pass

    async def test_full_cycle_triggers_textbook_import_when_kb_small(self, monkeypatch):
        await self._stub_everything(monkeypatch)
        monkeypatch.setattr(L.vector_db, "count", lambda name: 10)  # <500 → 需要补教材
        submitted = {}

        async def fake_submit(kind, user, payload):
            submitted["kind"] = kind
            return "job-1"

        import services.import_worker as iw
        monkeypatch.setattr(iw.import_worker, "submit", fake_submit)

        async with L.lifespan(app=None):
            pass
        assert submitted.get("kind") == "textbook"

    async def test_textbook_import_submit_failure_is_non_blocking(self, monkeypatch):
        await self._stub_everything(monkeypatch)
        monkeypatch.setattr(L.vector_db, "count", lambda name: 10)

        async def boom(kind, user, payload):
            raise RuntimeError("queue down")

        import services.import_worker as iw
        monkeypatch.setattr(iw.import_worker, "submit", boom)
        async with L.lifespan(app=None):
            pass

    async def test_auth_secret_failure_prevents_startup(self, monkeypatch):
        await self._stub_everything(monkeypatch)
        import shared.auth as auth

        def boom():
            raise RuntimeError("AUTH_SECRET 缺失")

        monkeypatch.setattr(auth, "resolve_auth_secret", boom)
        with pytest.raises(RuntimeError, match="AUTH_SECRET"):
            async with L.lifespan(app=None):
                pass

    async def test_empty_vector_db_triggers_seed(self, monkeypatch):
        await self._stub_everything(monkeypatch)
        counts = {"n": 0}

        def fake_count(name):
            counts["n"] += 1
            return 0 if counts["n"] == 1 else 1892

        monkeypatch.setattr(L.vector_db, "count", fake_count)
        seeded = {"called": False}
        monkeypatch.setattr(L, "_seed_vector_db", lambda: seeded.update(called=True))

        async with L.lifespan(app=None):
            pass
        assert seeded["called"] is True
