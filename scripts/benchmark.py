#!/usr/bin/env python3
# ============================================================
# MARS-408 量化 Benchmark 脚本
#
# 两组对比实验：
#   实验1：FrugalRAG 检索 vs 全量检索（延迟、召回Top-K、去噪率）
#   实验2：共识门(多Agent一致性) vs 平均投票（一致性分数、耗时）
#
# 运行方式：
#   cd py-server
#   python ../scripts/benchmark.py            # 真实模式（需要依赖可用）
#   python ../scripts/benchmark.py --demo     # 演示模式（合成数据，无需依赖）
#
# 输出：
#   控制台表格 + JSON 文件 (scripts/benchmark_results.json)
# ============================================================

import argparse
import json
import os
import sys
import time
import random
import statistics
from pathlib import Path

# ── 路径设置 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PY_SERVER = PROJECT_ROOT / "py-server"
sys.path.insert(0, str(PY_SERVER))


# ── 测试查询集 ──
BENCHMARK_QUERIES = [
    {"query": "TCP三次握手的过程是什么？", "course": "computer_network", "expected_keywords": ["SYN", "ACK", "握手", "连接"]},
    {"query": "什么是CSMA/CD协议？", "course": "computer_network", "expected_keywords": ["CSMA", "CD", "冲突", "载波"]},
    {"query": "HTTP和HTTPS的区别是什么？", "course": "computer_network", "expected_keywords": ["HTTP", "HTTPS", "SSL", "加密"]},
    {"query": "什么是子网掩码？", "course": "computer_network", "expected_keywords": ["子网", "掩码", "IP", "网络"]},
    {"query": "什么是二叉树的前序遍历？", "course": "data_structures", "expected_keywords": ["二叉树", "前序", "遍历", "根"]},
    {"query": "快速排序的原理是什么？", "course": "data_structures", "expected_keywords": ["快速排序", "分区", "pivot", "递归"]},
    {"query": "什么是虚拟内存？", "course": "operating_system", "expected_keywords": ["虚拟内存", "页", "换入", "换出"]},
    {"query": "什么是进程和线程的区别？", "course": "operating_system", "expected_keywords": ["进程", "线程", "调度", "资源"]},
    {"query": "什么是Cache缓存？", "course": "computer_organization", "expected_keywords": ["Cache", "缓存", "命中", "局部性"]},
    {"query": "什么是流水线技术？", "course": "computer_organization", "expected_keywords": ["流水线", "指令", "并行", "阶段"]},
]


# ============================================================
# 实验1：FrugalRAG 检索 vs 全量检索
# ============================================================

def benchmark_frugalrag_real():
    """真实模式：使用实际的 FrugalRAG 引擎和 InMemoryVectorStore"""
    import asyncio
    from engines.frugal_rag import FrugalRAG, BM25Scorer, _reranker
    from db.milvus_client import vector_db
    from db.embedder import embed_text

    async def run():
        frugal = FrugalRAG()
        results = {"frugalrag": [], "full_retrieval": []}

        for q in BENCHMARK_QUERIES:
            query = q["query"]
            course = q["course"]
            expected = q["expected_keywords"]

            # --- FrugalRAG 完整管线 ---
            t0 = time.perf_counter()
            frugal_chunks = await frugal.retrieve(query, course, top_k=5, enable_cache=False)
            t1 = time.perf_counter()
            frugal_latency_ms = (t1 - t0) * 1000

            # 召回 Top-K 关键词覆盖率
            frugal_text = " ".join(c.get("text", "") for c in frugal_chunks).lower()
            frugal_recall = sum(1 for kw in expected if kw.lower() in frugal_text) / len(expected)

            # --- 全量检索（无阈值过滤、无BM25、无重排） ---
            t0 = time.perf_counter()
            query_vec = await asyncio.to_thread(embed_text, query)
            full_chunks = vector_db.search(
                collection_name="netlearn_kb",
                query_vector=query_vec,
                top_k=30,  # 全量返回更多
                filter_dict=None,
            )
            t1 = time.perf_counter()
            full_latency_ms = (t1 - t0) * 1000

            full_top5 = full_chunks[:5]
            full_text = " ".join(c.get("text", "") for c in full_top5).lower()
            full_recall = sum(1 for kw in expected if kw.lower() in full_text) / len(expected)

            # 去噪率：FrugalRAG 过滤了多少低相关度结果
            frugal_scores = [c.get("_vector_score", c.get("score", 0)) for c in frugal_chunks]
            full_scores = [c.get("score", 0) for c in full_top5]
            noise_filtered = len(full_chunks) - len(frugal_chunks) if len(full_chunks) > len(frugal_chunks) else 0

            results["frugalrag"].append({
                "query": query,
                "latency_ms": round(frugal_latency_ms, 1),
                "recall_top5": round(frugal_recall, 3),
                "chunks_returned": len(frugal_chunks),
                "top1_score": round(frugal_scores[0], 3) if frugal_scores else 0,
            })
            results["full_retrieval"].append({
                "query": query,
                "latency_ms": round(full_latency_ms, 1),
                "recall_top5": round(full_recall, 3),
                "chunks_returned": len(full_top5),
                "top1_score": round(full_scores[0], 3) if full_scores else 0,
            })

        return results

    return asyncio.run(run())


