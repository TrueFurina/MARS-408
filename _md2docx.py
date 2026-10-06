#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md → docx 转换器（submission/02_配套文档 正式交付件专用）。

用途
----
把 `submission/02_配套文档/*.md` 转成 `submission/02_配套文档/docx/*.docx`，
保持与历史交付件（2026-09-21 版）一致的排版风格：

- 封面区（居中大标题 + 副标题 + 分隔线 + 版本行 + 提交方行）
- 可更新的 TOC 域（`TOC \\o "1-3" \\h \\z \\u`）
- `##`/`###`/`####` → Heading 2/3/4
- 围栏代码块 → Consolas + 浅灰底纹代码段，首行标注语言
- 引用块（`>`）→ 浅紫底纹 + 左侧紫色竖线
- GFM 表格 → `Table Grid` 表格
- 无序列表 → `•` 项目符号段落
- 水平分隔线（`---`）→ 居中细横线字符段
- `![alt](path)` → 居中内嵌图片（宽 5.5 英寸，按比例缩放）
- 行内 `**粗体**` / `` `等宽` `` → run 级格式

依赖
----
`python-docx`（已装于 `py-server/.venv`）。运行：

    py-server/.venv/Scripts/python.exe _md2docx.py            # 转换全部
    py-server/.venv/Scripts/python.exe _md2docx.py 系统架构设计文档   # 转换指定几份

设计约束
--------
1. **纯函数式、幂等**：同一 md 反复转换产物稳定（不含时间戳等易变字段）。
2. **不静默吞错**：图片缺失 / 标题层级跳跃等异常走 `WARN` 汇总后以非零码提示，
   但仍产出 docx（避免因单张图缺失阻断整批交付）。
3. **表格列数不齐**时按最长行补空单元格，不抛异常。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.shared import Inches, Pt, RGBColor
except ImportError as exc:  # pragma: no cover - 环境缺依赖时给出可执行指引
    sys.stderr.write(
        "缺少依赖 python-docx。请先安装：\n"
        "    py-server/.venv/Scripts/python.exe -m pip install python-docx\n"
        f"原始错误：{exc}\n"
    )
    raise SystemExit(2) from exc

# ---------------------------------------------------------------------------
# 常量：与历史交付件保持一致的配色与字号（单位：半磅，1pt = 2 半磅）
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(ROOT, "submission", "02_配套文档")
OUT_DIR = os.path.join(DOC_DIR, "docx")

FONT_ASCII = "Calibri"
FONT_EASTASIA = "宋体"
FONT_MONO = "Consolas"

CLR_PURPLE = "6C2BD9"        # 品牌紫：封面副标题、分隔线、引用块竖线
CLR_HEADING2 = "6C2BD9"
CLR_HEADING3 = "1A1A2E"
CLR_BODY = "1A1A2E"
CLR_MUTED = "666666"          # 弱化文字（引用块、注释）
CLR_RULE = "999999"           # 分隔线
CLR_CODE_BG = "F4F4F8"        # 代码块底纹
CLR_QUOTE_BG = "F8F6FC"       # 引用块底纹

SZ_COVER_TITLE = 52   # 26pt 封面主标题
SZ_COVER_SUB = 21     # 10.5pt 封面副标题
SZ_COVER_META = 21    # 10.5pt 版本 / 提交方
SZ_COVER_RULE = 22    # 11pt 封面分隔线
SZ_TOC_TITLE = 30     # 15pt 目录标题
SZ_BODY = 21          # 10.5pt 正文
SZ_BULLET = 21
SZ_CODE = 18          # 9pt 代码
SZ_CODE_LANG = 17     # 8.5pt 语言标注
SZ_RULE = 18          # 9pt 分隔线

INDENT_CODE = 227     # 代码块左缩进（twips）
INDENT_QUOTE = 340    # 引用块左缩进（twips）
INDENT_BULLET = 454   # 项目符号左缩进（twips）

IMG_WIDTH_IN = 5.5    # 内嵌图片统一宽度（英寸）

WARNINGS: List[str] = []


def warn(msg: str) -> None:
    """记录一条警告（不中断转换）。"""
    WARNINGS.append(msg)
    print(f"  WARN: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 低层 OOXML 辅助
# ---------------------------------------------------------------------------

def _set_run_font(run, *, name: str = FONT_ASCII, east_asia: str = FONT_EASTASIA,
                  size_hp: Optional[int] = None, bold: Optional[bool] = None,
                  italic: Optional[bool] = None, color: Optional[str] = None) -> None:
    """统一设置 run 的字体（含东亚字体），避免 Word 回退成 Times New Roman。"""
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), east_asia)
    if size_hp is not None:
        run.font.size = Pt(size_hp / 2)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def _shade(paragraph, fill: str) -> None:
    """给段落加底纹。"""
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def _left_bar(paragraph, color: str, sz: int = 18) -> None:
    """给段落加左侧竖线（引用块视觉标记）。"""
    ppr = paragraph._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), str(sz))
    left.set(qn("w:space"), "8")
    left.set(qn("w:color"), color)
    pbdr.append(left)
    ppr.append(pbdr)


