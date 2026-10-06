# ============================================================
# Wave B 针对性运行时验证 — 安全 P1（纯函数级 pytest）
# Author: Edward (QA Engineer)  |  team: software-residual-fixes
# ============================================================
# 隔离策略（严格遵守沙箱约束：禁止启动后端 / import main / 触发 E5 / pymilvus）：
#   1) importlib.util 按文件「独立加载」目标模块，绕过 api/__init__.py 重型依赖链。
#   2) stub 掉 db 包：knowledge.py 顶层 `from db.milvus_client import vector_db`
#      会触发 db/__init__.py -> pymilvus（Windows 原生库 SIGSEGV），故桩替换。
#   3) ratelimit.check_llm_quota 内部 `from db.redis_client import redis_client`
#      后调用 `redis_client.check_rate_limit(...)`；按源码实测无模块级 check_rate_limit
#      名字，故 patch 的是 db.redis_client 单例对象的 check_rate_limit 方法。
#   4) 运行加 --noconftest，避免 conftest 的 autouse fixture 去 import main。
# 覆盖：1) require_teacher  2) require_llm_quota / check_llm_quota  3) _safe_upload_path
# ============================================================

import os
import sys
import types
import importlib.util
import pytest
from fastapi import HTTPException

_PY_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PY_SERVER not in sys.path:
    sys.path.insert(0, _PY_SERVER)


# ── 隔离桩（仅 submodules，不桩父包）──
# knowledge.py 顶层仅 db.milvus_client 触发 pymilvus(Windows SIGSEGV)；config /
# shared.auth / shared.audit / services.import_worker / models 均为轻量纯 Python。
# 为与「独立加载、不拉起重型链」的初衷一致，仍对它们桩占位（submodule 级）。
# 父包 db / shared / config / services / models 始终保持真实，故同会话其它测试
# import db.llm_provider / shared.auth 等不受影响。
# knowledge 加载完成后立刻还原这些 submodule 桩（knowledge 已以独立名缓存）。
# ratelimit 的 require_llm_quota 在函数体内 `from db.redis_client import redis_client`，
# 故 db.redis_client 桩需在「测试执行期」保持，由模块级 autouse fixture 管理生命周期。
_ORIG_SUB = {}


def _stub_sub(name, mod):
    if name not in _ORIG_SUB:
        _ORIG_SUB[name] = sys.modules.get(name)
    sys.modules[name] = mod


# knowledge.py 加载所需（重型 + 轻量占位，均 submodule 级，不碰父包）
_mc = types.ModuleType("db.milvus_client")
_mc.vector_db = object()
_stub_sub("db.milvus_client", _mc)
_pg = types.ModuleType("db.pg_client")
_stub_sub("db.pg_client", _pg)
_cfg = types.ModuleType("config")
_cfg.load_config = lambda *a, **k: {}
_stub_sub("config", _cfg)
_siw = types.ModuleType("services.import_worker")
_siw.import_worker = type("ImportWorker", (), {"store_lock": object()})()
_stub_sub("services.import_worker", _siw)
_mods = types.ModuleType("models")
for _n in ("KnowledgeStatsResponse", "KnowledgeListResponse", "KnowledgeListItem",
           "KnowledgeUpsertRequest", "KnowledgeDeleteRequest"):
    setattr(_mods, _n, object)
_stub_sub("models", _mods)
_sauth = types.ModuleType("shared.auth")
_sauth.get_current_user = lambda *a, **k: {}
_sauth.require_admin = lambda *a, **k: {}
_stub_sub("shared.auth", _sauth)
_saudit = types.ModuleType("shared.audit")
_saudit.log_event = lambda *a, **k: None
_stub_sub("shared.audit", _saudit)


def _load_standalone(module_name: str, rel_path: str):
    """按文件直接加载模块，绕过 api 包的 __init__ 重型依赖链。"""
    full = os.path.join(_PY_SERVER, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, full)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


auth = _load_standalone("waveb_auth", "shared/auth.py")
ratelimit = _load_standalone("waveb_ratelimit", "shared/ratelimit.py")
knowledge = _load_standalone("waveb_knowledge", "api/knowledge.py")

# knowledge 已缓存，还原重型/轻量 submodule 桩（父包 db/shared/config/services/models 始终真实）
for _n, _orig in _ORIG_SUB.items():
    if _orig is None:
        sys.modules.pop(_n, None)
    else:
        sys.modules[_n] = _orig


# ── db.redis_client 桩（ratelimit 测试执行期需要）──
# require_llm_quota / check_llm_quota 在函数体内 `from db.redis_client import redis_client`，
# 故必须在调用时让 db.redis_client 指向桩；用模块级 autouse fixture 在测完还原，避免泄漏。
class _FakeRedis:
    """桩：模拟未启用 Redis（开发环境 fail-open）。check_rate_limit 可 monkeypatch。"""
    is_enabled = False

    def check_rate_limit(self, key, max_requests, window=60):
        # 默认 fail-open 放行；限流命中用例会将其 patch 为返回 False
        return True


_fake_redis = _FakeRedis()
_redis_orig = sys.modules.get("db.redis_client")
_db_redis = types.ModuleType("db.redis_client")
_db_redis.redis_client = _fake_redis
sys.modules["db.redis_client"] = _db_redis


