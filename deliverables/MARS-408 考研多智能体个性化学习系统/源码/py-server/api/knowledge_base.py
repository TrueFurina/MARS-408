# ============================================================
# API — 课程知识库（/api/knowledge-base/*）
# 对标学境：读原文、问选中、回答有出处、PDF展示
# ============================================================

import os
import logging
import json as json_mod
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field

from shared.auth import get_current_user

logger = logging.getLogger("netlearn.knowledge_base")
router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


# ── 请求模型 ──


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=500, description="搜索关键词")
    textbook_id: Optional[str] = Field(None, description="指定教材ID")


class AskRequest(BaseModel):
    selected_text: str = Field(..., max_length=5000, description="选中的文本")
    question: str = Field(..., max_length=500, description="用户的问题")


class MapPdfPagesRequest(BaseModel):
    filename: str = Field(..., max_length=255, description="PDF 文件名（如：王道操作系统.pdf）")


# ── API 端点 ──


@router.get("/textbooks")
async def api_list_textbooks(user: dict = Depends(get_current_user)):
    """列出已导入的教材"""
    from services.pdf_reader import list_textbooks
    textbooks = list_textbooks()
    return {"status": "ok", "textbooks": textbooks, "total": len(textbooks)}


@router.get("/textbook/{textbook_id}")
async def api_get_textbook(
    textbook_id: str,
    user: dict = Depends(get_current_user),
):
    """获取教材完整内容（含章节列表）"""
    from services.pdf_reader import get_textbook_content
    textbook = get_textbook_content(textbook_id)
    if not textbook:
        raise HTTPException(status_code=404, detail="教材不存在")
    return {"status": "ok", "textbook": textbook}


@router.post("/import")
async def api_import_textbook(
    name: str,
    subject: str = "general",
    user: dict = Depends(get_current_user),
):
    """导入教材（从已有文本）"""
    raise HTTPException(status_code=400, detail="请使用 /import-pdf 上传PDF文件")


@router.post("/import-pdf")
async def api_import_pdf(
    file: UploadFile = File(...),
    name: str = "",
    subject: str = "general",
    user: dict = Depends(get_current_user),
):
    """上传并导入PDF教材"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="仅支持 PDF 文件")

    from services.pdf_reader import import_textbook

    # 保存临时文件
    import tempfile
    import uuid
    from fastapi.concurrency import run_in_threadpool
    tmp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}.pdf")
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        textbook_name = name or file.filename.replace(".pdf", "")
        # P1: PDF 全文解析移入线程池，避免阻塞事件循环
        result = await run_in_threadpool(import_textbook, textbook_name, tmp_path, subject)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message", "导入失败"))
        return {"status": "ok", "textbook": result}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/search")
async def api_search_knowledge_base(
    body: SearchRequest,
    user: dict = Depends(get_current_user),
):
    """在教材知识库中搜索"""
    from services.pdf_reader import search_textbook
    results = search_textbook(body.query, body.textbook_id)
    return {"status": "ok", "results": results, "total": len(results)}


@router.post("/map-pdf-pages")
async def api_map_pdf_pages(
    body: MapPdfPagesRequest,
    user: dict = Depends(get_current_user),
):
    """把已导入的向量库 chunks 对齐到原始 PDF 页码，并提取图表标题。

    用法：先调用 /import-pdf 或 import_pdfs.py 导入教材，
    再对同一 PDF 文件调用本接口生成页码映射。
    """
    from fastapi.concurrency import run_in_threadpool
    from services.pdf_page_mapping import map_pdf_chunks

    # 在 documents/教材/ 下定位 PDF 文件
    documents_dir = Path(__file__).resolve().parents[2] / "documents" / "教材"
    pdf_path: Optional[Path] = None
    target = body.filename.strip()
    for root, _dirs, files in os.walk(str(documents_dir)):
        for f in files:
            if f.lower() == target.lower() or Path(f).stem == Path(target).stem:
                pdf_path = Path(root) / f
                break
        if pdf_path:
            break

    if not pdf_path or not pdf_path.is_file():
        raise HTTPException(status_code=404, detail=f"未在 documents/教材/ 下找到 PDF 文件: {body.filename}")

    source_name = pdf_path.name

    # 从向量库读取该源文件对应的 imported chunks
    from db.milvus_client import vector_db
    chunks, total = vector_db.get_all_with_texts(
        "netlearn_kb",
        skip=0,
        limit=10000,
        filter_dict={"type": "imported", "source": source_name},
    )
    if not chunks:
        raise HTTPException(status_code=404, detail=f"向量库中未找到 {source_name} 的导入 chunks，请先导入教材")

    result = await run_in_threadpool(
        map_pdf_chunks, str(pdf_path), chunks, source_name=source_name,
    )
    result["filename"] = source_name
    result["total_chunks"] = total
    return {"status": "ok", **result}


@router.post("/ask")
async def api_ask_selected_text(
    body: AskRequest,
    user: dict = Depends(get_current_user),
):
    """对选中的文本提问（回答有出处）

    流程：
    1. 用户选中文本 + 提问
    2. 用 FrugalRAG 检索相关知识
    3. LLM 基于选中文本 + 检索结果 + 教材内容 生成回答
    4. 返回回答 + 出处引用
    """
    from db.llm_provider import LLMProvider
    from engines.frugal_rag import frugal_rag

    llm = LLMProvider()

    # 用 FrugalRAG 检索相关知识
    knowledge_context = ""
    try:
        chunks = await frugal_rag.retrieve(f"{body.selected_text} {body.question}", course="computer_network", top_k=3)
        if chunks:
            knowledge_context = "\n\n".join([
                f"[来源: {c.get('metadata', {}).get('subject', '知识库')}] {c.get('text', '')[:500]}"
                for c in chunks[:3]
            ])
    except Exception as e:
        logger.warning("RAG retrieve failed (non-blocking): %s", e)

    # 在教材中搜索
    textbook_context = ""
    try:
        from services.pdf_reader import search_textbook
        tb_results = search_textbook(body.question[:50])
        if tb_results:
            textbook_context = "\n\n".join([
                f"[来源: {r['source']}] {r['content']}"
                for r in tb_results[:3]
            ])
    except Exception as e:
        logger.warning("textbook search failed (non-blocking): %s", e)

    # 构建 Prompt
    prompt = f"""你是一个基于教材的学习助手。请根据以下信息回答用户的问题。

## 选中文本
{body.selected_text}

## 用户问题
{body.question}

## 检索到的相关知识
{knowledge_context or '（无相关知识）'}

## 教材内容
{textbook_context or '（无教材内容）'}

请回答用户的问题，并注明信息来源。如果信息不足，请如实说明。"""

    system_prompt = "你是一个严谨的学术助手。回答必须基于提供的文本内容，并注明出处。不要编造信息。"

    try:
        response = await llm.text_completion(system_prompt, prompt, temperature=0.3, max_tokens=1000)
    except Exception as e:
        response = f"抱歉，回答生成失败: {e}"

    return {
        "status": "ok",
        "answer": response,
        "sources": {
            "selected_text": body.selected_text[:200],
            "knowledge_base": bool(knowledge_context),
            "textbook": bool(textbook_context),
        },
    }