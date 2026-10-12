# ============================================================
# API — 代码沙箱 (D-03 安全加固 + D-05 拆分 + 2026-10-12 逃逸面闭合)
# ============================================================
# ⚠️ 安全边界声明：本沙箱仅作为「管理员受控执行」用途，绝非对抗恶意用户的隔离边界。
#
# 防护层（2026-10-12 起，由外到内）：
#   1. AST 静态黑名单（危险调用/属性/下标/导入）
#   2. 子进程 sys.modules 投毒（被禁模块导入即得 _Blocker）
#   3. 子进程内置函数清洗（open/eval/exec/... 改为抛 PermissionError 的桩，
#      消灭 `o = open; o('x')` 别名绕过——旧版实测可直接读 py-server/.env）
#   4. getattr 防绕过（逃逸链 dunder 名单式拒绝，非一律拒绝——否则 import
#      机制与 enum 等自造 dunder 的库会大面积崩掉），消灭
#      `g = getattr; g(x, '__cla'+'ss__')` 字符串拼接穿两层
#   5. 文件读取原语收尾（FileLoader.get_data / codecs.open / tokenize.open），
#      open 清洗后这三条是仅剩的任意文件读入口
#   6. 子进程隔离启动（-I -S 忽略 PYTHONPATH/用户 site 且不执行 .pth 钩子、
#      最小 env、cwd=独立 scratch 目录，逃逸代码摸不到项目模块与相对路径文件）
#   7. POSIX 资源上限（preexec_fn 接线，旧版从未生效过）
#
# 残余风险（诚实声明）：以上仍是「纵深防御」而非「真实隔离」——模块名单式
# 阻断不排除存在未被枚举的第三方库自带读文件原语；在改用容器隔离
# （gVisor / nsjail / seccomp）之前，禁止向不可信用户（如学生提交代码）
# 开放本端点。

import os
import sys
import signal
import shutil
import logging
import subprocess

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

def _run_blocking_proc(argv: list, timeout: int, cwd: str = None, env: dict = None):
    """同步执行兜底（仅当 asyncio 子进程不可用时），在 asyncio.to_thread 中运行以免阻塞事件循环。

    返回 (out, err, returncode)。超时则击杀进程组后抛出 subprocess.TimeoutExpired。
    start_new_session 仅 POSIX 生效（Windows 不支持该参数，由 _kill_proc_group 回退 proc.kill）。
    cwd/env 由调用方传入隔离值（见 sandbox_run 的 scratch 目录与 _sandbox_child_env）。
    """
    popen_kwargs = {"start_new_session": True} if os.name == "posix" else {}
    if _RESOURCE is not None:
        popen_kwargs["preexec_fn"] = _sandbox_set_limits
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=cwd, env=env, **popen_kwargs
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_proc_group(proc)
        raise
    return out, err, proc.returncode


