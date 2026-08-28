# ============================================================
# AgentState — LangGraph 共享状态定义
# ============================================================

from typing import TypedDict, Optional, Annotated, Sequence
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """LangGraph 共享状态，所有 Agent 节点读写此状态"""

    # ── 用户输入 ──
    messages: Annotated[list, add_messages]
    user_request: str                   # 用户原始请求
    student_profile: dict               # 学生画像 {knowledge_base, learning_style, goal, weak_points, progress, interest_area, study_time, preferred_difficulty}
    memory_context: Optional[str]       # L1/L2/L3 三层学情记忆上下文（memory_service 组装，低侵入注入）
    topic: str                          # 学习主题
    difficulty: str                     # easy / medium / hard
    course: str                         # 课程 data_structures / computer_network / ...

    # ── 诊断结果 ──
    diagnosis: Optional[dict]           # 学情诊断 ：{weak_areas, recommended_focus, ...}

    # ── 规划结果 ──
    plan: Optional[dict]                # 任务规划 ：{topic_label, chapter, teacher_task, quiz_task, ...}
    topic_label: Optional[str]
    chapter: Optional[str]

    # ── 检索结果 ──
    retrieved_chunks: Optional[list[dict]]  # FrugalRAG 检索到的知识点

    # ── 生成结果（并行 7 个资源 Agent）──
    teacher_doc: Optional[str]           # 讲解文档 Agent
    quiz: Optional[str]                  # 题库生成 Agent
    media_plan: Optional[str]            # 多媒体方案 Agent（保留兼容）
    extension: Optional[str]             # 拓展阅读 Agent
    mindmap: Optional[dict]             # 思维导图 Agent {mermaid, json, markdown, weak_points, stats}
    code_practice: Optional[str]        # 代码实操 Agent
    ppt_outline: Optional[str]          # PPT大纲 Agent
    video_script: Optional[str]         # 多模态视频脚本 Agent（Lite降级版）
    ppt_file: Optional[dict]            # 真实 .pptx 文件（ppt_builder 生成）
    video_file: Optional[dict]          # 真实数字人视频（media_generator.generate_real_video 生成，P1-5②）

    # ── 共识结果 ──
    consensus: Optional[dict]           # GOMARL 共识输出 {status, scores, pre_assessment, ...}
    critic_report: Optional[str]        # 审阅 Agent 报告

    # ── 路径规划结果 ──
    path_plan: Optional[dict]            # 个性化学习路径 {current_chapter, next_chapter, weak_focus_chapters, ...}

# ── 证据校验结果（INC-01：evidence_check 节点写入）──
    evidence_report: Optional[dict]      # 证据校验结果（INC-01：evidence_check 节点写入）{status, consistency_score, conflicts, ...}

    # ── 产物验收闸门结果 ──
    gate_result: Optional[dict]         # {verdict, reasons, hard_failures, soft_failures, consistency_score, gate_retry_count}
    gate_verdict: str                   # "pass" | "fix" | "reject"
    gate_reasons: list[str]             # 闸门决策原因
    gate_retry_count: int               # 闸门重试计数（独立于 regenerate_round）
    gate_passed: bool                   # 闸门是否通过（fail-open 降级时也为 True）

    # ── 控制流 ──
    current_agent: str                  # 当前执行的 Agent 名称
    error: Optional[str]                # 错误信息
    status: str                         # "planning" | "diagnosing" | "retrieving" | "generating" | "assessing" | "path_planning" | "consensus" | "reviewing" | "done"
    regenerate_round: int               # 当前重生成轮数
