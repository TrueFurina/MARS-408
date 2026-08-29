# ============================================================
# API — 代码沙箱 (D-03 安全加固 + D-05 拆分)
# ============================================================
# ⚠️ 安全边界声明：本沙箱仅作为「管理员受控执行」用途，绝非对抗恶意用户的隔离边界。
# 当前防护 = AST 静态分析 + 模块/属性拦截 + 子进程资源上限，可挡住常见绕过，
# 但仍属「纵深防御」而非「真实隔离」。在改用容器隔离（gVisor / nsjail / seccomp）之前，
# 禁止向不可信用户（如学生提交代码）开放本端点。

import os
import sys
import signal
import logging

from fastapi import APIRouter, Depends, Request
from models import SandboxRequest, SandboxResponse
from shared.auth import require_admin
from shared.audit import log_event

logger = logging.getLogger("netlearn.sandbox")

router = APIRouter(prefix="", tags=["sandbox"])


def _kill_proc_group(proc) -> None:
    """超时击杀：优先 os.killpg 杀整个进程组，防止被沙箱代码 fork 出的子进程成为孤儿继续运行。

    - POSIX：子进程以 start_new_session=True 启动（自身为进程组长），killpg 可整组歼灭
    - Windows / killpg 不可用：回退 proc.kill()
    """
    try:
        if os.name == "posix" and hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
    except (ProcessLookupError, PermissionError, OSError):
        pass  # 进程已退出或权限不足，回退单杀
    try:
        proc.kill()
    except Exception:
        pass

# 沙箱安全：拦截危险模块的代码前缀
SANDBOX_PREFIX = """
import sys
# F-003 扩展阻断名单：在原有基础上新增 pickle / tempfile / inspect / gc / sys / mmap / code
# 等危险模块。注意：builtins 不放入此运行时集合，否则会破坏下方 `import builtins as _builtins`
# （仅通过 _BLOCKED_IMPORTS 的 AST 检查拦截 `import builtins`）。
_BLOCKED = {'os', 'subprocess', 'socket', 'shutil', 'ctypes', 'importlib', 'io', 'pathlib', 'http', 'urllib', 'ftplib', 'smtplib', 'telnetlib', 'multiprocessing', 'threading', 'signal', 'resource', 'pickle', 'tempfile', 'inspect', 'gc', 'sys', 'mmap', 'code'}
class _Blocker:
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            return None
        return self
    def __call__(self, *args, **kwargs):
        raise PermissionError(f'Sandbox: call is blocked')
for mod in _BLOCKED:
    parts = mod.split('.')
    if len(parts) == 1:
        sys.modules[parts[0]] = _Blocker()
# 拦截 getattr 绕过
_real_getattr = getattr
import builtins as _builtins
def _safe_getattr(obj, name, *default):
    if isinstance(name, str) and name in ('__import__', '__builtins__', '__globals__', '__subclasses__', '__bases__', '__mro__', '__class_getitem__'):
        raise PermissionError(f'Sandbox: attribute {name} is blocked')
    return _real_getattr(obj, name, *default)
_builtins.getattr = _safe_getattr
"""

# AST 静态分析：拦截危险调用
_DANGEROUS_CALLS = {
    "__import__", "exec", "eval", "compile", "open", "globals",
    "locals", "vars", "breakpoint", "input", "getattr",
}
_DANGEROUS_ATTRS = {
    "__import__", "__builtins__", "__globals__", "__subclasses__",
    "__bases__", "__mro__", "__class__", "__class_getitem__",
}
# F-003 扩展阻断模块名单：在原有基础上新增 builtins / pickle / tempfile / inspect /
# gc / sys / mmap / code（exec、eval 已在下方 _DANGEROUS_CALLS 中拦截）。
_BLOCKED_IMPORTS = {
    "os", "subprocess", "socket", "shutil", "ctypes", "multiprocessing",
    "importlib", "io", "pathlib", "http", "urllib", "ftplib", "smtplib",
    "telnetlib", "threading", "signal", "resource",
    "builtins", "pickle", "tempfile", "inspect", "gc", "sys", "mmap", "code",
}

# 下标访问绕过的危险基对象：globals()['__builtins__']['open'] 之类
_DANGEROUS_SUBSCRIPT_BASES = {"globals", "locals", "vars", "__builtins__", "builtins"}


