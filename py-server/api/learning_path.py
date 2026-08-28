# ============================================================
# API — 学习路径 + 资源推送（408四科全覆盖）
# 赛题功能3：个性化学习路径规划和资源推送
# ============================================================

import json
import logging

from fastapi import APIRouter, Depends
from db.llm_provider import LLMProvider
from models import (
    LearningPathRequest, LearningPathResponse, LearningPathNode,
    LearningPathWithResourcesResponse,
)
from seed_data import LEARNING_PATH_DAG
from shared.auth import get_current_user

logger = logging.getLogger("netlearn.learning_path")

router = APIRouter(prefix="", tags=["learning-path"])

# ── 408四科章节映射（subject key → 有序章节名列表） ──
_SUBJECT_CHAPTERS = {
    "computer_network": [
        "计算机网络概述", "物理层", "数据链路层", "网络层", "运输层", "应用层", "网络安全",
    ],
    "data_structures": [
        "线性表", "栈和队列", "串", "树与二叉树", "图", "查找", "排序",
    ],
    "computer_organization": [
        "计算机概述", "数据表示与运算", "存储系统", "指令系统", "中央处理器", "总线", "IO系统",
    ],
    "operating_system": [
        "操作系统概述", "进程管理", "内存管理", "文件系统", "IO管理",
    ],
}

# 薄弱点关键词 → 章节名映射（四科）
_WEAK_MAP = {
    # 计网
    "概述": "计算机网络概述", "物理": "物理层", "链路": "数据链路层",
    "网络层": "网络层", "运输": "运输层", "应用": "应用层", "安全": "网络安全",
    # 数据结构
    "线性": "线性表", "栈": "栈和队列", "队列": "栈和队列", "串": "串",
    "树": "树与二叉树", "二叉树": "树与二叉树", "图": "图",
    "查找": "查找", "排序": "排序",
    # 计组
    "概述": "计算机概述", "数据表示": "数据表示与运算", "运算": "数据表示与运算",
    "存储": "存储系统", "Cache": "存储系统", "指令": "指令系统",
    "CPU": "中央处理器", "流水线": "中央处理器", "总线": "总线", "IO": "IO系统",
    # 操作系统
    "进程": "进程管理", "线程": "进程管理", "死锁": "进程管理",
    "内存": "内存管理", "页面置换": "内存管理", "文件": "文件系统",
    "磁盘": "文件系统", "IO管理": "IO管理",
}


def _get_chapters(subject: str) -> list[str]:
    """获取指定科目的有序章节列表"""
    return _SUBJECT_CHAPTERS.get(subject, _SUBJECT_CHAPTERS["computer_network"])


def _resolve_subject(profile: dict, req_subject: str) -> str:
    """从请求或画像推断当前科目"""
    if req_subject and req_subject in _SUBJECT_CHAPTERS:
        return req_subject
    if profile:
        p_subject = profile.get("course", "")
        if p_subject in _SUBJECT_CHAPTERS:
            return p_subject
    return "computer_network"


@router.post("/learning-path", response_model=LearningPathResponse)
async def get_learning_path(req: LearningPathRequest, user: dict = Depends(get_current_user)):
    """根据画像和学习进度生成个性化学习路径（408四科）"""
    subject = _resolve_subject(req.profile or {}, req.subject)
    chapters_order = _get_chapters(subject)

    current_progress = req.current_chapter or 0
    if req.profile:
        current_progress = req.profile.get("progress", current_progress)

    nodes, completed_count = [], 0
    for i, name in enumerate(chapters_order):
        info = LEARNING_PATH_DAG.get(name, {})
        chapter_num = info.get("chapter", i + 1)
        if chapter_num < current_progress:
            status = "completed"
            completed_count += 1
        elif chapter_num == current_progress:
            status = "current"
        elif chapter_num == current_progress + 1:
            status = "ready"
        else:
            status = "locked"
        nodes.append(LearningPathNode(
            id=info.get("id", name), name=name, chapter=chapter_num,
            status=status, topics=info.get("topics", []),
        ))

    return LearningPathResponse(
        nodes=nodes, total=len(nodes), completed=completed_count,
        pct=completed_count * 100 // max(len(nodes), 1),
    )


