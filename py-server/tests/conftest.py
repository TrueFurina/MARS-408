import os
import sys

# 确保 py-server 根目录在 sys.path，使 `import api` / `import main` / `import seed_data` 可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# ── 集合级自动跳过（requires_milvus + segv_env + isolation）──
# 单一入口，同时处理三类隔离：
#   1) requires_milvus：无真实 Milvus 服务端时跳过
#      （CI 跑真实 Milvus 时由对应 job 显式 `pytest -m requires_milvus` 纳入）
#   2) segv_env：Windows 原生 torch/numpy 触发 SIGSEGV 的用例，仅 CI/Linux 干净环境运行，
#      本地 Windows 自动跳过（避免整轮 pytest 崩溃）。标记驱动的模块见 _SEGV_MODULES。
#   3) isolation：test_p0_incremental / test_teacher_role 设计为 --noconftest 运行，全平台跳过。
# 注：历史名 test_concurrent_writes 已更名为 test_import_queue_single_writer，
# 后者已用 isolate_vectordb + fake_embedder 隔离、不触达原生库，故不在此名单。
_SEGV_MODULES = {
    "test_engine_modules", "test_closed_loop",
    "test_audit_fixes", "test_e2e_p0_acceptance",
}

def pytest_collection_modifyitems(config, items):
    _skip_milvus = pytest.mark.skip(reason="需要真实 Milvus 服务端")
    _skip_segv = pytest.mark.skip(
        reason="segv_env: 本地 Windows 原生 torch/numpy 触发 SIGSEGV，仅在 CI/Linux 干净环境运行"
    )
    _ISOLATION_SKIP = {"test_p0_incremental", "test_teacher_role"}
    _iso_skip = pytest.mark.skip(
        reason="isolation-test: 设计为 --noconftest 运行；完整套件(conftest)下跳过，用 --noconftest 单独跑"
    )
    try:
        from db.milvus_client import MILVUS_AVAILABLE
    except Exception:
        MILVUS_AVAILABLE = False
    for item in items:
        # 隔离测试：全平台跳过（设计为 --noconftest 运行）
        # 注：item.module.__name__ 可能带 tests. 前缀（如 tests.test_teacher_role），
        # 需取末段再比对 _ISOLATION_SKIP，否则匹配失败导致隔离测试在完整套件下误跑。
        _mod_name = (item.module.__name__ or "").split(".")[-1]
        if _mod_name in _ISOLATION_SKIP:
            item.add_marker(_iso_skip)
            continue
        if item.get_closest_marker("requires_milvus") and not MILVUS_AVAILABLE:
            item.add_marker(_skip_milvus)
        # Windows 本地：跳过标记了 segv_env 的用例，及已知触达原生库的模块（兜底）
        if sys.platform == "win32":
            if item.get_closest_marker("segv_env") or \
               any(name in item.module.__name__ for name in _SEGV_MODULES):
                item.add_marker(_skip_segv)


@pytest.fixture(autouse=True)
def _temp_sessions(monkeypatch, tmp_path):
    """将会话存储重定向到独立临时目录，避免触碰真实 sessions/ 文件，
    也避免触发 WorkBuddy 沙箱的批量删除保护（之前导致 32 个 ERROR）。

    因为 api.sessions.SESSIONS_DIR 是模块级常量，monkeypatch 该属性后，
    所有会话读写/删除都落在临时目录，pytest 自动回收，零副作用。
    """
    import api.sessions as _sess_mod
    monkeypatch.setattr(_sess_mod, "SESSIONS_DIR", str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    """注入离线 Mock LLM，使所有依赖 LLM 的端点在测试环境确定性跑通。

    覆盖 LLMProvider.chat / stream_chat / text_completion / _resolve。
    各 api 模块以 `from db.llm_provider import LLMProvider` 引用同一类对象，
    因此 patch 类方法即可全局生效，无需逐个模块打桩。
    """
    import db.llm_provider as _lp

    _CANNED_PROFILE = (
        '{"learning_style":"visual","knowledge_base":"intermediate",'
        '"study_time":"1-2h","goal":"exam","weak_points":"子网划分",'
        '"progress":3,"interest_area":"networking","preferred_difficulty":"medium"}'
    )

    async def _fake_chat(self, messages, *args, **kwargs):
        return {
            "choices": [
                {"message": {"role": "assistant", "content": _CANNED_PROFILE}}
            ]
        }

    async def _fake_stream(self, messages, *args, **kwargs):
        """模拟 OpenAI 兼容的 SSE 流式块，使 chat_stream 等端点正常解析"""
        import json as _json
        chunk = _json.dumps({"choices": [{"delta": {"content": "mock stream response"}}]})
        yield chunk
        yield "[DONE]"

    async def _fake_text_completion(self, system_prompt, user_prompt, *args, **kwargs):
        # 返回非空串（但不含 JSON 数组括号）→ 端点兜底逻辑正常返回结构化响应；
        # 同时 chat/send 能拿到回复（不再误报 503），
        # learning-path-with-resources 因无法解析出 [..] 仍保持 llm_adjusted=False。
        return "mock llm response"

    def _fake_resolve(self):
        return {"name": "mock", "api_key": "x", "app_id": "x"}

    monkeypatch.setattr(_lp.LLMProvider, "chat", _fake_chat)
    monkeypatch.setattr(_lp.LLMProvider, "stream_chat", _fake_stream)
    monkeypatch.setattr(_lp.LLMProvider, "text_completion", _fake_text_completion)
    monkeypatch.setattr(_lp.LLMProvider, "_resolve", _fake_resolve)
    yield


@pytest.fixture(autouse=True)
def mock_auth():
    """绕过认证：所有测试请求自动以 admin 身份通过认证。
    使用 FastAPI dependency_overrides 覆盖，无需修改每个测试。"""
    from main import app
    from shared.auth import get_current_user, require_admin
    from db.user_store import create_user, authenticate

    # 确保 test_admin 用户存在，并拿到实际 user_id
    try:
        user = create_user("test_admin", "test_pw_123", "Test Admin", role="admin")
    except ValueError:
        # 用户已存在，用 authenticate 查回
        user = authenticate("test_admin", "test_pw_123")

    _fake_user = {"user_id": user["id"] if user else "unknown", "role": "admin"}

    app.dependency_overrides[get_current_user] = lambda: _fake_user
    app.dependency_overrides[require_admin] = lambda: _fake_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture()
def no_mock_auth():
    """opt-out fixture：请求此 fixture 的测试将临时清除认证覆盖，
    用于测试未认证场景（如 401 拒绝）。"""
    from main import app
    from shared.auth import get_current_user, require_admin
    saved_gcu = app.dependency_overrides.get(get_current_user)
    saved_ra = app.dependency_overrides.get(require_admin)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)
    yield
    if saved_gcu is not None:
        app.dependency_overrides[get_current_user] = saved_gcu
    if saved_ra is not None:
        app.dependency_overrides[require_admin] = saved_ra


