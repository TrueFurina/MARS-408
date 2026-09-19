#!/usr/bin/env python3
# Sync DesignSystemView `semantic` array to current _variables.css SSOT (dark + light), CRLF-safe.
import os
p = r"E:\Program\MARL\study-help-pro\src\views\DesignSystemView.vue"
with open(p, "rb") as f:
    data = f.read()
text = data.decode("utf-8")
lines = text.splitlines(keepends=True)

si = next(i for i, l in enumerate(lines) if "const semantic:" in l)
ei = next(j for j in range(si + 1, len(lines)) if lines[j].strip() == "]")
le = "\r\n" if lines[si].endswith("\r\n") else "\n"

new_rows = [
    "  ['--color-canvas', '#0E1217', '#F5F6F7', '页面底色'],",
    "  ['--color-surface', '#151A20', '#FFFFFF', '卡片/玻璃表面'],",
    "  ['--color-surface-2', '#1B2129', '#EFF1F3', '侧栏/输入底'],",
    "  ['--color-surface-hover', '#1D242C', '#EDF0F2', '悬停表面'],",
    "  ['--color-elevated', '#1B2129', '#FFFFFF', '抬升层(弹层)'],",
    "  ['--color-glass', 'rgba(21, 26, 32, 0.72)', 'rgba(255, 255, 255, 0.78)', '玻璃态底'],",
    "  ['--color-glass-border', 'rgba(255, 255, 255, 0.09)', 'rgba(16, 20, 26, 0.10)', '玻璃态边框'],",
    "  ['--color-border', 'rgba(255, 255, 255, 0.09)', 'rgba(16, 20, 26, 0.11)', '默认边框'],",
    "  ['--color-border-focus', 'rgba(124, 106, 242, 0.55)', 'rgba(107, 92, 219, 0.55)', '聚焦/强调边框'],",
    "  ['--color-text', '#E6E9ED', '#16191D', '主文本'],",
    "  ['--color-text-2', '#9AA4B0', '#545B66', '次文本'],",
    "  ['--color-text-3', '#79838F', '#6E7783', '弱文本'],",
]
new_block = [r + le for r in new_rows]
out = "".join(lines[:si + 1] + new_block + lines[ei:])
with open(p, "wb") as f:
    f.write(out.encode("utf-8"))
print(f"replaced {ei - (si + 1)} stale rows with {len(new_rows)} SSOT-synced rows")
