# ============================================================
# Docling 教材导入脚本 — IBM Docling 文档理解引擎
# 用法：python import_docling.py [--rebuild] [--max-pages 50]
# ============================================================

import os, sys, json, hashlib, logging, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("import_docling")

PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "documents" / "教材"
MAX_PAGES = int(os.environ.get("DOCLING_MAX_PAGES", "100"))

# 扫描版PDF列表（文字版由 import_pdfs.py 处理）—— 供 import_worker 导入队列复用
SCANNED_PDFS = [
    "操作系统/2025王道操作系统（带书签）.pdf",
    "数据结构/2025王道数据结构（电子书）.pdf",
    "计算机组成原理/2025王道计算机组成原理（电子书）.pdf",
    "计算机网络/916计算机网络[第7版][谢希仁].pdf",
]


def convert_with_docling(pdf_path: str, max_pages: int = 50) -> str:
    """用 Docling 解析 PDF（page_range 限制页数），失败时自动降级到 Tesseract OCR"""
    # 第一步：尝试 Docling
    try:
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        result = converter.convert(pdf_path, page_range=(1, max_pages), raises_on_error=False)
        if result and result.document:
            md = result.document.export_to_markdown()
            if md.strip():
                logger.info(f"  Docling 成功: {len(md)} 字符")
                return md
    except ImportError:
        logger.warning("  Docling 未安装")
    except Exception as e:
        logger.warning(f"  Docling 失败: {type(e).__name__}")

    # 第二步：降级到 Tesseract OCR
    logger.info("  降级到 Tesseract OCR...")
    try:
        from import_pdfs import extract_text_from_pdf_ocr
        text = extract_text_from_pdf_ocr(str(pdf_path))
        if text and text.strip():
            logger.info(f"  Tesseract OCR 成功: {len(text)} 字符")
            return text
    except Exception as e:
        logger.warning(f"  Tesseract OCR 也失败: {e}")

    # 两个引擎都不可用：显式抛出，让调用方（Worker）感知导入失败，
    # 而非静默返回空串导致 job 谎报成功（ADR-007 C1）。
    raise RuntimeError(
        f"Docling 与 Tesseract OCR 均不可用，无法解析扫描版 PDF: {pdf_path}。"
        " 请安装 docling 或 tesseract/pytesseract 后再导入。"
    )


def import_all(rebuild=False):
    sys.path.insert(0, str(PROJECT_ROOT))
    from db.milvus_client import vector_db
    from db.embedder import embed_batch
    from import_pdfs import detect_subject, semantic_chunk

    vector_db.connect()

    # 扫描版PDF列表（文字版已由 import_pdfs.py 处理）
    scanned_pdfs = SCANNED_PDFS

    # 如果 rebuild，先清掉旧的 docling 导入数据
    if rebuild:
        try:
            all_meta = vector_db.get_all_metadata("netlearn_kb")
            docling_ids = [m["id"] for m in all_meta if m.get("metadata", {}).get("type") == "docling"]
            if docling_ids:
                vector_db.delete_by_ids("netlearn_kb", docling_ids)
                logger.info(f"已清理 {len(docling_ids)} 条旧 Docling 导入数据")
        except Exception:
            pass

    total = 0
    for rel_path in scanned_pdfs:
        pdf_path = DOCS_DIR / rel_path
        if not pdf_path.exists():
            logger.warning(f"文件不存在: {rel_path}")
            continue

        start = time.time()
        logger.info(f"Docling 解析: {rel_path}")
        md_text = convert_with_docling(str(pdf_path), max_pages=MAX_PAGES)

        if not md_text.strip():
            logger.warning(f"  无有效文本，跳过")
            continue

        # 语义分块
        chunks = semantic_chunk(md_text)
        subject = detect_subject(str(pdf_path))
        elapsed = time.time() - start
        logger.info(f"  完成: {len(chunks)} 块, {len(md_text)} 字符 ({elapsed:.0f}s)")

        # E5 编码 + 入库
        texts = [c for c in chunks]
        embs = embed_batch(texts)
        vc = []
        for i, c in enumerate(chunks):
            cid = hashlib.md5(f"docling_{Path(rel_path).stem}_{i}".encode()).hexdigest()[:12]
            vc.append({
                "id": f"docling_{cid}",
                "text": c,
                "metadata": {
                    "subject": subject,
                    "chapter": "Docling导入",
                    "type": "docling",
                    "source": Path(rel_path).name,
                },
                "embedding": embs[i],
            })
        inserted = vector_db.insert("netlearn_kb", vc)
        total += inserted
        logger.info(f"  入库 {inserted} 条")

    final = vector_db.count("netlearn_kb")
    logger.info(f"Docling 导入完成！本次新增 {total} 条，向量库总计 {final} 条")


if __name__ == "__main__":
    import sys, subprocess
    from pathlib import Path
    print("[DEPRECATED] import_docling.py 不再直写向量库；已改为通过后端导入队列导入。")
    print("  等效命令： python tools/import_client.py --type docling [--rebuild] [--max-pages N]")
    client = Path(__file__).parent / "tools" / "import_client.py"
    args = [sys.executable, str(client), "--type", "docling"]
    if "--rebuild" in sys.argv:
        args.append("--rebuild")
    max_pages = 100
    if "--max-pages" in sys.argv:
        idx = sys.argv.index("--max-pages") + 1
        if idx < len(sys.argv):
            max_pages = int(sys.argv[idx])
    args.extend(["--max-pages", str(max_pages)])
    try:
        sys.exit(subprocess.call(args))
    except Exception as e:
        print(f"无法启动导入客户端（请先启动后端 python main.py）：{e}")
        sys.exit(1)
