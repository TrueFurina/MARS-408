# ============================================================
# WS1 覆盖率补全 — shared/sse_guard.py 与 shared/limits.py
#
# 此前二者在测试套件中零引用（grep shared.<mod> 无命中），属真实覆盖盲区：
#   - sse_guard.sse_disconnect_guard：客户端断开后提前终止 SSE 生成，避免空转烧 LLM 算力
#   - limits._env_int / 具名配额常量：边界常量被写坏（空串/非法/0/负）时必须保守回退
#
# 均为纯逻辑、无重依赖，可脱离 conftest 独立运行：
#   py-server/.venv/Scripts/python.exe -m pytest tests/test_shared_guard_limits.py --noconftest -q
# ================================================================

import asyncio


# ───────────────────────────── sse_guard ─────────────────────────────

async def _fake_agen(chunks):
    for c in chunks:
        yield c


async def _collect(request, chunks):
    from shared.sse_guard import sse_disconnect_guard

    out = []
    async for c in sse_disconnect_guard(request, _fake_agen(chunks)):
        out.append(c)
    return out


def _fake_request(seq):
    """is_disconnected 依次返回 seq 中的值（到尾后保持末值）。"""

    class FakeReq:
        def __init__(self, seq):
            self._seq = list(seq)
            self._i = 0

        async def is_disconnected(self):
            v = self._seq[min(self._i, len(self._seq) - 1)]
            self._i += 1
            return v

    return FakeReq(seq)


def test_sse_none_request_passthrough():
    chunks = [f"d{i}" for i in range(5)]
    out = asyncio.run(_collect(None, chunks))
    assert out == chunks


def test_sse_connected_yields_all():
    chunks = [f"d{i}" for i in range(25)]
    out = asyncio.run(_collect(_fake_request([False] * 30), chunks))
    assert out == chunks


def test_sse_disconnect_stops_early():
    chunks = [f"d{i}" for i in range(25)]
    # 第 1 次检测（count=10）即断连 → 仅前 9 块被 yield（第 10 块在检测后才 yield，故不产出）
    out = asyncio.run(_collect(_fake_request([True] * 30), chunks))
    assert out == chunks[:9]


def test_sse_disconnect_midstream():
    chunks = [f"d{i}" for i in range(30)]
    # count=10 检测连通（False），count=20 检测断连（True） → 前 19 块 yield
    out = asyncio.run(_collect(_fake_request([False, True]), chunks))
    assert out == chunks[:19]


def test_sse_disconnect_check_skips_within_window():
    # 不足一个检测周期（<10 块）时即便断连也不检测，全部产出（向后兼容低开销语义）
    chunks = [f"d{i}" for i in range(7)]
    out = asyncio.run(_collect(_fake_request([True] * 30), chunks))
    assert out == chunks


# ───────────────────────────── limits ─────────────────────────────

def test_env_int_default_when_unset(monkeypatch):
    from shared.limits import _env_int

    monkeypatch.delenv("RL_TEST_PROBE", raising=False)
    assert _env_int("RL_TEST_PROBE", 42) == 42


def test_env_int_parses_value(monkeypatch):
    from shared.limits import _env_int

    monkeypatch.setenv("RL_TEST_PROBE", "7")
    assert _env_int("RL_TEST_PROBE", 42) == 7


def test_env_int_empty_falls_back(monkeypatch):
    from shared.limits import _env_int

    monkeypatch.setenv("RL_TEST_PROBE", "   ")
    assert _env_int("RL_TEST_PROBE", 42) == 42


def test_env_int_noninteger_falls_back(monkeypatch):
    from shared.limits import _env_int

    monkeypatch.setenv("RL_TEST_PROBE", "abc")
    assert _env_int("RL_TEST_PROBE", 42) == 42


def test_env_int_zero_clamped(monkeypatch):
    from shared.limits import _env_int

    monkeypatch.setenv("RL_TEST_PROBE", "0")
    assert _env_int("RL_TEST_PROBE", 42, minimum=1) == 42


def test_env_int_negative_clamped(monkeypatch):
    from shared.limits import _env_int

    monkeypatch.setenv("RL_TEST_PROBE", "-5")
    assert _env_int("RL_TEST_PROBE", 42, minimum=1) == 42


def test_env_int_respects_minimum(monkeypatch):
    from shared.limits import _env_int

    monkeypatch.setenv("RL_TEST_PROBE", "3")
    assert _env_int("RL_TEST_PROBE", 42, minimum=2) == 3


def test_named_constants_are_positive_ints():
    import shared.limits as lim

    for name in lim.__all__:
        val = getattr(lim, name)
        assert isinstance(val, int), f"{name} 应为 int"
        assert val >= 1, f"{name}={val} 不应 <=0（否则全员 429）"
