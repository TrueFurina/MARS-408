# -*- coding: utf-8 -*-
# ============================================================
# api/kg408.py — 408 知识图谱骨架查询接口
#
# 端点（4 个，挂载后为 /api/kg408/*）：
#   GET /kg408/graph?subject=DS|CO|OS|CN|all → {nodes, edges, stats, provenance}
#   GET /kg408/ego/{kp_id}?hops=1|2          → {ego, hop1, hop2, candidates}
#   GET /kg408/stats                         → 统计（与 kg408_stats.json 同口径）
#   GET /kg408/unresolved                    → 未解析清单（诚信透明，隐藏即伪证）
#
# 本模块只读，不写任何状态；与 legacy KNOWLEDGE_GRAPH 完全解耦（决策 D4）。
#
# ── 鉴权（QA M13 判断与处置）──────────────────────────────────
# 结论：**原实现漏了鉴权，属遗漏而非有意公开**。依据：
#   1. 本项目的同级数据端点全部要求登录——api/subjects.py 的 /subjects 与
#      /knowledge-graph、api/knowledge.py 的 POST /knowledge/graph、
#      api/teacher.py、api/achievement.py、api/agents.py 均带
#      Depends(get_current_user)。
#   2. 本项目**没有全局鉴权中间件**（实测：无凭据访问 /api/subjects 返回 401，
#      而 /api/kg408/* 曾返回 200）——说明保护完全依赖路由级 Depends，
#      少写一个就是真的开了一个匿名口子。
#   3. 图数据本身不敏感，但匿名可枚举整份课程知识图谱结构，属于不必要的信息暴露。
# 处置：在 router 级统一挂 Depends(get_current_user)，与其它路由保持一致。
# 若将来确需匿名只读（例如公开演示页），请显式改为按端点挂载并在此处写明理由，
# 不要靠「忘记加」来达到公开效果。
# ============================================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from services import kg408 as kg408svc
from shared.auth import get_current_user

logger = logging.getLogger("netlearn.api.kg408")

router = APIRouter(
    prefix="/kg408",
    tags=["kg408"],
    dependencies=[Depends(get_current_user)],
)

_ALLOWED_SUBJECTS = ("DS", "CO", "OS", "CN", "ALL")
_SUBJECT_CN = {
    "DS": "数据结构",
    "CO": "计算机组成原理",
    "OS": "操作系统",
    "CN": "计算机网络",
    "ALL": "全部科目",
}
_ALLOWED_REASONS = ("absent_in_skeleton", "ambiguous_multi_match", "chapter_level_only")


def _store() -> kg408svc.Kg408Store:
    """取共享 store；加载失败时给出可操作的 500 提示（而非 500 裸栈）。"""
    try:
        return kg408svc.get_store()
    except FileNotFoundError as exc:
        logger.error("kg408 真源未生成: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "408 图谱真源尚未生成。请先运行："
                "python scripts/build_kg408.py --source <骨架HTML> --out-dir data/kg408"
            ),
        ) from exc
    except Exception as exc:  # pragma: no cover - 兜底
        logger.exception("kg408 加载失败")
        raise HTTPException(status_code=500, detail=f"kg408 加载失败: {exc}") from exc


@router.get("/graph")
async def get_graph(
    subject: str = Query("all", description="科目：DS / CO / OS / CN / all"),
) -> Dict[str, Any]:
    """返回整图或指定科目的子图，含统计与溯源。"""
    s = str(subject or "all").strip().upper()
    if s not in _ALLOWED_SUBJECTS:
        raise HTTPException(
            status_code=400,
            detail=f"subject 非法: {subject}。可选 {list(_ALLOWED_SUBJECTS)}",
        )
    store = _store()
    view = store.graph_view(s)
    view["subject"] = s
    view["subject_name"] = _SUBJECT_CN.get(s, s)
    return view


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """返回统计。

    口径（QA M2）：统计由 `kg408.json` 的 nodes/edges/unresolved **实时重算**
    （`Kg408Store.stats()`），不再读取 `kg408_stats.json` 里落盘的值——
    后者只是派生产物，与重算值一致由 `scripts/verify_kg408.py` 强制保证。
    """
    store = _store()
    return {
        "stats": store.stats(),
        "provenance": store.provenance.to_dict(),
        "unresolved_count": len(store.unresolved()),
    }


@router.get("/unresolved")
async def get_unresolved(
    reason: Optional[str] = Query(None, description="按 reason 过滤：absent_in_skeleton / ambiguous_multi_match / chapter_level_only"),
) -> Dict[str, Any]:
    """暴露未解析引用清单（诚信产物：宁可挂起，不可错配）。

    QA M10 修复：`reason` 非法值此前**静默返回空列表**（200 + count=0），
    拼错一个字母就会让人误判「系统没有问题项」——这在诚信场景下是危险的
    误读。现在非法值一律 **400**，并列出合法取值。
    """
    store = _store()
    if reason is not None and reason not in _ALLOWED_REASONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"reason 非法: {reason!r}。合法取值：{list(_ALLOWED_REASONS)}"
                "（不传表示不过滤）。为避免把拼写错误误读为「无未解析项」，"
                "非法值不再返回空列表。"
            ),
        )
    items: List[Dict[str, Any]] = [u.to_dict() for u in store.unresolved()]
    if reason:
        items = [u for u in items if u.get("reason") == reason]
    return {
        "count": len(items),
        "total": len(store.unresolved()),
        "reason_filter": reason,
        "allowed_reasons": list(_ALLOWED_REASONS),
        "policy": (
            "未解析引用一律如实挂起，禁止模糊相似度兜底匹配。"
            "resolution 只取 exact/alias/chapter_level/manual。"
        ),
        "unresolved": items,
    }


@router.get("/ego/{kp_id:path}")
async def get_ego(
    kp_id: str,
    hops: int = Query(2, ge=1, le=2, description="跳数：1 或 2"),
) -> Dict[str, Any]:
    """返回以 kp 为中心的 1~2 跳 ego-graph（BayesG 聚焦掩码的采样空间）。"""
    store = _store()
    result = store.ego_graph(kp_id, hops=hops)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"考点不存在: {kp_id}。可用 id 形如 408:DS:CH06:KP04",
        )
    return result
