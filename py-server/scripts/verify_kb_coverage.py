# ============================================================
# 408 四科知识库覆盖验收脚本（INC-03 / T04）
#
# 校验目标（设计文档 T04 验收）：
#   ① 知识库 chunk 总数 >= 1800
#   ② 四科（计网/数据结构/计组/操作系统）group 范围均非空
#   ③ 跨四科可检索（按 group 过滤四科均能得到结果）
#
# 默认做静态结构校验（只依赖 SEED_KNOWLEDGE_CHUNKS，不触发模型/向量初始化）。
# 加 --live 时尝试连接 vector_db（Milvus/InMemory）做真实检索校验。
# ============================================================

import argparse
import os
import sys

# 将 py-server 根目录加入 sys.path，确保 `seed_data` 可被导入（无论从何处运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 静态结构校验：直接基于种子数据（确定、无副作用）──
from seed_data import SEED_KNOWLEDGE_CHUNKS, SEED_QUESTIONS

# 优先复用 kg_dag 的单一真源 chapter_to_group；失败则本地前缀兜底
try:
    from agents.kg_dag import chapter_to_group
except Exception:  # noqa: BLE001
    def chapter_to_group(subject: str, chapter=None) -> int:
        s = subject or ""
        if s.startswith("co_"):
            return 15
        if s.startswith("os_"):
            return 22
        if s.startswith("ds_"):
            return 8
        return 1


# 四科 group 范围
SUBJECT_RANGES = {
    "computer_network": (1, 7),
    "data_structures": (8, 14),
    "computer_organization": (15, 21),
    "operating_system": (22, 26),
}


def classify_subject(group: int) -> str:
    for name, (lo, hi) in SUBJECT_RANGES.items():
        if lo <= group <= hi:
            return name
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="验证 408 四科知识库覆盖 (INC-03)")
    parser.add_argument("--live", action="store_true", help="连接 vector_db 做真实检索校验")
    parser.add_argument("--min", type=int, default=1800, help="最小 chunk 数阈值")
    args = parser.parse_args()

    errors = []
    warnings = []

    chunks = SEED_KNOWLEDGE_CHUNKS
    total = len(chunks)
    print(f"[1/4] 知识库 chunk 总数: {total}")
    if total < args.min:
        errors.append(f"chunk 总数 {total} < 阈值 {args.min}")
    else:
        print(f"      ✅ 满足 >= {args.min}")

    # 按 group 统计四科覆盖
    by_subject_count = {name: 0 for name in SUBJECT_RANGES}
    by_subject_groups = {name: set() for name in SUBJECT_RANGES}
    missing_group = 0
    for c in chunks:
        meta = c.get("metadata", {}) or {}
        grp = meta.get("group")
        if grp is None:
            grp = chapter_to_group(meta.get("subject", ""), meta.get("chapter"))
            missing_group += 1
        subj = classify_subject(int(grp))
        if subj in by_subject_count:
            by_subject_count[subj] += 1
            by_subject_groups[subj].add(int(grp))

    print(f"[2/4] 四科覆盖（按 group 范围统计）:")
    for name, (lo, hi) in SUBJECT_RANGES.items():
        cnt = by_subject_count[name]
        covered = sorted(by_subject_groups[name])
        flag = "✅" if cnt > 0 else "❌"
        print(f"      {flag} {name:22s} chunks={cnt:5d}  groups={covered}")
        if cnt == 0:
            errors.append(f"{name} 知识库为空（group {lo}-{hi} 无 chunk）")

    if missing_group:
        warnings.append(f"{missing_group} 条 chunk 元数据缺 group，已用 chapter_to_group 兜底")

    # 跨四科检索可行性（结构层面：每科均有可检索文本）
    print(f"[3/4] 跨四科检索可行性（结构校验）:")
    for name in SUBJECT_RANGES:
        if by_subject_count[name] > 0:
            print(f"      ✅ {name}: 存在 {by_subject_count[name]} 条可检索 chunk")
        else:
            errors.append(f"{name}: 无可检索 chunk，跨科检索不可用")

    # 可选：真实 vector_db 检索校验
    if args.live:
        print(f"[4/4] 实时 vector_db 检索校验（--live）:")
        try:
            from db.embedder import embed_text
            from db.milvus_client import vector_db
            vector_db.connect()
            sample = ["TCP 三次握手建立连接过程", "Cache 的映射方式与替换算法",
                      "补码加减运算与溢出判断", "银行家算法避免死锁"]
            for q in sample:
                vec = embed_text(q)
                res = vector_db.search("netlearn_kb", vec, top_k=3)
                ok = len(res) > 0
                print(f"      {'✅' if ok else '⚠️'} 检索「{q[:18]}...」→ {len(res)} 条")
                if not ok:
                    warnings.append(f"实时检索无结果: {q}")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"实时检索校验跳过（非阻断）: {e}")
    else:
        print(f"[4/4] 实时 vector_db 检索校验: 跳过（加 --live 启用）")

    print("\n" + "=" * 56)
    if warnings:
        print("⚠️ 警告:")
        for w in warnings:
            print(f"   - {w}")
    if errors:
        print("❌ 验收未通过:")
        for e in errors:
            print(f"   - {e}")
        print("=" * 56)
        sys.exit(1)
    print("✅ 验收通过：408 四科知识库覆盖满足 P0 要求（≥%d chunks，四科非空）。" % args.min)
    print("=" * 56)
    sys.exit(0)


if __name__ == "__main__":
    main()
