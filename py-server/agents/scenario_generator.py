# ============================================================
# scenario_generator — 芒得很职·场景自动生成器（对标 HireVue Builder）
#
# 从「岗位方向（前端/后端/算法/产品/运维）× 情景类型」自动生成
# scenario + rubric(bars_anchor) + probe_tree，产出物结构对齐
# app_config/career_scenarios.json 的 scenario 结构，人工审核后入库。
#
# 4 个手写种子保留为「黄金样本」（不参与生成），生成器产出的是**新**情景，
# 模板内容刻意与黄金样本（毕设开题答辩/需求评审加需求/线上故障应急/代码评审冲突）区分。
#
# 诚实边界：规则兜底模板是**静态方法论素材**，不是 LLM 幻觉产物；
# LLM 路径失败/非法时完整回退模板，保证无 LLM 环境可闭环、可离线测试。
# ============================================================

import json
import logging
import uuid
from typing import Optional

from agents.career_state import (
    DIMENSIONS, SCENARIO_TYPES, SCENARIO_TYPE_LABELS,
)
from prompts_career import SCENARIO_GEN_SYSTEM, SCENARIO_GEN_USER_TMPL

logger = logging.getLogger("netlearn.career.scenario_gen")

RUBRIC_VERSION = "1.0"  # 生成场景的 rubric 版本（与回溯重评⑤联动）

