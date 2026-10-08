# ============================================================
# py-server/scripts/verify_app_wiring.py
# 架构评审 M-4（main.py 拆分）的可机验守门脚本。
#
# 为什么必须有机验：把 main.py 拆成 app/* 后，最危险的失败模式不是「报错」，
# 而是「少装了一个中间件/异常处理器」——应用照样能起来，但安全头、限流、
# 请求体限制悄悄消失，且没有任何测试会失败。本脚本逐个钉死这些不可见契约。
#
# 刻意**不进入 TestClient 的 with 块**：那会触发 lifespan（连 Milvus + 对 151KB
# 种子数据跑真实 E5 嵌入），既慢又需要模型文件。这里只验证「组装结果」。
#
# 运行：cd py-server && python scripts/verify_app_wiring.py
# 退出码：0 = 全部通过，1 = 存在失败
# ============================================================

import ast
import os
import subprocess
import sys

# py-server 根目录入 path：`import main` 与 conftest 的约定一致
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 必须在 import main 之前设置：让体积限制与限流阈值小到可以被触发 ──
os.environ["MAX_REQUEST_BYTES"] = "1024"          # 1KB → 后续用 2KB body 触发 413
os.environ["RATE_CHAT"] = "2"                     # /api/chat 每窗口 2 次 → 第 3 次 429
os.environ["RATE_LIMIT_ENABLED"] = "true"         # 显式打开（生产默认）
os.environ.pop("PYTEST_CURRENT_TEST", None)       # 否则限流器会整体放行

BASELINE_COMMIT = "f36b83e"  # M-4 拆分前的最后一个提交

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {extra}")


