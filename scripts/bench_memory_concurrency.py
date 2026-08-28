"""MARS-408 50 并发记忆读取压测（循环14-P0）

验证 TTL 缓存带来的并发性能提升（技术方案声称 50 并发读 ↓75.6%）。
用法: python scripts/bench_memory_concurrency.py
"""
import asyncio
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8002"


def login() -> str:
    """登录 demo 用户获取 token"""
    body = json.dumps({"username": "demo", "password": "demo123456"}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/auth/login", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        return data.get("token", "")


async def hit_overview(token: str) -> float:
    """单次 /memory/overview 请求，返回耗时（ms）"""
    start = time.perf_counter()
    try:
        req = urllib.request.Request(
            f"{BASE}/api/memory/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return (time.perf_counter() - start) * 1000
    except Exception as e:
        return -1.0  # 失败标记


async def bench(concurrency: int = 50, rounds: int = 3):
    token = login()
    if not token:
        print("❌ 登录失败，无法压测")
        return
    print(f"✅ 登录成功（并发 {concurrency}，{rounds} 轮）")

    all_lat = []
    for r in range(rounds):
        latencies = await asyncio.gather(*[hit_overview(token) for _ in range(concurrency)])
        ok = [l for l in latencies if l >= 0]
        fail = len(latencies) - len(ok)
        if ok:
            avg = sum(ok) / len(ok)
            s = sorted(ok)
            p95 = s[int(len(s) * 0.95) - 1]
            print(f"  轮{r + 1}: 成功 {len(ok)}/{len(latencies)} 失败 {fail} "
                  f"平均 {avg:.1f}ms P95 {p95:.1f}ms")
            all_lat.extend(ok)
        else:
            print(f"  轮{r + 1}: 全部失败")

    if all_lat:
        total_avg = sum(all_lat) / len(all_lat)
        s = sorted(all_lat)
        total_p95 = s[int(len(s) * 0.95) - 1]
        print(f"\n📊 汇总: {len(all_lat)} 次成功请求")
        print(f"  平均: {total_avg:.1f}ms  P95: {total_p95:.1f}ms")


if __name__ == "__main__":
    import sys
    conc = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    asyncio.run(bench(conc, rounds))
