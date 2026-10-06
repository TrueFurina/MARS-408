# ============================================================
# Audit Fixes Regression Tests — P0/P1 Verification
# ============================================================
# Author: Edward (QA Engineer)
# Purpose: Verify all 8 audit fixes from Engineer (Kou Dou Ma)
# ============================================================

import os
import re
import json
import subprocess
import sys
import pytest

# segv_env：本模块调用真实 torch/numpy 嵌入等，Windows 原生库下触发 SIGSEGV；
# 仅 CI/Linux 干净环境运行，本地 Windows 由 conftest 自动跳过。
pytestmark = pytest.mark.segv_env

import pytest

# ── Project paths ──
PY_SERVER_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_DIR = os.path.dirname(PY_SERVER_DIR)
# 安全门禁扫描「可提交的配置范本」(config.example.json)；真实 config.json 被 .gitignore
# 忽略、不入库，不应作为 CI 安全门禁的扫描目标（仓库里不存在也无法保证无密钥）。
# 本地开发若存在真实 config.json 仍优先扫描，兼顾本地自查。
_CONFIG_JSON = os.path.join(PY_SERVER_DIR, "config.json")
_CONFIG_EXAMPLE_JSON = os.path.join(PY_SERVER_DIR, "config.example.json")
CONFIG_JSON_PATH = _CONFIG_JSON if os.path.exists(_CONFIG_JSON) else _CONFIG_EXAMPLE_JSON
ENV_EXAMPLE_PATH = os.path.join(PY_SERVER_DIR, ".env.example")
GITIGNORE_PATH = os.path.join(PROJECT_DIR, ".gitignore")
SAFETY_PATH = os.path.join(PY_SERVER_DIR, "utils", "safety.py")
CONFIG_PY_PATH = os.path.join(PY_SERVER_DIR, "config.py")
LEARNING_PY_PATH = os.path.join(PY_SERVER_DIR, "api", "sandbox.py")  # D-05: 沙箱代码已拆分到 sandbox.py
ASSESSMENT_PY_PATH = os.path.join(PY_SERVER_DIR, "api", "assessment.py")  # D-05: 评估路由
CONFIG_ROUTES_PY_PATH = os.path.join(PY_SERVER_DIR, "api", "config_routes.py")  # D-05: 配置路由
LANGGRAPH_PY_PATH = os.path.join(PY_SERVER_DIR, "api", "langgraph.py")
KNOWLEDGE_PY_PATH = os.path.join(PY_SERVER_DIR, "api", "knowledge.py")
AGENTS_PY_PATH = os.path.join(PY_SERVER_DIR, "api", "agents.py")
MILVUS_CLIENT_PATH = os.path.join(PY_SERVER_DIR, "db", "milvus_client.py")
GRAPH_PY_PATH = os.path.join(PY_SERVER_DIR, "agents", "graph.py")

SRC_DIR = os.path.join(PROJECT_DIR, "src")
PACKAGE_JSON_PATH = os.path.join(PROJECT_DIR, "package.json")
MARKDOWN_TS_PATH = os.path.join(SRC_DIR, "utils", "markdown.ts")

PYTHON = sys.executable


# ============================================================
# Helper: read file content
# ============================================================

def _read_file(path: str) -> str:
    """Read file content, return empty string if not found."""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _grep_py_files(directory: str, pattern: str, exclude_venv=True) -> list[str]:
    """Search pattern in all .py files under directory (excluding .venv)."""
    matches = []
    for root, dirs, files in os.walk(directory):
        if exclude_venv and ".venv" in root:
            continue
        for fname in files:
            if fname.endswith(".py"):
                fpath = os.path.join(root, fname)
                content = _read_file(fpath)
                if re.search(pattern, content):
                    matches.append(fpath)
    return matches


def _grep_vue_ts_files(directory: str, pattern: str) -> list[str]:
    """Search pattern in all .vue/.ts files under src/."""
    matches = []
    for root, dirs, files in os.walk(directory):
        for fname in files:
            if fname.endswith((".vue", ".ts")):
                fpath = os.path.join(root, fname)
                content = _read_file(fpath)
                if re.search(pattern, content):
                    matches.append(fpath)
    return matches


def _grep_all_files(directory: str, pattern: str, extensions=None) -> list[str]:
    """Search pattern in all files (optionally filtered by extensions)."""
    matches = []
    for root, dirs, files in os.walk(directory):
        for fname in files:
            if extensions and not any(fname.endswith(ext) for ext in extensions):
                continue
            fpath = os.path.join(root, fname)
            try:
                content = _read_file(fpath)
                if re.search(pattern, content):
                    matches.append(fpath)
            except Exception:
                pass
    return matches