@router.post("/learning-path-with-resources", response_model=LearningPathWithResourcesResponse)
async def get_learning_path_with_resources(req: LearningPathRequest, user: dict = Depends(get_current_user)):
    """学习路径 + 资源推送联动（408四科，赛题功能3）"""
    from prompts import PATH_PLANNER_PROMPT

    subject = _resolve_subject(req.profile or {}, req.subject)
    chapters_order = _get_chapters(subject)

    current_progress = req.current_chapter or 0
    if req.profile:
        current_progress = req.profile.get("progress", current_progress)

    base_nodes, completed_count = [], 0
    for name in chapters_order:
        info = LEARNING_PATH_DAG.get(name, {})
        ch = info.get("chapter", chapters_order.index(name) + 1)
        if ch < current_progress:
            status = "completed"
            completed_count += 1
        elif ch == current_progress:
            status = "current"
        elif ch == current_progress + 1:
            status = "ready"
        else:
            status = "locked"
        base_nodes.append({
            "chapter": name, "chapter_num": ch, "status": status,
            "topics": info.get("topics", []), "priority": ch,
            "mode": "主学" if status in ("current", "ready") else "复习" if status == "completed" else "未开始",
            "estimated_hours": 2, "weak_focus": "",
            "resources": {"doc": "", "quiz": "", "extension": ""},
        })

    weak_chapters = []
    if req.profile and req.profile.get("weak_points"):
        wp = req.profile["weak_points"]
        for kw, ch_name in _WEAK_MAP.items():
            if kw in wp and ch_name in chapters_order and ch_name not in weak_chapters:
                weak_chapters.append(ch_name)

    # L1/L2/L3 三层学情记忆消费（低侵入）：记忆中的薄弱点并入薄弱章节推导
    memory_ctx = ""
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        if user_id:
            from services.memory_service import build_memory_context
            memory_ctx = build_memory_context(user_id, session_id=None, max_episodes=6)
            if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
                for kw, ch_name in _WEAK_MAP.items():
                    if kw in memory_ctx and ch_name in chapters_order and ch_name not in weak_chapters:
                        weak_chapters.append(ch_name)
    except Exception as _me:
        logger.debug(f"学习路径记忆消费失败(降级): {_me}")

    llm_adjusted = False
    try:
        profile_str = "无"
        if req.profile:
            p = req.profile
            profile_str = f"科目:{subject} 基础:{p.get('knowledge_base','未知')} 薄弱点:{p.get('weak_points','无')} 目标:{p.get('goal','未知')} 进度:第{p.get('progress',0)}章 风格:{p.get('learning_style','未知')}"
        user_in = f"学生画像: {profile_str}\n当前科目: {subject}\n当前进度: 第{current_progress}章\n薄弱章节: {weak_chapters or '无'}"
        if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
            user_in += f"\n历史学情记忆(L1/L2/L3): {memory_ctx[:500]}"
        llm = LLMProvider()
        result = await llm.text_completion(PATH_PLANNER_PROMPT, user_in)
        if result:
            import re as _re
            m = _re.search(r'\[.*\]', result, _re.DOTALL)
            if m:
                plan = json.loads(m.group(0))
                plan_map = {item.get("chapter", ""): item for item in plan if isinstance(item, dict)}
                for node in base_nodes:
                    p_item = plan_map.get(node["chapter"])
                    if p_item:
                        node["priority"] = p_item.get("priority", node["priority"])
                        node["mode"] = p_item.get("mode", node["mode"])
                        node["estimated_hours"] = p_item.get("estimated_hours", 2)
                        node["weak_focus"] = p_item.get("weak_focus", "")
                        res = p_item.get("resources", {})
                        if isinstance(res, dict):
                            node["resources"] = {
                                "doc": res.get("doc", ""),
                                "quiz": res.get("quiz", ""),
                                "extension": res.get("extension", ""),
                            }
                base_nodes.sort(key=lambda x: x["priority"])
                llm_adjusted = True
    except Exception as e:
        logger.warning(f"学习路径 LLM 调整失败: {e}")

    return LearningPathWithResourcesResponse(
        nodes=base_nodes, total=len(base_nodes), completed=completed_count,
        pct=completed_count * 100 // max(len(base_nodes), 1),
        weak_focus_chapters=weak_chapters, llm_adjusted=llm_adjusted,
    )
