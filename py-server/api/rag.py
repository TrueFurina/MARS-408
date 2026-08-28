# ============================================================
# API — RAG 检索与题目生成（/api/rag/*）
# ============================================================

import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from db.milvus_client import vector_db
from engines.frugal_rag import frugal_rag
from models import (
    RAGSearchRequest, RAGSearchResponse, RAGSearchResult,
    GenerateQuestionsRequest, GenerateQuestionsResponse,
)
from seed_data import SEED_SUBJECTS, SEED_QUESTIONS
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota

logger = logging.getLogger("netlearn.rag")
# F-011：RAG 检索端点统一鉴权 + 每用户 LLM 配额（429）
router = APIRouter(prefix="/rag", tags=["rag"], dependencies=[Depends(require_llm_quota)])


@router.get("/status")
async def rag_status(user: dict = Depends(get_current_user)):
    """知识库状态统计（展示 RAG 知识库规模）"""
    from db.milvus_client import vector_db
    from collections import Counter

    total = vector_db.count("netlearn_kb")
    # 按科目统计（从 metadata 中读取）
    subject_counts = Counter()
    try:
        all_docs = vector_db.search("netlearn_kb", query_vector=[0.0] * 768, top_k=total)
        for doc in all_docs:
            meta = doc.get("metadata", {})
            subject = meta.get("subject", "unknown")
            subject_counts[subject] += 1
    except Exception as e:
        logger.warning("RAG stats: vector search failed (non-blocking): %s", e)

    return {
        "total_docs": total,
        "by_subject": dict(subject_counts.most_common()),
        "engine": "FrugalRAG (E5 + BM25 + Reranker)",
        "dimension": 768,
        "embedding_model": "intfloat/e5-base-v2",
    }


@router.post("/search", response_model=RAGSearchResponse)
async def rag_search(req: RAGSearchRequest, user: dict = Depends(get_current_user)):
    """语义搜索知识库（使用 FrugalRAG E5+BM25 融合检索，注入 L1/L2/L3 学情记忆）"""
    # L1/L2/L3 三层学情记忆增强（低侵入：薄弱点并入查询，检索个性化）
    query = req.query
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        if user_id:
            from services.memory_service import build_memory_context
            memory_ctx = build_memory_context(user_id, session_id=None, max_episodes=4)
            if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
                import re as _re
                weak_block = _re.search(r"薄弱[：:]\s*(.+?)(?:\n|$)", memory_ctx)
                if weak_block:
                    weak_terms = [w.strip() for w in weak_block.group(1).split(",") if w.strip()][:3]
                    if weak_terms:
                        query = f"{req.query} {' '.join(weak_terms)}"
    except Exception as _me:
        logger.debug(f"RAG 记忆增强失败(降级): {_me}")

    # 使用 FrugalRAG 进行融合检索
    course_filter = req.course if req.course and req.course != "all" else None
    results = await frugal_rag.retrieve(
        query=query,
        course=course_filter or "computer_network",
        top_k=req.top_k,
    )

    items = []
    for r in results:
        items.append(RAGSearchResult(
            id=r.get("id", ""),
            content=r.get("text", ""),
            metadata=r.get("metadata", {}),
            distance=r.get("score", 0.0),
        ))
    return RAGSearchResponse(results=items)


@router.post("/generate", response_model=GenerateQuestionsResponse)
async def rag_generate(req: GenerateQuestionsRequest, user: dict = Depends(get_current_user)):
    """生成练习题（从种子题库筛选 + LLM 补充）"""
    pool = [q for q in SEED_QUESTIONS
            if (not req.subject or q["subject"] == req.subject)
            and (not req.chapter or q["chapter"] == req.chapter)
            and (req.question_type == "all" or q["type"] == req.question_type)
            and (req.difficulty == "all" or q["difficulty"] == req.difficulty)]

    if not pool:
        return GenerateQuestionsResponse(
            questions=[],
            message="暂未找到匹配的题目，请调整筛选条件。",
        )

    import random
    random.shuffle(pool)
    questions = pool[:req.count]

    return GenerateQuestionsResponse(questions=questions)
