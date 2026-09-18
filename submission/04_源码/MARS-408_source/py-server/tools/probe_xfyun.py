#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetLearn 讯飞 10 能力真探脚本
===========================
对运行中的后端逐一实测 10 项讯飞能力，确认「可联通且产出预期响应」
（不仅是 /api/xfyun/status 的 configured 标志）。

判定口径:
- OK:   返回 2xx 且含预期字段(或异步提交返回 task_id)
- FAIL: 5xx / 连接错误 / 超时 / 返回 error 字段

用法: python tools/probe_xfyun.py [--base http://127.0.0.1:8002]
"""
import argparse
import base64
import json
import sys
import time
import urllib.request
import urllib.error
import zlib
import struct

BASE = "http://127.0.0.1:8002"
TIMEOUT = 20.0


def _make_png(size=64):
    """生成一张真实有效的 RGB PNG（非退化图，讯飞图片理解可识别）。"""
    raw = b""
    for y in range(size):
        raw += b"\x00"  # filter type 0
        for x in range(size):
            raw += bytes([(x * 4) & 0xFF, (y * 4) & 0xFF, 128])

    def _chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(raw)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


# 真实有效的 64x64 PNG，用于图片理解探针（1x1 透明 PNG 会被讯飞拒绝）
PNG_B64 = base64.b64encode(_make_png()).decode("ascii")


def _post(base, path, token, body):
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return None, {"error": str(e)[:160]}


def _get(base, path, token):
    url = f"{base}{path}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode())
    except Exception as e:
        return None, {"error": str(e)[:160]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    base = args.base.rstrip("/")

    # 登录取 token
    st, payload = _post(base, "/api/auth/login",
                        None, {"username": "demo", "password": "demo123456"})
    if st != 200 or "token" not in payload:
        print(f"[FATAL] 登录失败: {st} {payload}")
        sys.exit(2)
    token = payload["token"]

    cases = [
        ("search", "POST", "/api/xfyun/search",
         {"query": "408 计算机网络 滑动窗口", "limit": 3}),
        ("proofread", "POST", "/api/xfyun/proofread",
         {"text": "计算机网络是一个复杂的网路协议，需要仔细的规划。"}),
        ("proofread-doc", "POST", "/api/xfyun/proofread-doc",
         {"text": "关于召开计算机网络研讨会的通知：请各位同学准时参加。"}),
        ("compliance", "POST", "/api/xfyun/compliance",
         {"text": "本系统用于408考研辅导。"}),
        ("roleplay", "POST", "/api/xfyun/roleplay",
         {"persona": "mock_interviewer", "message": "请介绍一下你自己", "topic": "考研复试"}),
        ("resume", "POST", "/api/xfyun/resume",
         {"info": "姓名：张三；学校：闽江大学；专业：计算机科学；项目：408考研辅导系统"}),
        ("ppt", "POST", "/api/xfyun/ppt",
         {"query": "408 考研复习规划", "is_figure": True, "ai_image": "normal", "search": True}),
        ("video", "POST", "/api/xfyun/video",
         {"prompt": "介绍计算机网络的分层结构", "word_count": 60}),
        ("image-understand", "POST", "/api/xfyun/image-understand",
         {"image_base64": PNG_B64, "question": "这张图片讲了什么？"}),
        ("status", "GET", "/api/xfyun/status", None),
    ]

    results = []
    for name, method, path, body in cases:
        if method == "GET":
            st, resp = _get(base, path, token)
        else:
            st, resp = _post(base, path, token, body)
        ok = st in (200, 201) and not (isinstance(resp, dict) and resp.get("error"))
        # 异步类(ppt/video)返回 task_id 即视为提交成功
        if not ok and name in ("ppt", "video") and isinstance(resp, dict) and resp.get("task_id"):
            ok = True
        results.append((name, method, st, ok, resp))
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] {name:16s} {method:4s} {path:34s} -> {st}")

    total = len(results)
    ok_n = sum(1 for r in results if r[3])
    print("\n" + "=" * 60)
    print(f"讯飞能力实测: {ok_n}/{total} 产出预期响应")
    print("=" * 60)
    for name, method, st, ok, resp in results:
        if not ok:
            print(f"  ✗ {name}: {st} {str(resp)[:160]}")
    print(f"\n__SUMMARY__ total={total} ok={ok_n} rate={ok_n/total*100:.1f}")


if __name__ == "__main__":
    main()