def _spacing(paragraph, *, before: int = 80, after: int = 80, line: int = 276) -> None:
    """设置段前/段后间距与行距（line=276 即 1.15 倍）。"""
    pf = paragraph.paragraph_format
    pf.space_before = Pt(before / 20)
    pf.space_after = Pt(after / 20)
    pf.line_spacing = line / 240


def _indent(paragraph, twips: int) -> None:
    """设置左缩进（twips，1 英寸 = 1440 twips）。"""
    paragraph.paragraph_format.left_indent = Inches(twips / 1440)


# ---------------------------------------------------------------------------
# 行内标记解析：**粗体**、`等宽`
# ---------------------------------------------------------------------------

_INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def add_inline(paragraph, text: str, *, size_hp: int = SZ_BODY,
               color: str = CLR_BODY, base_bold: bool = False) -> None:
    """把带 `**粗体**` / `` `等宽` `` 标记的行内文本渲染成多个 run。"""
    for piece in _INLINE_RE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            run = paragraph.add_run(piece[2:-2])
            _set_run_font(run, size_hp=size_hp, bold=True, italic=False, color=color)
        elif piece.startswith("`") and piece.endswith("`") and len(piece) > 2:
            run = paragraph.add_run(piece[1:-1])
            _set_run_font(run, name=FONT_MONO, east_asia=FONT_MONO,
                          size_hp=size_hp - 1, bold=base_bold, italic=False, color=color)
        else:
            run = paragraph.add_run(piece)
            _set_run_font(run, size_hp=size_hp, bold=base_bold, italic=False, color=color)


def strip_inline(text: str) -> str:
    """去掉行内标记，得到纯文本（用于图片 alt 之外的场合）。"""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).replace("`", "")


# ---------------------------------------------------------------------------
# 块级渲染器
# ---------------------------------------------------------------------------

def render_cover(doc, *, brand: str, title: str, subtitle: str, meta_lines: Sequence[str]) -> None:
    """渲染封面区。"""
    for _ in range(3):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(p.add_run(brand), size_hp=26, bold=True, color=CLR_PURPLE)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(p.add_run(title), size_hp=SZ_COVER_TITLE, bold=True, color=CLR_BODY)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(p.add_run(subtitle), size_hp=SZ_COVER_SUB, bold=False, color=CLR_MUTED)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(p.add_run("━" * 34), size_hp=SZ_COVER_RULE, bold=False, color=CLR_PURPLE)

    for line in meta_lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_run_font(p.add_run(line), size_hp=SZ_COVER_META, bold=False, color=CLR_BODY)

    doc.add_paragraph()


def render_toc(doc) -> None:
    """渲染「目  录」标题 + 可更新的 TOC 域。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(p.add_run("目  录"), size_hp=SZ_TOC_TITLE, bold=True, color=CLR_PURPLE)

    p = doc.add_paragraph()
    run = p.add_run()
    _set_run_font(run, size_hp=SZ_BODY, color=CLR_BODY)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-3" \\h \\z \\u'
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, sep):
        run._r.append(el)
    run._r.append(end)
    hint = p.add_run("右键更新域可生成目录")
    _set_run_font(hint, size_hp=SZ_BODY, color=CLR_MUTED)

    doc.add_paragraph()


def render_code_block(doc, lines: Sequence[str], lang: str) -> None:
    """渲染围栏代码块：Consolas + 浅灰底纹，首行标注语言。"""
    p = doc.add_paragraph()
    _spacing(p, before=80, after=80, line=276)
    _indent(p, INDENT_CODE)
    _shade(p, CLR_CODE_BG)

    if lang:
        r = p.add_run(f"[{lang}]")
        _set_run_font(r, name=FONT_MONO, east_asia=FONT_MONO, size_hp=SZ_CODE_LANG,
                      bold=False, italic=True, color=CLR_RULE)
        r.add_break()

    for line in lines:
        r = p.add_run(line)
        _set_run_font(r, name=FONT_MONO, east_asia=FONT_MONO, size_hp=SZ_CODE,
                      bold=False, italic=False, color=CLR_BODY)
        r.add_break()


def render_quote(doc, lines: Sequence[str]) -> None:
    """渲染引用块：浅紫底纹 + 左侧紫竖线；块内换行用 <w:br/>。"""
    p = doc.add_paragraph()
    _spacing(p, before=60, after=60, line=312)
    _indent(p, INDENT_QUOTE)
    _shade(p, CLR_QUOTE_BG)
    _left_bar(p, CLR_PURPLE)

    for i, line in enumerate(lines):
        if i:
            p.add_run().add_break()
        add_inline(p, line, size_hp=20, color=CLR_MUTED)


def render_bullet(doc, text: str, level: int = 0) -> None:
    """渲染无序列表项。"""
    p = doc.add_paragraph()
    _spacing(p, before=40, after=40, line=276)
    _indent(p, INDENT_BULLET + level * 340)
    add_inline(p, "• " + text, size_hp=SZ_BULLET, color=CLR_BODY)


def render_ordered(doc, text: str, index: int, level: int = 0) -> None:
    """渲染有序列表项。"""
    p = doc.add_paragraph()
    _spacing(p, before=40, after=40, line=276)
    _indent(p, INDENT_BULLET + level * 340)
    add_inline(p, f"{index}. {text}", size_hp=SZ_BULLET, color=CLR_BODY)


def render_paragraph(doc, text: str) -> None:
    """渲染普通段落。"""
    p = doc.add_paragraph()
    _spacing(p, before=80, after=80, line=276)
    add_inline(p, text, size_hp=SZ_BODY, color=CLR_BODY)


def render_rule(doc) -> None:
    """渲染水平分隔线（居中横线字符）。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(p.add_run("─" * 30), size_hp=SZ_RULE, bold=False, color=CLR_RULE)


