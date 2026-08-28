# ============================================================
# Wave A 针对性运行时验证 — 纯函数级 pytest
# Author: Edward (QA Engineer)  |  team: software-residual-fixes
# ============================================================
# 隔离策略（严格遵守沙箱约束：禁止启动后端 / import main / 触发 E5 / pymilvus）：
#   1) 用 importlib.util 按文件「独立加载」目标模块，绕过 api/__init__.py 的重型依赖链
#      （api.agents / api.multimodal / api.engine 等会拉入 torch/langgraph）。
#   2) stub 掉 db 包：config_routes 顶层 `from db.llm_provider import LLMProvider`
#      会触发 db/__init__.py -> db.milvus_client -> pymilvus（Windows 原生库 SIGSEGV）。
#      _mask_key 本身只用 LLMProvider 作为类型引用，用桩替代即可，永不实例化。
#   3) 运行加 --noconftest，避免 conftest 的 mock_auth autouse fixture 去 import main。
# 覆盖：1) _mask_key  2) _check_sandbox_safety  3) _session_path
#       4) resolve_auth_secret  5) CORS 静态复查（不启动 app）
# ============================================================

import os
import sys
import types
import importlib.util
import pytest

_PY_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PY_SERVER not in sys.path:
    sys.path.insert(0, _PY_SERVER)

# ── 关键隔离：仅 stub 重型「子模块」，父包 db 始终真实 ──
# config_routes 顶层 `from db.llm_provider import LLMProvider` 仅作类型引用；
# 重型子模块（milvus/pg/redis）占位避免 db/__init__.py 触发 pymilvus SIGSEGV。
# 父包 db 保持真实 → 同会话 conftest 的 autouse fixture 仍可 import db.user_store 等；
# 加载完即还原子模块桩（各目标模块已以独立名缓存），零污染。
_ORIG_SUB = {}


def _stub_sub(name, mod):
    if name not in _ORIG_SUB:
        _ORIG_SUB[name] = sys.modules.get(name)
    sys.modules[name] = mod


class _LLMProvider:
    """桩：config_routes 仅将其作为类型引用，不参与任何调用。"""
_db_llm = types.ModuleType("db.llm_provider")
_db_llm.LLMProvider = _LLMProvider
_stub_sub("db.llm_provider", _db_llm)
for _sub in ("db.milvus_client", "db.pg_client", "db.redis_client"):
    _stub_sub(_sub, types.ModuleType(_sub))


def _load_standalone(module_name: str, rel_path: str):
    """按文件直接加载模块，绕过 api 包的 __init__ 重型依赖链。"""
    full = os.path.join(_PY_SERVER, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, full)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


config_routes = _load_standalone("wavea_config_routes", "api/config_routes.py")
sandbox = _load_standalone("wavea_sandbox", "api/sandbox.py")
sessions = _load_standalone("wavea_sessions", "api/sessions.py")
auth = _load_standalone("wavea_auth", "shared/auth.py")

# ── 还原子模块桩（父包 db 始终真实，各目标模块已以独立名缓存，零污染）──
for _n, _orig in _ORIG_SUB.items():
    if _orig is None:
        sys.modules.pop(_n, None)
    else:
        sys.modules[_n] = _orig

from fastapi import HTTPException  # noqa: E402  (供 _session_path 拒绝断言使用)


# ============================================================
# 1) config_routes._mask_key  — F-002 密钥脱敏
# ============================================================

class TestMaskKey:
    def test_long_key_masked(self):
        # 前4 + "****" + 后4
        assert config_routes._mask_key("sk-abcdefghij123456") == "sk-a****3456"

    def test_short_key_masked(self):
        assert config_routes._mask_key("abc") == "****"

    def test_empty_key_returns_empty(self):
        assert config_routes._mask_key("") == ""

    def test_boundary_len_8_is_masked(self):
        # len <= 8 -> "****"
        assert config_routes._mask_key("12345678") == "****"

    def test_boundary_len_9_has_middle(self):
        # len 9 -> 前4****后4
        assert config_routes._mask_key("123456789") == "1234****6789"

    @pytest.mark.parametrize("key,expected", [
        ("sk-abcdefghij123456", "sk-a****3456"),
        ("abcdefghijklmnop", "abcd****mnop"),
        ("abc", "****"),
        ("", ""),
        ("12345678", "****"),
        ("ab", "****"),
    ])
    def test_mask_key_parametrized(self, key, expected):
        assert config_routes._mask_key(key) == expected


# ============================================================
# 2) sandbox._check_sandbox_safety  — F-003 危险代码拦截
#    注意：该函数「返回」危险原因字符串 / None，并不抛异常。
# ============================================================

