# ============================================================
# MARS-408 性能基准测试脚本
# 赛题要求：核心功能响应时间合理，多模态资源生成需流式/进度追踪
# 运行：python -m scripts.benchmark
# ============================================================

import time
import json
import sys
import os
import asyncio
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.llm_provider import LLMProvider
from db.skill_store import create_skill, get_skill, delete_skill, list_skills
from schemas.skills import Skill, SkillStatus

# ── 配置 ──

RESULTS: dict[str, Any] = {
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "tests": [],
    "summary": {
        "total": 0,
        "passed": 0,
        "failed": 0,
    },
}


def record(name: str, success: bool, duration_ms: float, detail: str = ""):
    """记录测试结果"""
    RESULTS["tests"].append({
        "name": name,
        "success": success,
        "duration_ms": round(duration_ms, 1),
        "detail": detail,
    })
    RESULTS["summary"]["total"] += 1
    if success:
        RESULTS["summary"]["passed"] += 1
    else:
        RESULTS["summary"]["failed"] += 1

    status = "✅" if success else "❌"
    print(f"  {status} {name}: {duration_ms:.1f}ms {detail}")


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── 测试用例 ──


def test_skill_store():
    """技能存储层性能测试"""
    print_header("技能存储层基准测试")

    # 1. 创建技能
    t0 = time.perf_counter()
    s = Skill(
        name="性能测试技能",
        description="用于 benchmark 测试",
        system_prompt="你是一个测试助手。",
        creator_id="benchmark",
        creator_name="benchmark",
    )
    created = create_skill(s)
    t1 = time.perf_counter()
    record("创建技能", bool(created.id), (t1 - t0) * 1000, f"id={created.id}")

    # 2. 查询技能
    t0 = time.perf_counter()
    fetched = get_skill(created.id)
    t1 = time.perf_counter()
    record("查询技能（单条）", fetched is not None, (t1 - t0) * 1000)

    # 3. 列表查询
    t0 = time.perf_counter()
    items, total = list_skills(limit=10)
    t1 = time.perf_counter()
    record("技能列表查询", total >= 0, (t1 - t0) * 1000, f"total={total}")

    # 4. 搜索
    t0 = time.perf_counter()
    items, total = list_skills(search="性能测试")
    t1 = time.perf_counter()
    record("技能搜索", total >= 0, (t1 - t0) * 1000, f"found={total}")

    # 清理
    delete_skill(created.id)


async def test_llm_basic():
    """LLM 基础调用性能测试（仅测试连接，不消耗大量配额）"""
    print_header("LLM 基础调用测试")

    llm = LLMProvider()

    # 简单 chat 调用（测试通道可用性）
    t0 = time.perf_counter()
    try:
        response = await llm.chat(
            messages=[
                {"role": "system", "content": "你是一个测试助手，请简短回答。"},
                {"role": "user", "content": "请用一句话回答：什么是TCP？"},
            ],
            temperature=0.3,
            max_tokens=100,
        )
        t1 = time.perf_counter()
        record("LLM chat 调用（简单）", bool(response), (t1 - t0) * 1000, f"resp_len={len(response)}")
    except Exception as e:
        t1 = time.perf_counter()
        record("LLM chat 调用（简单）", False, (t1 - t0) * 1000, str(e)[:50])


def test_data_structures():
    """数据模型序列化性能测试"""
    print_header("数据模型序列化测试")

    # Skill 序列化
    s = Skill(
        name="测试技能",
        description="测试描述",
        system_prompt="你是一个测试助手。" * 20,
        creator_id="test",
        creator_name="测试",
        tags=["test", "benchmark", "performance"],
    )
    t0 = time.perf_counter()
    for _ in range(100):
        d = s.to_dict()
    t1 = time.perf_counter()
    record("Skill.to_dict() × 100", True, (t1 - t0) * 1000)

    # Skill 反序列化
    d = s.to_dict()
    t0 = time.perf_counter()
    for _ in range(100):
        s2 = Skill.from_dict(d)
    t1 = time.perf_counter()
    record("Skill.from_dict() × 100", True, (t1 - t0) * 1000)


async def test_rag_search():
    """RAG 检索性能测试（如果有向量库）"""
    print_header("RAG 检索测试（可选）")
    try:
        from engines.frugal_rag import frugal_rag
        from db.milvus_client import vector_db

        count = vector_db.count("netlearn_kb")
        if count == 0:
            record("RAG 检索", False, 0, "向量库为空，跳过")
            return

        t0 = time.perf_counter()
        chunks = await frugal_rag.retrieve("TCP三次握手的工作原理", top_k=3)
        t1 = time.perf_counter()
        record("RAG 检索（top_k=3）", True, (t1 - t0) * 1000, f"chunks={len(chunks) if chunks else 0}")

        t0 = time.perf_counter()
        chunks = await frugal_rag.retrieve("什么是IP地址", top_k=5)
        t1 = time.perf_counter()
        record("RAG 检索（top_k=5）", True, (t1 - t0) * 1000, f"chunks={len(chunks) if chunks else 0}")

    except Exception as e:
        record("RAG 检索", False, 0, str(e)[:50])


async def test_skill_agent():
    """技能 Agent 构造性能测试"""
    print_header("技能 Agent 测试")
    from agents.skill_agent import SkillAgent

    # 准备测试技能
    s = Skill(name="Agent测试", description="测试", system_prompt="你是一个测试助手。", creator_id="test", creator_name="test")
    created = create_skill(s)

    # 构造 Agent（不实际调用 LLM）
    t0 = time.perf_counter()
    agent = SkillAgent(created.id)
    t1 = time.perf_counter()
    record("SkillAgent 构造", True, (t1 - t0) * 1000)

    delete_skill(created.id)


# ── 主入口 ──


async def main():
    print("=" * 60)
    print("  MARS-408 性能基准测试")
    print(f"  时间: {RESULTS['timestamp']}")
    print("=" * 60)

    # 存储层测试
    test_skill_store()

    # 数据模型测试
    test_data_structures()

    # Agent 测试
    await test_skill_agent()

    # RAG 测试
    await test_rag_search()

    # LLM 测试
    await test_llm_basic()

    # 输出摘要
    print(f"\n{'='*60}")
    print(f"  测试结果摘要")
    print(f"{'='*60}")
    s = RESULTS["summary"]
    print(f"  总测试: {s['total']}")
    print(f"  通过: {s['passed']} ✅")
    print(f"  失败: {s['failed']} ❌")
    pass_rate = s["passed"] / s["total"] * 100 if s["total"] > 0 else 0
    print(f"  通过率: {pass_rate:.1f}%")
    print(f"{'='*60}")

    # 保存结果
    result_path = os.path.join(os.path.dirname(__file__), "..", "docs", "benchmark-results.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {result_path}")


if __name__ == "__main__":
    asyncio.run(main())