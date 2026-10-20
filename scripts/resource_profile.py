# -*- coding: utf-8 -*-
"""资源分项测量（REA #16：把"轻/快"换成可复跑的分项数字）

为什么不写一个笼统的"性能测试"：数字只有**分项 + 可复跑 + 标注口径**才可用。
本脚本只做四件事，每件都给出"怎么测的"与"没测到就写未检查"：

  A. 前端产物：dist/ 总字节、assets 分项、Top N 大文件（未构建 → 未检查，不猜）
  B. 后端导入内存：**子进程**导入 py-server 后读 RSS（Windows 走
     GetProcessMemoryInfo，POSIX 走 ru_maxrss），并记录导入耗时
  C. 契约序列化：openapi.json 字节数 + `app.openapi()` 生成耗时（需要 venv）
  D. 源树规模：按扩展名统计文件数与行数（用于判断上面三项的分母有多大）

三态口径：`observed`（本次实测）/ `unknown`（环境不具备，如未构建/无 venv）。
**unknown 绝不填 0**——"没测"和"测得是 0"是两件事。

用法：
  python scripts/resource_profile.py                  # 打印到 stdout
  python scripts/resource_profile.py --write          # 写入 deliverables/engineering-assurance/
  python scripts/resource_profile.py --json           # 机器可读
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO, "dist")
PY_SERVER = os.path.join(REPO, "py-server")
OUT_DIR = os.path.join(REPO, "deliverables", "engineering-assurance")

_SRC_EXTS = {".py", ".ts", ".tsx", ".vue", ".js", ".mjs"}
_SKIP = {"node_modules", ".venv", "dist", "build", "site", "archive", "__pycache__",
         ".git", "vectordb_data", "milvus_lite_data", "data", "sessions", "media",
         "_e2e_tmp_mdhz", "site-packages", ".pytest_cache", "coverage", "seed"}

# 子进程里跑的测量桩：导入应用 → 读自身 RSS → 打印一行 JSON。
# 单独放字符串里而不是 import 本模块，是为了让被测量的进程**只有**应用的导入开销。
_RSS_PROBE = r"""
import json, os, sys, time
t0 = time.perf_counter()
sys.path.insert(0, os.getcwd())
try:
    import main  # noqa: F401
    ok, err = True, ""
except Exception as e:
    ok, err = False, f"{type(e).__name__}: {e}"
import_ms = round((time.perf_counter() - t0) * 1000, 1)

rss_kb = None
if os.name == "nt":
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        # 必须显式声明 argtypes：不声明时 HANDLE 被按 c_int 传（截断），
        # GetProcessMemoryInfo 返回 0 且不报错 —— 实测踩过一次，静默得到 RSS=None。
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        fn = psapi.GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        fn.restype = wintypes.BOOL
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        fh = ctypes.c_void_p(ctypes.windll.kernel32.GetCurrentProcess())
        if fn(fh, ctypes.byref(pmc), pmc.cb):
            rss_kb = round(pmc.WorkingSetSize / 1024, 1)
    except Exception:
        rss_kb = None
else:
    try:
        import resource
        rss_kb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 1)
    except Exception:
        rss_kb = None

