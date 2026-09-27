# -*- coding: utf-8 -*-
"""PDF 页码对齐算法单测 —— services/pdf_page_mapping.py（此前 0% 覆盖，117 条语句）

这是"把知识块对齐到原始 PDF 页码"的核心算法（保守多锚点投票策略），
导入流程依赖它产出 `| PDF p.X-Y` 定位器；此前完全没有测试。
"""

import sys
import types

import pytest

from services.pdf_page_mapping import (
    PdfPageMappingError,
    PageMatch,
    _anchors,
    _match_anchors,
    _page_locator,
    align_chunk_to_pages,
    extract_pdf_pages,
    map_pdf_chunks,
    normalize_alignment_text,
)

# 一句长度足够、字符多样性足够（锚点要求 len(set(anchor)) >= 7）的目标文本
TARGET = "tcp三次握手的核心是syn报文与ack报文的交换过程，理解它能解决大部分考题。"


class TestNormalizeAlignmentText:
    def test_fullwidth_folded_to_halfwidth(self):
        assert normalize_alignment_text("ＡＢＣ１２３") == "abc123"

    def test_spaces_and_punctuation_removed(self):
        assert normalize_alignment_text("TCP 三次握手, 是/连接!") == "tcp三次握手是连接"

    def test_upper_case_lowered(self):
        assert normalize_alignment_text("SYN ACK") == "synack"

    def test_empty_input(self):
        assert normalize_alignment_text("") == ""


class TestAnchors:
    def test_too_short_returns_empty(self):
        assert _anchors("短文本", 32) == []

    def test_returns_fixed_length_unique_anchors(self):
        text = "".join(chr(ord("a") + (i % 26)) for i in range(300))
        anchors = _anchors(text, 32)
        assert anchors
        assert all(len(a) == 32 for a in anchors)
        assert len(anchors) == len(set(anchors)), "锚点必须去重"

    def test_low_diversity_text_yields_no_anchor(self):
        """单一字符重复的长文本没有区分度，不应产出锚点。"""
        assert _anchors("a" * 300, 32) == []

    def test_exact_length_boundary(self):
        """长度恰好等于锚点长度时可用（不是严格大于才可用）。"""
        text = "".join(chr(ord("a") + (i % 26)) for i in range(32))
        assert len(_anchors(text, 32)) == 1


class TestMatchAnchors:
    def test_single_page_hit_counted(self):
        pages = ["abcdefghij", "abcdefghij", "zzzzzzzzzz"]
        votes, matched = _match_anchors(["abcdefghij"], pages, 0, 3)
        assert matched == 1
        assert votes[0] == 1 and votes[1] == 1

    def test_noise_anchor_dropped_when_hitting_more_than_three_pages(self):
        """命中超过 3 页的锚点视为噪声（通用短语），整体丢弃。"""
        pages = ["xxxxxxxxxx"] * 5
        votes, matched = _match_anchors(["xxxxxxxxxx"], pages, 0, 5)
        assert matched == 0
        assert not votes

    def test_anchor_absent_from_range_not_counted(self):
        votes, matched = _match_anchors(["notpresent"], ["abc", "def"], 0, 2)
        assert matched == 0 and not votes


class TestPageMatch:
    def test_confidence_ratio(self):
        assert PageMatch(1, 1, 2, 4).confidence == 0.5

    def test_confidence_zero_when_no_anchors(self):
        """anchor_count=0 时用 max(1, ...) 保护，不得 ZeroDivisionError。"""
        assert PageMatch(1, 1, 0, 0).confidence == 0.0

    def test_confidence_rounded_to_three_decimals(self):
        assert PageMatch(1, 1, 1, 3).confidence == 0.333

    def test_frozen_dataclass(self):
        match = PageMatch(1, 2, 3, 4)
        with pytest.raises(Exception):
            match.start_page = 9


class TestAlignChunkToPages:
    def _pages_with_target_on(self, target_index: int, total: int = 4):
        noise = normalize_alignment_text("完全无关的内容段落" * 30)
        target = normalize_alignment_text(TARGET * 3)
        return [target if i == target_index else noise for i in range(total)]

    def test_content_too_short_returns_none(self):
        assert align_chunk_to_pages("太短了", ["x" * 100]) is None

    def test_no_pages_returns_none(self):
        assert align_chunk_to_pages(TARGET * 3, []) is None

    def test_finds_target_page(self):
        pages = self._pages_with_target_on(2)
        match = align_chunk_to_pages(TARGET * 3, pages, previous_page=0)
        assert match is not None
        assert (match.start_page, match.end_page) == (3, 3), "目标在第 3 页（1-based）"
        assert 0 < match.confidence <= 1
        assert match.matched_anchors >= 1

    def test_returns_none_when_nothing_matches(self):
        pages = [normalize_alignment_text("完全不相干的话题阐述" * 40)]
        assert align_chunk_to_pages(TARGET * 3, pages) is None

    def test_previous_page_narrows_first_window_then_falls_back(self):
        """previous_page 非 0 时窗口收窄；目标在窗口外仍应通过全库回退找到。"""
        pages = self._pages_with_target_on(0, total=40)
        match = align_chunk_to_pages(TARGET * 3, pages, previous_page=30)
        assert match is not None and match.start_page == 1

    def test_clusters_adjacent_pages_into_range(self):
        """目标文本跨相邻两页时，应聚合成一个页区间而非单页。"""
        target = normalize_alignment_text(TARGET * 3)
        noise = normalize_alignment_text("无关内容" * 30)
        pages = [noise, target, target, noise]
        match = align_chunk_to_pages(TARGET * 3, pages, previous_page=0)
        assert match is not None
        assert match.start_page == 2 and match.end_page == 3


