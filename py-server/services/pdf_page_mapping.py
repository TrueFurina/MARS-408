# ============================================================
# PDF 页码映射服务（移植自 OS_course pdf_page_mapping.py）
# 把向量库中的 imported chunks 对齐到原始 PDF 页码，并提取图表标题
# 纯算法部分无外部依赖；PDF 文本提取复用 pdfplumber/pdfminer
# ============================================================

import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

logger = logging.getLogger("netlearn.pdf_page_mapping")

# 图表标题模式：图/表 + 章节编号，如「图 3-1 进程状态转换」
CHART_CAPTION_PATTERN = re.compile(r"(?:图|表)\s*\d+(?:\s*[-.]\s*\d+)+[^\n]{0,80}")
# 已有定位器后缀（幂等：重复映射时先去掉旧后缀）
PDF_LOCATOR_PATTERN = re.compile(r"\s+\|\s+PDF\s+p\.\d+(?:-\d+)?\s*$")


class PdfPageMappingError(RuntimeError):
    pass


@dataclass(frozen=True)
class PageMatch:
    start_page: int
    end_page: int
    matched_anchors: int
    anchor_count: int

    @property
    def confidence(self) -> float:
        return round(self.matched_anchors / max(1, self.anchor_count), 3)


def normalize_alignment_text(value: str) -> str:
    """NFKC 归一化 + 去空白/标点，只保留字母数字（含中文）。"""
    normalized = unicodedata.normalize("NFKC", value).lower()
    return "".join(character for character in normalized if character.isalnum())


def _anchors(value: str, length: int) -> list[str]:
    """在文本的多个固定比例位置取定长片段作为对齐锚点。"""
    if len(value) < length:
        return []
    positions = (0.03, 0.18, 0.36, 0.54, 0.72, 0.9)
    limit = len(value) - length
    anchors: list[str] = []
    for fraction in positions:
        anchor = value[min(limit, int(limit * fraction)):][:length]
        if len(set(anchor)) < 7 or anchor in anchors:
            continue
        anchors.append(anchor)
    return anchors


def _match_anchors(
    anchors: Sequence[str],
    pages: Sequence[str],
    start: int,
    end: int,
) -> tuple[Counter, int]:
    """每个锚点在 [start, end) 页范围内投票；命中 >3 页的锚点视为噪声丢弃。"""
    votes: Counter = Counter()
    matched = 0
    for anchor in anchors:
        hits = [index for index in range(start, end) if anchor in pages[index]]
        if not hits or len(hits) > 3:
            continue
        matched += 1
        for index in hits:
            votes[index] += 1
    return votes, matched


def align_chunk_to_pages(
    content: str,
    normalized_pages: Sequence[str],
    *,
    previous_page: int = 0,
) -> Optional[PageMatch]:
    """仅当多个精确文本锚点一致时才返回页码（保守策略）。

    分两档：32 字符锚点需 ≥2 命中，20 字符锚点需 ≥3 命中；
    先在前文附近窗口内匹配，失败则全库匹配；结果做相邻页聚类。
    """
    normalized = normalize_alignment_text(content)
    if len(normalized) < 40 or not normalized_pages:
        return None

    page_count = len(normalized_pages)
    window_start = max(0, previous_page - 2)
    window_end = min(page_count, previous_page + (80 if previous_page == 0 else 16))

    for anchor_length, minimum_hits in ((32, 2), (20, 3)):
        anchors = _anchors(normalized, anchor_length)
        if not anchors:
            continue
        votes, matched = _match_anchors(anchors, normalized_pages, window_start, window_end)
        if matched < minimum_hits:
            votes, matched = _match_anchors(anchors, normalized_pages, 0, page_count)
        if matched < minimum_hits or not votes:
            continue

        candidate_pages = sorted(votes)
        cluster_scores = {
            page: sum(votes.get(candidate, 0) for candidate in range(max(0, page - 1), min(page_count, page + 2)))
            for page in candidate_pages
        }
        best = min(
            candidate_pages,
            key=lambda page: (-cluster_scores[page], abs(page - previous_page), page),
        )
        selected = [page for page in candidate_pages if abs(page - best) <= 1]
        return PageMatch(
            start_page=min(selected) + 1,
            end_page=max(selected) + 1,
            matched_anchors=matched,
            anchor_count=len(anchors),
        )
    return None