# ── 岗位方向模板库（规则兜底；结构对齐 career_scenarios.json 的 scenario）──
# 每个方向：label / scenario_type / subtype / title / setting / 角色 / 开场 / 追问 / 权重 / 重点 / BARS
_JOB_TEMPLATES: dict = {
    "frontend": {
        "label": "前端开发",
        "scenario_type": "review",
        "subtype": "前端体验与工期冲突",
        "title": "迭代评审：产品要求上线高级动效与无障碍适配，工期不变",
        "setting": (
            "你是一家互联网公司的前端开发实习生。迭代评审会上，产品经理坚持本迭代必须上线"
            "一套高级动效与无障碍（a11y）适配，理由是竞品都有、老板很看重，但交付时间不变、"
            "只剩一周。你评估这套改动至少要两周。团队成员都在等你表态。"
        ),
        "student_role": "实习前端开发",
        "interviewer_role": "强势的产品经理（坚持体验必须按期上线，会用竞品与老板施压）",
        "opening_question": "竞品这周都上线动效了，老板点名要这个效果，无障碍适配也得有，你一周内必须交付，没问题吧？",
        "probe_tree": [
            "用老板/竞品施压，要求无条件接下全部需求",
            "质疑你是不是技术不行、故意拖延",
            "要求当场给出可交付的功能切分与排期",
            "提出砍测试、先上线再补的折中方案试探底线",
            "若你提出分期/MVP，追问为什么这对业务与体验更优",
        ],
        "dimension_weights": {"expression": 0.12, "stress": 0.20, "decompose": 0.20, "collab": 0.24, "presentation": 0.10, "problem_solving": 0.14},
        "focus_points": [
            "用可演示的功能切分替代情绪化拒绝",
            "给出 MVP/分期等建设性替代方案",
            "守住质量底线（无障碍/性能）与工期现实",
            "对事不对人、先对齐诉求再谈排期",
        ],
        "bars_anchor": {
            "collab": {"1": "一味顺从或直接顶撞", "3": "表达了困难但缺少方案", "5": "换位思考+数据说话+给出共赢选项"},
            "problem_solving": {"1": "只说做不到", "3": "提出简单折中", "5": "给出可落地的分期/MVP方案与风险说明"},
        },
    },
    "backend": {
        "label": "后端开发",
        "scenario_type": "incident",
        "subtype": "接口性能事故应急",
        "title": "线上事故：核心查询接口慢查询拖垮数据库，业务方追问",
        "setting": (
            "你是值班后端开发，深夜收到告警：一个核心查询接口从几十毫秒飙升到十几秒，"
            "数据库连接池被打满，多个下游业务方在群里反馈超时。你初步怀疑是近期上线的一个"
            "新接口引入了未加索引的大表查询，但根因尚未完全定位，必须边排查边同步。"
        ),
        "student_role": "值班后端开发（现场处置第一责任人）",
        "interviewer_role": "焦急的技术主管（连续追问影响面、根因、恢复时间，需要清晰结论）",
        "opening_question": "现在到底什么情况？影响多少用户？是哪个接口、哪条 SQL 的问题？多久能恢复？",
        "probe_tree": [
            "在信息不全时要求立刻下结论并给恢复时间",
            "追问是不是最近那次上线引入的、谁的责任",
            "要求当场给出应急止血方案（限流/回滚/加索引）",
            "业务方施压要求立刻回滚，需判断利弊",
            "若排查指向自己上次提交，观察担责与复盘意识",
        ],
        "dimension_weights": {"expression": 0.14, "stress": 0.26, "decompose": 0.18, "collab": 0.12, "presentation": 0.14, "problem_solving": 0.16},
        "focus_points": [
            "高压下结构化同步（现象/影响/动作/时间点）",
            "区分事实与猜测、不盲目承诺",
            "应急止血优先级与回滚/限流决策",
            "担责与复盘意识",
        ],
        "bars_anchor": {
            "stress": {"1": "慌乱、甩锅或沉默", "3": "能回应但条理一般", "5": "高压下仍稳定、结构化推进处置"},
            "problem_solving": {"1": "只说在查、无头绪", "3": "能给出止血方向", "5": "给出止血+根因+验证的完整路径与风险"},
        },
    },
    "algorithm": {
        "label": "算法工程师",
        "scenario_type": "defense",
        "subtype": "算法方案评审答辩",
        "title": "算法评审：你的推荐方案被质疑效果与上线价值",
        "setting": (
            "你是算法实习生，正在向业务与评审方汇报一个推荐排序优化方案。评审中，一位"
            "资深评委连续质疑：离线指标提升到底有没有业务价值、A/B 实验设计是否科学、"
            "训练成本是否划算，并怀疑你只是套了开源模型没有真正的优化。"
        ),
        "student_role": "算法方案汇报人",
        "interviewer_role": "严苛的算法评委（关注效果归因、实验严谨性与落地价值）",
        "opening_question": "你这个方案离线 AUC 涨了 2 个点，但你凭什么说这 2 个点能带来真实业务收益？实验怎么设计的？",
        "probe_tree": [
            "质疑离线指标的线上归因与业务价值",
            "追问 A/B 实验设计、样本量与显著性",
            "质疑只是套开源模型、无实质创新",
            "要求量化训练成本与收益的投入产出比",
            "若方案被否，要求现场辩护或调整方向",
        ],
        "dimension_weights": {"expression": 0.22, "stress": 0.16, "decompose": 0.20, "collab": 0.08, "presentation": 0.18, "problem_solving": 0.16},
        "focus_points": [
            "用业务口径论证指标价值而非只报数字",
            "实验设计的严谨性与风险预案",
            "把技术方案拆成可验证的阶段目标",
            "面对否定时的情绪稳定与有理有据回应",
        ],
        "bars_anchor": {
            "expression": {"1": "逻辑混乱、只报数字不解释", "3": "结构基本清楚但有跳跃", "5": "结论先行、层层递进、业务与技术衔接严密"},
            "decompose": {"1": "只给结论不给路径", "3": "有阶段划分但粗糙", "5": "拆成可验证子目标+风险预案+投入产出"},
        },
    },
    "product": {
        "label": "产品经理",
        "scenario_type": "conflict",
        "subtype": "需求优先级冲突协调",
        "title": "优先级冲突：技术同学认为你的需求价值存疑且排期不合理",
        "setting": (
            "你是产品经理（学生角色），要推动一个新功能上线。开发同学在评审会上公开质疑："
            "这个功能没有明确的数据支撑、场景想当然，而且排期压缩得太紧，是在用大家的"
            "时间赌一个没验证过的方向。团队气氛紧张，老板要求下周给出结论。"
        ),
        "student_role": "负责该功能的产品经理",
        "interviewer_role": "质疑需求价值的开发同学（要求数据说话、拒绝拍脑袋排期）",
        "opening_question": "你这个需求连一个能验证的假设都讲不清楚，凭什么让我们两周全扑上去？你有数据吗？",
        "probe_tree": [
            "要求用数据/用户反馈证明需求价值",
            "质疑排期压缩是不尊重研发成本",
            "要求说明如何验证、失败了怎么办",
            "若你坚持，要求给出最小可行验证路径",
            "观察能否在不伤关系的前提下对齐目标",
        ],
        "dimension_weights": {"expression": 0.16, "stress": 0.14, "decompose": 0.16, "collab": 0.28, "presentation": 0.12, "problem_solving": 0.14},
        "focus_points": [
            "用数据/假设验证替代主观坚持",
            "对事不对人、先肯定技术同学的顾虑",
            "给出最小可行验证（MVP/试点）而非全量押注",
            "维护团队关系与共同目标",
        ],
        "bars_anchor": {
            "collab": {"1": "升级争吵或强行压排期", "3": "就事论事但忽略对方情绪", "5": "先处理情绪再对齐目标、达成双方接受的验证方案"},
            "problem_solving": {"1": "拿不出任何验证思路", "3": "提出简单试点", "5": "给出可验证假设+最小验证路径+失败预案"},
        },
    },
    "ops": {
        "label": "运维/SRE",
        "scenario_type": "incident",
        "subtype": "发布事故应急通报",
        "title": "发布事故：灰度发布触发大面积报错，需要立刻决策回滚还是修复",
        "setting": (
            "你是负责本次发布的运维/SRE，凌晨灰度发布一个新版本，刚开始 5% 流量就出现"
            "大面积报错，错误率飙升。业务方在群里催促，老板要求立刻给结论。你掌握的信息"
            "有限：是回滚最快但会丢部分新功能，还是继续查根因修复但恢复时间不确定。"
        ),
        "student_role": "值班 SRE（发布决策第一责任人）",
        "interviewer_role": "焦急的老板/业务方（要你立刻决定回滚还是修复，并给恢复时间）",
        "opening_question": "别跟我讲技术细节，我就问一句：现在回滚还是修？多久能好？你担不担得起这个责任？",
        "probe_tree": [
            "要求立刻在信息不全时拍板回滚或修复",
            "追问为什么不提前发现、发布流程是否规范",
            "要求给出明确恢复时间承诺",
            "追问回滚会丢哪些功能、对业务影响多大",
            "观察高压下的责任担当与结构化决策",
        ],
        "dimension_weights": {"expression": 0.14, "stress": 0.28, "decompose": 0.16, "collab": 0.12, "presentation": 0.14, "problem_solving": 0.16},
        "focus_points": [
            "高压下结构化同步（现象/影响/动作/时间点）",
            "回滚 vs 修复的利弊与决策依据",
            "区分事实与猜测、不盲目承诺",
            "责任担当与复盘意识",
        ],
        "bars_anchor": {
            "stress": {"1": "慌乱、甩锅或沉默", "3": "能回应但条理一般", "5": "高压下仍稳定、结构化推进处置并明确担责"},
            "presentation": {"1": "术语堆砌、领导听不懂", "3": "基本说清现状", "5": "用非技术方也能懂的语言给结论与预期"},
        },
    },
}

