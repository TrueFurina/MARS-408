# -*- coding: utf-8 -*-
"""前后端契约交叉审计（report-only / --gate 阻断双模）：

1. 后端真值源 = openapi.json（由 FastAPI 应用生成，含全部路径与方法）；
   CI 侧由 verify_openapi_snapshot.py 守护其与运行时一致（ci.yml）。
2. 前端调用面 = src/ 下 api.<method>(...) 与裸 fetch('...') 的字面量/模板路径；
   方法面与 src/utils/api.ts 的 api 对象对齐：get/post/put/delete/patch +
   postStream/upload/postBlob/getBlob（后四者同样以 path 为首参）。
3. 裁定两类：
   A. 前端调用 → 后端无对应路由（运行时必 404/405，🔴 级）—— --gate 下阻断；
   B. 后端路由 → 前端零调用（孤儿候选）—— 报告用途，不阻断
      （legacy 别名 / admin·诊断面 / 后端完整而前端未接，均可能合理）。

匹配语义（段级，容错前端惯用法）：
  - 后端占位段 {} 匹配任意前端段（字面量填充路径参数）；
  - 前端模板 ${...} 归一为 {}；尾部 {} 段可能是 query 串拼接（/x${qs}）；
  - 泛型类型参数 api.get<{...}>('/x') 可解析；fetch 默认 GET。

退出码契约：
  0 = 执行完毕且（非 gate 模式或 A 类为 0）
  1 = --gate 且 A 类 > 0（前端打到不存在的路由）
  2 = 探活自身失败（openapi.json 缺失/不可解析 / 扫描面为空——fail-closed：
      "照不到"不得当作"干净"）
"""
import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPENAPI = os.path.join(REPO, "py-server", "openapi.json")
SRC = os.path.join(REPO, "src")

# 泛型调用须容忍类型参数：api.get<{ classes: ClassItem[] }>('/career/classes')
# [^(]* 覆盖 <...> 类型参数（类型里含 ( 的箭头函数类型极罕见，不计）
# 长名在前避免 get 抢先匹配 getBlob（\b 亦可兜底，双保险）
_METHODS = r"postStream|postBlob|getBlob|upload|delete|patch|post|put|get"
_METHOD_MAP = {"postStream": "POST", "postBlob": "POST", "getBlob": "GET",
               "upload": "POST"}
CALL_RE = re.compile(
    rf"""api\.({_METHODS})\b[^(]*\(\s*[`'"]([^`'"]+)[`'"]""")
CALL_TPL_RE = re.compile(
    rf"""api\.({_METHODS})\b[^(]*\(\s*`([^`]*)`""")
FETCH_RE = re.compile(
    r"""fetch\(\s*[`'"]([^`'"]+)[`'"]""")
HTTP_METHODS = ("get", "post", "put", "delete", "patch")


def norm_path(p: str, frontend: bool = False) -> str:
    p = p.split("?")[0].split("#")[0]
    p = re.sub(r"\{[^}]*\}|\$\{[^}]*\}", "{}", p)
    if frontend and not p.startswith("/api"):
        # api.ts 的 request() 统一拼 `/api` 前缀（API_BASE='' + '/api'+path）
        p = "/api" + p
    if len(p) > 1:
        p = p.rstrip("/")
    return p


def seg_match(backend_seg: str, frontend_seg: str) -> bool:
    """段级匹配：后端占位段 {} 匹配任意前端段（字面量填充路径参数）；
    前端段尾缀 {}（query 串拼接残留，如 /experiments${suffix}）按前缀比。"""
    if backend_seg == frontend_seg or backend_seg == "{}":
        return True
    if frontend_seg.endswith("{}") and backend_seg == frontend_seg[:-2]:
        return True
    return False


