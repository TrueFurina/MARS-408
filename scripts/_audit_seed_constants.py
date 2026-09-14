"""核对 seed_demo_data 模块暴露的常量名与值指纹（不打印值）。

用途：修 main.py 的重复字面量前，先确认 DEMO_USERNAME / DEMO_PASSWORD 等常量
确实存在（否则 import 失败会被外层 except 吞掉，导致演示账号不再创建）。
"""
from __future__ import annotations

import hashlib
import importlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py-server"))


def sh(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def main() -> int:
    mod = importlib.import_module("seed_demo_data")
    print(f"模块文件: {mod.__file__}")
    print("=" * 80)

    print("模块级常量（仅名字与指纹，不打印值）:")
    names = [n for n in dir(mod) if n.isupper() or n.startswith("DEMO")]
    for n in sorted(names):
        v = getattr(mod, n)
        if isinstance(v, str):
            print(f"  {n:<24} str  len={len(v):<5} sha={sh(v)}")
        elif isinstance(v, (int, float, bool)) or v is None:
            print(f"  {n:<24} {type(v).__name__} = {v!r}")
        else:
            try:
                L = len(v)
            except TypeError:
                L = "-"
            print(f"  {n:<24} {type(v).__name__} len={L}")

    print("=" * 80)
    print("模块级函数:")
    for n, o in sorted(vars(mod).items()):
        if inspect.isfunction(o) and not n.startswith("_"):
            sig = str(inspect.signature(o))
            print(f"  {n}{sig}")

    print("=" * 80)
    print("关键判定:")
    for need in ("DEMO_USERNAME", "DEMO_PASSWORD", "DEMO_USER"):
        ok = hasattr(mod, need)
        print(f"  {need:<16} 存在={ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
