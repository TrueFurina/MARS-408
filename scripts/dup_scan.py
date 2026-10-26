# -*- coding: utf-8 -*-
"""复制粘贴扫描（report-only / --gate 双模，REA #20）

为什么不用 jscpd：本仓没有引入 jscpd 依赖（离线环境装不上就等于没有），
而"有个装不上的门禁"比"没有门禁"更糟。这里用标准库实现一个**行窗指纹**
扫描器，口径写清楚、可复跑、可自测：

  * 归一化：去行尾空白，把引号内字符串与数字折叠成占位符（避免变量名不同
    就算不同），保留注释行（注释成段复制同样是维护债）。
  * 指纹：连续 WINDOW=10 个"有意义行"的 SHA1；单窗内 >60% 是括号/关键字
    这类琐碎行则跳过（否则任何 Vue 文件都长得像）。
  * 重复：同一指纹出现在 >=2 个互不重叠的位置（不同文件，或同文件相隔
    >=WINDOW 行），记为一处克隆。

诚实边界：这是**文本级**克隆检测，不是 AST/token 级（jscpd 的语义级）。
它能抓"整段复制改两行"，抓不到"改名+重排"。故默认 report-only；
--gate 只在**新增**克隆超过基线时失败（存量登记在 baseline，避免首日就红
然后大家习惯性 --no-verify）。

退出码：
  0 = 执行完毕且（非 gate 或新增克隆为 0）
  1 = --gate 且新增克隆 > 0
  2 = 探活失败（扫描面为空 / 基线不可解析 —— fail-closed）

用法：
  python scripts/dup_scan.py                 # report-only
  python scripts/dup_scan.py --gate          # 只拦新增
  python scripts/dup_scan.py --update-baseline   # 显式刷新基线（会打印新增项）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(REPO, "scripts", "dup_scan.baseline.json")

WINDOW = 10
TRIVIAL_RATIO = 0.6
SKIP_DIRS = {"node_modules", ".venv", "dist", "build", "site", "archive", "__pycache__",
             ".git", "vectordb_data", "milvus_lite_data", "data", "sessions", "media",
             "_e2e_tmp_mdhz", "site-packages", ".pytest_cache", "coverage",
             # 数据与生成物不算克隆：种子语料/提示词常量/实验台账本来就是"重复的文本"，
             # 把它们计入只会把真实克隆淹掉（首跑实测：仅 seed/ 就贡献了 90% 的组）。
             "seed", "_scratch", "documents", "deliverables", "tests", "test",
             "assets", "public", "knowledge_base", "workspace"}
SCAN_ROOTS = ["src", "py-server", "scripts"]
EXTS = {".py", ".ts", ".tsx", ".vue", ".mjs", ".js"}
_MAX_FILE_BYTES = 400 * 1024

_TRIVIAL = frozenset({"", "{", "}", "(", ")", "});", "),", "};", "],", "}", "else:",
                      "try:", "try {", "} catch {", "</template>", "<template>",
                      "<script setup lang=\"ts\">", "</script>", "return", "pass"})
_STR_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\]|\\.)*`")
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_BLOCK_STR_RE = re.compile(r'("""|\'\'\')(?:.|\n)*?\1', re.MULTILINE)


