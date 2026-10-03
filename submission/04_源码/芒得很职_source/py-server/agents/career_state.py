# ============================================================
# CareerState — 芒得很职·职业素养对抗实训 共享状态与领域常量
#
# 与 408 的 agents/state.py 完全独立，互不影响（双图并存）。
# P0 采用「API 持状态、节点无状态逐轮调用」的简化方案：
#   状态在一轮轮对话间由 db/career_store.py 持久化到 career_sessions，
#   本文件的 CareerState 仅作为节点函数之间传参的内存字典约定。
# ============================================================

from typing import TypedDict, Optional

# ── 6 维软素养（评估维度，全程统一英文 key，中文展示名走 DIMENSION_LABELS）──
DIMENSIONS = [
    "expression",       # 表达逻辑
    "stress",           # 抗压应变
    "decompose",        # 方案拆解
    "collab",           # 协作沟通
    "presentation",     # 技术汇报
    "problem_solving",  # 问题解决
]

DIMENSION_LABELS = {
    "expression": "表达逻辑",
    "stress": "抗压应变",
    "decompose": "方案拆解",
    "collab": "协作沟通",
    "presentation": "技术汇报",
    "problem_solving": "问题解决",
}

DIMENSION_HINTS = {
    "expression": "条理是否清晰、论点是否有结构、有无逻辑跳跃、结论是否明确",
    "stress": "面对质疑/突发/高压追问时是否镇定、能否快速组织有效回应",
    "decompose": "能否把复杂问题拆成有优先级的子问题、识别关键约束与取舍",
    "collab": "能否换位思考、对齐诉求、推进共识，而非对抗或一味妥协",
    "presentation": "技术表达是否准确、能否用对方听得懂的方式讲清方案与权衡",
    "problem_solving": "是否给出可落地的解决路径、是否考虑风险与备选方案",
}

# ── 4 大类情景（每类先做 1 个高质量种子，共 4 个跑通最窄闭环）──
SCENARIO_TYPES = ["defense", "review", "incident", "conflict"]
SCENARIO_TYPE_LABELS = {
    "defense": "技术方案答辩",
    "review": "需求评审质询",
    "incident": "故障排查沟通",
    "conflict": "团队冲突协调",
}

# ── 对抗模式（normal 常规 / escalating 加压 / catfish 鲶鱼）──
ADVERSARY_MODES = ["normal", "escalating", "catfish"]
ADVERSARY_MODE_LABELS = {
    "normal": "常规追问",
    "escalating": "逐步加压",
    "catfish": "鲶鱼反诘",
}

DIFFICULTIES = ["easy", "medium", "hard"]
DEFAULT_MAX_TURNS = 8       # 默认对抗轮数
MIN_TURNS = 4               # 少于该轮数不允许评估（证据不足）
CATFISH_MAX_CONTINUE = 2    # 鲶鱼加压最多连续 2 轮即回到 normal


class CareerState(TypedDict, total=False):
    """一次对抗实训在内存中的状态约定（total=False：字段按需出现）"""

    # —— 会话标识 ——
    session_id: str
    user_id: str
    task_id: Optional[str]            # 教师任务（自主练习为空）

    # —— 场景配置 ——
    scenario_type: str                # defense/review/incident/conflict
    scenario_subtype: str
    difficulty: str                   # easy/medium/hard
    max_turns: int

    # —— 画像（P0 用中性先验，P1 接对话式画像）——
    initial_profile: dict

    # —— 情景脚本（scenario_planner 产出）——
    scenario_script: dict
    # {setting, student_role, interviewer_role, opening_question,
    #  probe_tree, dimension_weights, focus_points}

    # —— 多轮对抗（核心）——
    dialogue_turns: list[dict]
    # 每轮 {turn_index, mode, question, answer, evidence, probe_dimension, ts}
    current_turn: int
    adversary_mode: str
    catfish_triggered: bool
    catfish_continuous: int

    # —— 评估产出 ——
    dimension_scores: dict            # 6 维分(1-5)+置信度+证据 turn 引用
    evidence_chain: list[dict]        # 分→证据绑定
    consistency_score: Optional[float]
    assessment_report: dict
    improvement_plan: dict

    # —— 控制 ——
    status: str                       # ongoing/finished/abandoned
    error: Optional[str]


def new_state(session_id: str, user_id: str, scenario_type: str,
              scenario_subtype: str = "", difficulty: str = "medium",
              max_turns: int = DEFAULT_MAX_TURNS, task_id: Optional[str] = None) -> CareerState:
    """构造一份带中性先验的初始状态"""
    return CareerState(
        session_id=session_id,
        user_id=user_id,
        task_id=task_id,
        scenario_type=scenario_type,
        scenario_subtype=scenario_subtype,
        difficulty=difficulty,
        max_turns=max_turns,
        initial_profile={d: None for d in DIMENSIONS},  # None=尚无证据
        scenario_script={},
        dialogue_turns=[],
        current_turn=0,
        adversary_mode="normal",
        catfish_triggered=False,
        catfish_continuous=0,
        dimension_scores={},
        evidence_chain=[],
        consistency_score=None,
        assessment_report={},
        improvement_plan={},
        status="ongoing",
        error=None,
    )
