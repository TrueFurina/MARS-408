# -*- coding: utf-8 -*-
"""
门禁：前端不得引用 demo / 合成数据作为展示数值（证据链红线 ①）

背景（2026-09-15 前端证据链审计）：
  scripts/benchmark_results.json 的 results.mode == "demo"，是 --demo 合成产物，
  曾被误当作真产物写进 BenchmarkView.vue 与规划文档。真产物在
  py-server/experiments/results/benchmark_YYYY-MM-DD.json。

本脚本做三件事（全部只读，不改任何文件）：
  R1 扫描 src/：禁止出现 demo/合成数据源的引用与"写死的基准常量"特征
  R2 校验真产物存在且 mode 不是 demo
  R3 校验后端 /api/benchmark/results 只返回真产物

退出码：0 = 通过；1 = 命中红线。CI 中作为 gate 使用。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
REAL_RESULTS_DIR = ROOT / "py-server" / "experiments" / "results"
BACKEND_API_DIR = ROOT / "py-server" / "api"

FAILS: list[str] = []
WARNS: list[str] = []

# R1：src 下不允许出现的模式（正则，忽略大小写）
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"benchmark_results\.json", "引用了 demo 合成产物 scripts/benchmark_results.json"),
    (r"benchmark\.py\s+--demo", "宣称数据来自 benchmark.py --demo（合成模式）"),
    (r"scripts/benchmark", "引用 scripts/benchmark 下的合成产物"),
]

# 允许出现上述模式的地方（本门禁自身、文档、以及说明性注释不受限）
ALLOWED_FILES = {
    "tests/benchmark_evidence_gate.py",
}


def scan_src() -> None:
    if not SRC.is_dir():
        FAILS.append(f"src/ 目录不存在：{SRC}")
        return
    for path in SRC.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".vue", ".ts", ".js"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern, reason in FORBIDDEN_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                line_no = text[: m.start()].count("\n") + 1
                # 出现在注释/说明里的不算违规（说明为何不接入）
                line = text.splitlines()[line_no - 1].strip()
                if line.startswith(("//", "*", "/*", "#", "<!--")):
                    continue
                FAILS.append(f"{rel}:{line_no} {reason}")


def _load_backend_module():
    """加载后端 api/benchmark.py，返回 (module, error)。

    【为什么要注入 fastapi stub】api/benchmark.py 顶部 `from fastapi import ...`，
    但被复用的挑选/端点逻辑本身不依赖 fastapi 的真实行为。为了让本门禁在
    任意 Python 环境（含未装 fastapi 的 CI）都能跑，这里注入最小 stub；
    若环境已有真 fastapi 则原样使用。
    """
    mod_path = BACKEND_API_DIR / "benchmark.py"
    if not mod_path.is_file():
        return None, f"后端接口文件不存在：{mod_path}"
    try:
        import importlib.util
        import types

        try:
            import fastapi  # noqa: F401
        except ImportError:
            stub = types.ModuleType("fastapi")

            class _APIRouter:  # noqa: D401
                def __init__(self, *a, **k):
                    pass

                def get(self, *a, **k):
                    return lambda fn: fn

            class _HTTPException(Exception):  # noqa: D401
                def __init__(self, status_code=500, detail=""):
                    super().__init__(detail)
                    self.status_code = status_code
                    self.detail = detail

            stub.APIRouter = _APIRouter
            stub.HTTPException = _HTTPException
            sys.modules["fastapi"] = stub

        spec = importlib.util.spec_from_file_location("_bm_api_gate", mod_path)
        if spec is None or spec.loader is None:
            return None, f"无法加载 {mod_path}"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, None
    except Exception as e:  # noqa: BLE001
        return None, f"加载后端模块失败：{e}"


def _backend_pick_latest():
    """复用后端 api/benchmark.py 的挑选函数，避免门禁与后端口径漂移。

    【为什么必须复用】本门禁初版自己实现挑选规则，结果选出了
    benchmark_exp2_reproduce_2026-08-17.json，而后端因排除 reproduce/exp2
    实际选的是 benchmark_2026-08-17.json —— 门禁"通过"却与生产不一致，
    比没有门禁更危险。故改为单一真值源。
    """
    mod, err = _load_backend_module()
    if err:
        return None, err
    try:
        return mod._latest_real_result(), None  # noqa: SLF001
    except Exception as e:  # noqa: BLE001
        return None, f"调用后端挑选函数失败：{e}"


def check_real_artifact() -> None:
    """R2：真产物必须存在、且与后端挑选口径同源。

    【为什么这里必须是 FAIL 而不是 WARN】门禁的职责是"证明证据链可用"。
    若产物目录缺失 / 后端挑选函数调不起来，门禁就**无法证明**证据链可用 ——
    此时放行等于"拦不住的控制"（删掉 py-server/api/benchmark.py 即可绕过）。
    故一律 FAIL。
    """
    if not REAL_RESULTS_DIR.is_dir():
        FAILS.append(f"真产物目录不存在：{REAL_RESULTS_DIR}（证据链断裂，前端将无数据源）")
        return
    picked, err = _backend_pick_latest()
    if err:
        FAILS.append(f"无法复用后端挑选口径：{err}（门禁自身失效，等同于无门禁）")
        return
    if not picked:
        FAILS.append("后端未挑中任何真产物，/api/benchmark/results 将返回 404")
        return
    latest = Path(picked)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        FAILS.append(f"真产物读取失败 {latest.name}: {e}")
        return
    mode = data.get("mode") or (data.get("results") or {}).get("mode")
    if mode == "demo":
        FAILS.append(f"后端选中的产物 {latest.name} 的 mode == 'demo'，不应作为证据源")
    else:
        exp1 = data.get("experiment1") or {}
        exp2 = data.get("experiment2") or {}
        n_q = (exp1.get("summary") or {}).get("n_queries")
        n_qq = (exp2.get("summary") or {}).get("n_questions")
        print(f"  [OK] 后端选中真产物：{latest.name}（{n_q} 查询 / {n_qq} 题）")


def check_backend_payload() -> None:
    """R3：直接调用后端端点函数，校验 /api/benchmark/results 的实际响应契约。

    【为什么需要 R3】R2 只证明"磁盘上有真产物"，但前端真正消费的是**接口响应**。
    若接口被改坏（少返回 per_query / provenance.mode 被写成别的值 / 数据源切回 demo），
    R2 依然通过而前端已静默降级 —— 故必须验证端到端契约。
    """
    mod, err = _load_backend_module()
    if err:
        FAILS.append(f"R3 无法加载后端模块：{err}")
        return

    import asyncio

    try:
        payload = asyncio.run(mod.get_benchmark_results())
    except Exception as e:  # noqa: BLE001
        FAILS.append(f"R3 调用 /api/benchmark/results 失败：{e}")
        return

    local: list[str] = []
    prov = payload.get("provenance") or {}
    if prov.get("mode") != "real":
        local.append(
            f"R3 provenance.mode != 'real'（实际 {prov.get('mode')!r}）—— 接口疑似回退了合成数据"
        )
    src = str(prov.get("source_file", ""))
    if "benchmark_results.json" in src:
        local.append(f"R3 接口数据源指向 demo 产物：{src}（证据链红线）")

    n_q = len(payload.get("per_query") or [])
    n_qq = len(payload.get("per_question") or [])
    if n_q == 0:
        local.append("R3 per_query 为空 —— 前端逐查询明细区块将无数据")
    if n_qq == 0:
        local.append("R3 per_question 为空 —— 前端逐题点阵将无数据")

    for key in ("experiment1", "experiment2", "meta"):
        if not payload.get(key):
            local.append(f"R3 响应缺少 {key} 段")

    if local:
        FAILS.extend(local)
    else:
        print(f"  [OK] 接口契约完整：per_query={n_q} / per_question={n_qq} / mode=real")


def main() -> int:
    print("=== benchmark 证据链门禁 ===")
    print("R1 扫描 src/ 是否引用 demo 合成数据 …")
    scan_src()
    print("R2 校验真产物 …")
    check_real_artifact()
    print("R3 校验 /api/benchmark/results 响应契约 …")
    check_backend_payload()

    print()
    for w in WARNS:
        print(f"  [WARN] {w}")
    if FAILS:
        for f in FAILS:
            print(f"  [FAIL] {f}")
        print(f"\n门禁未通过：{len(FAILS)} 项命中红线。")
        return 1
    print("门禁通过：src/ 未引用 demo 合成数据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