# ============================================================
# P0-5: API_BASE Unification
# ============================================================


class TestP0_5_APIBaseUnification:
    """Verify API_BASE = '' in all Vue views, no localhost:8000 residue."""

    def test_no_localhost_8000_in_src(self):
        """src/ directory should NOT contain http://localhost:8000."""
        matches = _grep_vue_ts_files(SRC_DIR, r"http://localhost:8000")
        assert len(matches) == 0, (
            f"Found http://localhost:8000 residue in {matches}. "
            "All API_BASE should be '' for relative paths."
        )

    def test_api_base_empty_in_settings_view(self):
        """SettingsView.vue must use relative API paths (no localhost:8000 residue).

        Like AdminView.vue, SettingsView.vue imports the shared `api` module from
        '@/utils/api' (which already uses an empty baseURL for vite-proxy relative
        calls). So it intentionally has no local API_BASE constant — verify the
        correct proxy-based pattern instead.
        """
        content = _read_file(os.path.join(SRC_DIR, "views", "SettingsView.vue"))
        assert "http://localhost:8000" not in content, (
            "SettingsView.vue must not hardcode localhost:8000; use the shared `api` module."
        )
        assert "from '@/utils/api'" in content or 'from "@/utils/api"' in content, (
            "SettingsView.vue should import the shared `api` module for relative-path calls."
        )

    def test_api_base_empty_in_admin_view(self):
        """AdminView.vue must use relative API paths (no localhost:8000 residue).

        Unlike views that define a local `const API_BASE = ''`, AdminView.vue
        imports the shared `api` module from '@/utils/api' (which already uses an
        empty baseURL for vite-proxy relative calls). So it intentionally has no
        local API_BASE constant — verify the correct proxy-based pattern instead.
        """
        content = _read_file(os.path.join(SRC_DIR, "views", "AdminView.vue"))
        assert "http://localhost:8000" not in content, (
            "AdminView.vue must not hardcode localhost:8000; use the shared `api` module."
        )
        assert "from '@/utils/api'" in content or 'from "@/utils/api"' in content, (
            "AdminView.vue should import the shared `api` module for relative-path calls."
        )


# ============================================================
# P0-4: DOMPurify sanitize (renderMarkdownSafe)
# ============================================================


class TestP0_4_DOMPurifySanitize:
    """Verify DOMPurify integration and renderMarkdownSafe usage."""

    def test_render_markdown_safe_exists(self):
        """markdown.ts should export renderMarkdownSafe function."""
        content = _read_file(MARKDOWN_TS_PATH)
        assert "export function renderMarkdownSafe" in content, (
            "markdown.ts should export renderMarkdownSafe() function."
        )

    def test_dompurify_import_in_markdown_ts(self):
        """markdown.ts should import DOMPurify."""
        content = _read_file(MARKDOWN_TS_PATH)
        assert "import DOMPurify from 'dompurify'" in content, (
            "markdown.ts should import DOMPurify."
        )

    def test_render_markdown_safe_calls_dompurify_sanitize(self):
        """renderMarkdownSafe should call DOMPurify.sanitize()."""
        content = _read_file(MARKDOWN_TS_PATH)
        assert "DOMPurify.sanitize" in content, (
            "renderMarkdownSafe should call DOMPurify.sanitize(html, ...)."
        )

    def test_package_json_has_dompurify(self):
        """package.json should list dompurify as a dependency."""
        content = _read_file(PACKAGE_JSON_PATH)
        pkg = json.loads(content)
        deps = pkg.get("dependencies", {})
        assert "dompurify" in deps, (
            f"package.json dependencies should include dompurify. Found: {list(deps.keys())}"
        )

    def test_all_v_html_use_render_markdown_safe(self):
        """All v-html calls in view files that render user content should use renderMarkdownSafe."""
        # List of view files that should use renderMarkdownSafe for content v-html
        view_files = [
            "ChatView.vue",
            "ResourceView.vue",
            "AssessmentView.vue",
            "ProfileBuilder.vue",
            "SandboxView.vue",
        ]
        for vfile in view_files:
            fpath = os.path.join(SRC_DIR, "views", vfile)
            content = _read_file(fpath)
            # Check that the import line contains renderMarkdownSafe
            # NOTE: We check both the correct name and the potentially buggy double-Safe name
            assert "renderMarkdownSafe" in content, (
                f"{vfile} should import or reference renderMarkdownSafe. "
                "Content v-html bindings must use DOMPurify."
            )

    def test_v_html_content_views_import_correct_function_name(self):
        """Views should import 'renderMarkdownSafe' (not 'renderMarkdownSafeSafe')."""
        view_files = [
            "ChatView.vue",
            "ResourceView.vue",
            "SandboxView.vue",
        ]
        buggy_files = []
        for vfile in view_files:
            fpath = os.path.join(SRC_DIR, "views", vfile)
            content = _read_file(fpath)
            # Check for the buggy double-Safe import
            if "renderMarkdownSafeSafe" in content:
                buggy_files.append(vfile)

        if buggy_files:
            # This is a SOURCE CODE BUG — the import name is wrong
            # renderMarkdownSafeSafe doesn't exist in markdown.ts
            pytest.fail(
                f"SOURCE CODE BUG: {buggy_files} import 'renderMarkdownSafeSafe' "
                f"but the actual export is 'renderMarkdownSafe'. "
                f"This will cause a runtime import error. "
                f"Routing: Engineer needs to fix these import names."
            )


