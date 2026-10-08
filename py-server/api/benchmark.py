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
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("netlearn.benchmark_api")

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

# 真产物必须同时含这两段，端点才可能完整服务（experiment1 → per_query，
# experiment2 → per_question）。缺任一段的产物不是"旧版本"，而是**另一类**产物，
# 详见 _latest_real_result 的 docstring（2026-10-08 实测事故）。
_REQUIRED_BUNDLE_KEYS = ("experiment1", "experiment2")


# ── 响应契约（OpenAPI/前端类型生成的真值源）──
# 【为什么必须挂 response_model】此前端点返回 Dict[str, Any]，OpenAPI 里是
# 开放索引签名 {[k: string]: unknown}，前端从契约拿不到任何字段信息——
# 契约层形同虚设。此处给出顶层形状；行级明细保持 Dict 宽容（产物字段
# 可能随版本演化，过度收紧会把"新字段"变成 500）。
class BenchmarkResultsResponse(BaseModel):
    provenance: Dict[str, Any]
    meta: Dict[str, Any]
    experiment1: Dict[str, Any]
    experiment2: Dict[str, Any]
    per_query: List[Dict[str, Any]]
    per_question: List[Dict[str, Any]]


class PerQuestionResponse(BaseModel):
    provenance: Dict[str, Any]
    per_question: List[Dict[str, Any]]

# py-server/experiments/results/
_RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "experiments",
    "results",
)
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _artifact_head(path: str) -> Optional[Dict[str, Any]]:
    """读取产物 JSON 顶层对象；读取失败或顶层不是对象时返回 None。

    调用方据此**排除**该文件（交由 404 暴露问题），而不是静默使用可疑数据。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _declared_mode(head: Dict[str, Any]) -> Optional[str]:
    """产物自述的数据来源模式（兼容 results.mode 与顶层 mode 两种写法）。"""
    results = head.get("results")
    if isinstance(results, dict) and results.get("mode"):
        return str(results["mode"])
    mode = head.get("mode")
    return str(mode) if mode else None


def _scan_candidates() -> tuple[list[str], list[str]]:
    """扫描产物目录，返回 (合格候选文件名, 被跳过的候选描述)，两者均按文件名排序。

    抽成独立函数的理由：门禁 tests/benchmark_evidence_gate.py 需要**报出被跳过的候选**。
    2026-10-08 的事故有两半 —— ①不合格产物抢占了候选位（端点静默降级）；
    ②它是"新的、真实的"数据却因结构不符被丢掉，而没有任何地方说得出这件事。
    只修①（让挑选正确）而不修②，等于把问题从"端点返回空"变成"数据被静默忽略"。
    故本函数是"哪些被跳过"的单一真值源，端点与门禁共用。
    """
    if not os.path.isdir(_RESULTS_DIR):
        return [], []

    candidates: list[str] = []
    skipped: list[str] = []
    for name in sorted(os.listdir(_RESULTS_DIR)):
        if not (name.startswith("benchmark_") and name.endswith(".json")):
            continue
        if "reproduce" in name or "exp2" in name:
            continue
        head = _artifact_head(os.path.join(_RESULTS_DIR, name))
        if head is None:
            # 读不动的文件不作为候选，交由 404 暴露问题，而不是静默使用可疑数据
            skipped.append(f"{name}(读取失败/非对象)")
            continue
        if _declared_mode(head) == "demo":
            skipped.append(f"{name}(demo)")
            continue
        missing = [k for k in _REQUIRED_BUNDLE_KEYS if not head.get(k)]
        if missing:
            skipped.append(f"{name}(缺 {'/'.join(missing)})")
            continue
        candidates.append(name)
    return candidates, skipped


def _latest_real_result() -> Optional[str]:
    """挑选最新的**结构完整**的真产物文件（benchmark_*.json）。

    入选条件（需全部满足）：
      · 文件名 benchmark_*.json，且不含 reproduce / exp2（单实验复现文件，非主结果）
      · 自述模式不为 demo（合成产物）
      · **是完整 bundle**：experiment1 与 experiment2 两段同时存在（见 _REQUIRED_BUNDLE_KEYS）

    【为什么必须校验结构，而不是只按文件名排序取最新】
    2026-10-08 实测事故：同目录下混入了**另一类**产物 `benchmark_2026-10-08.json`
    （experiment1 单实验输出，顶层键 ['meta','per_query','summary']，20KB
    vs 完整 bundle 的 256KB；其 meta 自述 "exp2 BLOCKED"）。
    旧逻辑排除完 demo 后 `candidates.sort()` 取最后一个 —— 该文件名日期最新，于是被选中：
      · data 里没有 experiment1/experiment2 键 ⇒ 响应 experiment1/experiment2 为空、
        per_query/per_question 为 []，
      · 而 provenance.mode 仍**写死 "real"** ⇒ 端点自称返回真数据，却什么都没返回。
    真实 CI 后果（run 37787528338）：① Benchmark evidence chain gate R3 四项全红；
      ② 前端 useBenchmark.spec.ts 取 data.experiment1.per_query 得到 undefined → TypeError。
    """
    candidates, skipped = _scan_candidates()
    if skipped:
        logger.warning(
            "benchmark 产物候选被跳过（不满足端点契约 %s 两段齐全）：%s",
            "+".join(_REQUIRED_BUNDLE_KEYS),
            "、".join(skipped),
        )
    if not candidates:
        return None
    return os.path.join(_RESULTS_DIR, candidates[-1])


@router.get("/results", response_model=BenchmarkResultsResponse)
async def get_benchmark_results() -> Dict[str, Any]:
    """返回最新的真实 benchmark 产物（汇总 + per_query 明细 + provenance）。"""
    path = _latest_real_result()
    if not path:
        raise HTTPException(
            status_code=404,
            detail=(
                "未找到合格的真实 benchmark 产物：期待 py-server/experiments/results/"
                f"benchmark_*.json，且须同时含 {' 与 '.join(_REQUIRED_BUNDLE_KEYS)} 两段"
                "（缺任一即不合格，例如只有 experiment1 的单实验产物）。"
                "服务端日志已逐条列出被跳过的候选及原因。"
            ),
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


@router.get("/results/per-question", response_model=PerQuestionResponse)
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
