# ============================================================
# LangGraph StateGraph — 多智能体编排（10 节点）
#
# 节点顺序:
#   coordinator → diagnostician → planner → retriever
#   → generator_cluster → assessor → critic
#   → evidence_check → quality_gate → [PASS] → path_planner → END
#                                    → [FIX]  → generator_cluster (重试)
#                                    → [REJECT] → END
#
# 10 节点 (7种角色 + evidence_check + quality_gate + 1辅助PathPlanner):
#   全局协调(coordinator)、学情诊断(diagnostician)、任务规划(planner)、检索优化(retriever)、
#   资源生成集群(generator_cluster: 7个并行子Agent)、评估反馈(assessor)、
#   质量校验(critic)、证据校验(evidence_check)、产物验收闸门(quality_gate)、路径规划(path_planner)
#
# generator_cluster 内含 7 个并行资源 Agent:
#   Teacher(讲解文档) / QuizMaster(题库) / MindMap(思维导图4步流水线) /
#   Extension(拓展阅读) / CodePractice(代码实操) / PPT(PPT大纲) / VideoScript(视频脚本Lite)
#
# 独立 Agent (不在图中, API层按需调用):
#   Tutor(智能答疑) — 功能④加分项
# ============================================================

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.coordinator import coordinator_node
from agents.diagnostician import diagnostician_node
from agents.planner import planner_node
from agents.retriever import retriever_node
from agents.generator_cluster import generator_cluster_node
from agents.assessor import assessor_node
from agents.critic import critic_node
from agents.path_planner import path_planner_node
from agents.evidence_check import evidence_check_node
from agents.quality_gate import quality_gate_node, route_after_quality_gate

# 最大生成轮数（含首次）：读 config.gomarl.max_regenerate_rounds。
# 1 = 仅 1 次生成、Critic 不触发重试（提速，避免多轮打磨拖到数分钟）；
# 2 = 允许 1 次 Critic 重试（共 2 次生成）。路由比较 regenerate_round < 此值。
try:
    from config import get_gomarl_config
    _MAX_CRITIC_RETRIES = int(get_gomarl_config().get("max_regenerate_rounds", 1))
except Exception:
    _MAX_CRITIC_RETRIES = 1

logger = logging.getLogger("netlearn.graph")

# ── 路由函数（条件边）──

def route_after_retriever(state: AgentState) -> Literal["generator_cluster", "planner"]:
    """检索后：有结果 → 生成；无结果 → 重新规划（可能主题不明确）"""
    if state.get("retrieved_chunks") and len(state["retrieved_chunks"]) > 0:
        return "generator_cluster"

    # 检索结果为空，检查重试次数（regenerate_round 由 retriever 节点自增，路由函数只读不写）
    r = state.get("regenerate_round", 0)
    if r < 2:
        logger.info(f"检索为空，第{r}次重试规划")
        return "planner"

    # 重试耗尽，继续（无参考知识）
    logger.warning(f"检索结果为空，已尝试{r}次，继续生成（无参考知识）")
    return "generator_cluster"


def route_after_critic(state: AgentState) -> Literal["retriever", "evidence_check", "path_planner"]:
    """审阅后：通过 → 证据校验；需要改进 → 重新检索；超限 → 路径规划（降级通过）"""
    consensus = state.get("consensus", {})
    status = consensus.get("status", "unknown")  # 与 quality_gate 保持一致，缺失时降级通过
    r = state.get("regenerate_round", 0)

    if status == "passed":
        return "evidence_check"

    if status in ("regenerate", "flagged"):
        # regenerate_round 由 critic 节点自增（首次生成后=1），路由函数只读不写。
        # 比较 regenerate_round < _MAX_CRITIC_RETRIES：值为 1 时首次审阅后即降级通过（仅 1 轮产出）。
        if r < _MAX_CRITIC_RETRIES:
            logger.info(f"Critic审阅未通过，第{r}次重试检索")
            return "retriever"

    # 重试耗尽或状态未知，降级通过走路径规划
    logger.warning(f"审阅重试耗尽或未知状态: status={status}, round={r}, 降级通过")
    return "path_planner"


# ── 图构建 ──

def create_agent_graph() -> StateGraph:
    """构建 10 节点 LangGraph 状态图（7种角色 + evidence_check + quality_gate + 1辅助PathPlanner）"""
    workflow = StateGraph(AgentState)

    # 添加节点（7种角色 + evidence_check + quality_gate + 1辅助PathPlanner = 10节点）
    workflow.add_node("coordinator", coordinator_node)       # 全局协调
    workflow.add_node("diagnostician", diagnostician_node)   # 学情诊断
    workflow.add_node("planner", planner_node)               # 任务规划
    workflow.add_node("retriever", retriever_node)           # 检索优化
    workflow.add_node("generator_cluster", generator_cluster_node)  # 资源生成集群
    workflow.add_node("assessor", assessor_node)             # 评估反馈
    workflow.add_node("critic", critic_node)                 # 质量校验
    workflow.add_node("evidence_check", evidence_check_node)  # 证据校验（INC-01，critic 后）
    workflow.add_node("quality_gate", quality_gate_node)       # 产物验收闸门（硬性阻断）
    workflow.add_node("path_planner", path_planner_node)     # 路径规划

    # 入口
    workflow.set_entry_point("coordinator")

    # 边 — 主流程
    workflow.add_edge("coordinator", "diagnostician")
    workflow.add_edge("diagnostician", "planner")
    workflow.add_edge("planner", "retriever")

    # 检索后的条件分支
    workflow.add_conditional_edges(
        "retriever",
        route_after_retriever,
        {"generator_cluster": "generator_cluster", "planner": "planner"},
    )

    # 生成 → 评估 → 审阅（三段式质量保障）
    workflow.add_edge("generator_cluster", "assessor")
    workflow.add_edge("assessor", "critic")

    # 审阅后的条件分支：通过 → 路径规划，需改进 → 重新检索
    workflow.add_conditional_edges(
        "critic",
        route_after_critic,
        {"retriever": "retriever", "evidence_check": "evidence_check", "path_planner": "path_planner"},
)
    # 证据校验 → 产物验收闸门（替代原 evidence_check → path_planner 硬连线）
    workflow.add_edge("evidence_check", "quality_gate")

    # 闸门后的条件分支：PASS → 路径规划, FIX → 重新生成, REJECT → END
    workflow.add_conditional_edges(
        "quality_gate",
        route_after_quality_gate,
        {
            "path_planner": "path_planner",
            "generator_cluster": "generator_cluster",
            "__end__": END,
        },
    )

    # 路径规划 → END（完成输出）
    workflow.add_edge("path_planner", END)

    return workflow.compile()


# ── 全局实例 ──

agent_graph = create_agent_graph()