@pytest.fixture(scope="module", autouse=True)
def _restore_redis_stub():
    yield
    # 本文件测试结束后还原真实 db.redis_client，避免污染同会话其它测试
    if _redis_orig is None:
        sys.modules.pop("db.redis_client", None)
    else:
        sys.modules["db.redis_client"] = _redis_orig


# ============================================================
# 1) require_teacher — F-009 教师/管理员放行，其余 403
# ============================================================

class TestRequireTeacher:
    def test_admin_passes(self):
        u = {"role": "admin"}
        assert auth.require_teacher(user=u) is u

    def test_teacher_passes(self):
        u = {"role": "teacher"}
        assert auth.require_teacher(user=u) is u

    def test_student_rejected_403(self):
        with pytest.raises(HTTPException) as exc:
            auth.require_teacher(user={"role": "student"})
        assert exc.value.status_code == 403

    def test_default_role_student_rejected(self):
        # role 缺省按 student 处理 -> 403
        with pytest.raises(HTTPException) as exc:
            auth.require_teacher(user={})
        assert exc.value.status_code == 403


# ============================================================
# 2) require_llm_quota / check_llm_quota — F-011 双窗口限流
#    实测源码在 check_llm_quota 内 `from db.redis_client import redis_client`
#    后调用 redis_client.check_rate_limit，故 patch 单例方法。
# ============================================================

class TestLLMQuota:
    def test_require_llm_quota_passes(self, monkeypatch):
        monkeypatch.setattr(_fake_redis, "check_rate_limit", lambda *a, **k: True)
        u = {"id": "u1"}
        assert ratelimit.require_llm_quota(user=u) is u

    def test_check_llm_quota_passes(self, monkeypatch):
        monkeypatch.setattr(_fake_redis, "check_rate_limit", lambda *a, **k: True)
        # 不抛异常即视为放行
        ratelimit.check_llm_quota({"id": "u1"})

    def test_require_llm_quota_limit_hit_raises_429(self, monkeypatch):
        monkeypatch.setattr(_fake_redis, "check_rate_limit", lambda *a, **k: False)
        with pytest.raises(HTTPException) as exc:
            ratelimit.require_llm_quota(user={"id": "u1"})
        assert exc.value.status_code == 429

    def test_check_llm_quota_limit_hit_raises_429(self, monkeypatch):
        monkeypatch.setattr(_fake_redis, "check_rate_limit", lambda *a, **k: False)
        with pytest.raises(HTTPException) as exc:
            ratelimit.check_llm_quota({"id": "u1"})
        assert exc.value.status_code == 429

    def test_fail_open_when_redis_disabled(self, monkeypatch):
        # Redis 未启用（is_enabled=False）且开发环境（非 STRICT）应 fail-open 放行
        monkeypatch.setattr(_fake_redis, "is_enabled", False)
        monkeypatch.setattr(_fake_redis, "check_rate_limit", lambda *a, **k: True)
        u = {"id": "u2"}
        # 不抛异常，require 返回原 user
        assert ratelimit.require_llm_quota(user=u) is u


# ============================================================
# 3) _safe_upload_path — F-012 路径穿越防护
#    实测：先取 basename，故 /abs/path/x.pdf 被中性化为 x.pdf（安全，不抛）。
#    仅非法扩展名或 basename 内含 ".."/"/"/"\" 才抛 HTTPException(400)。
# ============================================================

class TestSafeUploadPath:
    def test_valid_filename_returns_path_within_base(self, tmp_path):
        base = str(tmp_path)
        p = knowledge._safe_upload_path("a.txt", base)
        assert p.endswith("a.txt")
        real_base = os.path.realpath(base)
        assert os.path.realpath(p).startswith(real_base + os.sep)

    def test_abs_path_neutralized_not_raised(self, tmp_path):
        # 绝对路径经 basename 剥离开头目录，落在 base_dir 内即为安全（不抛）
        base = str(tmp_path)
        p = knowledge._safe_upload_path("/abs/path/x.pdf", base)
        real_base = os.path.realpath(base)
        assert os.path.realpath(p).startswith(real_base + os.sep)
        assert p.endswith("x.pdf")

    def test_bad_extension_rejected(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            knowledge._safe_upload_path("x.exe", str(tmp_path))
        assert exc.value.status_code == 400

    def test_no_extension_traversal_rejected(self, tmp_path):
        # ../../etc/passwd -> basename "passwd"，无白名单扩展名 -> 400
        with pytest.raises(HTTPException) as exc:
            knowledge._safe_upload_path("../../etc/passwd", str(tmp_path))
        assert exc.value.status_code == 400

    def test_empty_filename_rejected(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            knowledge._safe_upload_path("", str(tmp_path))
        assert exc.value.status_code == 400

    def test_literal_dotdot_in_basename_rejected(self, tmp_path):
        # basename 内直接含 ".." 片段 -> 400
        with pytest.raises(HTTPException) as exc:
            knowledge._safe_upload_path(".._evil.txt", str(tmp_path))
        assert exc.value.status_code == 400

    def test_custom_prefix_used(self, tmp_path):
        base = str(tmp_path)
        p = knowledge._safe_upload_path("b.md", base, prefix="pre_")
        assert p.endswith("pre_b.md")
        real_base = os.path.realpath(base)
        assert os.path.realpath(p).startswith(real_base + os.sep)