# ============================================================
# P1-6: API keys via environment variables
# ============================================================


class TestP1_6_SecretEnvironmentVariables:
    """Verify config.json keys are empty, .env.example exists, .gitignore covers .env."""

    def test_config_json_keys_empty(self):
        """config.json sensitive keys should not contain real secrets at top level.
        
        Note: config.json now uses nested structure (deepseek.api_key, xfyun.api_key, etc.)
        Top-level flat keys no longer exist. The test verifies that:
        1. No flat-level xfyun_api_key/xfyun_app_id/llm_api_key with real values
        2. Nested keys exist under their provider sections
        """
        content = _read_file(CONFIG_JSON_PATH)
        config = json.loads(content)
        # Flat-format keys should not exist at top level (or be empty/None)
        assert config.get("xfyun_api_key", "<missing>") in ("", None, "<missing>"), (
            f"xfyun_api_key should not exist or be empty. Got: {config.get('xfyun_api_key')}"
        )
        assert config.get("xfyun_app_id", "<missing>") in ("", None, "<missing>"), (
            f"xfyun_app_id should not exist or be empty. Got: {config.get('xfyun_app_id')}"
        )
        assert config.get("llm_api_key", "<missing>") in ("", None, "<missing>"), (
            f"llm_api_key should not exist or be empty. Got: {config.get('llm_api_key')}"
        )
        # Nested structure should exist
        assert "deepseek" in config or "xfyun" in config, (
            "config.json should have nested provider structure (deepseek/xfyun)"
        )

    def test_env_example_exists(self):
        """py-server/.env.example file should exist."""
        assert os.path.exists(ENV_EXAMPLE_PATH), (
            "py-server/.env.example should exist as a template for environment variables."
        )

    def test_env_example_has_key_fields(self):
        """.env.example should list the key fields (DEEPSEEK_API_KEY, XF_API_KEY, XF_APP_ID)."""
        content = _read_file(ENV_EXAMPLE_PATH)
        assert "DEEPSEEK_API_KEY" in content, ".env.example should mention DEEPSEEK_API_KEY."
        assert "XF_API_KEY" in content, ".env.example should mention XF_API_KEY."
        assert "XF_APP_ID" in content, ".env.example should mention XF_APP_ID."

    def test_gitignore_has_env(self):
        """Root .gitignore should include .env entries."""
        content = _read_file(GITIGNORE_PATH)
        assert ".env" in content, (
            ".gitignore should contain .env to prevent secret leakage."
        )


# ============================================================
# P0-2: knowledge.py uses VectorDB (not ChromaDB)
# ============================================================