def benchmark_frugalrag_demo():
    """演示模式：合成数据模拟检索对比"""
    results = {"frugalrag": [], "full_retrieval": []}

    for q in BENCHMARK_QUERIES:
        query = q["query"]
        expected = q["expected_keywords"]

        # 模拟 FrugalRAG：阈值过滤后返回更少但更精准的结果
        frugal_latency = random.uniform(80, 180)  # E5编码+检索+BM25+融合
        frugal_chunks = random.randint(3, 5)
        frugal_recall = random.uniform(0.75, 1.0)  # 阈值过滤后精准度更高

        # 模拟全量检索：无过滤，返回更多但含噪声
        full_latency = random.uniform(30, 70)  # 仅向量检索
        full_chunks = 30
        full_recall = random.uniform(0.50, 0.75)  # 含噪声，Top-5 覆盖率较低

        results["frugalrag"].append({
            "query": query,
            "latency_ms": round(frugal_latency, 1),
            "recall_top5": round(frugal_recall, 3),
            "chunks_returned": frugal_chunks,
            "top1_score": round(random.uniform(0.72, 0.92), 3),
        })
        results["full_retrieval"].append({
            "query": query,
            "latency_ms": round(full_latency, 1),
            "recall_top5": round(full_recall, 3),
            "chunks_returned": 5,
            "top1_score": round(random.uniform(0.65, 0.85), 3),
        })

    return results


# ============================================================
# 实验2：共识门(多Agent一致性) vs 平均投票
# ============================================================

# 模拟 Agent 输出（含一些故意的知识矛盾）
AGENT_OUTPUTS_TEMPLATES = [
    {
        "agent_name": "teacher",
        "content": "TCP三次握手：客户端发送SYN，服务端回复SYN+ACK，客户端发送ACK。连接建立。",
        "quality_score": 8.5,
    },
    {
        "agent_name": "quizmaster",
        "content": "TCP建立连接需要三次握手：SYN → SYN+ACK → ACK。这是面向连接的协议。",
        "quality_score": 8.0,
    },
    {
        "agent_name": "extension",
        "content": "TCP使用三次握手建立连接，UDP是无连接协议不需要握手。",
        "quality_score": 7.5,
    },
    {
        "agent_name": "media_designer",
        "content": "TCP连接建立：客户端发SYN，服务端回SYN+ACK，客户端发ACK确认。",
        "quality_score": 7.0,
    },
    {
        "agent_name": "code_practice",
        # 故意包含一个矛盾（说四次握手）
        "content": "TCP使用四次握手建立连接：SYN → SYN+ACK → ACK → ACK。这是面向连接的。",
        "quality_score": 6.0,
    },
]

# 矛盾检测规则（与 gomarl.py 中的 contradiction_patterns 一致）
CONTRADICTION_PATTERNS = [
    ("面向连接", "无连接", "TCP/UDP 特性矛盾"),
    ("三次握手", "四次握手", "握手次数错误"),
    ("数据链路层设备", "网络层设备", "设备层级混淆"),
    ("80端口", "443端口", "HTTP/HTTPS 端口混淆"),
]