def _page_locator(original: Optional[str], match: PageMatch) -> str:
    """在原有 source_locator 上追加「 | PDF p.X-Y」定位器。"""
    base = PDF_LOCATOR_PATTERN.sub("", original or "").strip()
    pages = (
        str(match.start_page)
        if match.start_page == match.end_page
        else f"{match.start_page}-{match.end_page}"
    )
    suffix = f" | PDF p.{pages}"
    return f"{base[:500 - len(suffix)]}{suffix}"


def extract_pdf_pages(pdf_path: str) -> list[str]:
    """逐页提取 PDF 文本（优先 pdfplumber，降级 pdfminer），返回按页索引的原始文本。"""
    from pdf_reader import extract_text_from_pdf
    raw = extract_text_from_pdf(pdf_path)
    if not raw:
        raise PdfPageMappingError(f"PDF 文本提取失败: {Path(pdf_path).name}")
    # extract_text_from_pdf 输出「--- 第 N 页 ---\n...」格式
    blocks = re.split(r"---\s*第\s*(\d+)\s*页\s*---", raw)
    pages: list[str] = []
    # blocks[0] 是分隔符前的空串；之后是 (页码, 内容) 交替
    for i in range(1, len(blocks) - 1, 2):
        pages.append(blocks[i + 1] or "")
    if not pages:
        # 降级：整体文本当一页处理
        pages = [raw]
    return pages


def map_pdf_chunks(
    pdf_path: str,
    chunks: list[dict],
    *,
    source_name: Optional[str] = None,
) -> dict:
    """把向量库中的 imported chunks 对齐到 PDF 页码。

    Args:
        pdf_path: 原始 PDF 文件路径
        chunks: [{id, content, metadata:{source, chunk_index, ...}}]
        source_name: 用于输出定位器的源名（默认取 chunks[0].metadata.source）

    Returns:
        {
          "documents": 1,
          "mapped_chunks": int,
          "unmatched_chunks": int,
          "page_count": int,
          "chart_captions": [{caption, page}],
          "chunk_pages": {chunk_id: {"start_page", "end_page", "locator", "confidence"}},
          "mapped_at": iso,
          "method": "exact_text_anchor_v1",
          "errors": [...],
        }
    """
    if not chunks:
        return {
            "documents": 0, "mapped_chunks": 0, "unmatched_chunks": 0,
            "page_count": 0, "chart_captions": [], "chunk_pages": {},
            "mapped_at": datetime.now().isoformat(), "method": "exact_text_anchor_v1",
            "errors": ["没有可映射的 chunks"],
        }

    try:
        pages = extract_pdf_pages(pdf_path)
    except PdfPageMappingError as exc:
        return {
            "documents": 0, "mapped_chunks": 0, "unmatched_chunks": 0,
            "page_count": 0, "chart_captions": [], "chunk_pages": {},
            "mapped_at": datetime.now().isoformat(), "method": "exact_text_anchor_v1",
            "errors": [str(exc)],
        }

    normalized_pages = [normalize_alignment_text(page) for page in pages]
    source_name = source_name or (chunks[0].get("metadata") or {}).get("source", "")

    mapped_chunks = 0
    unmatched_chunks = 0
    previous_page = 0
    chunk_pages: dict[str, dict] = {}
    chart_captions: list[dict] = []

    for chunk in chunks:
        content = chunk.get("content", "")
        match = align_chunk_to_pages(content, normalized_pages, previous_page=previous_page)
        if not match:
            unmatched_chunks += 1
            continue
        locator = _page_locator(None, match)
        chunk_pages[chunk["id"]] = {
            "start_page": match.start_page,
            "end_page": match.end_page,
            "locator": locator,
            "confidence": match.confidence,
        }
        previous_page = max(previous_page, match.start_page - 1)
        mapped_chunks += 1

        captions = [caption.strip() for caption in CHART_CAPTION_PATTERN.findall(content)]
        for caption in captions[:5]:
            if len(chart_captions) >= 200:
                break
            chart_captions.append({"caption": caption, "page": match.start_page})

    return {
        "documents": 1,
        "mapped_chunks": mapped_chunks,
        "unmatched_chunks": unmatched_chunks,
        "page_count": len(pages),
        "chart_captions": chart_captions,
        "chunk_pages": chunk_pages,
        "source_name": source_name,
        "mapped_at": datetime.now().isoformat(),
        "method": "exact_text_anchor_v1",
        "errors": [],
    }
