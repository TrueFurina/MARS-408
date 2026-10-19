# -*- coding: utf-8 -*-
"""scripts/audit_api_contract.py 的语义与门禁契约测试（2026-10-17 新增）

锁定的不变量分两层：

1. **匹配语义**（单元级）：段级比对 + 前端惯用法容错——
   字面量填充路径参数 / 模板 ${...} / query 串拼接 / 泛型类型参数 / fetch 默认 GET。
   这些容错规则是「真实仓库 A 类归零」的前提，任何一条被改坏都会让
   审计从「准」变「吵」（误报）或「聋」（漏报），故逐条锁定。
2. **门禁契约**（集成级）：
   - --gate 且 A 类 > 0 → exit 1（阻断）；
   - --gate 且 A 类 = 0 → exit 0；
   - openapi.json 零路由 / 前端扫描面为零 → exit 2（fail-closed：
     "照不到"不得当作"干净"）。
3. **真实仓库不变量**：对仓库真值跑审计，A 类必须为 0——
   「前端每一个调用都找得到后端路由」是长期契约，新增前端调用打到
   不存在的端点时本测试即红（与 --gate 同一判据，本地可复跑）。
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "audit_api_contract.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_api_contract", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ac = _load_module()


# ── 1. 匹配语义 ──────────────────────────────────────────────

def test_literal_fills_path_param_matches():
    """/literacy/report/demo 命中 /api/literacy/report/{user_id}（段级占位匹配）。"""
    assert ac.path_match("/api/literacy/report/{}", "/api/literacy/report/demo")


def test_template_placeholder_matches():
    """/career/classes/${id} 归一后命中 /api/career/classes/{}。"""
    norm = ac.norm_path("/career/classes/${id}", frontend=True)
    assert norm == "/api/career/classes/{}"
    assert ac.path_match("/api/career/classes/{}", norm)


def test_query_string_concatenation_tolerated():
    """/experiments${suffix}（suffix 为 query 串）命中 /api/experiments。"""
    norm = ac.norm_path("/experiments${suffix}", frontend=True)
    assert ac.path_match("/api/experiments", norm)


def test_generic_type_args_parsed():
    """api.get<{ classes: ClassItem[] }>('/career/classes') 的类型参数不得吞掉路径。"""
    text = "const res = await api.get<{ classes: ClassItem[] }>('/career/classes')"
    assert ("GET", "/api/career/classes") in ac.extract_calls(text)


def test_post_stream_and_blob_methods_recognized():
    """postStream/upload/postBlob/getBlob 与 get/post/put/delete 同为 path 首参。"""
    text = (
        "api.postStream('/chat/stream', {})\n"
        "api.getBlob('/career/session/1/export-report')\n"
        "api.upload('/knowledge/upload', fd)\n"
        "api.postBlob('/x', {})\n"
    )
    calls = ac.extract_calls(text)
    assert ("POST", "/api/chat/stream") in calls
    assert ("GET", "/api/career/session/1/export-report") in calls
    assert ("POST", "/api/knowledge/upload") in calls
    assert ("POST", "/api/x") in calls


def test_fetch_defaults_to_get():
    """裸 fetch('/api/status') 按 GET 裁定（fetch 默认方法）。"""
    assert ("FETCH", "/api/status") in ac.extract_calls("fetch('/api/status')")
    missing, _ = ac.audit({("GET", "/api/status")}, [("FETCH", "/api/status", "x.ts")])
    assert missing == []


def test_method_mismatch_is_flagged_not_dropped():
    """路径存在但方法不符（前端 POST、后端仅 GET）必须进 A 类并标注。"""
    backend = {("GET", "/api/foo")}
    missing, _ = ac.audit(backend, [("POST", "/api/foo", "x.vue")])
    assert len(missing) == 1
    assert missing[0]["method_mismatch"] is True


def test_unknown_path_is_flagged():
    backend = {("GET", "/api/foo")}
    missing, _ = ac.audit(backend, [("GET", "/api/nope", "x.vue")])
    assert len(missing) == 1
    assert missing[0]["method_mismatch"] is False


def test_orphans_detected_without_param_false_positive():
    """后端 /api/skills/run/{} 被前端 /skills/run-stream/${id} 消费 ⇒ 不算孤儿。"""
    backend = {("POST", "/api/skills/run/{}"), ("POST", "/api/skills/run-stream/{}")}
    frontend = [("POST", "/api/skills/run-stream/abc", "SkillDetailView.vue")]
    _, orphans = ac.audit(backend, frontend)
    assert orphans == ["POST /api/skills/run/{}"]


# ── 2. 门禁契约（合成夹具，subprocess 验退出码） ──────────────

def _write_fixture(root: Path, paths: dict, calls: list) -> tuple:
    openapi = root / "openapi.json"
    openapi.write_text(json.dumps({"paths": paths}), encoding="utf-8")
    src = root / "src"
    src.mkdir(exist_ok=True)
    (src / "a.ts").write_text("\n".join(calls), encoding="utf-8")
    return openapi, src


def _run_gate(openapi: Path, src: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--gate",
         "--openapi", str(openapi), "--src", str(src)],
        capture_output=True, text=True, encoding="utf-8", timeout=120)


def test_gate_blocks_when_frontend_calls_missing_route(tmp_path):
    openapi, src = _write_fixture(
        tmp_path,
        {"/api/foo": {"get": {}}},
        ["api.get('/foo')", "api.post('/bar')"],  # /bar 不存在 ⇒ A 类 1 处
    )
    r = _run_gate(openapi, src)
    assert r.returncode == 1
    assert "A 类违约" in r.stderr


def test_gate_passes_when_contract_clean(tmp_path):
    openapi, src = _write_fixture(
        tmp_path,
        {"/api/foo": {"get": {}}},
        ["api.get('/foo')"],
    )
    r = _run_gate(openapi, src)
    assert r.returncode == 0
    assert "A 类为 0" in r.stdout


def test_fail_closed_on_empty_spec(tmp_path):
    """openapi.json 零路由 ⇒ exit 2（快照损坏不得静默放行）。"""
    openapi, src = _write_fixture(tmp_path, {}, ["api.get('/foo')"])
    r = _run_gate(openapi, src)
    assert r.returncode == 2


def test_fail_closed_on_empty_scan_surface(tmp_path):
    """src/ 里没有任何可解析调用 ⇒ exit 2（照不到 ≠ 干净）。"""
    openapi, src = _write_fixture(
        tmp_path, {"/api/foo": {"get": {}}}, [])
    r = _run_gate(openapi, src)
    assert r.returncode == 2


def test_fail_closed_on_missing_openapi(tmp_path):
    openapi = tmp_path / "nope.json"
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.ts").write_text("api.get('/foo')", encoding="utf-8")
    r = _run_gate(openapi, src)
    assert r.returncode == 2


# ── 3. 真实仓库不变量 ────────────────────────────────────────

def test_real_repo_contract_a_class_is_zero():
    """仓库真值：前端全部调用都能找到后端路由（A 类 = 0）。

    与 CI --gate 同判据；此处直接在测试进程内复算，便于本地先红后修。
    若因正当的新动态路径模式误报，应修脚本的匹配语义并同步本测试，
    不得靠放宽判据蒙混。
    """
    spec = json.loads((REPO_ROOT / "py-server" / "openapi.json").read_text(encoding="utf-8"))
    backend = ac.collect_backend(spec)
    assert backend, "openapi.json 零路由——快照损坏？"
    frontend = ac.collect_frontend(str(REPO_ROOT / "src"))
    assert frontend, "前端扫描面为零——src/ 缺失或解析规则全失效？"
    missing, _ = ac.audit(backend, frontend)
    assert missing == [], "前端存在打到不存在路由的调用：\n" + "\n".join(
        f"  {c['call']} @ {c['where']}" for c in missing)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