def path_match(backend_path: str, frontend_path: str) -> bool:
    b = backend_path.strip("/").split("/")
    f = frontend_path.strip("/").split("/")
    # 前端尾部纯占位段可能是 query 串拼接（/experiments${suffix} 归一后多一段）
    if len(f) == len(b) + 1 and f[-1] == "{}":
        f = f[:-1]
    # 前端尾部动态段可能是 query 串：允许前端少一段
    if len(f) == len(b) - 1 and b[-1] == "{}":
        f = f + ["{}"]
    if len(b) != len(f):
        return False
    return all(seg_match(bs, fs) for bs, fs in zip(b, f))


def collect_backend(spec: dict) -> set:
    """openapi spec dict → {(METHOD, norm_path)}。空 spec 由调用方判 fail-closed。"""
    routes = set()
    for path, methods in spec.get("paths", {}).items():
        for m in methods:
            if m.lower() in HTTP_METHODS:
                routes.add((m.upper(), norm_path(path)))
    return routes


def extract_calls(text: str) -> list:
    """单文件文本 → [(method, norm_path)]。method 为 FETCH 时调用方按 GET 裁定。"""
    calls = []
    for m, p in CALL_RE.findall(text):
        calls.append((_METHOD_MAP.get(m, m.upper()), norm_path(p, frontend=True)))
    for m, p in CALL_TPL_RE.findall(text):
        if "${API_BASE}" in p:
            continue  # api.ts 内部 request() 家族，真实路径由调用方字面量覆盖
        calls.append((_METHOD_MAP.get(m, m.upper()), norm_path(p, frontend=True)))
    for p in FETCH_RE.findall(text):
        if p.startswith(("http://", "https://", "data:", "blob:")) or "${" in p:
            continue  # 外部/数据 URL / 模板拼接非后端契约
        calls.append(("FETCH", norm_path(p, frontend=True)))
    return calls


def collect_frontend(src_root: str) -> list:
    """扫 src/（排除 node_modules / __tests__ / *.spec.* / *.test.*）→ [(method, path, relpath)]。
    测试内的假路径（/test、/retry 等）非生产契约，故排除。
    ⚠️ 2026-10-21 修正：原实现只排 `__tests__` **目录**，漏了 vitest 的文件后缀约定
    （`*.spec.ts` / `*.test.ts`）——首个 api 契约测试（src/utils/api.spec.ts）一落地，
    里面的 `/x`、`/admin/import` 等假路径就被当成生产调用，A 类闸直接误报 7 处。
    意图（注释里写明的"测试非生产契约"）没变，补的是实现漏的那半种约定。
    relpath 相对 src_root 计算；跨盘符等极端情形退化为绝对路径（不得抛错——
    报告路径只是给人定位，不能因为它让审计本身失败）。"""
    calls = []
    for root, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__tests__")]
        for fn in files:
            if not fn.endswith((".vue", ".ts", ".js")):
                continue
            # 测试文件不是调用点：vitest 用文件后缀而非目录约定（见上方 docstring）
            if fn.endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js", ".spec.jsx", ".test.jsx")):
                continue
            fp = os.path.join(root, fn)
            try:
                rel = os.path.relpath(fp, src_root)
            except ValueError:
                rel = fp
            with open(fp, encoding="utf-8", errors="replace") as f:
                text = f.read()
            for m, p in extract_calls(text):
                calls.append((m, p, rel))
    return calls


# ── 契约缺口模式（--contract-gaps）─────────────────────────────────────
# 判据不是"读 Python 源码有没有写 response_model"，而是直接看 openapi.json：
# **某操作的 200 响应 schema 为空对象 `{}`** ⟺ 该路由没有声明响应模型。
# 这样口径与 openapi-typescript 完全一致（它拿不到 schema 就生成不出类型），
# 不会出现"源码里写了 response_model 但生成物仍是空"的错位。
# 「放弃类型检查」有两种等价写法，必须都算进 hot，否则度量会说谎：
#   ① 泛型标注：api.get<any>('/path')
#   ② 变量标注：const res: any = await api.get('/path')
# 2026-11-06 修正：此前只认 ①，而仓库里 41 处用的是 ②（skillStore.ts 等），
# 导致「hot 清零」是假象——那些端点后端仍是裸 dict、前端仍用 any 接着，
# 只是审计看不见。两类写法语义完全相同：响应没有契约，前端主动放弃类型检查。
ANY_CALL_RE = re.compile(r"api\.(\w+)\s*<\s*any\s*>\s*\(\s*(['\"`])([^'\"`]+)\2")
ANY_VAR_RE = re.compile(
    r"\b(?:const|let|var)\s+\w+\s*:\s*any\s*=\s*await\s+"
    r"api\.(\w+)\s*(?:<[^>]*>)?\s*\(\s*(['\"`])([^'\"`]+)\2"
)
_ANY_RES = (ANY_CALL_RE, ANY_VAR_RE)


