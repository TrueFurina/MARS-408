# ============================================================
# 英语学习工作区 API（/api/english/*）
# 对标学境：考纲分级词库 + 单词裂变图谱 + 测验打卡
# ============================================================

import logging
import random
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from shared.auth import get_current_user

logger = logging.getLogger("netlearn.english")
router = APIRouter(prefix="/english", tags=["english"])


# ── 内置词库（考纲分级） ──

# CET-4 核心词汇样本
CET4_WORDS = [
    {"word": "abandon", "meaning": "放弃", "root": "aban-", "affix": "-don", "example": "abandon the plan"},
    {"word": "ability", "meaning": "能力", "root": "abil-", "affix": "-ity", "example": "learning ability"},
    {"word": "absorb", "meaning": "吸收", "root": "sorb-", "affix": "ab-", "example": "absorb knowledge"},
    {"word": "abstract", "meaning": "抽象的", "root": "tract-", "affix": "abs-", "example": "abstract concept"},
    {"word": "access", "meaning": "访问；通道", "root": "cess-", "affix": "ac-", "example": "access the data"},
    {"word": "achieve", "meaning": "实现", "root": "chiev-", "affix": "a-", "example": "achieve the goal"},
    {"word": "acquire", "meaning": "获得", "root": "quir-", "affix": "ac-", "example": "acquire skills"},
    {"word": "adapt", "meaning": "适应", "root": "apt-", "affix": "ad-", "example": "adapt to change"},
    {"word": "adequate", "meaning": "充足的", "root": "equ-", "affix": "ad-", "example": "adequate resources"},
    {"word": "analyze", "meaning": "分析", "root": "lyz-", "affix": "ana-", "example": "analyze the data"},
]

# 考研核心词汇样本
POSTGRAD_WORDS = [
    {"word": "algorithm", "meaning": "算法", "root": "arithm-", "affix": "-thm", "example": "sorting algorithm"},
    {"word": "allocate", "meaning": "分配", "root": "loc-", "affix": "al-", "example": "allocate memory"},
    {"word": "alternative", "meaning": "替代的", "root": "alter-", "affix": "-native", "example": "alternative solution"},
    {"word": "ambiguous", "meaning": "模糊的", "root": "ambig-", "affix": "-uous", "example": "ambiguous meaning"},
    {"word": "artificial", "meaning": "人工的", "root": "art-", "affix": "-ficial", "example": "artificial intelligence"},
    {"word": "autonomous", "meaning": "自主的", "root": "auto-", "affix": "-nomous", "example": "autonomous system"},
    {"word": "binary", "meaning": "二进制的", "root": "bin-", "affix": "-ary", "example": "binary search"},
    {"word": "cache", "meaning": "缓存", "root": "cach-", "affix": "", "example": "cache memory"},
    {"word": "calibrate", "meaning": "校准", "root": "calibr-", "affix": "-ate", "example": "calibrate the sensor"},
    {"word": "certificate", "meaning": "证书", "root": "cert-", "affix": "-ificate", "example": "digital certificate"},
]


@router.get("/vocabulary")
async def get_vocabulary(
    level: str = "cet4",
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """获取考纲分级词库"""
    limit = max(1, min(limit, 200))  # 防负数/超大值导致崩溃
    word_list = CET4_WORDS if level == "cet4" else POSTGRAD_WORDS
    # 随机打乱返回
    selected = random.sample(word_list, min(limit, len(word_list)))
    return {
        "status": "ok",
        "level": level,
        "level_label": {"cet4": "CET-4", "postgrad": "考研英语"}.get(level, level),
        "words": selected,
        "total": len(word_list),
    }


@router.get("/word/{word}")
async def get_word_detail(
    word: str,
    user: dict = Depends(get_current_user),
):
    """获取单词详情（含裂变图谱数据）"""
    all_words = CET4_WORDS + POSTGRAD_WORDS
    target = next((w for w in all_words if w["word"].lower() == word.lower()), None)
    if not target:
        raise HTTPException(status_code=404, detail="单词不存在")

    # 构建裂变图谱：词根相同的单词
    root = target["root"]
    related = [w for w in all_words if w["root"] == root and w["word"] != target["word"]]

    # 图谱节点
    nodes = [{"id": "center", "label": target["word"], "group": "center", "color": "#7c6af2", "value": 30}]
    for r in related:
        nodes.append({"id": r["word"], "label": r["word"], "group": "related", "color": "#06b6d4", "value": 22})

    # 图谱边
    edges = [{"from": "center", "to": r["word"], "label": f"同根: {root}", "color": {"color": "#94a3b8"}} for r in related]

    return {
        "status": "ok",
        "word": target,
        "related_words": related,
        "graph": {"nodes": nodes, "edges": edges},
    }


@router.post("/quiz")
async def generate_quiz(
    level: str = "cet4",
    count: int = 5,
    user: dict = Depends(get_current_user),
):
    """生成词汇测验"""
    count = max(1, min(count, 50))  # 防负数/超大值导致崩溃
    word_list = CET4_WORDS if level == "cet4" else POSTGRAD_WORDS
    selected = random.sample(word_list, min(count, len(word_list)))
    questions = []
    for w in selected:
        # 生成干扰项
        distractors = [x["meaning"] for x in word_list if x["word"] != w["word"]]
        random.shuffle(distractors)
        options = [w["meaning"]] + distractors[:3]
        random.shuffle(options)
        questions.append({
            "word": w["word"],
            "options": options,
            "answer": w["meaning"],
            "example": w["example"],
        })
    return {"status": "ok", "level": level, "questions": questions, "total": len(questions)}