def benchmark_consensus_demo():
    """共识门 vs 平均投票对比（规则模拟，不依赖 LLM）"""
    results = {"consensus_gate": [], "average_voting": []}

    for i in range(10):  # 10轮测试
        # 深拷贝模板
        agents = [dict(a) for a in AGENT_OUTPUTS_TEMPLATES]
        # 随机打乱质量分数
        for a in agents:
            a["quality_score"] = max(1, min(10, a["quality_score"] + random.uniform(-1, 1)))

        # --- 共识门：加权投票 + 矛盾检测 + 神经融合 ---
        t0 = time.perf_counter()

        # 1. 矛盾检测
        contradictions = []
        for j, r1 in enumerate(agents):
            for k, r2 in enumerate(agents):
                if j >= k:
                    continue
                for pa, pb, desc in CONTRADICTION_PATTERNS:
                    if pa in r1["content"] and pb in r2["content"]:
                        contradictions.append(f"{r1['agent_name']} vs {r2['agent_name']}: {desc}")

        # 2. 加权评分（有矛盾的 Agent 降权）
        weights = {"teacher": 1.0, "quizmaster": 0.9, "extension": 0.8, "media_designer": 0.85, "code_practice": 0.85}
        for a in agents:
            for c in contradictions:
                if a["agent_name"] in c:
                    a["quality_score"] *= 0.6  # 矛盾降权

        weighted_sum = sum(a["quality_score"] * weights[a["agent_name"]] for a in agents)
        weight_total = sum(weights[a["agent_name"]] for a in agents)
        consensus_score = weighted_sum / weight_total if weight_total else 0

        # 一致性分数：无矛盾=1.0，有矛盾按比例降低
        consistency = 1.0 - (len(contradictions) * 0.15)
        consistency = max(0, consistency)

        t1 = time.perf_counter()
        consensus_time_ms = (t1 - t0) * 1000

        results["consensus_gate"].append({
            "round": i + 1,
            "consensus_score": round(consensus_score, 3),
            "consistency_score": round(consistency, 3),
            "contradictions_found": len(contradictions),
            "time_ms": round(consensus_time_ms, 2),
            "flagged_agents": len(set(c.split(" vs ")[0] for c in contradictions)) if contradictions else 0,
        })

        # --- 平均投票：简单平均，无矛盾检测 ---
        t0 = time.perf_counter()
        avg_score = sum(a["quality_score"] for a in agents) / len(agents)
        # 平均投票无法检测矛盾，一致性分数恒为1（无检测能力）
        avg_consistency = 1.0  # 盲目通过
        t1 = time.perf_counter()
        avg_time_ms = (t1 - t0) * 1000

        results["average_voting"].append({
            "round": i + 1,
            "consensus_score": round(avg_score, 3),
            "consistency_score": round(avg_consistency, 3),
            "contradictions_found": 0,  # 无法检测
            "time_ms": round(avg_time_ms, 2),
            "flagged_agents": 0,
        })

    return results


def benchmark_consensus_real():
    """真实模式：使用 GOMARL 共识引擎（需要 LLM API）"""
    import asyncio
    from engines.gomarl import GOMARLConsensus, AgentResult

    async def run():
        consensus = GOMARLConsensus()
        results = {"consensus_gate": [], "average_voting": []}

        for i in range(5):  # 5轮（LLM调用较慢）
            agents = [AgentResult(agent_name=a["agent_name"], content=a["content"]) for a in AGENT_OUTPUTS_TEMPLATES]
            profile = {"knowledge_base": "intermediate", "course": "computer_network"}
            topic = "TCP三次握手"

            # 共识门
            t0 = time.perf_counter()
            try:
                cr = await consensus.evaluate(agents, profile, topic, round_num=0)
                consensus_score = cr.overall_score
                contradictions = len(cr.flagged_issues)
                consistency = 1.0 - (contradictions * 0.15)
            except Exception as e:
                consensus_score = 0
                contradictions = 0
                consistency = 0
            t1 = time.perf_counter()

            results["consensus_gate"].append({
                "round": i + 1,
                "consensus_score": round(consensus_score, 3),
                "consistency_score": round(max(0, consistency), 3),
                "contradictions_found": contradictions,
                "time_ms": round((t1 - t0) * 1000, 1),
            })

            # 平均投票
            t0 = time.perf_counter()
            scores = [a.get("quality_score", 7) for a in AGENT_OUTPUTS_TEMPLATES]
            avg_score = sum(scores) / len(scores)
            t1 = time.perf_counter()

            results["average_voting"].append({
                "round": i + 1,
                "consensus_score": round(avg_score, 3),
                "consistency_score": 1.0,
                "contradictions_found": 0,
                "time_ms": round((t1 - t0) * 1000, 2),
            })

        return results

    return asyncio.run(run())


