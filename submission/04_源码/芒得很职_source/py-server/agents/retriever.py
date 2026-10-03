# ============================================================
# 检索优化 Agent (Retriever)
# 调用 FrugalRAG 引擎检索相关知识
# ============================================================

import logging

from agents.state import AgentState
from engines.frugal_rag import frugal_rag, format_retrieval_for_llm

logger = logging.getLogger("netlearn.retriever")


async def retriever_node(state: AgentState) -> AgentState:
    """检索 Agent：调用 FrugalRAG 获取知识库内容"""
    state["status"] = "retrieving"
    state["current_agent"] = "retriever"

    # 构造查询：主题 + 规划内容
    topic = state.get("topic_label") or state.get("topic", "")
    plan = state.get("plan", {})
    course = state.get("course", "computer_network")

    # 丰富查询
    query_parts = [topic]
    if plan.get("teacher_task"):
        query_parts.append(plan["teacher_task"][:100])
    query = " ".join(query_parts)

    # L1/L2/L3 三层学情记忆：薄弱知识点加入检索查询（个性化检索增强，低侵入）
    memory_context = state.get("memory_context") or ""
    weak_terms = []
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        # 从记忆上下文中提取薄弱/未掌握关键词（简单正则，失败不影响主流程）
        import re as _re
        _weak_block = _re.search(r"薄弱[：:]\s*(.+?)(?:\n|$)", memory_context)
        if _weak_block:
            weak_terms = [w.strip() for w in _weak_block.group(1).split(",") if w.strip()]
    weak_terms = weak_terms[:3]
    if weak_terms:
        query = f"{query} {' '.join(weak_terms)}"

    logger.info(f"FrugalRAG 检索: course={course}, query_len={len(query)}")

    try:
        chunks = await frugal_rag.retrieve(query, course=course)
        state["retrieved_chunks"] = chunks

        if chunks:
            logger.info(f"检索到 {len(chunks)} 个知识点片段")
        else:
            # 检索空结果 → 在节点内自增重试计数。
            # 注意：LangGraph 路由函数是纯函数，对 state 的修改不会持久化，
            # 必须在节点里自增并通过返回值传回，否则 route_after_retriever 读到的永远是 0 → 死循环。
            r = state.get("regenerate_round", 0)
            state["regenerate_round"] = r + 1
            logger.warning(f"未检索到相关知识: {topic} (第{r}轮)")

    except Exception as e:
        logger.error(f"FrugalRAG 检索失败: {e}")
        state["retrieved_chunks"] = []
        state["error"] = f"检索失败: {e}"
        # 同样在节点内自增，避免路由函数修改不生效
        r = state.get("regenerate_round", 0)
        state["regenerate_round"] = r + 1

    return state