# ============================================================
# 导入队列测试（ADR-007）共享 fixtures
# ============================================================
# 以下 fixtures 仅按需（被具体测试显式请求）生效，不干扰既有测试套件。
# 设计目标：避免重依赖（torch / 真实 E5 / 真实 Milvus），CI 干净环境可直接跑。
# ============================================================


@pytest.fixture
def isolate_vectordb(tmp_path, monkeypatch):
    """将向量库落盘与导入 journal 重定向到独立临时目录，并强制 InMemory 回退。

    - 强制 MILVUS_AVAILABLE=False，避免加载 pymilvus 原生库（Windows 上可能 segfault）；
    - 重定向 InMemoryVectorStore 的 persist_path 到 tmp，避免污染真实 vectordb_data；
    - 重定向 import_worker.JOURNAL_DIR，使导入任务 journal 落在 tmp/import_jobs。
    """
    import db.milvus_client as _mc
    import services.import_worker as _iw

    monkeypatch.setattr(_mc, "MILVUS_AVAILABLE", False)

    _orig_init = _mc.InMemoryVectorStore.__init__

    def _init(self, persist_path=str(tmp_path), *a, **k):
        _orig_init(self, persist_path, *a, **k)

    monkeypatch.setattr(_mc.InMemoryVectorStore, "__init__", _init)
    monkeypatch.setattr(_iw, "JOURNAL_DIR", tmp_path / "import_jobs")
    yield


@pytest.fixture
def fake_embedder(monkeypatch):
    """注入确定性 768 维嵌入，避免加载真实 E5 模型。

    基于文本 SHA-256 派生随机数种子，保证同一文本每次得到相同向量（可复现）。
    覆盖 db.embedder.embed_batch / embed_text（import_worker._embed 在调用时
    才 `from db.embedder import embed_batch`，因此 patch 模块属性即可全局生效）。
    """
    import hashlib
    import numpy as np
    import db.embedder as _eb

    _DIM = 768

    def _fake_batch(texts):
        out = []
        for t in texts:
            _h = hashlib.sha256(t.encode("utf-8")).digest()
            _rng = np.random.default_rng(int.from_bytes(_h[:8], "big"))
            _v = _rng.standard_normal(_DIM).astype(np.float32)
            _n = np.linalg.norm(_v) or 1.0
            out.append((_v / _n).tolist())
        return out

    monkeypatch.setattr(_eb, "embed_batch", _fake_batch)
    monkeypatch.setattr(_eb, "embed_text", lambda t: _fake_batch([t])[0])
    yield


@pytest.fixture
def client():
    """返回 FastAPI TestClient（惰性导入 main，避免无关测试触发重依赖模块加载）。

    用例如需触发 lifespan（拉起 import_worker 消费者），请使用 `with client:`。
    """
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


# ── Windows 本地 SIGSEGV 防护 / 隔离测试说明 ──
# - segv_env 用例（及 _SEGV_MODULES 已知模块）在 win32 下自动跳过，
#   仅 CI/Linux 干净环境运行；标记由对应测试文件
#   `pytestmark = pytest.mark.segv_env` 声明，或为历史模块走 _SEGV_MODULES 兜底
#   （见顶部 pytest_collection_modifyitems，已合并为一个入口）。
# - 隔离测试（test_p0_incremental / test_teacher_role）设计为 `--noconftest` 运行，
#   其覆盖率由单独的 `pytest tests/test_X.py --noconftest` 保证，不在完整套件下跑。

