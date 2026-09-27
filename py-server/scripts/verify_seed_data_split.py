# ============================================================
# py-server/scripts/verify_seed_data_split.py
# 架构评审 M-4 ③（seed_data 按科目拆域）的可机验守门脚本。
#
# 为什么需要它：这次拆包的失败模式是**静默的** —— 数据符号会照样导出来，
# 只是值悄悄变了（例如四科 group 偏移错位、某科 chunks 被漏合并、同名定义
# 的覆盖顺序反了），上层 rgba 全部跑得动，直到 KB 检索按 group 过滤时才出错。
#
# 校验方式：差分。先在拆分前冻结一份符号快照
# （scripts/seed_data_baseline_snapshot.json：33 个公共符号的 repr sha256），
# 拆分后逐个符号比对 repr 哈希 + 类型 + 长度，任一不符即失败。
#
# 运行：cd py-server && python scripts/verify_seed_data_split.py
# 退出码：0 = 全部通过，1 = 存在失败
# ============================================================

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seed  # noqa: E402
import seed_data  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_SNAPSHOT = os.path.join(_HERE, "seed_data_baseline_snapshot.json")

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {extra}")


def _sha(value) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:16]


def main():
    with open(_SNAPSHOT, "r", encoding="utf-8") as f:
        base = json.load(f)["symbols"]

    check("基线快照可读且非空", len(base) > 0, f"n={len(base)}")

    # ── 1) seed 包：每个符号的值与基线逐一对账 ──
    diff = []
    for name, meta in base.items():
        try:
            value = getattr(seed, name)
        except AttributeError:
            diff.append((name, "MISSING"))
            continue
        got = _sha(value)
        if got != meta["sha256"]:
            diff.append((name, f"HASH {got} != {meta['sha256']}"))
        if type(value).__name__ != meta["type"]:
            diff.append((name, f"TYPE {type(value).__name__} != {meta['type']}"))
        if meta["len"] is not None and len(value) != meta["len"]:
            diff.append((name, f"LEN {len(value)} != {meta['len']}"))
    check("seed 包符号值与基线逐项一致", not diff, diff[:5])

    # ── 2) seed_data 兼容层：同一批对象（动态委托，非快照）──
    diff2 = [n for n in base if _sha(getattr(seed_data, n)) != base[n]["sha256"]]
    check("seed_data 委托层值一致", not diff2, diff2[:5])
    check("委托层与包是同一批对象（动态穿透）",
          all(getattr(seed_data, n) is getattr(seed, n) for n in base))
    check("seed_data 公共符号集合与基线一致",
          sorted(n for n in dir(seed_data) if not n.startswith("_")) == sorted(base))

    # ── 3) 关键不变量（group 偏移对齐，错一位就破坏 KG-DAG 与 KB group 过滤）──
    groups = sorted({n.get("group") for n in seed.KNOWLEDGE_GRAPH["nodes"] if n.get("group") is not None})
    check("KG 节点数 = 643", len(seed.KNOWLEDGE_GRAPH["nodes"]) == 643,
          str(len(seed.KNOWLEDGE_GRAPH["nodes"])))
    check("KG 边数 = 639", len(seed.KNOWLEDGE_GRAPH["edges"]) == 639,
          str(len(seed.KNOWLEDGE_GRAPH["edges"])))
    check("KG group 覆盖 1-26 共 26 组", groups == list(range(1, 27)), f"groups={groups[:5]}...{groups[-3:]}")
    check("语料 chunks = 1892", len(seed.SEED_KNOWLEDGE_CHUNKS) == 1892,
          str(len(seed.SEED_KNOWLEDGE_CHUNKS)))
    check("试题 questions = 230", len(seed.SEED_QUESTIONS) == 230, str(len(seed.SEED_QUESTIONS)))
    check("SEED_SUBJECTS 含 27 个方向", len(seed.SEED_SUBJECTS) == 27, str(len(seed.SEED_SUBJECTS)))

    # ── 4) 私有/未登记符号不外泄 ──
    leaked = False
    try:
        seed_data._not_exist_symbol
    except AttributeError:
        leaked = True
    check("未登记符号按 AttributeError 拒绝（非静默返回 None）", leaked)

    print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