def _baseline_router_names():
    """从拆分前的 main.py 源文本中提取 _all_routers 列表（顺序敏感）。

    ⚠️ 本函数依赖 git **历史对象**：CI 的 actions/checkout 默认 fetch-depth=1（浅克隆），
    此时 `git show <历史 sha>` 会以 `fatal: invalid object name` 失败（exit 128）。
    故 verify-structural.yml 的 checkout 步骤必须声明 `fetch-depth: 0`。
    （实测：2026-10-08 run 37787528182 的 structural job 即因此整条 workflow 变红。）

    基线取不到时**必须判失败**而非跳过 —— 跳过等于「拆掉 main.py 后本门禁静默失效」。
    失败信息给出可执行的两种修法，避免下次只看到一句 traceback。
    """
    cmd = ["git", "show", f"{BASELINE_COMMIT}:py-server/main.py"]
    try:
        out = subprocess.check_output(cmd, cwd=_REPO_ROOT, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        reason = (e.stderr or b"").decode("utf-8", "replace").strip() or f"exit={e.returncode}"
        raise RuntimeError(
            f"无法读取基线 {BASELINE_COMMIT}:py-server/main.py —— {reason}\n"
            "    原因一（最常见）：CI 浅克隆。请在 verify-structural.yml 的 checkout 步骤加 "
            "`with: fetch-depth: 0`。\n"
            "    原因二：该提交已随历史重写消失（本仓库曾用 git filter-repo 重写过历史）。"
            f"此时需把基线 router 列表固化为常量，去掉对 {BASELINE_COMMIT} 的 git 依赖。"
        ) from e
    src = out.decode("utf-8")
    tree = ast.parse(src)
    names = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "_all_routers":
                    names = [e.id for e in node.value.elts if isinstance(e, ast.Name)]
    return names


def _current_router_names():
    """从 app/routers.py 中提取 ALL_ROUTERS 列表（顺序敏感）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "app", "routers.py"), "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "ALL_ROUTERS":
                    return [e.id for e in node.value.elts if isinstance(e, ast.Name)]
    return None


def main():
    # ── 1) 路由集合：与拆分前逐项、逐序比对 ──
    try:
        baseline = _baseline_router_names()
    except RuntimeError as e:
        # 基线取不到 = 本门禁无法证明路由未丢（最危险的失败模式是"少装了一个 router
        # 而应用照样起得来"）。故判 FAIL 并打印可执行修法，而不是让 traceback 淹没结论。
        baseline = None
        check("基线 _all_routers 可读取", False, str(e))
    else:
        check("基线 _all_routers 可解析", len(baseline) > 0, f"n={len(baseline)}")
    current = _current_router_names()
    check("ALL_ROUTERS 与拆分前完全一致（含顺序）", baseline == current,
          f"baseline={len(baseline) if baseline else 0} current={len(current) if current else 0}")

    # ── 2) 组装结果 ──
    import main
    import app.lifespan as lifespan_mod
    import app.status as status_mod
    from app.errors import http_exception_handler, request_validation_error_handler

    app = main.app
    check("app 组装成功", app is not None)

    # 路由枚举走 verify_auth_coverage 的**跨 fastapi 版本**实现（单一真值源）：
    # fastapi 0.141+ 起 include_router 不再把子路由拍平进 app.routes，而是放一个
    # _IncludedRouter 包装对象（且它不保证有 .path）。直接 `for r in app.routes`
    # 取属性会 AttributeError；用 len(app.routes) 计数则会**严重低估**（实测
    # 0.141.1 下 app.routes 只剩 {'Route':4,'_IncludedRouter':1,'APIRoute':2}），
    # 让下面这条「> 200」变成假红。故统一改用 iter_route_entries。
    from verify_auth_coverage import iter_route_entries

    route_entries = iter_route_entries(app)
    check(
        "路由数量 > 200（业务路由确实注册）",
        len(route_entries) > 200,
        f"routes={len(route_entries)}",
    )

    paths = {e.path for e in route_entries}
    for expected in ("/api/status", "/api/status/competition", "/metrics"):
        check(f"运维端点存在：{expected}", expected in paths)

    # ── 3) 公开契约：历史 import 路径未断 ──
    check("main.app 可用", hasattr(main, "app"))
    check("main.lifespan 指向 app.lifespan.lifespan", main.lifespan is lifespan_mod.lifespan)
    check("main._seed_vector_db 指向 app.lifespan._seed_vector_db",
          main._seed_vector_db is lifespan_mod._seed_vector_db)
    check("main.competition_status 指向 app.status.competition_status",
          main.competition_status is status_mod.competition_status)

    # ── 4) 异常处理器全部注册 ──
    # 注：fastapi.HTTPException 是 starlette HTTPException 的子类，注册以 fastapi 为准
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    from shared.errors import DomainError
    for exc_type in (DomainError, HTTPException, RequestValidationError, Exception):
        found = any(h[0] is exc_type for h in app.exception_handlers.items())
        check(f"异常处理器已注册：{exc_type.__name__}", found)
    check("http_exception_handler 即为拆出前的实现",
          app.exception_handlers.get(HTTPException) is not None
          and app.exception_handlers.get(HTTPException).__name__ == http_exception_handler.__name__)
    check("request_validation_error_handler 已绑定", app.exception_handlers.get(
        RequestValidationError).__name__ == request_validation_error_handler.__name__)

    # ── 5) 中间件逐个验证（不进 lifespan）──
    from fastapi.testclient import TestClient
    client = TestClient(app)

    r_metrics = client.get("/metrics")
    check("/metrics 返回 200", r_metrics.status_code == 200)
    check("Prometheus 文本格式正确",
          "text/plain" in r_metrics.headers.get("content-type", ""),
          r_metrics.headers.get("content-type", ""))
    check("安全头：X-Frame-Options", r_metrics.headers.get("X-Frame-Options") == "SAMEORIGIN")
    check("安全头：X-Content-Type-Options", r_metrics.headers.get("X-Content-Type-Options") == "nosniff")
    check("安全头：Referrer-Policy", r_metrics.headers.get("Referrer-Policy") == "no-referrer")
    check("安全头：Content-Security-Policy 存在", bool(r_metrics.headers.get("Content-Security-Policy")))
    check("安全头：Permissions-Policy 存在", bool(r_metrics.headers.get("Permissions-Policy")))
    check("安全头：COOP/COEP（WASI 代码实验室依赖）",
          r_metrics.headers.get("Cross-Origin-Opener-Policy") == "same-origin"
          and r_metrics.headers.get("Cross-Origin-Embedder-Policy") == "require-corp")
    # 开发环境不发送 HSTS（避免浏览器拒绝本地 http）
    check("开发环境不发送 HSTS", "Strict-Transport-Security" not in r_metrics.headers)

    # 请求体限制：MAX_REQUEST_BYTES=1024，此处发 2KB body 应返回 413
    r_big = client.request("POST", "/api/status", content=b"x" * 2048,
                           headers={"Content-Type": "text/plain"})
    check("请求体超限被拦截（413）", r_big.status_code == 413,
          f"status={r_big.status_code}")

    # 限流：RATE_CHAT=2，第 3 次请求 /api/chat/* 应返回 429
    statuses = [client.get("/api/chat/__ratelimit_probe").status_code for _ in range(3)]
    check("限流器生效（第 3 次 429）", statuses[2] == 429, f"statuses={statuses}")
    check("限流响应带 Retry-After",
          "Retry-After" in client.get("/api/chat/__ratelimit_probe").headers)

    # SPA / 静态挂载（仓库根 dist 存在时才会挂载 assets）
    print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