def _strip_block_strings(text: str) -> str:
    """把三引号字符串**整段**抹掉，但保留行数（换成空行占位）。

    不这么做，任何两段长度相近的提示词/文档字符串都会命中——首跑实测
    prompts.py 的 6 个常量互相"克隆"了 20+ 次，全是假阳性。
    """
    def repl(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")

    return _BLOCK_STR_RE.sub(repl, text)


def _normalize(line: str) -> str:
    s = _STR_RE.sub("'S'", line.strip())
    s = _NUM_RE.sub("N", s)
    return re.sub(r"\s+", " ", s)


def _iter_files():
    for root_name in SCAN_ROOTS:
        base = os.path.join(REPO, root_name)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in EXTS:
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    if os.path.getsize(path) > _MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                yield path


def _windows(path: str):
    """产出 (指纹, 起始行号, 结束行号)。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return
    norm = [_normalize(ln) for ln in _strip_block_strings(text).splitlines()]
    n = len(norm)
    if n < WINDOW:
        return
    for i in range(n - WINDOW + 1):
        chunk = norm[i:i + WINDOW]
        trivial = sum(1 for c in chunk if c in _TRIVIAL)
        if trivial / WINDOW > TRIVIAL_RATIO:
            continue
        # 行多样性门槛：10 行里少于 5 种不同内容 ⇒ 重复的字典/常量块，
        # 不是"可抽公共逻辑"的克隆，计入只会制造噪声。
        if len(set(chunk)) < 5:
            continue
        digest = hashlib.sha1("\n".join(chunk).encode("utf-8")).hexdigest()[:16]
        yield digest, i + 1, i + WINDOW, chunk[0][:60]


def _canonical(hits: list[tuple[str, int, int, str]]) -> tuple[tuple[str, int], ...]:
    """把「同一段克隆的一串相邻窗口」归到一个规范键。

    窗口步长是 1（不是 WINDOW），这样块起始位置错位 1~9 行也能命中；
    代价是长度 L 的克隆会产生 L-WINDOW+1 个连续指纹。规范化后它们的
    (文件, 相对起点) 集合完全一致，据此合并成**一个克隆区域**——
    否则报告里同一次复制会以 10 倍数量出现（首跑 844 组里约 760 组是这个原因）。
    """
    mins: dict[str, int] = {}
    for rel, start, _end, _head in hits:
        mins[rel] = min(mins.get(rel, start), start)
    return tuple(sorted((rel, start - mins[rel]) for rel, start, _e, _h in hits))


def scan() -> dict:
    index: dict[str, list[tuple[str, int, int, str]]] = {}
    files = 0
    for path in _iter_files():
        rel = os.path.relpath(path, REPO).replace("\\", "/")
        for digest, start, end, head in _windows(path):
            index.setdefault(digest, []).append((rel, start, end, head))
        files += 1

    # 1) 逐指纹去重叠：同一文件里相隔 < WINDOW 的命中属于同一段
    per_digest: dict[str, list[tuple[str, int, int, str]]] = {}
    for digest, hits in index.items():
        uniq: list[tuple[str, int, int, str]] = []
        for hit in sorted(hits, key=lambda h: (h[0], h[1])):
            if uniq and uniq[-1][0] == hit[0] and hit[1] - uniq[-1][1] < WINDOW:
                continue
            uniq.append(hit)
        if len(uniq) >= 2:          # 至少两处才算克隆
            per_digest[digest] = uniq

    # 2) 相邻窗口合并成克隆区域（同一段代码只报一次）
    regions: dict[tuple, dict] = {}
    for digest, hits in per_digest.items():
        key = _canonical(hits)
        slot = regions.setdefault(key, {"digests": [], "hits": hits, "longest": 0})
        slot["digests"].append(digest)
        # 代表命中取窗口起点最小的那组（区域开头），长度取最大
        if hits[0][1] < slot["hits"][0][1]:
            slot["hits"] = hits
        slot["longest"] = max(slot["longest"], len(slot["digests"]))
    return {"files": files, "regions": regions}


def _sig(key: tuple[tuple[str, int], ...]) -> str:
    """区域规范键 → 短指纹（写进基线，稳定且可读性无关）。"""
    raw = "|".join(f"{rel}@{off}" for rel, off in key)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ==== 豁免（2026-10-26 新增）================================================
# 与 scripts/token_scan_exemptions.json 同一范式：**理由枚举 + 僵尸检测 + 不提供刷新入口**。
#
# 存在理由：声明式规则表（如 scan_metric_occurrences.py 的 RULES 元组）**天然就是重复的**，
# 它不像业务代码里的复制粘贴那样代表"该抽象没抽象"。若每次加一条规则都去基线登记一批
# 指纹，只会把真实克隆淹没在一串纯噪声提交里——实测 4 轮共 10 组指纹全来自同一处表。
#
# 范围如何保证窄：豁免按「**文件 + 声明区间**」生效，区间由**标记串**在运行时解析
# （不用硬编码行号，避免行号漂移后要同步豁免清单）。判定要求克隆区域的**每一处命中
# 都落在区间内**才豁免——因此区间之外（哪怕是同一个文件里）的复制粘贴照旧被抓。
# 实测：该文件 6 组全在区间内被豁免，而 :304/:320 那组（解析函数）在区间外，仍被拦。
EXEMPT_FILE = os.path.join(REPO, "scripts", "dup_scan_exemptions.json")
EXEMPT_REASONS = {"declarative-rule-table"}


def load_exemptions() -> list[dict]:
    """读豁免清单。理由不在枚举内 / 缺 range 标记 → fail-closed。

    刻意**不提供** `--update-exemptions` 之类的刷新入口：新增豁免必须手写进
    JSON 并在提交信息里写明理由，与 token_scan 的处置一致。
    """
    if not os.path.isfile(EXEMPT_FILE):
        return []
    try:
        with open(EXEMPT_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[fail-closed] 豁免清单不可解析：{e}", file=sys.stderr)
        sys.exit(2)

    rules: list[dict] = []
    for idx, r in enumerate(data.get("exemptions", []), 1):
        if not r.get("file"):
            print(f"[fail-closed] 豁免 #{idx} 缺 file", file=sys.stderr)
            sys.exit(2)
        if r.get("reason") not in EXEMPT_REASONS:
            print(f"[fail-closed] 豁免 #{idx} 的 reason={r.get('reason')!r} 不在枚举 "
                  f"{sorted(EXEMPT_REASONS)} 内（防止随手开万能豁免）", file=sys.stderr)
            sys.exit(2)
        if not (r.get("range") or {}).get("start_marker"):
            print(f"[fail-closed] 豁免 #{idx} 缺 range.start_marker"
                  f"（不允许整文件豁免，必须界定区间）", file=sys.stderr)
            sys.exit(2)
        rules.append(r)
    return rules


def _resolve_range(rel: str, spec: dict) -> tuple[int, int] | None:
    """把「声明区间」解析成 (起始行, 结束行)，1 起、含端点。

    用**标记串**而非硬编码行号：行号会随文件增删漂移，标记串不会；否则每次改
    这个文件都要同步豁免清单，等于把噪声从一个地方搬到另一个地方。
    """
    path = os.path.join(REPO, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    start_marker = spec["start_marker"]
    end_marker = spec.get("end_marker", ")")
    start = None
    for i, ln in enumerate(lines, 1):
        if start is None:
            if start_marker in ln:
                start = i
        elif ln == end_marker:
            return start, i
    return None


def apply_exemptions(regions: dict) -> tuple[dict, list[dict], list[dict]]:
    """按豁免规则拆分区域 → (计入门禁的, 被豁免的, 僵尸规则)。"""
    rules = load_exemptions()
    if not rules:
        return regions, [], []

    resolved = [(r, _resolve_range(r["file"], r["range"])) for r in rules]
    kept: dict = {}
    exempted: list[dict] = []
    used: set[int] = set()

    for key, region in regions.items():
        hits = region["hits"]
        hit_rule = None
        for r, rng in resolved:
            if rng is None:
                continue
            s, e = rng
            # 必须**每一处**命中都在区间内才豁免（窄的关键）。
            if all(h[0] == r["file"] and s <= h[1] <= e for h in hits):
                hit_rule = r
                break
        if hit_rule is not None:
            used.add(id(hit_rule))
            exempted.append({"sig": _sig(key), "hits": len(hits),
                             "reason": hit_rule["reason"]})
        else:
            kept[key] = region

    stale = [r for r, _ in resolved if id(r) not in used]
    return kept, exempted, stale


def _report(result: dict, top: int) -> tuple[int, int]:
    regions = result["regions"]
    total_dup_lines = sum(WINDOW + r["longest"] - 1 for r in regions.values())
    print(f"扫描文件 {result['files']} 个（{', '.join(SCAN_ROOTS)}，扩展名 {sorted(EXTS)}）")
    print(f"克隆区域：{len(regions)} 处；重复代码约 {total_dup_lines} 行 "
          f"（窗口 {WINDOW} 行、步长 1、相邻窗口已合并；文本级指纹，非 AST 级）")
    if regions:
        print(f"\nTop {min(top, len(regions))} 处（按重合位置数）：")
        ordered = sorted(regions.items(), key=lambda kv: -len(kv[1]["hits"]))
        for key, region in ordered[:top]:
            length = WINDOW + region["longest"] - 1
            hits = region["hits"]
            print(f"  [{_sig(key)}] {len(hits)} 处 × 约 {length} 行  {hits[0][3]!r}")
            for rel, start, end, _ in hits[:6]:
                print(f"      {rel}:{start}-{max(end, start + length - 1)}")
            if len(hits) > 6:
                print(f"      … 另 {len(hits) - 6} 处")
    return len(regions), total_dup_lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="文本级复制粘贴扫描（report-only 默认）")
    ap.add_argument("--gate", action="store_true", help="新增克隆 > 0 时退出 1")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--update-baseline", action="store_true",
                    help="把当前克隆块写入基线（需说明为什么这些是合理的）")
    args = ap.parse_args(argv)

    result = scan()
    if result["files"] == 0:
        print("[fail-closed] 扫描面为 0 个文件（路径配错不能当作干净）", file=sys.stderr)
        return 2

    # 豁免先于一切判定：被豁免的区域既不进报告、也不进基线比较。
    kept, exempted, stale = apply_exemptions(result["regions"])
    if stale:
        # 僵尸检测：豁免规则不再命中任何东西 = 声明区间被改名/删除，或该文件已无克隆。
        # 此时**不得**静默放行——继续豁免一个不存在的东西，等于豁免悄悄扩到了别处。
        print("[僵尸豁免] 以下豁免规则已不命中任何克隆区域（区间被改名/删除？）——"
              "豁免过期不得静默放行：", file=sys.stderr)
        for r in stale:
            print(f"    {r['file']}  reason={r['reason']}", file=sys.stderr)
        return 1
    if exempted:
        reasons = ", ".join(f"{k}={sum(1 for e in exempted if e['reason'] == k)}"
                            for k in sorted({e["reason"] for e in exempted}))
        print(f"豁免（不计入门禁）：{len(exempted)} 组  [{reasons}]")
    result = {"files": result["files"], "regions": kept}

    current = sorted(_sig(k) for k in result["regions"])
    baseline: list[str] = []
    if os.path.isfile(BASELINE):
        try:
            with open(BASELINE, encoding="utf-8") as f:
                baseline = json.load(f).get("known", [])
        except (OSError, json.JSONDecodeError) as e:
            print(f"[fail-closed] 基线不可解析：{e}", file=sys.stderr)
            return 2

    n_blocks, n_lines = _report(result, args.top)
    new = [d for d in current if d not in set(baseline)]
    print(f"\n基线：{len(baseline)} 组；当前 {n_blocks} 组；新增 {len(new)} 组")

    if args.update_baseline:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump({"window": WINDOW, "known": current}, f, ensure_ascii=False, indent=1)
        print(f"已写入基线：{os.path.relpath(BASELINE, REPO)}")
        return 0

    if new and args.gate:
        print("\n[gate] 新增克隆区域（请抽公共函数/组件，或在基线里说明理由后 --update-baseline）：",
              file=sys.stderr)
        by_sig = {_sig(k): v for k, v in result["regions"].items()}
        for sig in new[:10]:
            hits = by_sig[sig]["hits"]
            print(f"  [{sig}] {hits[0][0]}:{hits[0][1]} 等 {len(hits)} 处", file=sys.stderr)
        return 1

    if new:
        print("[report-only] 有新增克隆但不阻断；`npm run gate:dup` 的 CI 档会拦。")
    else:
        print("✅ 无新增克隆块")
    return 0


if __name__ == "__main__":
    sys.exit(main())