# 岗位方向 label 映射（供前端下拉）
JOB_DIRECTION_LABELS = {k: v["label"] for k, v in _JOB_TEMPLATES.items()}

# 六维默认权重（生成器模板未覆盖时兜底；LLM 输出若缺失也用此）
_DEFAULT_WEIGHTS = {
    "expression": 0.15, "stress": 0.15, "decompose": 0.20,
    "collab": 0.20, "presentation": 0.15, "problem_solving": 0.15,
}


def list_job_directions() -> list[dict]:
    """返回可选岗位方向（含默认情景类型），供前端/调用方展示。"""
    return [
        {"key": k, "label": v["label"], "default_scenario_type": v["scenario_type"]}
        for k, v in _JOB_TEMPLATES.items()
    ]


def _norm_weights(weights: Optional[dict]) -> dict:
    """规整维度权重：只保留合法维度、数值化、缺省补默认；不强制归一（保持生成语义）。"""
    out = {}
    for d in DIMENSIONS:
        raw = (weights or {}).get(d)
        try:
            out[d] = float(raw) if raw is not None else _DEFAULT_WEIGHTS[d]
        except (TypeError, ValueError):
            out[d] = _DEFAULT_WEIGHTS[d]
    return out


def _norm_bars_anchor(bars: Optional[dict]) -> dict:
    """规整 BARS 锚点：只保留合法维度且含 1/3/5 三档的条目。"""
    out = {}
    for d, levels in (bars or {}).items():
        if d not in DIMENSIONS or not isinstance(levels, dict):
            continue
        ok = {k: levels.get(k) for k in ("1", "3", "5") if levels.get(k)}
        if len(ok) >= 2:  # 至少两档才算有效锚点，否则丢弃
            out[d] = ok
    return out


