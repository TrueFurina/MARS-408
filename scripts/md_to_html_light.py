# -*- coding: utf-8 -*-
"""MD → 轻量化 HTML 转换脚本（按《模板-轻量化HTML转换规范》）

白名单标签：h1/h2/h3/section/table/thead/tbody/tr/th/td/p/pre/ul/ol/li/strong
严禁：div/style/script/class/id/svg/span/link/img/内联样式

用法: python md_to_html_light.py <input.md> <output.html>
"""
import re
import sys


def _inline(s: str) -> str:
    """行内转换：**bold** → <strong>（仅白名单）"""
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # strong 标签已被转义，恢复
    s = s.replace("&lt;strong&gt;", "<strong>").replace("&lt;/strong&gt;", "</strong>")
    return s


def convert(md: str, title: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    in_table = False
    in_code = False
    in_list: str | None = None  # "ul" or "ol"
    in_section = False
    table_rows: list[str] = []

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            if in_code:
                out.append("</pre>")
                in_code = False
            else:
                out.append("<pre>")
                in_code = True
            continue
        if in_code:
            out.append(stripped.replace("&", "&amp;").replace("<", "&lt;"))
            continue

        # 表格
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(stripped)
            continue
        if in_table:
            out.append(_flush_table(table_rows))
            table_rows = []
            in_table = False

        # 标题
        if stripped.startswith("# "):
            out.append(f"<h1>{_inline(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            if in_section:
                out.append("</section>")
            out.append(f"<section>\n<h2>{_inline(stripped[3:])}</h2>")
            in_section = True
            continue
        if stripped.startswith("### "):
            out.append(f"<h3>{_inline(stripped[4:])}</h3>")
            continue

        # 列表
        m_ul = re.match(r"^- (.*)$", stripped)
        m_ol = re.match(r"^\d+\. (.*)$", stripped)
        if m_ul or m_ol:
            tag = "ul" if m_ul else "ol"
            item = m_ul.group(1) if m_ul else m_ol.group(1)
            if in_list != tag:
                if in_list:
                    out.append(f"</{in_list}>")
                out.append(f"<{tag}>")
                in_list = tag
            out.append(f"<li>{_inline(item)}</li>")
            continue
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

        # 引用/分隔线/空行
        if stripped.startswith(">"):
            out.append(f"<p>{_inline(stripped.lstrip('> '))}</p>")
            continue
        if stripped in ("---", "***", ""):
            if in_list:
                out.append(f"</{in_list}>")
                in_list = None
            continue

        # 普通段落
        if stripped:
            out.append(f"<p>{_inline(stripped)}</p>")

    if in_table:
        out.append(_flush_table(table_rows))
    if in_list:
        out.append(f"</{in_list}>")
    if in_code:
        out.append("</pre>")
    if in_section:
        out.append("</section>")

    body = "\n".join(out)
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n"
        f"<meta charset=\"UTF-8\">\n<title>{title}</title>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )


def _flush_table(rows: list[str]) -> str:
    """表格行 → table/thead/tbody"""
    cells = [r.strip().strip("|").split("|") for r in rows]
    # 过滤分隔行 |---|---|
    cells = [c for c in cells if not all(re.fullmatch(r":?-{2,}:?", x.strip()) for x in c)]
    if not cells:
        return ""
    parts = ["<table>"]
    head = cells[0]
    parts.append("<thead><tr>" + "".join(f"<th>{_inline(x.strip())}</th>" for x in head) + "</tr></thead>")
    parts.append("<tbody>")
    for row in cells[1:]:
        parts.append("<tr>" + "".join(f"<td>{_inline(x.strip())}</td>" for x in row) + "</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    text = open(src, encoding="utf-8").read()
    # 取首个 # 标题作为 title
    m = re.search(r"^# (.+)$", text, re.M)
    title = m.group(1).strip() if m else src.split("/")[-1]
    open(dst, "w", encoding="utf-8").write(convert(text, title))
    print(f"✅ {src} → {dst}")