def collect_any_calls(src_root: str) -> list:
    """扫 src/ 收集「响应被主动标成 any」的调用点（泛型标注 + 变量标注两类）。

    这些是"想写类型但没类型可写"的地方：后端一旦补上 response_model，
    前端就能立刻换成生成类型。返回 [(method, norm_path, relpath)]，按三元组去重
    （同一个调用若同时命中两类正则不应被计两次）。
    """
    out = []
    for root, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__tests__")]
        for fn in files:
            if not fn.endswith((".ts", ".vue")):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            rel = os.path.relpath(fp, os.path.dirname(src_root)).replace("\\", "/")
            for regex in _ANY_RES:
                for m, _q, path in regex.findall(text):
                    out.append((_METHOD_MAP.get(m, m.upper()), norm_path(path, frontend=True), rel))
    return sorted(set(out))


def collect_contract_gaps(spec: dict, src_root: str):
    """→ (gaps, blocked_by_frontend, total_ops)。

    gaps: [(METHOD, path)] 200 响应 schema 为空的路由；
    blocked_by_frontend: 其中被前端 `api.*<any>()` 实际调用的（= 优先级最高，
    补完模型就能立刻把前端那处 any 换成生成类型）。
    """
    gaps = []
    total = 0
    for path, methods in spec.get("paths", {}).items():
        for m, op in methods.items():
            if m.lower() not in HTTP_METHODS:
                continue
            total += 1
            schema = (
                op.get("responses", {})
                .get("200", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            # 空 dict / 无 $ref 无 properties ⇒ 没有可用 schema
            if not schema or (not schema.get("$ref") and not schema.get("properties")):
                gaps.append((m.upper(), norm_path(path)))
    any_calls = collect_any_calls(src_root)
    hot = []
    for gm, gp in gaps:
        hits = [rel for cm, cp, rel in any_calls if cm == gm and path_match(gp, cp)]
        if hits:
            hot.append((gm, gp, sorted(set(hits))))
    hot.sort(key=lambda x: (-len(x[2]), x[1]))
    return gaps, hot, total


def audit(backend: set, frontend: list):
    """→ (missing, orphans)。
    missing: [{call, where, method_mismatch}] 前端调用无后端路由；
    orphans: ["METHOD /path"] 后端路由前端零调用。"""
    missing = []
    for m, p, where in frontend:
        eff_m = "GET" if m == "FETCH" else m
        if any(bm == eff_m and path_match(bp, p) for bm, bp in backend):
            continue
        alt = [bm for bm, bp in backend if path_match(bp, p)]
        missing.append({"call": f"{m} {p}", "where": where,
                        "method_mismatch": bool(alt)})
    fpaths = {p for _, p, _ in frontend}
    orphans = [f"{m} {p}" for m, p in sorted(backend)
               if not any(path_match(p, fp) for fp in fpaths)]
    return missing, orphans


def main() -> None:
    parser = argparse.ArgumentParser(description="前后端契约交叉审计")
    parser.add_argument("--gate", action="store_true",
                        help="阻断模式：A 类（前端打到不存在的路由）> 0 时 exit 1")
    parser.add_argument("--openapi", default=OPENAPI, help="openapi.json 路径")
    parser.add_argument("--src", default=SRC, help="前端源码根目录")
    parser.add_argument("--contract-gaps", action="store_true",
                        help="只输出「无响应模型」的契约缺口清单（按前端 any 调用热度排序）")
    args = parser.parse_args()

    try:
        with open(args.openapi, encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"🔴 [contract] openapi.json 不可用：{type(e).__name__}", file=sys.stderr)
        sys.exit(2)
    if args.contract_gaps:
        gaps, hot, total = collect_contract_gaps(spec, args.src)
        print("=" * 72)
        print("契约缺口：200 响应无 schema 的路由（= 没有 response_model）")
        print("=" * 72)
        print(f"路由总数 {total}；有响应模型 {total - len(gaps)}"
              f"（{(total - len(gaps)) / total * 100:.1f}%）；缺口 {len(gaps)}")
        print()
        print(f"=== 优先级最高：缺口且前端把响应标成 any（{len(hot)} 条）===")
        print("  两类写法都计入：api.*<any>() 与 const res: any = await api.*()。")
        print("  补完这些的 response_model，前端对应那处 any 就能立刻换成生成类型。")
        for m, p, files in hot:
            print(f"  {m:6s} {p}")
            for f in files:
                print(f"           ↳ {f}")
        print()
        print("=== 其余缺口（前端暂未用 any 调，可按需）===")
        hot_set = {(m, p) for m, p, _ in hot}
        rest = [g for g in gaps if g not in hot_set]
        by_mod: dict = {}
        for m, p in rest:
            mod = p.split("/")[2] if p.count("/") >= 2 else p
            by_mod.setdefault(mod, 0)
            by_mod[mod] += 1
        for mod, n in sorted(by_mod.items(), key=lambda x: -x[1])[:20]:
            print(f"  {n:4d}  /{mod}/…")
        return

    backend = collect_backend(spec)
    if not backend:
        print("🔴 [contract] openapi.json 零路由——快照损坏？fail-closed", file=sys.stderr)
        sys.exit(2)

    frontend = collect_frontend(args.src)
    if not frontend:
        print("🔴 [contract] 前端扫描面为零——src/ 缺失或解析规则全失效？fail-closed",
              file=sys.stderr)
        sys.exit(2)

    missing, orphans = audit(backend, frontend)

    print(f"后端路由（openapi.json）：{len(backend)}")
    print(f"前端字面量调用点：{len(frontend)}（去重路径 {len({p for _, p, _ in frontend})}）")
    print()
    print(f"=== A. 前端调用 → 后端无路由（潜在 404/405）：{len(missing)} 处 ===")
    for c in sorted(missing, key=lambda x: x["call"]):
        flag = "⚠️方法不匹配" if c["method_mismatch"] else "🔴无此路径"
        print(f"  {flag}  {c['call']}   @ {c['where']}")
    print()
    print(f"=== B. 后端路由 → 前端零字面量调用（孤儿候选，不阻断）：{len(orphans)} 条 ===")
    for o in orphans:
        print(f"  {o}")

    if args.gate:
        if missing:
            print(f"\n🔴 [contract] A 类违约 {len(missing)} 处：前端调用打到不存在的路由",
                  file=sys.stderr)
            sys.exit(1)
        print("\n🟢 [contract] A 类为 0：前端调用全部有后端路由对应")


if __name__ == "__main__":
    # Windows 兼容：控制台/管道默认走 locale（cp936），脚本里的中文与 🔴/🟢 emoji 会触发
    # UnicodeEncodeError 直接崩溃——CI windows-latest 实测命中（pytest 以 subprocess 调本脚本
    # 并捕获 stderr，charmap 编码失败 ⇒ returncode=1 且断言 "A 类违约" in stderr 落空）。
    # 本地不复现是因为开发机设了 PYTHONUTF8=1；CI 无该变量，Python 3.12 在 Windows 用 locale 编码。
    # 显式重配为 UTF-8；Linux/macOS 上本即 UTF-8，无副作用。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            # 流已被替换为非文本对象或不支持重配时保持原样，不影响主流程
            pass
    main()
