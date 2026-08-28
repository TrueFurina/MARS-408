# ============================================================
# 针对性验证：teacher 账户创建通道（缺口修复）
# 环境约束：禁止启动完整后端（E5 加载会 SIGSEGV）。
# 仅做隔离纯函数 / 轻量 import 测试：
#   - 用 importlib 独立加载 shared/auth.py、db/user_store.py、api/admin_users.py
#     （均不触发 db.__init__ 重型子模块 pymilvus/psycopg/redis/模型加载）
#   - 对 api/admin_users 运行时测试，预先把重型 db 子模块 stub 进 sys.modules
#   - --noconftest 避免加载项目级 conftest 的重型 fixture
# 运行：py-server/.venv/Scripts/python.exe -m pytest \
#        py-server/tests/test_teacher_role.py -v --noconftest
# ============================================================

import os
import sys
import types
import asyncio
import logging
import importlib.util

import pytest
from fastapi import HTTPException

logging.disable(logging.CRITICAL)  # 保持测试输出干净

# ---- 绝对路径（不依赖 sys.path 包含 py-server） ----
_HERE = os.path.abspath(__file__)
_PY_SERVER = os.path.dirname(os.path.dirname(_HERE))
AUTH_PATH = os.path.join(_PY_SERVER, "shared", "auth.py")
USER_STORE_PATH = os.path.join(_PY_SERVER, "db", "user_store.py")
ADMIN_USERS_PATH = os.path.join(_PY_SERVER, "api", "admin_users.py")


def _load_isolated(name: str, path: str):
    """用 importlib 按绝对路径独立加载模块，避免触发父包的 __init__ 重型链。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ---- 轻量、安全的独立加载（仅依赖 stdlib + fastapi） ----
AUTH_MOD = _load_isolated("iso_shared_auth", AUTH_PATH)
USER_STORE_MOD = _load_isolated("iso_db_user_store", USER_STORE_PATH)


# ============================================================
# 验证点 1：require_teacher 对 teacher/admin 放行，对 student 抛 403
# ============================================================

def test_require_teacher_allows_teacher():
    out = AUTH_MOD.require_teacher(user={"role": "teacher"})
    assert out["role"] == "teacher"


def test_require_teacher_allows_admin():
    out = AUTH_MOD.require_teacher(user={"role": "admin"})
    assert out["role"] == "admin"


def test_require_teacher_rejects_student():
    with pytest.raises(HTTPException) as exc:
        AUTH_MOD.require_teacher(user={"role": "student"})
    assert exc.value.status_code == 403


# ============================================================
# 验证点 2：teacher 账户可落库并读回（端点实际调用的底层函数）
# 注：源码无 get_user(username)，使用 authenticate（按 username 读回并校验密码）
#     作为读回手段，同时验证了密码哈希落库正确。
# ============================================================

@pytest.fixture
def store(tmp_path):
    USER_STORE_MOD._conn = None
    USER_STORE_MOD._DB_PATH = str(tmp_path / "users.db")
    yield USER_STORE_MOD
    try:
        if USER_STORE_MOD._conn is not None:
            USER_STORE_MOD._conn.close()
    except Exception:
        pass
    USER_STORE_MOD._conn = None


def test_create_and_readback_teacher(store):
    # 密码需 >= 8 位（MIN_PASSWORD_LENGTH），故用 Password123
    created = store.create_user("teacher1", "Password123", "T1", role="teacher")
    assert created["role"] == "teacher"

    read = store.authenticate("teacher1", "Password123")
    assert read is not None
    assert read["role"] == "teacher"


# ============================================================
# 验证点 3：角色校验（尽力运行时 import api.admin_users）
# 若隔离导入成功：非法 role -> 400；合法 teacher + monkeypatch create_user -> 返回用户。
# 若导入不安全（拉起重型链）：fixture 跳过，由静态确认替代（见报告）。
# ============================================================

def _setup_admin_module():
    # stub shared 包 + 注入已加载的 shared.auth
    shared_pkg = sys.modules.get("shared") or types.ModuleType("shared")
    sys.modules["shared"] = shared_pkg
    sys.modules["shared.auth"] = AUTH_MOD
    shared_pkg.auth = AUTH_MOD

    # stub db 包 + 重型子模块（milvus/pg/redis/llm_provider），避免真实加载
    db_pkg = sys.modules.get("db") or types.ModuleType("db")
    sys.modules["db"] = db_pkg
    for sub in ("milvus_client", "pg_client", "redis_client", "llm_provider"):
        m = types.ModuleType("db." + sub)
        m.vector_db = m
        m.pg_client = m
        m.redis_client = m
        m.connect = lambda: None
        m.LLMProvider = object
        m.LLMUnavailable = Exception
        sys.modules["db." + sub] = m
        setattr(db_pkg, sub, m)
    # 注入已加载的 db.user_store（同一实例，避免双连接）
    sys.modules["db.user_store"] = USER_STORE_MOD
    db_pkg.user_store = USER_STORE_MOD

    # 独立加载 api/admin_users.py（扁平名，不触发 api.__init__ 全量路由）
    return _load_isolated("iso_api_admin_users", ADMIN_USERS_PATH)


@pytest.fixture(scope="module")
def admin_mod():
    try:
        return _setup_admin_module()
    except Exception as exc:  # 环境相关，无法隔离导入时跳过
        pytest.skip(f"无法隔离导入 api.admin_users（重型链），改为静态确认：{exc}")


def test_admin_endpoint_valid_roles_and_route_guard(admin_mod):
    # 角色集合正确
    assert admin_mod.VALID_ROLES == ("student", "teacher", "admin")
    # 整路由受 require_admin 保护
    deps = admin_mod.router.dependencies
    assert len(deps) == 1
    assert deps[0].dependency is admin_mod.require_admin


def test_admin_endpoint_illegal_role_400(admin_mod):
    req = admin_mod.CreateUserRequest(username="x", password="Password123", role="hacker")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(admin_mod.create_user_endpoint(req))
    assert exc.value.status_code == 400


def test_admin_endpoint_teacher_ok(admin_mod, monkeypatch):
    fake = {
        "id": "u_t", "username": "tchr", "display_name": "T",
        "role": "teacher", "created_at": "2026-01-01 00:00:00",
    }
    # 端点从 admin_mod 命名空间绑定 create_user，故直接 patch 该引用
    monkeypatch.setattr(admin_mod, "create_user", lambda **kw: fake)
    req = admin_mod.CreateUserRequest(username="tchr", password="Password123", role="teacher")
    result = asyncio.run(admin_mod.create_user_endpoint(req))
    assert result["role"] == "teacher"
    # 绝不返回敏感字段
    assert "password_hash" not in result
    assert "salt" not in result