def render_image(doc, rel_path: str, alt: str, base_dir: str) -> None:
    """渲染居中内嵌图片，宽度固定 IMG_WIDTH_IN 英寸并按比例缩放。"""
    abs_path = os.path.normpath(os.path.join(base_dir, rel_path))
    if not os.path.isfile(abs_path):
        warn(f"图片缺失，已跳过：{rel_path}")
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    try:
        p.add_run().add_picture(abs_path, width=Inches(IMG_WIDTH_IN))
    except Exception as exc:  # noqa: BLE001 - 损坏图片不应中断整批转换
        warn(f"图片写入失败（{rel_path}）：{exc}")
        return
    if alt:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_run_font(cap.add_run(strip_inline(alt)), size_hp=18, bold=False, color=CLR_MUTED)


def render_table(doc, rows: Sequence[Sequence[str]]) -> None:
    """渲染 GFM 表格为 `Table Grid` 表格；首行为表头。"""
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=0, cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_i, row in enumerate(rows):
        cells = table.add_row().cells
        for c_i in range(ncols):
            text = row[c_i] if c_i < len(row) else ""
            para = cells[c_i].paragraphs[0]
            para.paragraph_format.space_before = Pt(2)
            para.paragraph_format.space_after = Pt(2)
            add_inline(para, text, size_hp=18,
                       color=CLR_HEADING3 if r_i == 0 else CLR_BODY,
                       base_bold=(r_i == 0))
    doc.add_paragraph()


# ---------------------------------------------------------------------------
# Markdown 解析（面向本仓库文档子集，够用即可，不追求 CommonMark 完备）
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_HR_RE = re.compile(r"^-{3,}\s*$")
_UL_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")