def build_scenario_from_template(job_direction: str, scenario_type: str,
                                 difficulty: str = "medium") -> dict:
    """规则兜底：从岗位方向模板组装一份完整 scenario（结构对齐 career_scenarios.json）。

    产出的 id 带随机后缀，避免与黄金样本/历史生成冲突；rubric_version 固定。
    """
    tpl = _JOB_TEMPLATES.get(job_direction)
    if not tpl:
        raise ValueError(f"未知岗位方向: {job_direction}")
    stype = scenario_type if scenario_type in SCENARIO_TYPES else tpl["scenario_type"]
    suffix = uuid.uuid4().hex[:8]
    return {
        "id": f"gen_{job_direction}_{stype}_{suffix}",
        "type": stype,
        "subtype": tpl["subtype"],
        "type_label": SCENARIO_TYPE_LABELS.get(stype, stype),
        "subtype_label": tpl["subtype"],
        "title": tpl["title"],
        "difficulty_default": difficulty if difficulty in ("easy", "medium", "hard") else "medium",
        "setting": tpl["setting"],
        "student_role": tpl["student_role"],
        "interviewer_role": tpl["interviewer_role"],
        "opening_question": tpl["opening_question"],
        "probe_tree": list(tpl["probe_tree"]),
        "dimension_weights": _norm_weights(tpl.get("dimension_weights")),
        "focus_points": list(tpl["focus_points"]),
        "bars_anchor": _norm_bars_anchor(tpl.get("bars_anchor")),
        "rubric_version": RUBRIC_VERSION,
        "generated": True,
        "job_direction": job_direction,
    }


async def generate_scenario(job_direction: str, scenario_type: str,
                            difficulty: str = "medium") -> dict:
    """生成场景入口：LLM 增强，失败/非法完整回退模板。

    返回完整 scenario dict（含 generated=True 与 job_direction），结构对齐黄金样本。
    权重与 BARS 一律走规整函数（LLM 不得产出非法维度/缺失三档的锚点）。
    """
    if job_direction not in _JOB_TEMPLATES:
        raise ValueError(f"未知岗位方向: {job_direction}")
    stype = scenario_type if scenario_type in SCENARIO_TYPES else _JOB_TEMPLATES[job_direction]["scenario_type"]
    tpl = _JOB_TEMPLATES[job_direction]
    fallback = build_scenario_from_template(job_direction, stype, difficulty)

    user = SCENARIO_GEN_USER_TMPL.format(
        job_label=tpl["label"],
        type_label=SCENARIO_TYPE_LABELS.get(stype, stype),
        difficulty=difficulty if difficulty in ("easy", "medium", "hard") else "medium",
    )
    try:
        from db.llm_provider import LLMProvider
        llm = LLMProvider()
        raw = await llm.text_completion(SCENARIO_GEN_SYSTEM, user, temperature=0.8, max_tokens=1200)
        data = _extract_json(raw)
        if isinstance(data, dict) and data.get("title") and data.get("setting"):
            # 组装：结构字段来自模板（type/subtype_label 等），内容字段优先 LLM，缺失回退模板
            merged = {
                "id": fallback["id"],
                "type": stype,
                "subtype": (data.get("subtype") or tpl["subtype"]),
                "type_label": SCENARIO_TYPE_LABELS.get(stype, stype),
                "subtype_label": (data.get("subtype") or tpl["subtype"]),
                "title": data.get("title") or tpl["title"],
                "difficulty_default": difficulty if difficulty in ("easy", "medium", "hard") else "medium",
                "setting": data.get("setting") or tpl["setting"],
                "student_role": data.get("student_role") or tpl["student_role"],
                "interviewer_role": data.get("interviewer_role") or tpl["interviewer_role"],
                "opening_question": data.get("opening_question") or tpl["opening_question"],
                "probe_tree": [p for p in (data.get("probe_tree") or []) if isinstance(p, str) and p.strip()] or list(tpl["probe_tree"]),
                "dimension_weights": _norm_weights(data.get("dimension_weights") or tpl.get("dimension_weights")),
                "focus_points": [p for p in (data.get("focus_points") or []) if isinstance(p, str) and p.strip()] or list(tpl["focus_points"]),
                "bars_anchor": _norm_bars_anchor(data.get("bars_anchor") or tpl.get("bars_anchor")),
                "rubric_version": RUBRIC_VERSION,
                "generated": True,
                "job_direction": job_direction,
            }
            return merged
        logger.warning("场景生成 JSON 解析失败，使用模板兜底")
    except Exception as e:
        logger.warning(f"场景生成失败，使用模板兜底: {e}")
    return fallback


def _extract_json(text: str):
    """从 LLM 输出稳健提取 JSON 对象（复用 career_nodes.extract_json 的语义，避免反向依赖）。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None