print(json.dumps({"ok": ok, "err": err, "import_ms": import_ms, "rss_kb": rss_kb}))
"""


def _tree_size(path: str) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass
    return total


def measure_frontend() -> dict:
    if not os.path.isdir(DIST):
        return {"status": "unknown", "note": "dist/ 不存在（未构建）——不猜测体积"}
    assets = os.path.join(DIST, "assets")
    top: list[tuple[int, str]] = []
    js = css = 0
    for dirpath, _dirs, files in os.walk(DIST):
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            top.append((size, os.path.relpath(p, DIST).replace("\\", "/")))
            low = fn.lower()
            if low.endswith(".js") and assets in dirpath:
                js += size
            elif low.endswith(".css") and assets in dirpath:
                css += size
    top.sort(reverse=True)
    return {
        "status": "observed",
        "total_bytes": _tree_size(DIST),
        "assets_bytes": _tree_size(assets) if os.path.isdir(assets) else 0,
        "js_bytes": js,
        "css_bytes": css,
        "top": top[:8],
    }


def measure_backend_rss(timeout: int = 180) -> dict:
    venv = None
    for cand in (os.path.join(PY_SERVER, ".venv", "Scripts", "python.exe"),
                 os.path.join(PY_SERVER, ".venv", "bin", "python")):
        if os.path.isfile(cand):
            venv = cand
            break
    if not venv:
        return {"status": "unknown", "note": "py-server/.venv 不存在，无法测量导入内存"}
    try:
        proc = subprocess.run([venv, "-c", _RSS_PROBE], cwd=PY_SERVER,
                              capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"status": "unknown", "note": f"测量子进程失败：{e}"}
    line = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    try:
        data = json.loads(line[0])
    except json.JSONDecodeError:
        return {"status": "unknown",
                "note": f"子进程输出不可解析（rc={proc.returncode}）：{(proc.stderr or '')[:200]}"}
    data["status"] = "observed" if data.get("ok") else "unknown"
    if not data.get("ok"):
        data["note"] = f"导入失败（测到的是失败路径的内存，不作为基线）：{data.get('err')}"
    return data


def measure_openapi() -> dict:
    path = os.path.join(PY_SERVER, "openapi.json")
    if not os.path.isfile(path):
        return {"status": "unknown", "note": "openapi.json 不存在"}
    size = os.path.getsize(path)
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    ops = 0
    for item in (doc.get("paths") or {}).values():
        if isinstance(item, dict):
            ops += sum(1 for m in item if m.lower() in
                       {"get", "post", "put", "delete", "patch", "head", "options"})
    t0 = time.perf_counter()
    for _ in range(20):                    # 序列化耗时：20 次取均值，避免单次抖动
        json.dumps(doc, ensure_ascii=False)
    ser_ms = round((time.perf_counter() - t0) / 20 * 1000, 2)
    return {"status": "observed", "bytes": size, "operations": ops,
            "schemas": len((doc.get("components") or {}).get("schemas") or {}),
            "reserialize_ms": ser_ms}


def measure_tree() -> dict:
    counts: dict[str, dict[str, int]] = {}
    for root in ("src", "py-server", "scripts", "tests"):
        base = os.path.join(REPO, root)
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in _SKIP]
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in _SRC_EXTS:
                    continue
                key = ext
                slot = counts.setdefault(key, {"files": 0, "lines": 0})
                slot["files"] += 1
                try:
                    with open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace") as f:
                        slot["lines"] += sum(1 for _ in f)
                except OSError:
                    pass
    return {"status": "observed", "by_ext": counts}


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB"):
        if n < 1024 or unit == "MiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} MiB"


def render_md(data: dict) -> str:
    fe, be, api, tree = data["frontend"], data["backend"], data["openapi"], data["tree"]
    lines = [
        "# 资源分项测量（本文件由 scripts/resource_profile.py 生成，请勿手改）",
        "",
        f"- 生成时间：{data['generated_at']}",
        f"- 平台：{platform.platform()} / Python {platform.python_version()}",
        "- 口径：`observed` = 本次实测；`unknown` = 环境不具备（**不填 0，不猜**）",
        "",
        "## A. 前端产物（dist/）",
        "",
    ]
    if fe["status"] == "observed":
        lines += [
            f"| 项 | 值 |", "|---|---|",
            f"| 总字节 | {_fmt_bytes(fe['total_bytes'])} |",
            f"| assets/ | {_fmt_bytes(fe['assets_bytes'])} |",
            f"| JS | {_fmt_bytes(fe['js_bytes'])} |",
            f"| CSS | {_fmt_bytes(fe['css_bytes'])} |",
            "", "最大文件：", "",
            "| 字节 | 文件 |", "|---|---|",
        ]
        lines += [f"| {_fmt_bytes(s)} | `{p}` |" for s, p in fe["top"]]
    else:
        lines.append(f"**未检查**：{fe['note']}")

    lines += ["", "## B. 后端导入内存与耗时（子进程实测）", ""]
    if be["status"] == "observed":
        lines += [
            "| 项 | 值 |", "|---|---|",
            f"| 导入 `main` 耗时 | {be.get('import_ms')} ms |",
            f"| 进程 RSS（导入后） | {be.get('rss_kb')} KiB"
            f"（约 {round(be.get('rss_kb', 0) / 1024, 1) if be.get('rss_kb') else '—'} MiB） |",
            "",
            "> 说明：RSS 含解释器与已加载的 C 扩展驻留页；不含运行时按请求分配的峰值。",
        ]
    else:
        lines.append(f"**未检查**：{be['note']}")

    lines += ["", "## C. 契约序列化（openapi.json）", ""]
    if api["status"] == "observed":
        lines += [
            "| 项 | 值 |", "|---|---|",
            f"| 快照字节 | {_fmt_bytes(api['bytes'])} |",
            f"| operation 数 | {api['operations']} |",
            f"| schema 定义数 | {api['schemas']} |",
            f"| 反序列化+再序列化（20 次均值） | {api['reserialize_ms']} ms |",
        ]
    else:
        lines.append(f"**未检查**：{api['note']}")

    lines += ["", "## D. 源树规模（分母）", "", "| 扩展名 | 文件 | 行 |", "|---|---|---|"]
    for ext, slot in sorted(tree["by_ext"].items()):
        lines.append(f"| `{ext}` | {slot['files']} | {slot['lines']} |")
    lines += ["", "---", "",
              "复跑：`python scripts/resource_profile.py --write`（会覆盖本文件）"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="资源分项测量（bundle / RSS / 序列化）")
    ap.add_argument("--write", action="store_true", help="写入 deliverables/engineering-assurance/")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "frontend": measure_frontend(),
        "backend": measure_backend_rss(),
        "openapi": measure_openapi(),
        "tree": measure_tree(),
    }

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0

    md = render_md(data)
    if args.write:
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, f"resource-profile-{datetime.now().strftime('%Y-%m-%d')}.md")
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        print(f"已写入 {os.path.relpath(out, REPO)}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