# 沙箱安全：拦截危险模块的代码前缀（在子进程中、用户代码之前执行）
SANDBOX_PREFIX = """
def _sandbox_init():
    # 整个初始化包进一个函数：前缀与用户代码同处 __main__ 命名空间，任何模块级
    # 辅助名（_real_getattr / _deny / _Blocker，乃至 import 进来的 sys）都是
    # 现成的绕过入口——旧版前缀即因此可被 `_real_getattr(1, '__class__')`
    # 一句话穿透（2026-10-12 复核发现）。函数局部量在返回后即消失，只有已装进
    # builtins / sys.modules 的拦截存活。
    import sys
    import os as _os

    def _deny(*a, **k):
        raise PermissionError('Sandbox: builtin is blocked')

    # 1) site-packages 手动补回（必须在下方投毒之前）。
    #    子进程以 -S 启动（见 sandbox_run argv）：site 不初始化，第三方 .pth 启动
    #    钩子不执行。这一步是必须的——2026-10-12 实测：setuptools 的
    #    _distutils_hack 在 find_spec 里调 locals()，而 locals 已被下方清洗成
    #    _deny，导致**任何** import（含 import math）都以 PermissionError 失败。
    #    为保持与旧版一致的能力面，此处把 purelib 补回 sys.path（放在投毒前，
    #    否则 import sysconfig 会拿到被投毒的 os）。
    try:
        import sysconfig as _sc
        _pl = _sc.get_paths().get('purelib')
        if _pl and _pl not in sys.path:
            sys.path.append(_pl)
    except Exception:
        pass

    # 2) 收尾「文件读取原语」：open 被清洗后，这三条是仅剩的任意文件读入口
    #    （py-server/.env 里的凭据即经此泄露）。
    #    - FileLoader.get_data：`getattr(某模块, '__loader__').get_data(path)`
    #    - codecs.open / tokenize.open：两者各自持有 _builtin_open 引用，
    #      不受 open 清洗影响。
    #    tokenize.open 仅放行沙箱脚本自身：linecache 经它读源码，traceback 的
    #    源码行显示依赖它；其余路径一律拒绝。
    _self = _os.path.realpath(__file__)
    try:
        from importlib.abc import FileLoader as _FL
        _FL.get_data = _deny
    except Exception:
        pass
    try:
        import codecs as _codecs
        _codecs.open = _deny
    except Exception:
        pass
    try:
        import tokenize as _tokenize
        _real_tok_open = _tokenize.open
        def _safe_tokenize_open(filename, *a, **k):
            try:
                if _os.path.realpath(filename) == _self:
                    return _real_tok_open(filename, *a, **k)
            except Exception:
                pass
            raise PermissionError('Sandbox: tokenize.open is blocked')
        _tokenize.open = _safe_tokenize_open
    except Exception:
        pass

    # 3) 模块投毒。F-003 扩展阻断名单：在原有基础上新增 pickle / tempfile /
    #    inspect / gc / mmap / code 等危险模块。注意：builtins 与 sys 不放入此
    #    运行时集合——builtins 用于下方 `import builtins as _builtins` 的内置
    #    清洗；sys 用于本函数 `sys.modules[mod] = _Blocker()` 的拦截机制，若把
    #    sys 也列入 _BLOCKED，会令 `sys.modules['sys']` 自身被覆盖为 _Blocker()
    #    而自伤机制（仅通过 _BLOCKED_IMPORTS 的 AST 检查拦截 `import builtins`）。
    #    site 入列：阻止用户代码 `import site` 重新触发 .pth 钩子（绕开 -S）。
    #    runpy / zipimport 入列：run_path 任意代码执行、zipimporter.get_data。
    _BLOCKED = {'os', 'subprocess', 'socket', 'shutil', 'ctypes', 'importlib', 'io', 'pathlib', 'http', 'urllib', 'ftplib', 'smtplib', 'telnetlib', 'multiprocessing', 'threading', 'signal', 'resource', 'pickle', 'tempfile', 'inspect', 'gc', 'mmap', 'code', 'site', 'runpy', 'zipimport'}
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

    # 4) 内置函数清洗（子进程内一次性执行，全局改写安全）。
    #    旧版仅靠 AST 黑名单拦 `open(...)` 这类*直接调用*，但 `o = open; o('x')`
    #    这种别名写法 AST 看到的是 Name 'o'，两层都放行——实测可直接读服务器上
    #    任何文件。故在子进程内把危险内置改成抛 PermissionError 的桩：别名取到的
    #    是桩，直接调用的也是桩。globals/locals/vars 同批清洗：其返回值里的
    #    `__builtins__` / `__loader__` 是逃逸跳板（AST 本就禁止用户代码调用它们，
    #    此处只是堵别名路由，不构成新的能力损失）。
    #    ⚠️ eval/exec/compile **不能**清洗：import 机制执行纯 Python 模块走
    #    `exec(module_code, module.__dict__)`（_bootstrap.py 的 _call_with_frames_
    #    removed(exec, ...)），ast.literal_eval 等也要 compile；清洗掉会让
    #    import json / import decimal 这类**未预载**模块全部失败（2026-10-12 实测）。
    #    三者并不构成新增能力面：用户代码本身就是任意 Python，且 exec 传入自定义
    #    globals 时 `__builtins__` 要么被自动填为本模块（已清洗）、要么只能拿到
    #    清洗后的 builtins 模块，够不到未清洗的内置。
    import builtins as _builtins
    for _bn in ('open', 'input', 'breakpoint',
                'globals', 'locals', 'vars', 'exit', 'quit', 'help'):
        if hasattr(_builtins, _bn):
            setattr(_builtins, _bn, _deny)
    # 注意不在此清洗 __import__：`import math` 语句经 IMPORT_NAME 字节码查找
    # builtins.__import__，清洗会误杀一切 import。导入面由上方的 sys.modules
    # 投毒 + AST 黑名单把守（`__import__('os')` 拿到的已是 _Blocker）。

    # 5) getattr 防绕过：拒绝「逃逸链 dunder」名单，其余 dunder 放行。
    #    旧版只拦 7 个名字，`g = getattr; g(x, '__cla'+'ss__')` 可同时穿过两层
    #    （AST 看到的调用名是 g；运行时拼出的 __class__ 不在旧名单），进而走
    #    `__class__.__base__.__subclasses__` 经典逃逸链。现按逃逸链枚举拒绝。
    #    ⚠️ 不能「一律拒绝所有 dunder」：importlib 自身要 getattr(module,
    #    '__name__'/'__loader__'/'__path__'/...)（_bootstrap.py:546,740,746,
    #    774,785,794,800,892,903,907），enum 等库还自造 dunder
    #    （enum.py:1017 读 __new_member__），一律拒绝会让 import 大面积崩掉
    #    （2026-10-12 实测：import math / import traceback 全灭，故改为名单式）。
    #    残留：__loader__/__spec__ 必须放行（import 机制要用），其上的
    #    get_data/get_source 已由上方 FileLoader.get_data 补丁堵死。
    _real_getattr = getattr
    _ESCAPE_DUNDERS = {
        '__class__', '__base__', '__bases__', '__mro__', '__subclasses__',
        '__globals__', '__builtins__', '__import__', '__code__', '__closure__',
        '__func__', '__self__', '__getattribute__', '__reduce__', '__reduce_ex__',
        '__init_subclass__', '__set_name__', '__class_getitem__',
        '__subclasshook__', '__prepare__',
    }
    def _safe_getattr(obj, name, *default):
        if isinstance(name, str) and name in _ESCAPE_DUNDERS:
            raise PermissionError(f'Sandbox: attribute {name} is blocked')
        return _real_getattr(obj, name, *default)
    _builtins.getattr = _safe_getattr
_sandbox_init()
del _sandbox_init
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
    "site", "runpy", "zipimport",
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


# POSIX 子进程资源上限。⚠️ 本函数在 2026-10-12 之前从未被任何调用路径接线
# （preexec_fn 参数从未传入）——即"文档声称有上限、实际从未生效"的假防护。
# 现由 sandbox_run 以 preexec_fn 正式接线（仅 POSIX；Windows 无 resource 模块）。
# resource 在模块导入时一次性装好（父进程、单线程期），preexec_fn 体内只做纯
# setrlimit 调用，避免 fork 后在子进程 import 触发锁竞争。
# 不设 RLIMIT_AS：虚拟内存口径会把 numpy/torch 这类重库的正常 import 误杀
# （VA 计数常达数 GB），而纯分配炸弹本就会触发 MemoryError，收益不抵误伤。
_RESOURCE = None
if os.name == "posix":
    try:
        import resource as _resource_module
        _RESOURCE = _resource_module
    except Exception:
        _RESOURCE = None


def _sandbox_set_limits():
    """子进程资源上限（仅 POSIX，在 preexec_fn 中调用）：限制 CPU/文件/进程/描述符，
    防 CPU 耗尽、磁盘写爆与 fork 炸弹。Windows 不支持 preexec_fn，_RESOURCE 为 None 时直接返回。"""
    if _RESOURCE is None:
        return
    try:
        _MB = 1024 * 1024
        _RESOURCE.setrlimit(_RESOURCE.RLIMIT_CPU, (65, 65))                # CPU 时间上限 65s（> 最大墙钟超时 60s，墙钟先杀）
        _RESOURCE.setrlimit(_RESOURCE.RLIMIT_FSIZE, (10 * _MB, 10 * _MB))  # 单文件大小 10MB
        _RESOURCE.setrlimit(_RESOURCE.RLIMIT_NPROC, (64, 64))              # 进程/线程数上限
        _RESOURCE.setrlimit(_RESOURCE.RLIMIT_NOFILE, (64, 64))             # 文件描述符上限
        _RESOURCE.setrlimit(_RESOURCE.RLIMIT_CORE, (0, 0))                 # 不产 core dump
    except Exception:
        logger.debug("sandbox: resource.setrlimit unavailable")


def _sandbox_child_env(scratch_dir: str) -> dict:
    """子进程最小环境：不继承服务器 environ。

    旧版子进程原样继承服务器环境——PYTHONPATH 指向 py-server（逃逸代码可
    import main/config 等项目模块）、VECTORDB_DATA_DIR 等运行时变量乃至潜在
    密钥全部暴露给沙箱代码。现仅放行解释器自身需要的少量变量；HF/Transformers
    离线开关显式保留（沙箱代码若 import 模型库，保持与服务端一致的离线策略）。
    """
    env = {}
    for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP"):
        v = os.environ.get(k)
        if v:
            env[k] = v
    # 家目录指向 scratch：逃逸代码即便摸到 ~ 也够不到真实用户目录
    env["HOME" if os.name == "posix" else "USERPROFILE"] = scratch_dir
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    return env


@router.post("/sandbox", response_model=SandboxResponse)
@router.post("/sandbox/run", response_model=SandboxResponse)
async def sandbox_run(req: SandboxRequest, user: dict = Depends(require_admin), request: Request = None):
    """代码沙箱执行（安全加固版：AST静态分析 + import拦截 + 内置清洗 + 隔离启动 + timeout下限 + async subprocess）"""
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
    scratch = None
    try:
        # 每次执行独立 scratch 目录：既作子进程 cwd（相对路径摸不到项目文件），
        # 又作执行后统一清理单元
        scratch = tempfile.mkdtemp(prefix="sandbox_")
        tmpfile = os.path.join(scratch, "main.py")
        with open(tmpfile, "w", encoding="utf-8") as f:
            f.write(safe_code)
        # -I 隔离模式：忽略 PYTHONPATH 等环境变量、不加用户 site、不把脚本目录
        # 放进 sys.path —— 旧版子进程原样继承服务器 environ（含指向 py-server 的
        # PYTHONPATH）与 cwd（=py-server），逃逸代码可 import main/config 等项目
        # 模块或以相对路径读项目文件。-S：不初始化 site，第三方 .pth 启动钩子
        # （setuptools 的 _distutils_hack 在 find_spec 里调 locals()，会被下方
        # 内置清洗挡成 PermissionError，曾导致任何 import 全灭）不执行；
        # purelib 由 SANDBOX_PREFIX 手动补回 sys.path 保持能力面。
        # -X utf8：-I 会忽略 PYTHONUTF8 环境变量，用命令行旗标保证子进程输出 UTF-8。
        argv = [sys.executable, "-I", "-S", "-X", "utf8", tmpfile]
        # 使用 asyncio subprocess 避免阻塞事件循环
        # POSIX 下 start_new_session=True：子进程自成进程组，超时可用 killpg 整组击杀
        _popen_kwargs = {"start_new_session": True} if os.name == "posix" else {}
        if _RESOURCE is not None:
            _popen_kwargs["preexec_fn"] = _sandbox_set_limits
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=scratch,
                env=_sandbox_child_env(scratch),
                **_popen_kwargs,
            )
            try:
                out_bytes, err_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_sec
                )
                out = out_bytes.decode("utf-8", errors="replace") if out_bytes else ""
                err = err_bytes.decode("utf-8", errors="replace") if err_bytes else ""
                proc_returncode = proc.returncode
            except asyncio.TimeoutError:
                _kill_proc_group(proc)
                log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result="timeout", detail=f"timeout={timeout_sec}s")
                return SandboxResponse(output="", error=f"执行超时（{timeout_sec}秒）", status="timeout")
        except Exception:
            # asyncio 子进程不可用（如部分 Windows 配置）→ 同步兜底，经 to_thread 不阻塞事件循环
            try:
                out, err, rc = await asyncio.to_thread(
                    _run_blocking_proc, argv, timeout_sec, scratch, _sandbox_child_env(scratch)
                )
                proc_returncode = rc
            except subprocess.TimeoutExpired:
                # _run_blocking_proc 已在超时分支内击杀进程组
                log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result="timeout", detail=f"timeout={timeout_sec}s")
                return SandboxResponse(output="", error=f"执行超时（{timeout_sec}秒）", status="timeout")
        status = "ok" if proc_returncode == 0 else "error"
        log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result=status, detail=f"exit_code={proc_returncode}")

        # L1/L2/L3 三层学情记忆联动（低侵入：沙箱执行入 L3，供代码实践轨迹追溯）
        try:
            from db import memory_store as _ms
            _ms.append_episode(user["user_id"], "sandbox_exec", {
                "status": status,
                "exit_code": proc_returncode,
                "code_len": len(req.code),
            })
        except Exception as _me:
            logger.debug(f"沙箱执行记忆写入失败(忽略): {_me}")

        return SandboxResponse(output=out, error=err, status=status)
    except Exception as e:
        log_event("sandbox_exec", user_id=user["user_id"], ip=ip, result="error", detail=str(e)[:200])
        return SandboxResponse(output="", error=str(e), status="error")
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
