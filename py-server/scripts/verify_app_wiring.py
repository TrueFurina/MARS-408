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

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {extra}")


def _baseline_router_names():
    """从拆分前的 main.py 源文本中提取 _all_routers 列表（顺序敏感）。"""
    src = subprocess.check_output(
        ["git", "show", f"{BASELINE_COMMIT}:py-server/main.py"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ).decode("utf-8")
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
    baseline = _baseline_router_names()
    current = _current_router_names()
    check("基线 _all_routers 可解析", baseline is not None and len(baseline) > 0,
          f"n={len(baseline) if baseline else 0}")
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