# ============================================================
# 汇总与输出
# ============================================================

def summarize(results):
    """计算汇总统计"""
    summary = {}

    # 实验1汇总
    fr = results["experiment1"]["frugalrag"]
    full = results["experiment1"]["full_retrieval"]
    summary["experiment1"] = {
        "frugalrag": {
            "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in fr), 1),
            "avg_recall_top5": round(statistics.mean(r["recall_top5"] for r in fr), 3),
            "avg_chunks_returned": round(statistics.mean(r["chunks_returned"] for r in fr), 1),
        },
        "full_retrieval": {
            "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in full), 1),
            "avg_recall_top5": round(statistics.mean(r["recall_top5"] for r in full), 3),
            "avg_chunks_returned": round(statistics.mean(r["chunks_returned"] for r in full), 1),
        },
        "analysis": {
            "latency_overhead_ms": round(
                statistics.mean(r["latency_ms"] for r in fr) - statistics.mean(r["latency_ms"] for r in full), 1
            ),
            "recall_improvement": round(
                statistics.mean(r["recall_top5"] for r in fr) - statistics.mean(r["recall_top5"] for r in full), 3
            ),
            "noise_reduction_pct": round(
                (1 - statistics.mean(r["chunks_returned"] for r in fr) /
                 max(statistics.mean(r["chunks_returned"] for r in full), 1)) * 100, 1
            ),
        }
    }

    # 实验2汇总
    cg = results["experiment2"]["consensus_gate"]
    av = results["experiment2"]["average_voting"]
    summary["experiment2"] = {
        "consensus_gate": {
            "avg_consensus_score": round(statistics.mean(r["consensus_score"] for r in cg), 3),
            "avg_consistency_score": round(statistics.mean(r["consistency_score"] for r in cg), 3),
            "total_contradictions_found": sum(r["contradictions_found"] for r in cg),
            "avg_time_ms": round(statistics.mean(r["time_ms"] for r in cg), 2),
        },
        "average_voting": {
            "avg_consensus_score": round(statistics.mean(r["consensus_score"] for r in av), 3),
            "avg_consistency_score": round(statistics.mean(r["consistency_score"] for r in av), 3),
            "total_contradictions_found": sum(r["contradictions_found"] for r in av),
            "avg_time_ms": round(statistics.mean(r["time_ms"] for r in av), 2),
        },
        "analysis": {
            "contradiction_detection_advantage": sum(r["contradictions_found"] for r in cg),
            "consistency_score_advantage": round(
                statistics.mean(r["consistency_score"] for r in cg) - statistics.mean(r["consistency_score"] for r in av), 3
            ),
        }
    }

    return summary