def _split_table_row(line: str) -> List[str]:
    """切分表格行（兼容首尾竖线与转义竖线）。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells, buf, escaped = [], [], False
    for ch in s:
        if escaped:
            buf.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    cells.append("".join(buf).strip())
    return cells


def _collect_quote(lines: Sequence[str], start: int) -> Tuple[List[str], int]:
    """收集从 start 起的连续引用行，返回（内容行，下一行索引）。"""
    buf: List[str] = []
    i = start
    while i < len(lines):
        raw = lines[i].rstrip("\n")
        if raw.startswith(">"):
            content = raw[1:]
            if content.startswith(" "):
                content = content[1:]
            buf.append(content)
            i += 1
        elif not raw.strip() and i + 1 < len(lines) and lines[i + 1].startswith(">"):
            buf.append("")
            i += 1
        else:
            break
    while buf and not buf[-1].strip():
        buf.pop()
    return buf, i


def convert_markdown(md_path: str, out_path: str) -> None:
    """把单个 md 转为 docx。"""
    base_dir = os.path.dirname(md_path)
    with open(md_path, "r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    doc = Document()

    # --- 封面：取 H1 作主标题，首个引用块拆成副标题 + 版本/提交方行 ---
    title = os.path.splitext(os.path.basename(md_path))[0]
    body_lines = list(lines)
    if lines and _HEADING_RE.match(lines[0]):
        title = _HEADING_RE.match(lines[0]).group(2).strip()
        body_lines = lines[1:]

    # 文档头部引用块是「版本/注意事项」元信息，按历史交付件惯例留在正文，
    # 封面元信息行用固定署名（与 09-21 版式一致）。
    subtitle = "计算机类学生职业素养对抗实训平台"
    meta_lines: List[str] = ["闽江大学 · 计算机类学生职业素养对抗实训平台"]

    render_cover(
        doc,
        brand="闽江大学 · 芒得很职",
        title=title,
        subtitle=subtitle,
        meta_lines=meta_lines,
    )
    render_toc(doc)

    # --- 正文 ---
    i = 0
    n = len(body_lines)
    while i < n:
        raw = body_lines[i].rstrip("\n")
        line = raw.strip()

        if not line:
            i += 1
            continue

        # 围栏代码块
        fence = _FENCE_RE.match(line)
        if fence:
            lang = fence.group(1)
            i += 1
            block: List[str] = []
            while i < n and not _FENCE_RE.match(body_lines[i].strip()):
                block.append(body_lines[i].rstrip("\n"))
                i += 1
            if i < n:
                i += 1  # 吃掉收尾 ```
            while block and not block[-1].strip():
                block.pop()
            render_code_block(doc, block, lang)
            continue

        # 水平分隔线
        if _HR_RE.match(line):
            render_rule(doc)
            i += 1
            continue

        # 表格（当前行是表头且下一行是分隔行）
        if line.startswith("|") and i + 1 < n and _TABLE_SEP_RE.match(body_lines[i + 1].strip()):
            rows = [_split_table_row(body_lines[i])]
            i += 2
            while i < n and body_lines[i].strip().startswith("|"):
                rows.append(_split_table_row(body_lines[i]))
                i += 1
            render_table(doc, rows)
            continue

        # 引用块
        if raw.startswith(">"):
            quote_lines, i = _collect_quote(body_lines, i)
            render_quote(doc, quote_lines)
            continue

        # 图片
        img = _IMAGE_RE.match(line)
        if img:
            render_image(doc, img.group(2).strip(), img.group(1), base_dir)
            i += 1
            continue

        # 标题：H1 降为 Heading 2（封面已用掉主标题），其余顺延
        head = _HEADING_RE.match(line)
        if head:
            level = len(head.group(1))
            text = head.group(2).strip()
            mapped = max(1, min(level - 1, 4)) if level >= 2 else 1
            h = doc.add_heading(level=mapped)
            _set_run_font(h.add_run(strip_inline(text)),
                          size_hp={1: 28, 2: 24, 3: 20, 4: 18}.get(mapped, 18),
                          bold=True, color=CLR_HEADING2 if mapped <= 2 else CLR_HEADING3)
            i += 1
            continue

        # 无序列表（连续同缩进的项归为一个列表）
        ul = _UL_RE.match(raw)
        if ul:
            while i < n:
                m = _UL_RE.match(body_lines[i].rstrip("\n"))
                if not m:
                    break
                render_bullet(doc, m.group(2).strip(), level=len(m.group(1)) // 2)
                i += 1
            continue

        # 有序列表
        ol = _OL_RE.match(raw)
        if ol:
            while i < n:
                m = _OL_RE.match(body_lines[i].rstrip("\n"))
                if not m:
                    break
                render_ordered(doc, m.group(3).strip(), int(m.group(2)),
                               level=len(m.group(1)) // 2)
                i += 1
            continue

        render_paragraph(doc, line)
        i += 1

    doc.save(out_path)


# ---------------------------------------------------------------------------
# 批量入口
# ---------------------------------------------------------------------------

#: 需要转换的 md（不含「作品详细介绍-芒得很职.docx」——该件无 md 源，不在本次范围）
DOC_NAMES: Tuple[str, ...] = (
    "DEPLOY",
    "OPENSOURCE_LICENSES",
    "开发说明书",
    "快速启动指南",
    "技术方案说明书",
    "概要设计说明书",
    "测试分析报告",
    "测试说明书",
    "系统架构设计文档",
    "软件需求规格说明书",
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="把 submission/02_配套文档 的 md 转成 docx")
    parser.add_argument("names", nargs="*", help=f"只转换指定文档名（默认全部：{'、'.join(DOC_NAMES)}）")
    args = parser.parse_args(argv)

    targets = tuple(args.names) if args.names else DOC_NAMES
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"输出目录：{OUT_DIR}")
    for name in targets:
        md_path = os.path.join(DOC_DIR, f"{name}.md")
        out_path = os.path.join(OUT_DIR, f"{name}.docx")
        if not os.path.isfile(md_path):
            warn(f"md 源缺失，跳过：{name}.md")
            continue
        convert_markdown(md_path, out_path)
        size = os.path.getsize(out_path)
        print(f"  OK  {name}.md -> docx/{name}.docx  ({size:,} bytes)")

    if WARNINGS:
        print(f"\n共 {len(WARNINGS)} 条警告：", file=sys.stderr)
        for w in WARNINGS:
            print(f"  - {w}", file=sys.stderr)
        return 1
    print("\n全部转换完成，无警告。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