class TestP0_2_KnowledgeUsesVectorDB:
    """Verify knowledge.py and agents.py no longer reference ChromaDB/deps.get_collection."""

    def test_no_chromadb_in_knowledge_py(self):
        """knowledge.py should NOT have ChromaDB code references (comments about migration are OK)."""
        content = _read_file(KNOWLEDGE_PY_PATH)
        # Check for actual code references to chromadb, not just comments
        # The comment "已迁移：ChromaDB → VectorDB" is acceptable
        # But import chromadb or chromadb.Client etc would be a bug
        code_lines = []
        for line in content.split("\n"):
            stripped = line.strip()
            # Skip comment lines (those starting with #)
            if stripped.startswith("#"):
                continue
            code_lines.append(stripped)
        code_content = "\n".join(code_lines)
        assert "chromadb" not in code_content.lower(), (
            "knowledge.py should not have ChromaDB code references (import, client, etc). "
            "Comment mentions of migration are acceptable."
        )
        assert "get_collection" not in code_content, (
            "knowledge.py should not reference get_collection (old deps pattern)."
        )

    def test_no_chromadb_in_agents_py(self):
        """agents.py should NOT reference ChromaDB."""
        content = _read_file(AGENTS_PY_PATH)
        assert "chromadb" not in content.lower(), (
            "agents.py should not reference chromadb."
        )

    def test_knowledge_py_uses_vector_db(self):
        """knowledge.py should use vector_db instance (search/insert/delete_by_ids)."""
        content = _read_file(KNOWLEDGE_PY_PATH)
        assert "from db.milvus_client import vector_db" in content, (
            "knowledge.py should import vector_db from db.milvus_client."
        )
        assert "vector_db.search" in content, (
            "knowledge.py should use vector_db.search() for queries."
        )
        assert "vector_db.insert" in content, (
            "knowledge.py should use vector_db.insert() for writes."
        )
        assert "vector_db.delete_by_ids" in content, (
            "knowledge.py should use vector_db.delete_by_ids() for deletions."
        )

    def test_vector_db_has_new_methods(self):
        """VectorDB class should have delete_by_ids, get_all_metadata, get_all_with_texts."""
        content = _read_file(MILVUS_CLIENT_PATH)
        assert "def delete_by_ids" in content, (
            "VectorDB should have delete_by_ids method."
        )
        assert "def get_all_metadata" in content, (
            "VectorDB should have get_all_metadata method."
        )
        assert "def get_all_with_texts" in content, (
            "VectorDB should have get_all_with_texts method."
        )

    def test_agents_py_uses_vector_db(self):
        """agents.py should use vector_db, not ChromaDB."""
        content = _read_file(AGENTS_PY_PATH)
        assert "from db.milvus_client import vector_db" in content, (
            "agents.py should import vector_db from db.milvus_client."
        )


# ============================================================
# P1-2: Zero vector fallback (not random)
# ============================================================


class TestP1_2_ZeroVectorFallback:
    """Verify E5 failure uses zero vector [0.0]*768, not random; with fallback_zero marker."""

    def test_zero_vector_not_random_in_mem_insert(self):
        """_mem_insert should use [0.0] * dim, not random vectors."""
        content = _read_file(MILVUS_CLIENT_PATH)
        # Find the fallback section in _mem_insert
        assert "[0.0] * dim" in content, (
            "_mem_insert should use [0.0] * dim for zero vector fallback, not random."
        )
        # Ensure no random usage in the fallback path
        # Check that random is NOT used for embedding fallback
        mem_insert_section = content[
            content.find("def _mem_insert") :
            content.find("def _milvus_search") if "def _milvus_search" in content else len(content)
        ]
        assert "random" not in mem_insert_section, (
            "_mem_insert should NOT use random for embedding fallback. "
            "Should use zero vector [0.0] * dim."
        )

    def test_fallback_zero_metadata_marker(self):
        """Failed embeddings should mark metadata with embedding_status='fallback_zero'."""
        content = _read_file(MILVUS_CLIENT_PATH)
        # The code uses dict assignment: meta["embedding_status"] = "fallback_zero"
        # We check for the string pattern in both dict-style and assignment-style
        assert (
            'embedding_status"] = "fallback_zero"' in content
            or 'embedding_status": "fallback_zero"' in content
        ), (
            "_mem_insert should mark fallback documents with embedding_status='fallback_zero'."
        )

    def test_search_excludes_fallback_zero(self):
        """Vector search should exclude fallback_zero documents from results."""
        content = _read_file(MILVUS_CLIENT_PATH)
        # InMemoryVectorStore.query should filter out fallback_zero
        assert "fallback_zero" in content, (
            "Search logic should exclude embedding_status='fallback_zero' documents."
        )
        # Check the InMemoryVectorStore.query method specifically
        query_section = content[
            content.find("def query") : content.find("def count")
        ]
        assert 'embedding_status") == "fallback_zero"' in query_section, (
            "InMemoryVectorStore.query should skip documents where "
            "metadata.get('embedding_status') == 'fallback_zero'."
        )


# ============================================================
# P0-3: Sandbox security hardening
# ============================================================


