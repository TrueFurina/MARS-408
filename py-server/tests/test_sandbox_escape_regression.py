# ============================================================
# Sandbox 逃逸面回归测试（2026-10-12 加固收尾）
# ------------------------------------------------------------
# 策略：直接从 api/sandbox.py 抽取真实 SANDBOX_PREFIX，并用与
# 生产 sandbox_run 完全一致的子进程 argv / cwd / env 启动执行，
# 仅去掉 HTTP 层。覆盖旧版（加固前）实测可穿透的逃逸路径：
#   - 别名 open      o = open; o(path)            （AST 只拦直接 open(...)）
#   - getattr 拼接  g = getattr; g(x, '__cla'+'ss__')  （穿 AST + 运行时两层）
#   - codecs.open    import codecs; codecs.open(path)  （持有 _builtin_open 引用）
#   - tokenize.open  import tokenize; tokenize.open(path)
#   - runpy.run_path import runpy; runpy.run_path(path)
#   - 前缀辅助名泄漏 _real_getattr(1, '__class__')  （旧版可穿透）
#
# 不 import sandbox.py 模块本身（避免触发 models/shared 重型依赖链 /
# Windows 原生库 SIGSEGV），纯 subprocess + 正则抽取，双平台均可跑。
# ============================================================

import os
import re
import sys
import shutil
import subprocess
import tempfile

_PY_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SANDBOX_SRC = os.path.join(_PY_SERVER, "api", "sandbox.py")


def _extract_sandbox_prefix() -> str:
    with open(_SANDBOX_SRC, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'SANDBOX_PREFIX = """(.*?)"""', content, re.DOTALL)
    if not m:
        raise RuntimeError("SANDBOX_PREFIX not found in api/sandbox.py")
    return m.group(1)


_PREFIX = _extract_sandbox_prefix()


def _run_in_sandbox(payload: str) -> subprocess.CompletedProcess:
    """复刻 sandbox_run 的子进程启动参数（不含 HTTP 层）。"""
    scratch = tempfile.mkdtemp(prefix="sandbox_test_")
    try:
        tmpfile = os.path.join(scratch, "main.py")
        with open(tmpfile, "w", encoding="utf-8") as f:
            f.write(_PREFIX + "\n" + payload)
        env = {}
        for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP"):
            v = os.environ.get(k)
            if v:
                env[k] = v
        env["HOME" if os.name == "posix" else "USERPROFILE"] = scratch
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        return subprocess.run(
            [sys.executable, "-I", "-S", "-X", "utf8", tmpfile],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=scratch,
            env=env,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# 合法控制组：必须执行成功
class TestSandboxRuntimeAllowlist:
    def test_print(self):
        r = _run_in_sandbox("print(1 + 1)")
        assert r.returncode == 0, r.stderr
        assert "2" in r.stdout

    def test_import_math(self):
        r = _run_in_sandbox("import math\nprint(math.sqrt(4))")
        assert r.returncode == 0, r.stderr
        assert "2.0" in r.stdout

    def test_import_json(self):
        r = _run_in_sandbox("import json\nprint(json.dumps({'k': 1}))")
        assert r.returncode == 0, r.stderr

    def test_raise_traceback(self):
        r = _run_in_sandbox("raise ValueError('boom')")
        assert r.returncode != 0
        assert "boom" in r.stderr  # traceback 可用（linecache 经放行路径读源码）


# 逃逸面：必须被阻断（PermissionError / blocked 且 returncode != 0）
class TestSandboxEscapeBlocking:
    def test_alias_open_blocked(self, tmp_path):
        secret = "SECRET_LEAK_PROOF_%s" % os.getpid()
        target = tmp_path / "secret.txt"
        target.write_text(secret, encoding="utf-8")
        payload = "o = open\nprint(o(%r).read())" % str(target)
        r = _run_in_sandbox(payload)
        assert r.returncode != 0, r.stdout + r.stderr
        assert "PermissionError" in r.stderr or "blocked" in r.stderr.lower(), r.stderr
        assert secret not in r.stdout, "别名 open 读到了文件内容！"

    def test_direct_open_blocked(self, tmp_path):
        secret = "SECRET_LEAK_PROOF_%s" % os.getpid()
        target = tmp_path / "secret.txt"
        target.write_text(secret, encoding="utf-8")
        payload = "print(open(%r).read())" % str(target)
        r = _run_in_sandbox(payload)
        assert r.returncode != 0, r.stdout + r.stderr
        assert "PermissionError" in r.stderr or "blocked" in r.stderr.lower(), r.stderr
        assert secret not in r.stdout

    def test_getattr_concat_blocked(self):
        # g = getattr; g(1, '__cla'+'ss__') 走经典逃逸链起点
        payload = "g = getattr\nprint(g(1, '__cla' + 'ss__'))"
        r = _run_in_sandbox(payload)
        assert r.returncode != 0, r.stdout + r.stderr
        assert "PermissionError" in r.stderr or "blocked" in r.stderr.lower(), r.stderr

    def test_codecs_open_blocked(self, tmp_path):
        secret = "SECRET_LEAK_PROOF_%s" % os.getpid()
        target = tmp_path / "secret.txt"
        target.write_text(secret, encoding="utf-8")
        payload = "import codecs\nprint(codecs.open(%r).read())" % str(target)
        r = _run_in_sandbox(payload)
        assert r.returncode != 0, r.stdout + r.stderr
        assert "PermissionError" in r.stderr or "blocked" in r.stderr.lower(), r.stderr
        assert secret not in r.stdout

    def test_tokenize_open_blocked(self, tmp_path):
        secret = "SECRET_LEAK_PROOF_%s" % os.getpid()
        target = tmp_path / "secret.txt"
        target.write_text(secret, encoding="utf-8")
        payload = "import tokenize\nprint(tokenize.open(%r).read())" % str(target)
        r = _run_in_sandbox(payload)
        assert r.returncode != 0, r.stdout + r.stderr
        assert "PermissionError" in r.stderr or "blocked" in r.stderr.lower(), r.stderr
        assert secret not in r.stdout

    def test_runpy_exec_blocked(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("print('ESCAPED')", encoding="utf-8")
        payload = "import runpy\nrunpy.run_path(%r)" % str(target)
        r = _run_in_sandbox(payload)
        assert r.returncode != 0, r.stdout + r.stderr
        assert "PermissionError" in r.stderr or "blocked" in r.stderr.lower(), r.stderr
        assert "ESCAPED" not in r.stdout


# 前缀辅助名不可达：_real_getattr 等初始化辅助名必须随 _sandbox_init 返回后消失
class TestSandboxPrefixHygiene:
    def test_prefix_helper_not_reachable(self):
        payload = "print(_real_getattr(1, '__class__'))"
        r = _run_in_sandbox(payload)
        # 期望 NameError（辅助名未泄漏）；若实现回退到模块级辅助名则会被穿透
        assert "NameError" in r.stderr, (
            "前缀辅助名 _real_getattr 仍可访问，存在逃逸风险: " + r.stderr
        )
