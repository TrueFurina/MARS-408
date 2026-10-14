# -*- coding: utf-8 -*-
"""拼图①韧性证据：LLM 四通道「运行级回退链」端到端实证。

为什么需要它
------------
ADR-020 的对外口径是「四通道容灾：讯飞星火X2 → DeepSeek → Qwen3.8-Max → 智谱GLM」。
这条链实现在 `db/llm_provider.py` 的 `LLMProvider.chat`（auto 模式逐通道尝试，
失败即 record_llm_fallback 并切下一通道，另有通道级熔断）。但「代码写着会回退」
与「回退真的跑得通」是两件事——本脚本用**真实网络调用**把后者变成可复现证据。

做法（故障注入，零改动生产代码与配置）
--------------------------------------
逐场景把「前 N 个通道」的凭证改为无效串（引发上游真实 401 / 11200），
观察 auto 模式是否自动切到下一个健康通道并成功返回：

  s0  不注入                    —— 基线：链路本身可用（观察哪个通道胜出）
  s1  注入 xfyun 无效           —— 主通道故障 → 应回退并成功（证明回退机制）
  s2  注入 xfyun + deepseek 无效 —— deepseek 故障后链路继续向后走
  s3  注入 xfyun + deepseek + qwen 无效 —— 前三通道全故障 → 应落到 GLM 并成功
                                （即「DeepSeek 故障 → 自动回落 GLM」的完整形态）

凭证隔离：无效串只写进程内的 config dict（场景结束后原样恢复），不落盘、
不改 py-server/.env 与 config.json，不触碰任何真实密钥。

DB 隔离：NETLEARN_USER_DB / NETLEARN_PG_DIR 指向临时目录。chat 链路不写库，
仅防 import 期副作用误连真实库。

退出码契约（与 experiments/pilot_evidence_report.py 一致）
--------------------------------------------------------
0 = 全部可判定场景的硬断言通过；1 = 有断言失败或运行异常。
**退出码为 1 时，不得引用本产物的任何结论。**

已知边界（诚实声明）
------------------
* 本脚本证明的是「回退机制 + 各通道真实可达性」，不证明任何教学/业务效果。
* s3 依赖 GLM 通道已配置（env ZHIPU_API_KEY / GLM_API_KEY，或 .env 同名键）；
  未配置时 s3 的预期结果为「链路耗尽抛 LLMUnavailable」，脚本据实报告，
  不会把「没测到」记成通过。

用法
----
  python experiments/verify_llm_fallback_chain.py                  # 全场景
  python experiments/verify_llm_fallback_chain.py --scenario s3    # 单场景
"""
from __future__ import annotations

import argparse
import asyncio
import atexit
import datetime
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # py-server
sys.path.insert(0, _ROOT)