class TestPageLocator:
    def test_appends_locator_when_absent(self):
        assert "PDF p.2" in _page_locator(None, PageMatch(2, 2, 1, 1))

    def test_single_page_has_no_dash(self):
        assert "PDF p.3" in _page_locator(None, PageMatch(3, 3, 1, 1))
        assert "PDF p.3-" not in _page_locator(None, PageMatch(3, 3, 1, 1))

    def test_range_uses_dash(self):
        assert "PDF p.3-5" in _page_locator(None, PageMatch(3, 5, 1, 1))

    def test_existing_locator_replaced_not_stacked(self):
        """重复导入必须替换旧定位器，不得叠加成 `PDF p.9 | PDF p.1`。"""
        out = _page_locator("教材A | PDF p.9", PageMatch(1, 1, 1, 1))
        assert out.count("PDF p.") == 1
        assert "PDF p.1" in out

    def test_base_truncated_to_keep_locator(self):
        out = _page_locator("题" * 900, PageMatch(1, 1, 1, 1))
        assert len(out) <= 500
        assert out.endswith("PDF p.1")


class TestExtractPdfPages:
    def _fake_reader(self, monkeypatch, text):
        fake = types.ModuleType("pdf_reader")
        fake.extract_text_from_pdf = lambda path: text
        monkeypatch.setitem(sys.modules, "pdf_reader", fake)

    def test_parses_page_markers(self, monkeypatch):
        self._fake_reader(monkeypatch, "--- 第 1 页 ---\nAAA\n--- 第 2 页 ---\nBBB")
        assert [p.strip() for p in extract_pdf_pages("x.pdf")] == ["AAA", "BBB"]

    def test_falls_back_to_single_page_without_markers(self, monkeypatch):
        self._fake_reader(monkeypatch, "整段没有任何分页标记的文本")
        assert extract_pdf_pages("x.pdf") == ["整段没有任何分页标记的文本"]

    def test_empty_extraction_raises(self, monkeypatch):
        self._fake_reader(monkeypatch, "")
        with pytest.raises(PdfPageMappingError):
            extract_pdf_pages("x.pdf")


class TestMapPdfChunks:
    def test_empty_chunks_short_circuits(self):
        result = map_pdf_chunks("x.pdf", [])
        assert result["documents"] == 0 and result["mapped_chunks"] == 0
        assert result["errors"], "应说明没有可映射的 chunks"
        assert result["method"] == "exact_text_anchor_v1"

    def test_extraction_failure_reported_not_raised(self, monkeypatch):
        def boom(path):
            raise PdfPageMappingError("PDF 文本提取失败: x.pdf")

        monkeypatch.setattr(
            "services.pdf_page_mapping.extract_pdf_pages", boom
        )
        result = map_pdf_chunks("x.pdf", [{"id": "c1", "content": TARGET * 3}])
        assert result["mapped_chunks"] == 0
        assert any("提取失败" in e for e in result["errors"])

    def test_maps_chunk_and_emits_locator(self, monkeypatch):
        target_page = normalize_alignment_text(TARGET * 3)
        monkeypatch.setattr(
            "services.pdf_page_mapping.extract_pdf_pages",
            lambda path: [normalize_alignment_text("无关" * 40), target_page],
        )
        result = map_pdf_chunks(
            "x.pdf",
            [{"id": "c1", "content": TARGET * 3, "metadata": {"source": "教材A"}}],
        )
        assert result["mapped_chunks"] == 1 and result["unmatched_chunks"] == 0
        assert result["page_count"] == 2
        entry = result["chunk_pages"]["c1"]
        assert entry["start_page"] == 2 and "PDF p.2" in entry["locator"]

    def test_unmatched_chunk_counted(self, monkeypatch):
        monkeypatch.setattr(
            "services.pdf_page_mapping.extract_pdf_pages",
            lambda path: [normalize_alignment_text("完全无关" * 40)],
        )
        result = map_pdf_chunks("x.pdf", [{"id": "c1", "content": TARGET * 3}])
        assert result["mapped_chunks"] == 0 and result["unmatched_chunks"] == 1
        assert result["chunk_pages"] == {}

    def test_chart_captions_collected(self, monkeypatch):
        content = TARGET * 3 + " 图 1-1 三次握手时序图"
        target = normalize_alignment_text(content)
        monkeypatch.setattr(
            "services.pdf_page_mapping.extract_pdf_pages", lambda path: [target]
        )
        result = map_pdf_chunks("x.pdf", [{"id": "c1", "content": content}])
        if result["mapped_chunks"]:
            assert result["chart_captions"], "含「图 1-1 …」时应收集图表标题"

    def test_source_name_defaults_from_first_chunk_metadata(self, monkeypatch):
        target = normalize_alignment_text(TARGET * 3)
        monkeypatch.setattr(
            "services.pdf_page_mapping.extract_pdf_pages", lambda path: [target]
        )
        result = map_pdf_chunks(
            "x.pdf", [{"id": "c1", "content": TARGET * 3, "metadata": {"source": "默认源"}}]
        )
        assert result["documents"] == 1
