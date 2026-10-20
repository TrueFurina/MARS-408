# -*- coding: utf-8 -*-
"""广告 schema 可达递归检查 + 紧凑画像（REA #31 / MCP contracts §Schema）

背景：MCP / 前端渲染器这类「引用预算有限的客户端」，拿到 schema 后要做一次
**递归展开**才能画表单或做类型校验。若 schema 里存在**可达递归**
（A 的字段引用 B，B 又引用回 A），客户端要么栈溢出、要么必须自己实现
"展开到第 N 层就截断"的兜底——而后者不会出现在任何契约里。

REA 的原话是「Advertised input and output schemas contain no reachable
recursive references」。本脚本把这句话变成可执行检查：

1. 遍历 openapi.json 的每个 operation，收集它**广告出去**的 schema 集合
   （requestBody / parameters / responses 里的 $ref 与内联对象）；
2. 在 components.schemas 的引用图上做 DFS，找出**从该 operation 可达**的环；
3. 顺带输出紧凑画像：每个 operation 广告的 schema 去重后有多少个、共多少字节
   ——这是"引用预算"的实际占用量，不是拍脑袋估的。

退出码：
  0 = 执行完毕且无可达递归（或非 --gate 模式下 report-only）
  1 = --gate 且存在可达递归
  2 = 探活自身失败（openapi.json 缺失/不可解析/零 operation —— fail-closed：
      "照不到"不得当作"干净"）

用法：
  python scripts/check_schema_advertisement.py            # report-only
  python scripts/check_schema_advertisement.py --gate     # CI 阻断
  python scripts/check_schema_advertisement.py --top 20   # 画像只看前 20 大
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OPENAPI = os.path.join(REPO, "py-server", "openapi.json")

# 内联 schema 的包装层键（requestBody.content.*.schema 之类）不在 schema 语义里，
# 但 $ref 会藏在里面，故收集时**遍历所有键**——不做键过滤（过滤错一个键就把
# 递归漏在盲区里）。深度上限只防结构异常，不承担语义。
_MAX_DEPTH = 60


def _load(path: str) -> dict:
    if not os.path.isfile(path):
        print(f"[fail-closed] 快照不存在：{path}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[fail-closed] 快照不可解析：{e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(doc, dict) or not doc.get("paths"):
        print("[fail-closed] 快照里没有 paths（零 operation 不能当作干净）", file=sys.stderr)
        sys.exit(2)
    return doc


def _ref_name(node: Any) -> str | None:
    if isinstance(node, dict) and isinstance(node.get("$ref"), str):
        ref = node["$ref"]
        prefix = "#/components/schemas/"
        return ref[len(prefix):] if ref.startswith(prefix) else None
    return None


def _collect_refs(node: Any, out: set[str], *, depth: int = 0) -> None:
    """递归收集内联 schema 里出现的所有 $ref 名字（全键遍历，不做键过滤）。"""
    if depth > _MAX_DEPTH:
        return
    if isinstance(node, dict):
        name = _ref_name(node)
        if name:
            out.add(name)
        for value in node.values():
            _collect_refs(value, out, depth=depth + 1)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, out, depth=depth + 1)


def _operation_advertised_schemas(op: dict) -> set[str]:
    """一个 operation 广告出去的 schema 名字集合（不展开，只取第一层）。"""
    refs: set[str] = set()
    _collect_refs(op.get("parameters", []), refs)
    _collect_refs(op.get("requestBody", {}), refs)
    _collect_refs(op.get("responses", {}), refs)
    return refs


def _build_graph(schemas: dict) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for name, node in schemas.items():
        refs: set[str] = set()
        _collect_refs(node, refs)
        # 自引用（链表/树节点 properties.children.items.$ref 指回自己）**必须保留**：
        # 它就是客户端递归展开时最先炸的那一类，discard 掉等于把最常见形态漏掉。
        graph[name] = refs
    return graph


def _find_cycles(graph: dict[str, set[str]], roots: set[str],
                 limit: int = 50) -> list[list[str]]:
    """DFS 找出从 roots 可达的环，返回环路径（去重后最多 limit 条）。"""
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def dfs(node: str, stack: list[str]) -> None:
        if len(cycles) >= limit:
            return
        state = color.get(node, WHITE)
        if state == GREY:
            # 找到环：从 stack 里 node 第一次出现处截断
            idx = stack.index(node)
            cycle = stack[idx:] + [node]
            key = tuple(sorted(set(cycle)))
            if key not in seen_cycles:
                seen_cycles.add(key)
                cycles.append(cycle)
            return
        if state == BLACK:
            return
        color[node] = GREY
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            dfs(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for root in sorted(roots):
        dfs(root, [])
    return cycles


def _closure(graph: dict[str, set[str]], roots: set[str]) -> set[str]:
    """根集合的传递闭包：客户端展开时会一路跟下去，预算要算全量。"""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, ()))
    return seen


def _schema_bytes(schemas: dict, names: set[str]) -> int:
    """广告 schema 去重后的 JSON 字节数（紧凑编码，不含空白）。"""
    total = 0
    for name in names:
        if name in schemas:
            total += len(json.dumps(schemas[name], ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8"))
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="广告 schema 可达递归检查 + 紧凑画像")
    ap.add_argument("--openapi", default=DEFAULT_OPENAPI)
    ap.add_argument("--gate", action="store_true", help="发现可达递归时 exit 1")
    ap.add_argument("--top", type=int, default=10, help="画像输出前 N 大 operation")
    args = ap.parse_args(argv)

    doc = _load(args.openapi)
    schemas: dict = (doc.get("components") or {}).get("schemas") or {}
    graph = _build_graph(schemas)

    rows: list[tuple[int, str, str, int]] = []   # (字节, 方法, 路径, ref 数)
    offending: dict[tuple[str, str], list[list[str]]] = {}

    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch", "head", "options"}:
                continue
            if not isinstance(op, dict):
                continue
            roots = _operation_advertised_schemas(op)
            expand = _closure(graph, roots)
            rows.append((_schema_bytes(schemas, expand), method.upper(), path, len(expand)))
            cycles = _find_cycles(graph, roots)
            if cycles:
                offending[(method.upper(), path)] = cycles

    if not rows:
        print("[fail-closed] 一个 operation 都没扫到", file=sys.stderr)
        return 2

    total_bytes = sum(r[0] for r in rows)
    print(f"扫描 operation：{len(rows)} 个；广告 schema 总量（逐 operation 累加）："
          f"{total_bytes / 1024:.1f} KiB；components.schemas 共 {len(schemas)} 个定义")

    rows.sort(reverse=True)
    print(f"\n引用预算 Top {min(args.top, len(rows))}（按广告字节数）：")
    print(f"  {'字节':>8}  {'refs':>4}  操作")
    for size, method, path, nrefs in rows[: args.top]:
        print(f"  {size:>8}  {nrefs:>4}  {method:5s} {path}")

    if not offending:
        print("\n✅ 无可达递归：所有广告 schema 在引用图上都是 DAG（客户端可安全递归展开）")
        return 0

    print(f"\n⚠️ 存在可达递归的 operation：{len(offending)} 个")
    for (method, path), cycles in sorted(offending.items()):
        print(f"  {method} {path}")
        for cycle in cycles[:3]:
            print("    环：" + " → ".join(cycle))

    if args.gate:
        print("\n[gate] 可达递归属阻断项：请把环打断（改用 id 引用 / 提升为独立 schema）。",
              file=sys.stderr)
        return 1
    print("\n[report-only] 未加 --gate，不阻断。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
