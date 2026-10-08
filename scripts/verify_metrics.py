#!/usr/bin/env python
"""verify_metrics.py — 工程规模指标真值校验（SSOT 机检）

对齐 `docs/METRICS_CURRENT.md` 的「工程规模指标」表：
重算当前值 → 与文档记录的真值比对 → 任何一项不一致即 exit 1。

为什么需要：此前 README 的 views / 代码量 / API 端点 / 测试数多次漂移（45→46、414→374、
约240→244、917→1177），根因是"手抄数字、无机检"。本脚本把可静态复算的指标纳入门禁。

用法：
    python scripts/verify_metrics.py            # 校验（CI / pre-commit 用）
    python scripts/verify_metrics.py --update   # 用当前实测值改写文档表格
    python scripts/verify_metrics.py --print    # 只打印实测值（调试用）

注意：测试数（passed/skipped/xfail）**不在本脚本校验范围**——它需要真正跑一遍 pytest，
耗时且依赖环境；其真值以 CI 全量回归为准，文档中已标注来源。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "METRICS_CURRENT.md"
START = "<!-- METRICS_TABLE_START -->"
END = "<!-- METRICS_TABLE_END -->"

SKIP_DIR_PARTS = {".venv", "site-packages", "node_modules", ".git", "dist", "__pycache__"}


def _skip(p: pathlib.Path) -> bool:
    return any(part in SKIP_DIR_PARTS for part in p.parts)


def _files(base: pathlib.Path, pattern: str) -> list[pathlib.Path]:
    return [p for p in base.rglob(pattern) if not _skip(p)]


def _lines(paths: list[pathlib.Path]) -> int:
    n = 0
    for p in paths:
        try:
            with open(p, "rb") as f:
                n += sum(1 for _ in f)
        except OSError:
            pass
    return n


def measure() -> dict[str, tuple[int, str]]:
    """返回 {指标键: (真值, 口径说明)}。口径即复现命令，写进文档供人核对。"""
    src = ROOT / "src"
    py = ROOT / "py-server"

    views = sorted((src / "views").glob("*.vue"))
    vue = _files(src, "*.vue")
    ts = _files(src, "*.ts")
    pys = _files(py, "*.py")
    api_mods = [p for p in (py / "api").glob("*.py") if p.name != "__init__.py"]

    import json

    spec = json.loads((py / "openapi.json").read_text(encoding="utf-8"))
    methods = {"get", "post", "put", "delete", "patch", "head", "options"}
    api_ops = [
        (p, m)
        for p, ms in spec.get("paths", {}).items()
        if p.startswith("/api")
        for m in ms
        if m in methods
    ]
    api_paths = {p for p, _ in api_ops}

    return {
        "frontend_views": (len(views), "`ls src/views/*.vue \\| wc -l`"),
        "frontend_vue_total": (len(vue), "`find src -name '*.vue' \\| wc -l`"),
        "frontend_ts_total": (len(ts), "`find src -name '*.ts' \\| wc -l`"),
        "frontend_lines": (
            _lines(vue) + _lines(ts),
            "`.vue` + `.ts` 全部行数（不含 node_modules/dist）",
        ),
        "backend_py": (len(pys), "`find py-server -name '*.py'`（不含 .venv）"),
        "backend_lines": (_lines(pys), "`.py` 全部行数（不含 .venv）"),
        "api_modules": (len(api_mods), "`ls py-server/api/*.py` 去 `__init__.py`"),
        "api_paths": (len(api_paths), "`py-server/openapi.json` 中 `/api` 路径数"),
        "api_operations": (len(api_ops), "`py-server/openapi.json` 中 `/api` 操作数（method 级）"),
    }


LABELS = {
    "frontend_views": "前端 views（页面级组件）",
    "frontend_vue_total": "前端 .vue 总数",
    "frontend_ts_total": "前端 .ts 总数",
    "frontend_lines": "前端代码行数（.vue+.ts）",
    "backend_py": "后端 Python 文件数",
    "backend_lines": "后端代码行数",
    "api_modules": "API 路由模块数",
    "api_paths": "API 路径数（/api）",
    "api_operations": "API 操作数（/api，method 级）",
}


def render_table(data: dict[str, tuple[int, str]]) -> str:
    lines = [
        "| 指标 | 真值 | 口径（可复现） |",
        "| --- | --- | --- |",
    ]
    for key, (val, how) in data.items():
        lines.append(f"| {LABELS[key]} | {val} | {how} |")
    return "\n".join(lines)


def read_doc_table() -> dict[str, int] | None:
    if not DOC.is_file():
        return None
    text = DOC.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return None
    block = text.split(START, 1)[1].split(END, 1)[0]
    out: dict[str, int] = {}
    for key, label in LABELS.items():
        for line in block.splitlines():
            if line.startswith("|") and label in line:
                for tok in line.split("|"):
                    tok = tok.strip().strip("*")
                    if tok.isdigit():
                        out[key] = int(tok)
                        break
                break
    return out or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="用实测值改写文档表格")
    ap.add_argument("--print", dest="show", action="store_true", help="只打印实测值")
    args = ap.parse_args()

    data = measure()

    if args.show:
        print(render_table(data))
        return 0

    if args.update:
        text = DOC.read_text(encoding="utf-8")
        if START not in text or END not in text:
            print(f"[verify_metrics] 错误：{DOC} 缺少 {START} / {END} 标记块")
            return 1
        head, rest = text.split(START, 1)
        _, tail = rest.split(END, 1)
        DOC.write_text(head + START + "\n" + render_table(data) + "\n" + END + tail, encoding="utf-8")
        print(f"[verify_metrics] 已更新 {DOC.relative_to(ROOT)} 的指标表")
        return 0

    doc = read_doc_table()
    if doc is None:
        print(f"[verify_metrics] 错误：无法从 {DOC.relative_to(ROOT)} 解析指标表（缺少标记块？）")
        return 1

    bad: list[str] = []
    for key, (actual, _how) in data.items():
        expect = doc.get(key)
        if expect is None:
            bad.append(f"  {LABELS[key]}: 文档表格缺该行")
        elif expect != actual:
            bad.append(f"  {LABELS[key]}: 文档={expect} 实测={actual}")

    if bad:
        print("[verify_metrics] ❌ 工程规模指标与真值不一致：")
        print("\n".join(bad))
        print("  修正文档或跑 `python scripts/verify_metrics.py --update` 同步。")
        return 1

    print(f"[verify_metrics] ✅ {len(data)} 项工程规模指标全部与真值一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())