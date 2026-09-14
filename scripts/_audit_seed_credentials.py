"""指纹化凭据审计 —— 判定 seed_demo_data.py 中的可疑字面量是真凭据还是演示占位值。

设计原则：**绝不打印任何原值**。只输出
  - 哈希前缀（sha256[:12]，用于跨文件比对同一性）
  - 长度 / 字符集类别 / 香农熵（用于识别高熵密钥形态）
  - 与 .env / config.json 中已配置值的哈希是否**相同**（相同 => 极可能是真凭据副本）
  - 占位符形态启发式（your_/xxx/test/demo/example/change_me/***）

只读，不写任何文件。
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "py-server" / "seed_demo_data.py"
ENV = ROOT / "py-server" / ".env"
CFG = ROOT / "py-server" / "config.json"

PLACEHOLDER_HINTS = (
    "your", "xxx", "yyy", "zzz", "test", "demo", "example", "sample",
    "placeholder", "change_me", "changeme", "todo", "fake", "dummy",
    "123456", "abcdef", "foobar", "<", ">", "****", "secret_key_here",
)

# 收集敏感字段名附近的值时用的关键词
SENSITIVE_KEY_HINTS = (
    "key", "secret", "token", "password", "passwd", "pwd", "credential",
    "appid", "app_id", "access", "salt", "sign", "authorization", "bearer",
)


def sh(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def entropy(s: str) -> float:
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def classes(s: str) -> str:
    kinds = []
    if re.search(r"[a-z]", s):
        kinds.append("a-z")
    if re.search(r"[A-Z]", s):
        kinds.append("A-Z")
    if re.search(r"[0-9]", s):
        kinds.append("0-9")
    if re.search(r"[^A-Za-z0-9]", s):
        kinds.append("sym")
    return ",".join(kinds) or "empty"


def looks_placeholder(s: str) -> bool:
    low = s.lower()
    if any(h in low for h in PLACEHOLDER_HINTS):
        return True
    # 全同一字符 / 明显递增序列
    if len(set(s)) <= 3:
        return True
    return False


def collect_config_values() -> dict[str, list[str]]:
    """返回 {hash: [来源标签]}，只保留可能是凭据的长字符串。"""
    found: dict[str, list[str]] = {}

    def register(val: str, label: str) -> None:
        if not isinstance(val, str):
            return
        v = val.strip()
        if len(v) < 12:
            return
        found.setdefault(sh(v), []).append(label)

    if CFG.exists():
        try:
            raw = json.loads(io.open(CFG, encoding="utf-8", errors="replace").read())
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] config.json 解析失败: {type(exc).__name__}")
            raw = None
        if isinstance(raw, dict):
            def walk(node, path):
                if isinstance(node, dict):
                    for k, v in node.items():
                        walk(v, f"{path}.{k}" if path else str(k))
                elif isinstance(node, list):
                    for i, v in enumerate(node):
                        walk(v, f"{path}[{i}]")
                else:
                    register(str(node), f"config.json:{path}")
            walk(raw, "")

    if ENV.exists():
        for ln, line in enumerate(io.open(ENV, encoding="utf-8", errors="replace"), 1):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            register(v.strip().strip('"').strip("'"), f".env:{k.strip()} (line {ln})")

    return found


def scan_seed(path: Path) -> list[dict]:
    """粗粒度正则抽出所有长度 >= 16 的字符串字面量，并记录上下文。"""
    text = io.open(path, encoding="utf-8", errors="replace").read()
    lines = text.splitlines()
    out: list[dict] = []
    pat = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\]){16,})\1""")
    for ln, line in enumerate(lines, 1):
        for m in pat.finditer(line):
            val = m.group(2)
            prefix = line[: m.start()].strip()
            # 同行是否出现敏感字段名（用于区分普通文案字符串）
            near = line.lower()
            sensitive_named = any(h in near for h in SENSITIVE_KEY_HINTS)
            out.append(
                {
                    "line": ln,
                    "value": val,
                    "ctx": prefix[-60:],
                    "sensitive_named": sensitive_named,
                    "placeholder": looks_placeholder(val),
                    "entropy": round(entropy(val), 2),
                    "classes": classes(val),
                    "len": len(val),
                    "sha": sh(val),
                }
            )
    return out


def main() -> int:
    if not SEED.exists():
        print("!! seed_demo_data.py 不存在")
        return 2

    cfg_hashes = collect_config_values()
    print(f"配置侧登记的长字符串指纹数：{len(cfg_hashes)}（来自 config.json / .env，只记哈希）")
    print("=" * 96)

    items = scan_seed(SEED)
    print(f"seed_demo_data.py 中长度>=16 的字符串字面量：{len(items)} 个")
    print("=" * 96)

    suspicious = []
    for it in items:
        in_cfg = it["sha"] in cfg_hashes
        # 高熵 + 非占位 + 敏感字段名附近 => 可疑真凭据
        risky = (not it["placeholder"]) and it["entropy"] >= 3.0 and it["len"] >= 20
        tag = []
        if in_cfg:
            tag.append("*** 与配置中值同源(真凭据副本) ***")
        if risky and it["sensitive_named"]:
            tag.append("可疑：疑似真密钥形态 & 敏感字段名同行")
        if it["placeholder"]:
            tag.append("占位符形态")
        if tag:
            suspicious.append((it, tag))
            print(
                f"L{it['line']:>4} sha={it['sha']} len={it['len']:>3} "
                f"H={it['entropy']:>4} [{it['classes']}] :: {'; '.join(tag)}"
            )
            print(f"      上下文: {it['ctx'][:70]}")

    print("=" * 96)
    if not suspicious:
        print("结论：无任何可疑项（全部为普通文案/占位）。")
        return 0

    cfg_hit = [s for s in suspicious if s[0]["sha"] in cfg_hashes]
    print(f"汇总：可疑/标记项 {len(suspicious)} 个，其中与配置同源 {len(cfg_hit)} 个。")
    if cfg_hit:
        print(">>> 判定：存在与 .env/config.json 完全一致的字符串 => 真凭据已入库，建议轮换。")
    else:
        print(">>> 判定：无与配置同源者；需人工看上下文确认是否为演示字面量。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