class TestSandboxSafety:
    def test_safe_arithmetic(self):
        assert sandbox._check_sandbox_safety("x = 1 + 2") is None

    def test_safe_print(self):
        assert sandbox._check_sandbox_safety("print('hi')") is None

    def test_syntax_error_detected(self):
        reason = sandbox._check_sandbox_safety("x = (")  # 语法错误
        assert reason is not None
        assert "语法错误" in reason

    @pytest.mark.parametrize("code", [
        "import pickle",
        "import os",
        "import subprocess",
        "import tempfile",
        "import socket",
        "import builtins",
        "from os import path",
        "__import__('os')",
    ])
    def test_dangerous_imports_blocked(self, code):
        reason = sandbox._check_sandbox_safety(code)
        assert reason is not None, f"期望返回危险原因，但得到 None: {code!r}"
        assert ("禁止导入模块" in reason) or ("禁止调用" in reason), (
            f"危险代码未被正确识别: {code!r} -> {reason!r}"
        )


# ============================================================
# 3) sessions._session_path  — 路径穿越防护
#    实际签名：_session_path(user_id, conv_id)；非法 id 抛 HTTPException(400)。
#    合法 id 返回落在 SESSIONS_DIR 内的 realpath。
# ============================================================

class TestSessionPath:
    def test_valid_id_returns_path_within_base(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sessions, "SESSIONS_DIR", str(tmp_path))
        p = sessions._session_path("user1", "abc_123")
        assert p.endswith("abc_123.json")
        base = os.path.realpath(str(tmp_path))
        assert os.path.realpath(p).startswith(base + os.sep)

    def test_invalid_id_with_space_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sessions, "SESSIONS_DIR", str(tmp_path))
        with pytest.raises(HTTPException):
            sessions._session_path("user1", "abc def")

    def test_invalid_user_id_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sessions, "SESSIONS_DIR", str(tmp_path))
        with pytest.raises(HTTPException):
            sessions._session_path("user one", "abc_123")

    def test_dotdot_alone_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sessions, "SESSIONS_DIR", str(tmp_path))
        with pytest.raises(HTTPException):
            sessions._session_path("user1", "..")

    def test_traversal_normalized_within_base(self, tmp_path, monkeypatch):
        # 路径穿越片段经 basename 归一化后，realpath 仍必须落在 SESSIONS_DIR 内
        monkeypatch.setattr(sessions, "SESSIONS_DIR", str(tmp_path))
        p = sessions._session_path("user1", "../../../etc/passwd")
        base = os.path.realpath(str(tmp_path))
        assert os.path.realpath(p).startswith(base + os.sep)
        assert p.endswith(".json")


# ============================================================
# 4) shared.auth.resolve_auth_secret  — F-005 fail-closed
#    有模块级 _SECRET 缓存，每个用例必须重置。
# ============================================================

class TestResolveAuthSecret:
    def test_production_no_secret_raises(self, monkeypatch):
        monkeypatch.setattr(auth, "_SECRET", None)
        monkeypatch.setenv("NETLEARN_ENV", "production")
        monkeypatch.delenv("AUTH_SECRET", raising=False)
        with pytest.raises(RuntimeError):
            auth.resolve_auth_secret()

    def test_dev_no_secret_returns_long_random(self, monkeypatch):
        monkeypatch.setattr(auth, "_SECRET", None)
        monkeypatch.setenv("NETLEARN_ENV", "development")
        monkeypatch.delenv("AUTH_SECRET", raising=False)
        secret = auth.resolve_auth_secret()
        assert isinstance(secret, str)
        assert len(secret) >= 32

    def test_production_short_secret_raises(self, monkeypatch):
        monkeypatch.setattr(auth, "_SECRET", None)
        monkeypatch.setenv("NETLEARN_ENV", "production")
        monkeypatch.setenv("AUTH_SECRET", "short")
        with pytest.raises(RuntimeError):
            auth.resolve_auth_secret()

    def test_production_explicit_secret_accepted(self, monkeypatch):
        monkeypatch.setattr(auth, "_SECRET", None)
        monkeypatch.setenv("NETLEARN_ENV", "production")
        monkeypatch.setenv("AUTH_SECRET", "x" * 40)
        secret = auth.resolve_auth_secret()
        assert secret == "x" * 40


# ============================================================
# 5) CORS — 静态复查（不启动 app，仅校验 main.py 配置片段）
# ============================================================

class TestCORSStaticReview:
    def test_dev_uses_origin_regex_not_wildcard(self):
        main_path = os.path.join(_PY_SERVER, "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()
        # dev 分支使用 allow_origin_regex 放行 loopback / LAN
        assert "allow_origin_regex" in content
        assert "localhost" in content
        assert "127.0.0.1" in content
        # 生产分支只允许显式白名单，绝不使用通配符 "*"
        assert 'allow_origins"] = ["*"' not in content
        assert 'allow_origins"]=["*"' not in content