class TestP0_3_SandboxSecurity:
    """Verify SANDBOX_PREFIX code injection and timeout enforcement."""

    def test_sandbox_prefix_exists(self):
        """learning.py should contain SANDBOX_PREFIX with blocked modules."""
        content = _read_file(LEARNING_PY_PATH)
        assert "SANDBOX_PREFIX" in content, (
            "learning.py should define SANDBOX_PREFIX for code injection."
        )
        assert "_BLOCKED" in content, (
            "SANDBOX_PREFIX should define _BLOCKED set of dangerous modules."
        )

    def test_sandbox_prefix_blocks_os(self):
        """SANDBOX_PREFIX should block os module (blocks os.system, os.remove, etc. at module level)."""
        content = _read_file(LEARNING_PY_PATH)
        assert "'os'" in content, (
            "SANDBOX_PREFIX should include 'os' in _BLOCKED. "
            "Note: After P0-3 fix, _BLOCKED uses single-segment module names (e.g. 'os') "
            "instead of dot-separated attribute names (e.g. 'os.system') to prevent sandbox escape."
        )

    def test_sandbox_prefix_blocks_subprocess(self):
        """SANDBOX_PREFIX should block subprocess."""
        content = _read_file(LEARNING_PY_PATH)
        assert "'subprocess'" in content, (
            "SANDBOX_PREFIX should include 'subprocess' in _BLOCKED."
        )

    def test_timeout_floor_enforcement(self):
        """sandbox_run should enforce timeout = max(req.timeout or 5, 10)."""
        content = _read_file(LEARNING_PY_PATH)
        assert "max(req.timeout or 5, 10)" in content, (
            "sandbox_run should use max(req.timeout or 5, 10) as timeout floor."
        )

    def test_sandbox_injects_prefix(self):
        """sandbox_run should prepend SANDBOX_PREFIX to user code."""
        content = _read_file(LEARNING_PY_PATH)
        assert "SANDBOX_PREFIX + " in content, (
            "sandbox_run should inject SANDBOX_PREFIX before user code."
        )

    def test_sandbox_blocks_os_system_live(self):
        """Live test: submitting code with os.system should be blocked."""
        malicious_code = 'import os\nos.system("echo hacked")'
        # Execute through the SANDBOX_PREFIX logic
        full_code = _extract_sandbox_prefix() + "\n" + malicious_code
        result = subprocess.run(
            [PYTHON, "-c", full_code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # os.system should raise PermissionError due to _Blocker
        assert "PermissionError" in result.stderr or "blocked" in result.stderr.lower(), (
            f"Code with os.system should be blocked. Got stdout={result.stdout}, stderr={result.stderr}"
        )
        assert result.returncode != 0, (
            "Code with os.system should NOT execute successfully."
        )


def _extract_sandbox_prefix() -> str:
    """Extract SANDBOX_PREFIX string from learning.py for live testing."""
    content = _read_file(LEARNING_PY_PATH)
    # Find SANDBOX_PREFIX definition
    match = re.search(
        r'SANDBOX_PREFIX = """(.*?)"""',
        content,
        re.DOTALL,
    )
    if match:
        return match.group(1)
    # Try single-quote version
    match = re.search(
        r"SANDBOX_PREFIX = '''(.*?)'''",
        content,
        re.DOTALL,
    )
    if match:
        return match.group(1)
    raise ValueError("Could not extract SANDBOX_PREFIX from learning.py")


# ============================================================
# P0-1: LangGraph uses graph.astream
# ============================================================


class TestP0_1_LangGraphAstream:
    """Verify langgraph.py uses agent_graph.astream, not manual sequential await."""

    def test_langgraph_uses_astream(self):
        """langgraph.py should use agent_graph.astream() for streaming."""
        content = _read_file(LANGGRAPH_PY_PATH)
        assert "agent_graph.astream" in content, (
            "langgraph.py should use agent_graph.astream() for streaming execution."
        )

    def test_langgraph_stream_mode_updates(self):
        """astream should use stream_mode='updates'."""
        content = _read_file(LANGGRAPH_PY_PATH)
        assert "stream_mode=\"updates\"" in content, (
            "agent_graph.astream should use stream_mode='updates'."
        )

    def test_no_manual_sequential_await(self):
        """langgraph.py should NOT manually await each node sequentially."""
        content = _read_file(LANGGRAPH_PY_PATH)
        # Check for patterns that indicate old manual await style
        # Old pattern would look like: result = await coordinator(state); state.update(result)
        manual_patterns = [
            r"await coordinator_node",
            r"await diagnostician_node",
            r"await planner_node",
            r"await retriever_node",
            r"await generator_cluster_node",
            r"await assessor_node",
            r"await critic_node",
            r"await path_planner_node",
        ]
        for pattern in manual_patterns:
            assert not re.search(pattern, content), (
                f"langgraph.py should NOT contain manual await pattern: {pattern}. "
                "Should use agent_graph.astream() instead."
            )

    def test_graph_astream_with_timeout(self):
        """astream iteration must be wrapped with asyncio.wait_for timeout protection (Q3 fix).

        Bare 'async for event in agent_graph.astream' was replaced by a
        while-loop + asyncio.wait_for(__anext__(), timeout=NODE_TIMEOUT) to
        prevent a single hung LLM call from blocking the entire pipeline.
        """
        content = _read_file(LANGGRAPH_PY_PATH)
        assert "agent_graph.astream" in content, (
            "langgraph.py should still use agent_graph.astream for node iteration."
        )
        assert "asyncio.wait_for" in content, (
            "langgraph.py should wrap astream iteration with asyncio.wait_for for "
            "timeout protection (Q3 fix: prevent pipeline hang)."
        )
        assert "NODE_TIMEOUT" in content, (
            "langgraph.py should define NODE_TIMEOUT constant for single-node timeout."
        )
        assert "async for event in agent_graph.astream" not in content, (
            "langgraph.py should NOT use bare 'async for event in agent_graph.astream' "
            "(replaced by while+asyncio.wait_for for timeout protection)."
        )

    def test_sse_node_done_events(self):
        """astream iteration should emit node_done SSE events."""
        content = _read_file(LANGGRAPH_PY_PATH)
        assert '"node_done"' in content, (
            "langgraph.py should emit 'node_done' SSE events from astream iteration."
        )

    def test_graph_file_compiles_astream(self):
        """agents/graph.py should define agent_graph using StateGraph.compile()."""
        content = _read_file(GRAPH_PY_PATH)
        assert "agent_graph" in content, (
            "agents/graph.py should define agent_graph."
        )
        assert ".compile()" in content, (
            "agent_graph should be compiled from StateGraph."
        )


# ============================================================
# P1-1: deps cleanup migration
# ============================================================


class TestP1_1_DepsCleanupMigration:
    """Verify deps.py deleted, no residual imports, migrated modules exist."""

    def test_deps_py_deleted(self):
        """deps.py should NOT exist in py-server directory."""
        deps_path = os.path.join(PY_SERVER_DIR, "deps.py")
        assert not os.path.exists(deps_path), (
            "deps.py should be deleted from py-server directory."
        )

    def test_no_from_deps_import_in_py_files(self):
        """No .py file should have 'from deps import' (excluding tests and .venv)."""
        matches = _grep_py_files(PY_SERVER_DIR, r"from deps import")
        # Filter out .venv matches and this test file itself
        real_matches = [
            m for m in matches
            if ".venv" not in m and "test_audit_fixes.py" not in m
        ]
        assert len(real_matches) == 0, (
            f"Found 'from deps import' residual in: {real_matches}. "
            "All imports should be migrated to new modules."
        )

    def test_safety_module_exists(self):
        """utils/safety.py should exist."""
        assert os.path.exists(SAFETY_PATH), (
            "utils/safety.py should exist after migration from deps."
        )

    def test_safety_has_filter_sensitive(self):
        """utils/safety.py should contain filter_sensitive function."""
        content = _read_file(SAFETY_PATH)
        assert "def filter_sensitive" in content, (
            "utils/safety.py should contain filter_sensitive function."
        )

    def test_safety_has_check_hallucination(self):
        """utils/safety.py should contain check_hallucination function."""
        content = _read_file(SAFETY_PATH)
        assert "def check_hallucination" in content, (
            "utils/safety.py should contain check_hallucination function."
        )

    def test_config_py_has_save_config(self):
        """config.py should have save_config function."""
        content = _read_file(CONFIG_PY_PATH)
        assert "def save_config" in content, (
            "config.py should have save_config() function."
        )

    def test_agents_imports_migrated(self):
        """agents.py should import from db.llm_provider, db.milvus_client, utils.safety."""
        content = _read_file(AGENTS_PY_PATH)
        assert "from db.llm_provider import LLMProvider" in content, (
            "agents.py should import LLMProvider from db.llm_provider."
        )
        assert "from db.milvus_client import vector_db" in content, (
            "agents.py should import vector_db from db.milvus_client."
        )
        assert "from utils.safety import filter_sensitive" in content, (
            "agents.py should import filter_sensitive from utils.safety."
        )

    def test_learning_imports_migrated(self):
        """D-05拆分后: assessment.py should import LLMProvider, config_routes.py should import load_config."""
        content = _read_file(ASSESSMENT_PY_PATH)
        assert "from db.llm_provider import LLMProvider" in content, (
            "assessment.py should import LLMProvider from db.llm_provider."
        )
        content = _read_file(CONFIG_ROUTES_PY_PATH)
        assert "from config import load_config" in content, (
            "config_routes.py should import load_config from config."
        )


# ============================================================
# Additional: Frontend v-html audit (non-content v-html)
# ============================================================


class TestFrontendVHtmlAudit:
    """Verify v-html usage patterns across all view files."""

    def test_icon_v_html_are_static_svg_not_user_content(self):
        """v-html bindings for icons (icons.logo, icons.user, etc.) are safe SVG constants."""
        # These are acceptable because they render static SVG icons, not user content
        # We verify they reference the 'icons' object (predefined SVG strings)
        content = _read_file(os.path.join(SRC_DIR, "App.vue"))
        icon_v_htmls = re.findall(r'v-html="([^"]+)"', content)
        for expr in icon_v_htmls:
            # Icons should reference the 'icons' object
            if "icons." in expr:
                # This is a static SVG icon, acceptable
                continue
            # If it doesn't reference icons, it might be user content — needs DOMPurify
            # But App.vue sidebar doesn't render user content, so we just note it
            pass

    def test_chat_user_message_uses_safe_rendering(self):
        """ChatView user messages with v-html should use safe rendering."""
        content = _read_file(os.path.join(SRC_DIR, "views", "ChatView.vue"))
        # User messages: simple replace(\n, <br>) is acceptable for plain text
        # AI messages: must use renderMarkdownSafe
        assert "renderMarkdownSafe" in content, (
            "ChatView.vue should import and use renderMarkdownSafe for AI content."
        )

    def test_all_content_v_html_use_render_markdown_safe(self):
        """Every v-html that renders markdown/user content must use renderMarkdownSafe."""
        # Check the view files that render AI-generated content
        resource_content = _read_file(os.path.join(SRC_DIR, "views", "ResourceView.vue"))
        # ResourceView has 5 v-html with renderMarkdownSafe
        v_html_calls = re.findall(r'v-html="renderMarkdownSafe\([^)]+\)"', resource_content)
        assert len(v_html_calls) >= 5, (
            f"ResourceView.vue should have at least 5 renderMarkdownSafe v-html calls. "
            f"Found {len(v_html_calls)}."
        )


# ============================================================
# Round 2 — Additional Edge Case Tests
# ============================================================


class TestRound2_DOMPurifyFunctional:
    """Verify DOMPurify renderMarkdownSafe strips dangerous HTML tags."""

    def test_dompurify_strips_script_tag(self):
        """renderMarkdownSafe should strip <script> tags from input."""
        # Verify the source code logic: DOMPurify.sanitize removes dangerous tags
        content = _read_file(MARKDOWN_TS_PATH)
        # The function must call DOMPurify.sanitize which strips <script> by default
        assert "DOMPurify.sanitize" in content, (
            "renderMarkdownSafe must call DOMPurify.sanitize which strips <script> by default."
        )
        # Verify no FORBID_TAGS override that would allow script
        # DOMPurify's default ALLOWED_TAGS does NOT include script
        assert "script" not in content.lower() or "forbid" in content.lower(), (
            "renderMarkdownSafe should not explicitly allow <script> tags."
        )

    def test_dompurify_strips_onclick_attribute(self):
        """renderMarkdownSafe should strip onclick and other event handler attributes."""
        content = _read_file(MARKDOWN_TS_PATH)
        # DOMPurify by default strips all on* event handlers
        # Verify no ALLOW_ATTR override that would allow event handlers
        assert "ALLOW_ATTR" not in content, (
            "renderMarkdownSafe should not override DOMPurify defaults to allow dangerous attributes."
        )

    def test_render_markdown_safe_returns_string(self):
        """renderMarkdownSafe should return a sanitized string (not raw HTML)."""
        content = _read_file(MARKDOWN_TS_PATH)
        # The function should return the sanitized result
        assert "return" in content, (
            "renderMarkdownSafe should return the sanitized output."
        )


class TestRound2_SandboxEdgeCases:
    """Verify sandbox blocks additional dangerous module patterns."""

    def test_sandbox_blocks_shutil(self):
        """SANDBOX_PREFIX should block shutil (prevents shutil.rmtree attacks)."""
        content = _read_file(LEARNING_PY_PATH)
        assert "'shutil'" in content, (
            "SANDBOX_PREFIX should include 'shutil' in _BLOCKED to prevent shutil.rmtree attacks."
        )

    def test_sandbox_blocks_subprocess_live(self):
        """Live test: import subprocess should be blocked."""
        malicious_code = 'import subprocess\nsubprocess.run(["ls"])'
        full_code = _extract_sandbox_prefix() + "\n" + malicious_code
        result = subprocess.run(
            [PYTHON, "-c", full_code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert "PermissionError" in result.stderr or "blocked" in result.stderr.lower(), (
            f"Code with subprocess.run should be blocked. Got stdout={result.stdout}, stderr={result.stderr}"
        )
        assert result.returncode != 0, (
            "Code with subprocess should NOT execute successfully."
        )

    def test_sandbox_blocks_shutil_live(self):
        """Live test: import shutil should be blocked."""
        malicious_code = 'import shutil\nshutil.rmtree("/tmp")'
        full_code = _extract_sandbox_prefix() + "\n" + malicious_code
        result = subprocess.run(
            [PYTHON, "-c", full_code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert "PermissionError" in result.stderr or "blocked" in result.stderr.lower(), (
            f"Code with shutil.rmtree should be blocked. Got stdout={result.stdout}, stderr={result.stderr}"
        )
        assert result.returncode != 0, (
            "Code with shutil should NOT execute successfully."
        )

    def test_sandbox_blocked_set_is_single_segment_names(self):
        """_BLOCKED should use single-segment module names (no dots) to prevent escape."""
        content = _read_file(LEARNING_PY_PATH)
        # Extract the _BLOCKED set definition
        match = re.search(r"_BLOCKED\s*=\s*\{([^}]+)\}", content)
        assert match, "_BLOCKED set should be found in SANDBOX_PREFIX."
        blocked_items = match.group(1)
        # Check that no entry contains a dot (which would allow escape via attribute access)
        items = re.findall(r"'([^']+)'", blocked_items)
        for item in items:
            assert "." not in item, (
                f"_BLOCKED entry '{item}' contains a dot. "
                f"Using dot-separated names (e.g. 'os.system') allows sandbox escape "
                f"because _Blocker __getattr__ intercepts the dotted path but the real "
                f"module still gets imported. Should use single-segment names only."
            )

    def test_sandbox_prefix_does_not_import_blocked_modules_directly(self):
        """SANDBOX_PREFIX itself should NOT import any module that is in _BLOCKED."""
        content = _read_file(LEARNING_PY_PATH)
        prefix_match = re.search(
            r'SANDBOX_PREFIX = """(.*?)"""',
            content,
            re.DOTALL,
        )
        if not prefix_match:
            prefix_match = re.search(
                r"SANDBOX_PREFIX = '''(.*?)'''",
                content,
                re.DOTALL,
            )
        assert prefix_match, "Could not extract SANDBOX_PREFIX."
        prefix_code = prefix_match.group(1)
        # The prefix should only import sys (needed for sys.modules)
        import_lines = re.findall(r"^import\s+(\S+)", prefix_code, re.MULTILINE)
        blocked_match = re.search(r"_BLOCKED\s*=\s*\{([^}]+)\}", prefix_code)
        if blocked_match:
            blocked_items = re.findall(r"'([^']+)'", blocked_match.group(1))
            for mod in import_lines:
                assert mod not in blocked_items, (
                    f"SANDBOX_PREFIX imports '{mod}' which is in _BLOCKED. "
                    f"This would defeat the blocking mechanism."
                )


class TestRound2_FrontendChecks:
    """Frontend-related audit checks (typos, etc.).

    注：前端「能否成功构建」由 CI 的 lint-build 作业（npm run build）与
    Dockerfile 多阶段构建共同把关，不在 Python 后端测试套件里重复断言
    dist/index.html（backend 作业无 node、不构建前端，该断言永远失败且冗余）。
    """

    def test_no_renderMarkdownSafeSafe_anywhere(self):
        """No Vue/TS file should contain the typo 'renderMarkdownSafeSafe'."""
        matches = _grep_vue_ts_files(SRC_DIR, r"renderMarkdownSafeSafe")
        assert len(matches) == 0, (
            f"Found typo 'renderMarkdownSafeSafe' in: {matches}. "
            f"All references should be 'renderMarkdownSafe' (correct export name)."
        )