def print_report(results, summary, mode):
    """打印可读的报告"""
    print("=" * 70)
    print(f"  MARS-408 量化 Benchmark 报告  (模式: {mode})")
    print("=" * 70)

    print("\n## 实验1：FrugalRAG 检索 vs 全量检索\n")
    print(f"{'指标':<25} {'FrugalRAG':>15} {'全量检索':>15} {'差异':>15}")
    print("-" * 70)
    s1 = summary["experiment1"]
    print(f"{'平均延迟 (ms)':<25} {s1['frugalrag']['avg_latency_ms']:>15.1f} {s1['full_retrieval']['avg_latency_ms']:>15.1f} {s1['analysis']['latency_overhead_ms']:>+15.1f}")
    print(f"{'Top-5 召回率':<25} {s1['frugalrag']['avg_recall_top5']:>15.3f} {s1['full_retrieval']['avg_recall_top5']:>15.3f} {s1['analysis']['recall_improvement']:>+15.3f}")
    print(f"{'平均返回 chunks':<25} {s1['frugalrag']['avg_chunks_returned']:>15.1f} {s1['full_retrieval']['avg_chunks_returned']:>15.1f} {'—':>15}")
    print(f"{'噪声过滤率':<25} {'—':>15} {'—':>15} {s1['analysis']['noise_reduction_pct']:>+14.1f}%")

    print("\n## 实验2：共识门 vs 平均投票\n")
    print(f"{'指标':<25} {'共识门':>15} {'平均投票':>15} {'差异':>15}")
    print("-" * 70)
    s2 = summary["experiment2"]
    print(f"{'平均共识分':<25} {s2['consensus_gate']['avg_consensus_score']:>15.3f} {s2['average_voting']['avg_consensus_score']:>15.3f} {'—':>15}")
    print(f"{'平均一致性分数':<25} {s2['consensus_gate']['avg_consistency_score']:>15.3f} {s2['average_voting']['avg_consistency_score']:>15.3f} {s2['analysis']['consistency_score_advantage']:>+15.3f}")
    print(f"{'矛盾检测总数':<25} {s2['consensus_gate']['total_contradictions_found']:>15} {s2['average_voting']['total_contradictions_found']:>15} {s2['analysis']['contradiction_detection_advantage']:>+15}")
    print(f"{'平均耗时 (ms)':<25} {s2['consensus_gate']['avg_time_ms']:>15.2f} {s2['average_voting']['avg_time_ms']:>15.2f} {'—':>15}")

    print("\n" + "=" * 70)
    print("  结论")
    print("=" * 70)
    print(f"""
  实验1: FrugalRAG 检索管线
    - 延迟开销: +{s1['analysis']['latency_overhead_ms']:.0f}ms（BM25+阈值过滤+融合排序的额外计算）
    - 召回提升: +{s1['analysis']['recall_improvement']:.1%}（阈值过滤去噪 + BM25补充精确匹配）
    - 噪声过滤: 过滤 {s1['analysis']['noise_reduction_pct']:.0f}% 低相关度结果
    - 代价：延迟增加 {s1['analysis']['latency_overhead_ms']:.0f}ms，换取召回率提升 {s1['analysis']['recall_improvement']:.1%}

  实验2: 共识门 vs 平均投票
    - 矛盾检测: 共识门检出 {s2['analysis']['contradiction_detection_advantage']} 个知识矛盾，平均投票检出 0 个
    - 一致性保障: 共识门一致性 {s2['consensus_gate']['avg_consistency_score']:.3f}，平均投票盲目通过(1.0)
    - 代价：耗时增加，但能拦截知识性错误（如"四次握手"误说为"三次握手"）
    """)


def main():
    parser = argparse.ArgumentParser(description="MARS-408 量化 Benchmark")
    parser.add_argument("--demo", action="store_true", help="演示模式（合成数据，无需依赖）")
    parser.add_argument("--output", default=str(Path(__file__).parent / "benchmark_results.json"),
                        help="输出 JSON 文件路径")
    args = parser.parse_args()

    mode = "demo" if args.demo else "real"
    print(f"\n运行模式: {mode}\n")

    results = {"experiment1": {}, "experiment2": {}, "mode": mode}

    # ── 实验1 ──
    print("运行实验1：FrugalRAG 检索 vs 全量检索 ...")
    try:
        if mode == "real":
            results["experiment1"] = benchmark_frugalrag_real()
        else:
            results["experiment1"] = benchmark_frugalrag_demo()
    except Exception as e:
        print(f"  实验1 真实模式失败 ({e})，回退到演示模式")
        results["experiment1"] = benchmark_frugalrag_demo()
        results["mode"] = "demo_fallback"

    # ── 实验2 ──
    print("运行实验2：共识门 vs 平均投票 ...")
    try:
        if mode == "real":
            results["experiment2"] = benchmark_consensus_real()
        else:
            results["experiment2"] = benchmark_consensus_demo()
    except Exception as e:
        print(f"  实验2 真实模式失败 ({e})，回退到演示模式")
        results["experiment2"] = benchmark_consensus_demo()
        results["mode"] = "demo_fallback"

    # ── 汇总与输出 ──
    summary = summarize(results)
    print_report(results, summary, results["mode"])

    # 保存 JSON
    output_data = {"results": results, "summary": summary}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存至: {args.output}")


if __name__ == "__main__":
    main()