# ── DB 隔离（必须在 import 任何 db.* 之前设 env）──
_TMP = tempfile.mkdtemp(prefix="llm_fallback_chain_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["NETLEARN_USER_DB"] = os.path.join(_TMP, "users.db")
os.environ["NETLEARN_PG_DIR"] = _TMP

import shared.metrics as _metrics  # noqa: E402
from db.llm_provider import LLMProvider, LLMUnavailable  # noqa: E402
from shared.circuit_breaker import reset_breaker  # noqa: E402
from shared.container import get_container  # noqa: E402

CHANNELS = ["xfyun", "deepseek", "qwen", "glm"]
_CRED_FIELDS = ("api_key", "api_password", "app_id", "api_secret")
_INVALID = "invalid-fault-injection-000000"  # 无真实凭证特征的无效串，触发上游真实鉴权失败

SCENARIOS = {
    "s0": {"inject": [], "desc": "基线：不注入，链路本身应可用"},
    "s1": {"inject": ["xfyun"], "desc": "主通道(xfyun)凭证无效 → 应自动回退并成功"},
    "s2": {"inject": ["xfyun", "deepseek"], "desc": "xfyun+deepseek 无效 → 链路应继续向后走"},
    "s3": {"inject": ["xfyun", "deepseek", "qwen"], "desc": "前三通道无效 → 应落到 GLM 并成功"},
}


# ── 通道尝试顺序采集（只取通道名+结果，绝不存错误体，防凭证泄漏）──

class _WalkCollector(logging.Handler):
    _PATTERNS = [
        (re.compile(r"LLM 通道 (\w+) 调用失败"), "failed"),
        (re.compile(r"LLM 调用成功: (\w+)"), "ok"),
        (re.compile(r"LLM 通道 (\w+) 熔断中，跳过"), "breaker_open"),
        (re.compile(r"LLM 通道 (\w+) 未配置可用凭证，跳过"), "unconfigured"),
    ]

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.events: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            return
        for pat, outcome in self._PATTERNS:
            m = pat.search(msg)
            if m:
                self.events.append((m.group(1), outcome))
                return


# ── 故障注入 / 恢复（只动进程内 config dict）──

def _inject_invalid(settings: dict, channels: list[str]) -> dict:
    """把指定通道的凭证字段改为无效串；返回原值快照供恢复。"""
    saved: dict = {}
    for name in channels:
        cfg = settings.get(name)
        if not isinstance(cfg, dict):
            continue
        saved[name] = dict(cfg)
        for k in _CRED_FIELDS:
            if k in cfg:
                cfg[k] = _INVALID
        cfg["api_key"] = _INVALID  # _provider_configured 对非 xfyun 只看 api_key
    return saved


def _restore(settings: dict, saved: dict) -> None:
    for name, orig in saved.items():
        cfg = settings.get(name)
        if isinstance(cfg, dict):
            cfg.clear()
            cfg.update(orig)


# ── 指标快照（进程内计数器，取 delta 判定胜出通道与回退次数）──

def _metrics_snapshot() -> tuple:
    with _metrics._lock:
        return (dict(_metrics._llm_calls_total), _metrics._llm_fallback_total)


def _metrics_delta(before: tuple, after: tuple) -> tuple:
    calls_b, fb_b = before
    calls_a, fb_a = after
    delta = {ch: calls_a.get(ch, 0) - calls_b.get(ch, 0) for ch in set(calls_b) | set(calls_a)}
    winners = [ch for ch, d in delta.items() if d > 0]
    return winners, fb_a - fb_b


# ── 场景执行 ──

async def run_scenario(name: str, inject: list[str], settings: dict, timeout: float) -> dict:
    collector = _WalkCollector()
    logger = logging.getLogger("netlearn.llm")
    logger.setLevel(logging.INFO)
    logger.addHandler(collector)

    saved = _inject_invalid(settings, inject) if inject else {}
    for ch in CHANNELS:  # 重置熔断器，避免场景间失败计数串扰
        reset_breaker(f"llm_{ch}")

    before = _metrics_snapshot()
    provider = LLMProvider()  # auto 模式（读 config.llm_provider）
    t0 = time.monotonic()
    error = None
    error_type = None
    content = ""
    try:
        resp = await provider.chat(
            [{"role": "user", "content": "请只回复两个字：你好"}],
            temperature=0.0,
            max_tokens=16,
            timeout=timeout,
        )
        content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception as e:  # noqa: BLE001 — 场景需要原样记录任何失败形态
        error = f"{type(e).__name__}: {e}"
        error_type = type(e).__name__
    finally:
        latency = time.monotonic() - t0
        after = _metrics_snapshot()
        _restore(settings, saved)
        logger.removeHandler(collector)

    winners, fb_delta = _metrics_delta(before, after)
    return {
        "scenario": name,
        "injected_invalid": inject,
        "success": error is None and len(winners) == 1 and bool(content.strip()),
        "winner": winners[0] if len(winners) == 1 else winners,
        "fallback_delta": fb_delta,
        "walk": collector.events,
        "latency_ms": round(latency * 1000),
        "content_preview": content.strip()[:40],
        "error": error,
        "error_type": error_type,
    }


def evaluate(res: dict, glm_configured: bool) -> tuple:
    """硬断言判定。只判可判定项；测不到的据实判不过，不凑数。"""
    sc = res["scenario"]
    if sc == "s0":
        ok = res["success"]
        return ok, "auto 链路基线调用成功" if ok else f"基线调用失败: {res['error']}"
    if sc == "s1":
        ok = res["success"] and res["winner"] == "deepseek" and res["fallback_delta"] >= 1
        return ok, (
            f"xfyun 故障后自动回退 deepseek 并成功（回退 {res['fallback_delta']} 次）"
            if ok else
            f"未回退到 deepseek: winner={res['winner']} fallback={res['fallback_delta']} err={res['error']}"
        )
    if sc == "s2":
        ok = (
            res["success"]
            and res["winner"] in ("qwen", "glm")
            and res["fallback_delta"] >= 2
        )
        return ok, (
            f"deepseek 故障后链路继续向后走，落到 {res['winner']} 并成功（回退 {res['fallback_delta']} 次）"
            if ok else
            f"deepseek 故障后未恢复到健康通道: winner={res['winner']} fallback={res['fallback_delta']} err={res['error']}"
        )
    if sc == "s3":
        if glm_configured:
            ok = res["success"] and res["winner"] == "glm" and res["fallback_delta"] >= 3
            return ok, (
                f"前三通道全故障 → 自动回落 GLM 并成功（回退 {res['fallback_delta']} 次）"
                if ok else
                f"未回落到 GLM: winner={res['winner']} fallback={res['fallback_delta']} err={res['error']}"
            )
        ok = (
            res.get("error_type") == LLMUnavailable.__name__
            and res["fallback_delta"] >= 3
            and any(ch == "glm" and outcome == "unconfigured" for ch, outcome in res["walk"])
        )
        return ok, (
            f"GLM 未配置（跳过）→ 链路如实耗尽（回退 {res['fallback_delta']} 次）；GLM 可达性需另行验证"
            if ok else
            f"GLM 未配置但结果异常: winner={res['winner']} fallback={res['fallback_delta']} err={res['error']}"
        )
    return False, f"未知场景 {sc}"


async def amain(args: argparse.Namespace) -> int:
    settings = get_container().settings
    # 语义级注入防护在本测试中关闭：语义分类器自身会经同一 LLMProvider 发起递归调用，
    # 会双倍计数并污染回退链观测。句法级 _sanitize_messages 仍在链路内，不受影响。
    settings["semantic_check"] = {"enabled": False}
    glm_configured = bool(settings.get("glm", {}).get("api_key"))

    names = [args.scenario] if args.scenario else list(SCENARIOS)
    results = []
    for n in names:
        spec = SCENARIOS[n]
        print(f"\n=== {n}: {spec['desc']} ===", flush=True)
        res = await run_scenario(n, spec["inject"], settings, args.timeout)
        ok, reason = evaluate(res, glm_configured)
        res["passed"] = ok
        res["reason"] = reason
        results.append(res)
        print(json.dumps(
            {k: res[k] for k in ("winner", "fallback_delta", "walk", "latency_ms",
                                 "content_preview", "error", "passed", "reason")},
            ensure_ascii=False, indent=1), flush=True)

    all_passed = all(r["passed"] for r in results)

    # 恢复校验（fail-closed）：全部场景结束后做一次无注入调用。
    # 若某场景的无效凭证没被还原，这里会失败——隔离声明不允许只靠"看起来没问题"。
    restore_check = await run_scenario("restore_check", [], settings, args.timeout)
    restore_ok = restore_check["success"]
    print(f"\n=== 恢复校验: {'PASS' if restore_ok else 'FAIL'} ===")
    print(json.dumps(
        {k: restore_check[k] for k in ("winner", "fallback_delta", "walk", "error")},
        ensure_ascii=False, indent=1), flush=True)
    if not restore_ok:
        print("❌ 恢复校验失败：场景注入的无效凭证可能未还原，隔离性存疑，结论不得引用")

    out = {
        "date": datetime.date.today().isoformat(),
        "python": sys.version.split()[0],
        "glm_configured": glm_configured,
        "scenarios": results,
        "restore_check": restore_check,
        "all_passed": all_passed and restore_ok,
    }
    out_path = args.out or os.path.join(
        _HERE, "results", f"llm_fallback_chain_{datetime.date.today().isoformat()}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    overall = all_passed and restore_ok
    print("\n=== 汇总 ===")
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['scenario']}: {r['reason']}")
    print(f"[{'PASS' if restore_ok else 'FAIL'}] restore_check: 场景结束后无注入调用{'成功（凭证已还原）' if restore_ok else '失败（隔离性存疑）'}")
    print(f"\n产物: {out_path}")
    print(f"总体: {'全部通过' if overall else '存在失败（退出码 1，结论不得引用）'}")
    return 0 if overall else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 四通道运行级回退链端到端实证")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default=None,
                        help="只跑单个场景（默认全部）")
    parser.add_argument("--timeout", type=float, default=30.0, help="单次调用超时（秒）")
    parser.add_argument("--out", default=None, help="结果 JSON 输出路径")
    args = parser.parse_args()
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
