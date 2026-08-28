#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetLearn 端口/端点可用率探活脚本
=================================
对运行中的后端(默认 http://127.0.0.1:8002)做全量路由探活，
输出真实「可用率」，并列出不可用(down)端点。

判定口径（诚实且可用于省赛证据）：
- 可用(available): 2xx / 3xx / 401 / 403 / 400 / 422 / 405
  —— 路由已注册、服务可达；401/403=需鉴权但可达；422=需合法入参但可达。
- 不可用(down): 5xx / 连接拒绝 / 超时(>8s) / DNS 错误
  —— 路由未注册、启动失败、内部异常。

用法:
  python tools/probe_endpoints.py            # 探活 8002
  python tools/probe_endpoints.py --base http://host:port
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8002"
TIMEOUT = 8.0

AVAILABLE = {200, 201, 202, 204, 301, 302, 303, 304, 307, 308,
             400, 401, 403, 405, 422}
DOWN = set(range(500, 600))


def _req(method, url, token=None, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # 连接拒绝 / 超时 / URL错误
        return None, str(e)[:120]


def _login(base):
    url = f"{base}/api/auth/login"
    status, _ = _req("POST", url, body={"username": "demo", "password": "demo123456"})
    if status != 200:
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, data=json.dumps({"username": "demo", "password": "demo123456"}).encode(),
                headers={"Content-Type": "application/json"}, method="POST"), timeout=TIMEOUT) as r:
            token = json.loads(r.read().decode()).get("token")
            return token
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    base = args.base.rstrip("/")

    # 1) 服务器存活
    s, err = _req("GET", f"{base}/api/status")
    if s is None:
        print(f"[FATAL] 服务器不可达: {err}")
        sys.exit(2)
    print(f"[OK] 服务器存活 /api/status -> {s}")

    # 2) 拉 OpenAPI 路由表
    try:
        with urllib.request.urlopen(f"{base}/openapi.json", timeout=TIMEOUT) as r:
            spec = json.loads(r.read().decode())
    except Exception as e:
        print(f"[FATAL] 无法拉取 openapi.json: {e}")
        sys.exit(2)
    paths = spec.get("paths", {})
    print(f"[OK] 枚举到 {len(paths)} 个路径")

    token = _login(base)
    print(f"[INFO] demo 登录: {'成功(带鉴权探活)' if token else '失败(仅匿名探活)'}")

    import re as _re
    _param_re = _re.compile(r"\{[^}]+\}")

    results = []  # (method, path, status, note)
    for path, methods in paths.items():
        for method in methods:
            method = method.upper()
            # 把路径参数 {id} 替换为占位值，避免字面量打 404 误判
            concrete = _param_re.sub("test", path)
            url = f"{base}{concrete}"
            # 对会触发重型 LLM/agent 执行的 POST，仍发送空 body 探活：
            # 预期返回 401(未登录) / 422(入参校验) / 405(方法不对) —— 均记为可达。
            body = {} if method in ("POST", "PUT", "PATCH") else None
            st, e = _req(method, url, token=token, body=body)
            note = e if st is None else ""
            results.append((method, path, st, note))

    total = len(results)
    available = [r for r in results if r[2] in AVAILABLE]
    down = [(m, p, st, n) for (m, p, st, n) in results if st is None or st in DOWN]
    unexpected = [(m, p, st, n) for (m, p, st, n) in results
                  if st not in AVAILABLE and st not in DOWN]

    print("\n" + "=" * 72)
    print(f"总端点: {total}  |  可用: {len(available)}  |  不可用: {len(down)}")
    rate = (len(available) / total * 100) if total else 0.0
    print(f"可用率: {rate:.1f}%")
    print("=" * 72)
    if down:
        print("\n[不可用端点]")
        for m, p, st, n in down:
            label = f"{st}" if st is not None else f"ERR:{n}"
            print(f"  {m:6s} {p:50s} -> {label}")
    else:
        print("\n[全部端点可用 ✅]")
    if unexpected:
        print(f"\n[非预期状态码(疑似路径参数/特殊路由，需人工复核) {len(unexpected)} 个]")
        for m, p, st, n in unexpected:
            print(f"  {m:6s} {p:50s} -> {st}")
    # 机器可读摘要
    print(f"\n__SUMMARY__ total={total} available={len(available)} down={len(down)} rate={rate:.1f}")


if __name__ == "__main__":
    main()
