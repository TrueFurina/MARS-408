"""静默降级可观测性回归 —— 配置加载与状态端点不得无声吞错。

背景：本项目曾因「静默回退」引发 P0 数据事故（向量库空载却照常启动）。
因此「失败降级」本身可以接受，但**必须留下可审计的信号**。

本文件锁死三处加固（scripts/harden_silent_config_load.py）：
  1. config.json 解析失败  -> 必须 WARNING（否则静默回退 DEFAULTS，凭据/模型配置为空）
  2. .env 解析失败          -> 必须 WARNING（否则凭据静默缺失）
  3. /api/status/competition 用户数查询失败 -> 必须 WARNING（状态端点不得无声报告 0）

变异验证（已执行）：移除任一 logger.warning，对应断言 FAIL。
"""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import contextmanager
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod  # noqa: E402


@contextmanager
def capture_logs(logger_name: str):
    """独立于 propagate 设置的日志捕获（不依赖 caplog 的 root handler）。"""
    records: list[logging.LogRecord] = []

    class _Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - 简单转发
            records.append(record)

    target = logging.getLogger(logger_name)
    sink = _Sink(level=logging.DEBUG)
    old_level = target.level
    old_disabled = target.disabled
    manager = logging.root.manager
    old_global_disable = manager.disable  # logging.disable() 的全局开关
    target.addHandler(sink)
    target.setLevel(logging.DEBUG)
    # 防御性：若有模块调用过 logging.disable() 或禁用了该 logger，
    # 记录会在到达 handler 之前被丢弃，这里临时复位以保证捕获可靠。
    target.disabled = False
    manager.disable = logging.NOTSET
    try:
        yield records
    finally:
        manager.disable = old_global_disable
        target.disabled = old_disabled
        target.removeHandler(sink)
        target.setLevel(old_level)


def _reset_config_cache() -> None:
    config_mod.reload_config()


# ── 1. config.json 解析失败 ─────────────────────────────────────────────────

def test_malformed_config_json_warns_and_still_falls_back(tmp_path, monkeypatch):
    """解析失败必须 fail-open（返回可用配置）*且*留下 WARNING。"""
    bad = tmp_path / "config.json"
    bad.write_text("{ this is not valid json at all", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", bad)

    try:
        with capture_logs("netlearn.config") as records:
            cfg = config_mod.reload_config()

        assert isinstance(cfg, dict) and cfg, "解析失败仍须返回可用配置（fail-open 不变）"
        messages = [r.getMessage() for r in records]
        assert any("config.json 解析失败" in m for m in messages), (
            f"config.json 解析失败必须留下 WARNING；实际日志={messages!r}"
        )
    finally:
        monkeypatch.undo()
        _reset_config_cache()  # 用真实 CONFIG_PATH 重建缓存，避免污染其它用例


# ── 2. .env 解析失败 ───────────────────────────────────────────────────────

def test_malformed_dotenv_warns(tmp_path, monkeypatch):
    bad_env = tmp_path / ".env"
    bad_env.write_bytes(b"\xff\xfe\x00not-valid-utf8")
    monkeypatch.setattr(config_mod, "ENV_PATH", bad_env)

    try:
        with capture_logs("netlearn.config") as records:
            config_mod._load_dotenv()

        messages = [r.getMessage() for r in records]
        assert any(".env 解析失败" in m for m in messages), (
            f".env 解析失败必须留下 WARNING；实际日志={messages!r}"
        )
    finally:
        monkeypatch.undo()


# ── 3. 状态端点不得无声报告 0 ───────────────────────────────────────────────

def test_competition_status_warns_on_db_error(monkeypatch):
    import db.user_store as user_store
    from main import competition_status

    def _boom():
        raise RuntimeError("simulated sqlite failure")

    monkeypatch.setattr(user_store, "get_db_conn", _boom)

    with capture_logs("netlearn") as records:
        result = asyncio.run(competition_status())

    assert result["stats"]["user_count"] == 0, "降级后仍返回 0（保持原行为）"
    messages = [r.getMessage() for r in records]
    assert any("读取用户总数失败" in m for m in messages), (
        f"状态端点查询失败必须留下 WARNING，不能无声报告 0；实际日志={messages!r}"
    )
