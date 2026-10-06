# ============================================================
# PDF 解析服务（课程知识库基础）
# 对标学境：读原文、问选中、回答有出处
# ============================================================

import os
import logging
import tempfile
from typing import Optional

logger = logging.getLogger("netlearn.pdf_reader")

# PDF 解析库
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    HAS_PDFMINER = True
except ImportError:
    HAS_PDFMINER = False


# 教材存储目录
_TEXTBOOK_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "textbooks")
os.makedirs(_TEXTBOOK_DIR, exist_ok=True)


def extract_text_from_pdf(pdf_path: str) -> Optional[str]:
    """从 PDF 文件中提取文本

    Args:
        pdf_path: PDF 文件路径

    Returns:
        提取的文本内容，失败返回 None
    """
    if not os.path.exists(pdf_path):
        logger.error(f"PDF 文件不存在: {pdf_path}")
        return None

    # 优先使用 pdfplumber（更准确）
    if HAS_PDFPLUMBER:
        try:
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"--- 第 {i+1} 页 ---\n{page_text}")
            if text_parts:
                logger.info(f"PDF 解析成功（pdfplumber）: {os.path.basename(pdf_path)}")
                return "\n\n".join(text_parts)
        except Exception as e:
            logger.warning(f"pdfplumber 解析失败: {e}")

    # 降级使用 pdfminer
    if HAS_PDFMINER:
        try:
            text = pdfminer_extract(pdf_path)
            if text and text.strip():
                logger.info(f"PDF 解析成功（pdfminer）: {os.path.basename(pdf_path)}")
                return text
        except Exception as e:
            logger.warning(f"pdfminer 解析失败: {e}")

    logger.error(f"PDF 解析失败，无可用解析库: {pdf_path}")
    return None


def import_textbook(name: str, pdf_path: str, subject: str = "general") -> dict:
    """导入教材到知识库

    1. 解析 PDF 提取文本
    2. 按章节分割
    3. 存储到教材目录
    4. 返回教材信息

    Args:
        name: 教材名称
        pdf_path: PDF 文件路径
        subject: 科目

    Returns:
        {"id", "name", "subject", "chapters", "total_chars", "status"}
    """
    import json
    import uuid
    import datetime

    text = extract_text_from_pdf(pdf_path)
    if not text:
        return {"status": "error", "message": "PDF 解析失败"}

    textbook_id = uuid.uuid4().hex[:12]

    # 按章节分割（根据常见章节标题模式）
    import re
    chapter_pattern = r'(?:^|\n)(?:第[一二三四五六七八九十]+章|Chapter\s+\d+|第\d+章|\d+\.\s+[A-Z])'
    chapters = re.split(chapter_pattern, text)
    chapter_titles = re.findall(chapter_pattern, text)

    chapter_list = []
    for i, content in enumerate(chapters):
        if not content.strip():
            continue
        title = chapter_titles[i - 1].strip() if i > 0 and i - 1 < len(chapter_titles) else f"章节 {i}"
        chapter_list.append({
            "id": f"ch{i}",
            "title": title,
            "content": content.strip()[:5000],
            "char_count": len(content.strip()),
        })

    # 保存教材信息
    textbook_info = {
        "id": textbook_id,
        "name": name,
        "subject": subject,
        "chapters": chapter_list,
        "total_chars": len(text),
        "chapter_count": len(chapter_list),
        "created_at": datetime.datetime.now().isoformat(),
    }

    path = os.path.join(_TEXTBOOK_DIR, f"{textbook_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(textbook_info, f, ensure_ascii=False, indent=2)

    logger.info(f"教材导入成功: {name} ({len(chapter_list)} 章, {len(text)} 字符)")
    return textbook_info


def search_textbook(query: str, textbook_id: Optional[str] = None) -> list[dict]:
    """在教材知识库中搜索

    Args:
        query: 搜索关键词
        textbook_id: 指定教材 ID（可选）

    Returns:
        [{textbook_name, chapter, content, source}]
    """
    import json

    results = []
    keyword = query.lower()

    if not os.path.exists(_TEXTBOOK_DIR):
        return results

    for fname in os.listdir(_TEXTBOOK_DIR):
        if not fname.endswith(".json"):
            continue
        if textbook_id and textbook_id not in fname:
            continue

        try:
            with open(os.path.join(_TEXTBOOK_DIR, fname), "r", encoding="utf-8") as f:
                textbook = json.load(f)
        except Exception:
            continue

        for ch in textbook.get("chapters", []):
            content = ch.get("content", "")
            if keyword in content.lower() or keyword in ch.get("title", "").lower():
                # 找到匹配位置，返回上下文
                idx = content.lower().find(keyword)
                start = max(0, idx - 100)
                end = min(len(content), idx + 200)
                context = content[start:end] if start < end else content[:300]

                results.append({
                    "textbook_name": textbook.get("name", "未知"),
                    "textbook_id": textbook.get("id", ""),
                    "chapter": ch.get("title", ""),
                    "content": context,
                    "source": f"《{textbook.get('name', '')}》- {ch.get('title', '')}",
                })

    return results[:10]


def list_textbooks() -> list[dict]:
    """列出已导入的教材"""
    import json
    textbooks = []
    if not os.path.exists(_TEXTBOOK_DIR):
        return textbooks
    for fname in sorted(os.listdir(_TEXTBOOK_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_TEXTBOOK_DIR, fname), "r", encoding="utf-8") as f:
                tb = json.load(f)
            textbooks.append({
                "id": tb.get("id", ""),
                "name": tb.get("name", "未知"),
                "subject": tb.get("subject", "general"),
                "chapter_count": tb.get("chapter_count", 0),
                "total_chars": tb.get("total_chars", 0),
                "created_at": tb.get("created_at", ""),
            })
        except Exception:
            continue
    return textbooks


def get_textbook_content(textbook_id: str) -> Optional[dict]:
    """获取教材完整内容"""
    import json
    path = os.path.join(_TEXTBOOK_DIR, f"{textbook_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None