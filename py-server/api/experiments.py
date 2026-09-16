# ============================================================
# API — 真实实验产物读取（证据链：真实证据变现）
#
# 背景（2026-09-15 后端变现）：
#   py-server/experiments/results/ 下沉淀了 51 份 mode=real 的真实实验产物
#   （career_mappo_train / diag_calib_alignment / review_mappo_* /
#    review_shadow_summary_* / sweep_shadow_budget_* / benchmark_* 等），
#   是平台相对"PPT 项目"的决定性护城河——但此前仅 benchmark_2026-08-17.json
#   被前端 useBenchmark 接通，其余 50 份尚未被任何接口/页面变现。
#
#   本接口把它们统一暴露为只读 API，让评审/前端能亲手验证
#   MAPPO / 三元评审 / 预算敏感 等结论都是真的（可溯源到源文件 + sha256）。
#
# 设计纪律（与 benchmark.py 对齐，2026-09-15 证据链审计）：
#   1. 本接口**只返回真实产物**（experiments/results/ 下的文件）；
#   2. 产物缺失或读取失败 → 404/500 + 明确原因，
#      **绝不回退到 demo/合成数据**；
#   3. 响应携带 provenance（来源文件 / 大小 / 修改时间 / sha256 / 样本量），
#      前端必须原样展示，使每个数字可追溯。
# ============================================================

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/experiments", tags=["experiments"])

_RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "experiments",
    "results",
)


# ── 文件名 → 分类 / 可读标题（启发式，仅用于画廊展示）─────────────
_CATEGORY_MAP = [
    (r"^career_", "职业素养 MAPPO"),
    (r"^review_shadow_summary_", "三元评审·影子探针"),
    (r"^review_mappo_", "三元评审·MAPPO"),
    (r"^review_action_dist_", "三元评审·动作分布"),
    (r"^review_", "三元评审"),
    (r"^diag_", "诊断 / 校准对齐"),
    (r"^mappo_", "MARL 算法"),
    (r"^marl_", "MARL 算法"),
    (r"^sweep_shadow_budget_", "预算敏感·扫描"),
    (r"^tune_shadow_budget", "预算敏感·调参"),
    (r"^_b_wrapup_budget", "预算敏感·收尾"),
    (r"^mixer_", "神经混合器"),
    (r"^retrieval_eval_", "检索评测"),
    (r"^benchmark", "检索基准"),
    (r"^accept_", "评审接受"),
]


def _classify(name: str) -> str:
    for pattern, label in _CATEGORY_MAP:
        if re.match(pattern, name):
            return label
    return "其它实验"


def _human_title(name: str) -> str:
    # 去掉目录前缀与日期/时间戳后缀，下划线转空格
    base = re.sub(r"\.json$", "", name)
    base = re.sub(r"_\d{8}(_\d{6})?$", "", base)  # 20260914 / 20260914_144351
    base = re.sub(r"_\d{4}-\d{2}-\d{2}", "", base)
    base = base.replace("_", " ").strip()
    return base or name


def _safe_name(name: str) -> str:
    """校验并归一化请求的名字，禁止路径穿越。返回不带 .json 的基名。"""
    if not name:
        raise HTTPException(status_code=400, detail="缺少产物名称")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", name):
        raise HTTPException(status_code=400, detail="非法的产物名称")
    base = name[:-5] if name.endswith(".json") else name
    if "/" in base or "\\" in base or base in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="非法的产物名称")
    return base


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _list_meta() -> List[Dict[str, Any]]:
    """扫描 results 目录，返回每个真实产物的元信息（同步，置于 to_thread）。"""
    if not os.path.isdir(_RESULTS_DIR):
        raise HTTPException(status_code=500, detail="实验结果目录不存在")
    items: List[Dict[str, Any]] = []
    for fn in sorted(os.listdir(_RESULTS_DIR)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(_RESULTS_DIR, fn)
        if not os.path.isfile(path):
            continue
        try:
            stat = os.stat(path)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mode = data.get("mode") if isinstance(data, dict) else None
            keys = sorted(data.keys()) if isinstance(data, dict) else []
            items.append(
                {
                    "name": fn[:-5],
                    "file": fn,
                    "category": _classify(fn),
                    "title": _human_title(fn),
                    "mode": mode,
                    "real": mode != "demo",
                    "size_bytes": stat.st_size,
                    "modified": time.strftime(
                        "%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)
                    ),
                    "keys": keys,
                }
            )
        except Exception as exc:  # 单文件损坏不影响列表
            items.append(
                {
                    "name": fn[:-5],
                    "file": fn,
                    "category": _classify(fn),
                    "title": _human_title(fn),
                    "mode": None,
                    "size_bytes": 0,
                    "modified": None,
                    "keys": [],
                    "read_error": str(exc),
                }
            )
    # 新的在前
    items.sort(key=lambda x: x.get("modified") or "", reverse=True)
    return items


def _load_detail(base: str) -> Dict[str, Any]:
    """读取单个真实产物完整内容 + provenance（同步，置于 to_thread）。"""
    path = os.path.join(_RESULTS_DIR, base + ".json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"未找到真实产物：{base}")
    try:
        stat = os.stat(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "name": base,
            "file": base + ".json",
            "provenance": {
                "source": path,
                "size_bytes": stat.st_size,
                "modified": time.strftime(
                    "%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)
                ),
                "sha256": _sha256_file(path),
            },
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取真实产物失败：{exc}")


@router.get("")
async def list_experiments(
    category: Optional[str] = Query(None, description="按分类过滤"),
    real_only: bool = Query(False, description="排除 mode=demo 的产物（results/ 下默认均为真实产物）"),
) -> Dict[str, Any]:
    """列出全部真实实验产物（元信息，不含完整数据）。

    experiments/results/ 目录只存放真实实验产物（demo 合成数据已迁至
    scripts/_demo/），故默认列出全部；real_only=True 时仅排除显式 mode=demo 的项。
    """
    items = await asyncio.to_thread(_list_meta)
    if real_only:
        items = [it for it in items if it.get("mode") != "demo"]
    if category:
        items = [it for it in items if it.get("category") == category]
    return {
        "count": len(items),
        "results_dir": _RESULTS_DIR,
        "items": items,
    }


@router.get("/{name}")
async def get_experiment(name: str) -> Dict[str, Any]:
    """返回单个真实产物的完整内容 + provenance（sha256 溯源）。"""
    base = _safe_name(name)
    return await asyncio.to_thread(_load_detail, base)
