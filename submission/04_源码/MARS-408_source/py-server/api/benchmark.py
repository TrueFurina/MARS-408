# ============================================================
# API — Benchmark 真产物读取（证据链 P0）
#
# 背景（2026-09-15 前端证据链审计）：
#   此前前端 src/views/BenchmarkView.vue 把四组聚合数硬编码为常量，
#   注释却写"来自 scripts/benchmark.py --demo 的真实输出" —— 自相矛盾：
#   scripts/benchmark.py:12 明确写着"--demo  演示模式（合成数据，无需依赖）"，
#   其产物 scripts/benchmark_results.json 的 results.mode 字段值就是 "demo"。
#
#   真产物在 py-server/experiments/results/benchmark_YYYY-MM-DD.json：
#     · experiment1: 28 条查询，FrugalRAG vs 全量检索（含 per_query 明细）
#     · experiment2: 30 题 × 3 次，NeuralMixer vs 加权投票（含 per_question 明细）
#     · meta: random_seed / env(python, torch, numpy) / kb_chunks / top_k
#
# 设计纪律：
#   1. 本接口**只返回真实产物**；
#   2. 产物缺失或读取失败 → 404/500 + 明确原因，
#      **绝不回退到 demo/合成数据**（否则等于把假数据换个地方再骗一次）；
#   3. 响应携带 provenance（来源文件 / 修改时间 / 样本量 / 随机种子 / 环境版本），
#      前端必须原样展示，使每个数字可追溯。
# ============================================================

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

# py-server/experiments/results/
_RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "experiments",
    "results",
)
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _latest_real_result() -> Optional[str]:
    """挑选最新的真产物文件。

    入选条件：benchmark_*.json
    排除：
      · 含 reproduce / exp2 的复现文件（单实验复现，非主结果）
      · 任何 mode 为 demo 的产物
    """
    if not os.path.isdir(_RESULTS_DIR):
        return None

    candidates: list[str] = []
    for name in os.listdir(_RESULTS_DIR):
        if not (name.startswith("benchmark_") and name.endswith(".json")):
            continue
        if "reproduce" in name or "exp2" in name:
            continue
        # 排除 demo 合成产物（若有混入）
        try:
            with open(os.path.join(_RESULTS_DIR, name), "r", encoding="utf-8") as f:
                head = json.load(f)
            if (head.get("results") or {}).get("mode") == "demo" or head.get("mode") == "demo":
                continue
        except Exception:
            # 读不动的文件不作为候选，交由 404 暴露问题，而不是静默使用可疑数据
            continue
        candidates.append(name)

    if not candidates:
        return None
    candidates.sort()
    return os.path.join(_RESULTS_DIR, candidates[-1])


@router.get("/results")
async def get_benchmark_results() -> Dict[str, Any]:
    """返回最新的真实 benchmark 产物（汇总 + per_query 明细 + provenance）。"""
    path = _latest_real_result()
    if not path:
        raise HTTPException(
            status_code=404,
            detail="未找到真实 benchmark 产物（期待 py-server/experiments/results/benchmark_*.json）",
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"benchmark 产物读取失败: {e}")

    st = os.stat(path)
    meta = data.get("meta", {}) or {}
    exp1 = data.get("experiment1", {}) or {}
    exp2 = data.get("experiment2", {}) or {}
    s1 = exp1.get("summary") or {}
    s2 = exp2.get("summary") or {}

    return {
        "provenance": {
            "source_file": os.path.relpath(path, _PKG_ROOT).replace("\\", "/"),
            "file_name": os.path.basename(path),
            "file_mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
            "file_size_bytes": st.st_size,
            "mode": "real",
            "n_queries": s1.get("n_queries"),
            "n_questions": s2.get("n_questions"),
            "n_trials_per_question": s2.get("n_trials_per_question"),
            "random_seed": meta.get("random_seed"),
            "benchmark_date": meta.get("date"),
            "env": meta.get("env", {}),
        },
        "meta": meta,
        "experiment1": s1,
        "experiment2": s2,
        "per_query": exp1.get("per_query", []),
        "per_question": exp2.get("per_question", []),
    }


@router.get("/results/per-question")
async def get_benchmark_per_question() -> Dict[str, Any]:
    """experiment2 的逐题明细（30 题 × 3 次观测），供下钻查看。"""
    path = _latest_real_result()
    if not path:
        raise HTTPException(status_code=404, detail="未找到真实 benchmark 产物")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"benchmark 产物读取失败: {e}")

    return {
        "provenance": {"file_name": os.path.basename(path)},
        "per_question": (data.get("experiment2") or {}).get("per_question", []),
    }