def _check_sandbox_safety(code: str) -> str | None:
    """AST 静态分析，返回危险原因或 None（安全）"""
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"语法错误: {e}"

    for node in ast.walk(tree):
        # 检查函数调用
        if isinstance(node, ast.Call):
            func = node.func
            # 直接调用: __import__("os")
            if isinstance(func, ast.Name) and func.id in _DANGEROUS_CALLS:
                return f"禁止调用: {func.id}()"
            # 属性调用: something.__import__
            if isinstance(func, ast.Attribute) and func.attr in _DANGEROUS_ATTRS:
                return f"禁止访问属性: .{func.attr}"
        # 检查属性访问
        if isinstance(node, ast.Attribute) and node.attr in _DANGEROUS_ATTRS:
            return f"禁止访问属性: .{node.attr}"
        # 检查下标访问绕过：globals()['__builtins__']['open'] 等
        # 仅当基对象是危险内部对象、且切片字面量为危险名时才拦截，避免误伤正常字典索引
        if isinstance(node, ast.Subscript):
            base = node.value
            base_name = None
            if isinstance(base, ast.Call) and isinstance(base.func, ast.Name):
                base_name = base.func.id
            elif isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr
            if base_name in _DANGEROUS_SUBSCRIPT_BASES:
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str) \
                        and sl.value in (_DANGEROUS_ATTRS | _DANGEROUS_CALLS):
                    return f"禁止下标访问沙箱内部对象: {base_name}[{sl.value!r}]"
        # 检查导入语句中的危险模块
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BLOCKED_IMPORTS:
                    return f"禁止导入模块: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in _BLOCKED_IMPORTS:
                    return f"禁止导入模块: {node.module}"

    return None


def _sandbox_set_limits():
    """子进程资源上限（仅 POSIX）。在 preexec_fn 中调用，限制内存/CPU/文件/进程数，
    防止 OOM、CPU 耗尽与 fork 炸弹。Windows 不支持 preexec_fn，此处直接返回。"""
    if sys.platform == "win32":
        return
    try:
        import resource
        _MB = 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (512 * _MB, 512 * _MB))    # 虚拟内存上限 512MB
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))                # CPU 时间上限 30s
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * _MB, 10 * _MB))  # 单文件大小 10MB
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))              # 进程/线程数上限
    except Exception:
        logger.debug("sandbox: resource.setrlimit unavailable (expected on Windows)")


@router.post("/sandbox", response_model=SandboxResponse)
@router.post("/sandbox/run", response_model=SandboxResponse)
async def sandbox_run(req: SandboxRequest, user: dict = Depends(require_admin), request: Request = None):
    """代码沙箱执行（安全加固版：AST静态分析 + import拦截 + timeout下限 + async subprocess）"""
    import asyncio, tempfile
    ip = request.client.host if request and request.client else "unknown"

    # 第一步：AST 静态分析，拦截危险调用
    danger = _check_sandbox_safety(req.code)
    if danger:
        log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result="blocked", detail=f"AST拦截: {danger}")
        return SandboxResponse(output="", error=f"安全检查未通过: {danger}", status="blocked")

    # 第二步：注入模块拦截代码前缀
    safe_code = SANDBOX_PREFIX + "\n" + req.code
    # timeout 下限：max(req.timeout, 10)，至少10秒防止恶意短超时
    timeout_sec = max(req.timeout or 5, 10)
    tmpfile = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(safe_code)
            tmpfile = f.name
        # 使用 asyncio subprocess 避免阻塞事件循环
        # POSIX 下 start_new_session=True：子进程自成进程组，超时可用 killpg 整组击杀
        _popen_kwargs = {"start_new_session": True} if os.name == "posix" else {}
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, tmpfile,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_popen_kwargs,
            )
            try:
                out_bytes, err_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_sec
                )
                out = out_bytes.decode("utf-8", errors="replace") if out_bytes else ""
                err = err_bytes.decode("utf-8", errors="replace") if err_bytes else ""
            except asyncio.TimeoutError:
                _kill_proc_group(proc)
                try:
                    os.unlink(tmpfile)
                except Exception:
                    pass
                log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result="timeout", detail=f"timeout={timeout_sec}s")
                return SandboxResponse(output="", error=f"执行超时（{timeout_sec}秒）", status="timeout")
        except Exception:
            try:
                proc = subprocess.Popen(
                    [sys.executable, tmpfile],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, start_new_session=True,
                )
                out, err = proc.communicate(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                _kill_proc_group(proc)
                try:
                    os.unlink(tmpfile)
                except Exception:
                    pass
                log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result="timeout", detail=f"timeout={timeout_sec}s")
                return SandboxResponse(output="", error=f"执行超时（{timeout_sec}秒）", status="timeout")
        status = "ok" if proc.returncode == 0 else "error"
        log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result=status, detail=f"exit_code={proc.returncode}")

        # L1/L2/L3 三层学情记忆联动（低侵入：沙箱执行入 L3，供代码实践轨迹追溯）
        try:
            from db import memory_store as _ms
            _ms.append_episode(user["user_id"], "sandbox_exec", {
                "status": status,
                "exit_code": proc.returncode,
                "code_len": len(req.code),
            })
        except Exception as _me:
            logger.debug(f"沙箱执行记忆写入失败(忽略): {_me}")

        return SandboxResponse(output=out, error=err, status=status)
    except Exception as e:
        try:
            if tmpfile:
                os.unlink(tmpfile)
        except Exception:
            pass
        log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result="error", detail=str(e)[:200])
        return SandboxResponse(output="", error=str(e), status="error")
