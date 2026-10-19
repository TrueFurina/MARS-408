# ============================================================
# career_nodes — 芒得很职·对抗实训 LLM 节点（无状态、可逐轮调用）
#
# P0 简化方案：不使用 LangGraph interrupt，节点都是 async 纯函数，
# 由 services/career_service.py 编排、db/career_store.py 持久化。
# 每个节点：强制 JSON 输出 + 解析容错 + LLM 失败安全兜底，保证闭环不崩。
# ============================================================

import json
import logging
import os
from typing import Optional

from agents.career_state import (
    DIMENSIONS, DIMENSION_LABELS, ADVERSARY_MODE_LABELS,
    CATFISH_MAX_CONTINUE,
)
from prompts_career import (
    SCENARIO_SCRIPT_SYSTEM, SCENARIO_SCRIPT_USER_TMPL,
    ADVERSARY_SYSTEM, ADVERSARY_USER_TMPL,
    EVIDENCE_COLLECT_SYSTEM, EVIDENCE_COLLECT_USER_TMPL,
    CAREER_ASSESS_SYSTEM, CAREER_ASSESS_USER_TMPL,
    IMPROVEMENT_SYSTEM, IMPROVEMENT_USER_TMPL,
)

logger = logging.getLogger("netlearn.career.nodes")

# 中文维度名 → 英文 key（防御 LLM 偶尔返回中文维度）
_DIM_CN2KEY = {v: k for k, v in DIMENSION_LABELS.items()}


def norm_dimension(d) -> Optional[str]:
    """把英文 key 或中文维度名统一成英文 key，非法返回 None"""
    if d in DIMENSIONS:
        return d
    return _DIM_CN2KEY.get(d)

_SCENARIO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "app_config", "career_scenarios.json"
)

# 终评（六维 ECD）专用超时：实测免费档 glm-4-flash 单次 64.2s，默认 60s 必超时
# ⇒ 静默退回规则兜底。终评走后台异步，不受发布平台 ~60s 网关超时限制，可放宽。
ASSESS_TIMEOUT = float(os.getenv("CAREER_ASSESS_TIMEOUT", "150"))
IMPROVEMENT_TIMEOUT = float(os.getenv("CAREER_IMPROVEMENT_TIMEOUT", "90"))


# ────────────────────────────────────────────────────────────
# 通用工具
# ────────────────────────────────────────────────────────────
def extract_json(text: str):
    """从 LLM 输出中稳健提取 JSON 对象（优先整体解析，再截取首个{到末个}）。"""
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


def _load_scenario_file() -> dict:
    try:
        with open(_SCENARIO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"情景库读取失败 {_SCENARIO_PATH}: {e}")
        return {"scenarios": []}


def _scenario_display(s: dict) -> dict:
    """从完整 scenario 提取展示字段（黄金样本与生成场景共用同一口径，不泄露完整脚本）"""
    return {
        "id": s["id"], "type": s["type"], "subtype": s.get("subtype", ""),
        "type_label": s.get("type_label", s["type"]),
        "subtype_label": s.get("subtype_label", ""),
        "title": s["title"],
        "difficulty_default": s.get("difficulty_default", "medium"),
    }


def _load_active_generated_scenarios() -> list[dict]:
    """读取 DB 中已审核(active)的生成场景；DB 不可用时返回空（不影响黄金样本）。"""
    try:
        from db import career_store
        return career_store.list_generated_scenarios(status="active")
    except Exception as e:
        logger.warning(f"读取生成场景失败（仅返回黄金样本）: {e}")
        return []


def list_scenarios() -> list[dict]:
    """返回前端可选场景列表（黄金样本 + 已审核生成场景；只给展示字段，不泄露完整脚本）"""
    out = [_scenario_display(s) for s in _load_scenario_file().get("scenarios", [])]
    out += [_scenario_display(s) for s in _load_active_generated_scenarios()]
    return out


def get_scenario(scenario_id: str) -> Optional[dict]:
    """取完整场景：先黄金样本（JSON），再已入库生成场景（DB）。"""
    data = _load_scenario_file()
    for s in data.get("scenarios", []):
        if s["id"] == scenario_id:
            # rubric 版本：场景自身缺省时回退文件顶层（回溯重评⑤的版本来源）
            s.setdefault("rubric_version", data.get("rubric_version", "1.0"))
            return s
    try:
        from db import career_store
        return career_store.get_generated_scenario(scenario_id)
    except Exception:
        return None


# ────────────────────────────────────────────────────────────
# 节点 1：情景脚本生成
# ────────────────────────────────────────────────────────────
async def build_scenario_script(scenario_seed: dict, difficulty: str) -> dict:
    """把情景种子细化为对抗脚本；LLM 失败时用种子兜底（保证可开场）"""
    user = SCENARIO_SCRIPT_USER_TMPL.format(
        title=scenario_seed.get("title", ""),
        setting=scenario_seed.get("setting", ""),
        student_role=scenario_seed.get("student_role", ""),
        interviewer_role=scenario_seed.get("interviewer_role", ""),
        difficulty=difficulty,
        opening=scenario_seed.get("opening_question", ""),
        probe_tree="；".join(scenario_seed.get("probe_tree", [])),
        focus_points="；".join(scenario_seed.get("focus_points", [])),
        weights=json.dumps(scenario_seed.get("dimension_weights", {}), ensure_ascii=False),
        weight_json=json.dumps(scenario_seed.get("dimension_weights", {}), ensure_ascii=False),
    )
    fallback = {
        "setting": scenario_seed.get("setting", ""),
        "student_role": scenario_seed.get("student_role", ""),
        "interviewer_role": scenario_seed.get("interviewer_role", ""),
        "opening_question": scenario_seed.get("opening_question", "请先介绍一下你自己和你目前的方案。"),
        "probe_plan": scenario_seed.get("probe_tree", []),
        "dimension_weights": scenario_seed.get("dimension_weights", {}),
        "bars_anchor": scenario_seed.get("bars_anchor", {}),
        "success_signals": [],
        "template_warnings": [],
    }
    try:
        from db.llm_provider import LLMProvider
        llm = LLMProvider()
        raw = await llm.text_completion(SCENARIO_SCRIPT_SYSTEM, user, temperature=0.6, max_tokens=1200)
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("opening_question"):
            # 权重以种子为准，避免模型乱改
            data["dimension_weights"] = scenario_seed.get("dimension_weights", {})
            # BARS 行为锚点以种子为准（评分量表依据），LLM 不得覆盖/编造
            data["bars_anchor"] = scenario_seed.get("bars_anchor", {})
            return data
        logger.warning("情景脚本 JSON 解析失败，使用种子兜底")
    except Exception as e:
        logger.warning(f"情景脚本生成失败，使用种子兜底: {e}")
    return fallback


# ────────────────────────────────────────────────────────────
# 节点 2：单轮证据采集
# ────────────────────────────────────────────────────────────
def _derive_evidence_gap(evidence: dict, answer: str) -> dict:
    """规则兜底：从单轮取证的结构化信号派生「证据缺口」（LLM 未输出 evidence_gap 时）。

    缺口类型对齐牛客「动态取证式追问」的三类缺口：
      - no_quantification：缺具体数字/时间/影响范围
      - role_ambiguous：分不清团队参与还是个人主导
      - vague：空泛总结无实质
      - none：无缺口

    仅供下一轮追问定向使用，不参与评分（评分仍以 dimension_hits + 原话为准）。
    """
    signals = evidence.get("signals") or {}
    specificity = signals.get("specificity", "general")
    template_suspect = bool(evidence.get("template_suspect"))
    density = float(evidence.get("density", 0.5) or 0.5)
    ans_len = len((answer or "").strip())

    if template_suspect or specificity == "empty" or ans_len < 12:
        return {"gap_type": "vague", "description": "回答疑似套话或几乎无实质内容",
                "suggested_probe": "用反事实或具体场景逼出真实取舍，不接受空话"}
    if specificity == "general" or density < 0.35:
        return {"gap_type": "no_quantification", "description": "回答偏空泛，缺具体数字/步骤/影响范围",
                "suggested_probe": "追问具体数字、时间、影响范围与个人分工"}
    return {"gap_type": "none", "description": "", "suggested_probe": ""}


async def collect_evidence(scenario_label: str, question: str, answer: str) -> dict:
    user = EVIDENCE_COLLECT_USER_TMPL.format(
        scenario_label=scenario_label, question=question, answer=answer,
    )
    ans_len = len((answer or "").strip())
    # 无 LLM 时按作答长度粗估信息密度（仅用于规则兜底，不伪装成模型判断）
    fallback_density = max(0.1, min(0.9, round(ans_len / 240, 2)))
    fallback = {
        "dimension_hits": [], "key_quotes": [answer[:40]] if answer else [],
        "template_suspect": ans_len > 0 and ans_len < 12,
        "template_reason": "作答过短" if 0 < ans_len < 12 else "",
        "signals": {"structure": "partial",
                    "specificity": "concrete" if ans_len >= 120 else "general" if ans_len >= 30 else "empty",
                    "composure": "calm"},
        "density": fallback_density,
    }
    fallback["evidence_gap"] = _derive_evidence_gap(fallback, answer)
    try:
        from db.llm_provider import LLMProvider
        llm = LLMProvider()
        raw = await llm.text_completion(EVIDENCE_COLLECT_SYSTEM, user, temperature=0.2, max_tokens=600)
        data = extract_json(raw)
        if isinstance(data, dict):
            # 规整维度 key（兼容中文维度名），剔除非法维度
            hits = []
            for h in data.get("dimension_hits", []) or []:
                if isinstance(h, dict):
                    dk = norm_dimension(h.get("dimension"))
                    if dk:
                        h["dimension"] = dk
                        hits.append(h)
            data["dimension_hits"] = hits
            data.setdefault("key_quotes", [answer[:40]] if answer else [])
            data.setdefault("template_suspect", False)
            data.setdefault("density", 0.5)
            # 证据缺口：优先用 LLM 结构化输出，缺失/非法则规则兜底
            gap = data.get("evidence_gap")
            if not isinstance(gap, dict) or not gap.get("gap_type"):
                data["evidence_gap"] = _derive_evidence_gap(data, answer)
            return data
    except Exception as e:
        logger.warning(f"证据采集失败，规则兜底: {e}")
    return fallback


# ────────────────────────────────────────────────────────────
# 对抗模式决策（鲶鱼机制，规则驱动，稳定可控）
# ────────────────────────────────────────────────────────────
def _decide_adversary_mode_rule(turns: list[dict], current_mode: str, catfish_continuous: int) -> tuple[str, bool, int]:
    """规则版决策（P3③ MAPPO 化后的兜底路径，逻辑与原版完全一致）"""
    n = len(turns)
    if n == 0:
        return "normal", False, 0

    recent = turns[-2:]
    template_cnt = sum(1 for t in recent if (t.get("evidence") or {}).get("template_suspect"))
    # 无证据轮默认密度对齐 career_policy.EVIDENCE_DENSITY_DEFAULT（0.3）：旧值 0.5 ≥ 0.35 阈值
    # ⇒ 无证据轮恒不满足加压条件（规则死锁 normal）。对齐后"低信息/无证据"轮恢复可达。
    avg_density = sum(float((t.get("evidence") or {}).get("density", 0.3)) for t in recent) / len(recent)

    # 已在鲶鱼/加压中：连续不超过 CATFISH_MAX_CONTINUE 轮，之后回 normal
    if current_mode in ("catfish", "escalating"):
        if catfish_continuous >= CATFISH_MAX_CONTINUE:
            return "normal", False, 0
        # 仍满足加压条件则延续
        if template_cnt >= 1 or avg_density < 0.35:
            return current_mode, False, catfish_continuous + 1
        return "normal", False, 0

    # 至少打完 2 轮才允许触发，避免开场误判
    if n >= 2:
        if template_cnt >= 2:
            return "catfish", True, 1
        if avg_density < 0.35:
            return "escalating", True, 1
    return "normal", False, 0


def decide_adversary_mode(turns: list[dict], current_mode: str, catfish_continuous: int) -> tuple[str, bool, int]:
    """决策层入口（P3③）：灰度开启 MAPPO 时走学习策略，否则/失败走规则版。

    对外签名与返回契约（三模式 + 触发标记 + 连压计数）不变，下游零改动。
    """
    try:
        from engines.career_policy import maybe_mappo_decide
        result = maybe_mappo_decide(turns, current_mode, catfish_continuous,
                                    rule_fn=_decide_adversary_mode_rule)
        if result is not None:
            return result
    except Exception:
        pass  # 任何异常（含导入失败）→ 规则版兜底
    return _decide_adversary_mode_rule(turns, current_mode, catfish_continuous)


# ────────────────────────────────────────────────────────────
# 节点 3：生成下一轮对抗问题
# ────────────────────────────────────────────────────────────
def _dialogue_brief(turns: list[dict], keep: int = 4) -> str:
    brief = []
    for t in turns[-keep:]:
        brief.append(f"第{t.get('turn_index')}轮 对手：{t.get('question','')}")
        brief.append(f"第{t.get('turn_index')}轮 学生：{t.get('answer','')}")
    return "\n".join(brief) if brief else "（这是第一轮，尚无历史）"


def _format_evidence_gap(evidence: dict) -> str:
    """把上轮取证的 evidence_gap 格式化成追问提示语（动态取证式追问的注入点）。"""
    gap = (evidence or {}).get("evidence_gap") or {}
    gt = gap.get("gap_type")
    if not gt or gt == "none":
        return "（上轮回答无明确证据缺口）"
    desc = gap.get("description", "")
    probe = gap.get("suggested_probe", "")
    return f"{desc}；建议追问：{probe}" if probe else desc


async def generate_adversary_question(script: dict, turns: list[dict], last_answer: str,
                                      mode: str, probe_dimension: str = "") -> dict:
    catfish_hint = ""
    if mode == "catfish":
        catfish_hint = "【特别提示】判定学生疑似套模板，请务必用反事实极端假设逼其给出具体取舍。"
    last_evidence = turns[-1].get("evidence") if turns else {}
    user = ADVERSARY_USER_TMPL.format(
        setting=script.get("setting", ""),
        interviewer_role=script.get("interviewer_role", ""),
        mode_label=ADVERSARY_MODE_LABELS.get(mode, mode),
        dialogue_brief=_dialogue_brief(turns),
        last_answer=last_answer or "（学生未作答）",
        probe_plan="；".join(script.get("probe_plan", [])),
        evidence_gap=_format_evidence_gap(last_evidence),
        catfish_hint=catfish_hint,
    )
    fallback_q = _fallback_question(script, turns, mode)
    try:
        from db.llm_provider import LLMProvider
        llm = LLMProvider()
        raw = await llm.text_completion(
            ADVERSARY_SYSTEM.get(mode, ADVERSARY_SYSTEM["normal"]),
            user, temperature=0.7 if mode == "normal" else 0.85, max_tokens=300,
        )
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("question"):
            dim = norm_dimension(data.get("probe_dimension")) or "problem_solving"
            return {"question": data["question"], "probe_dimension": dim,
                    "intent": data.get("intent", ""), "mode": mode}
    except Exception as e:
        logger.warning(f"对抗问题生成失败，规则兜底: {e}")
    fallback_q["mode"] = mode
    return fallback_q


def _fallback_question(script: dict, turns: list[dict], mode: str) -> dict:
    """LLM 不可用时按 probe_plan 顺序兜底提问，保证流程不断"""
    plan = script.get("probe_plan", [])
    idx = min(len(turns), len(plan) - 1) if plan else 0
    if plan:
        q = plan[idx]
    else:
        q = "请结合一个具体例子，说明你会怎么一步步处理？"
    if mode == "catfish":
        q = "假设关键资源在最后一刻失效、你又联系不上任何人，你刚才的方案还成立吗？具体怎么办？"
    return {"question": q, "probe_dimension": "problem_solving", "intent": "兜底追问"}


# ────────────────────────────────────────────────────────────
# 节点 4：六维 ECD 终评
# ────────────────────────────────────────────────────────────
def _dialogue_with_evidence(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        lines.append(f"第{t.get('turn_index')}轮（模式{t.get('mode','normal')}，考察{DIMENSION_LABELS.get(t.get('probe_dimension',''),'')}）")
        lines.append(f"  对手：{t.get('question','')}")
        lines.append(f"  学生：{t.get('answer','')}")
        ev = t.get("evidence") or {}
        if ev:
            hits = "；".join(
                f"{DIMENSION_LABELS.get(h.get('dimension'),'')}:{h.get('note','')}"
                for h in ev.get("dimension_hits", [])
            )
            lines.append(f"  采集证据：{hits}；套话嫌疑={ev.get('template_suspect')}；信息密度={ev.get('density')}")
    return "\n".join(lines)


async def assess_session(script: dict, scenario_label: str, title: str, turns: list[dict]) -> dict:
    user = CAREER_ASSESS_USER_TMPL.format(
        scenario_label=scenario_label, title=title,
        weights=json.dumps(script.get("dimension_weights", {}), ensure_ascii=False),
        bars=json.dumps(script.get("bars_anchor", {}), ensure_ascii=False),
        dialogue_with_evidence=_dialogue_with_evidence(turns),
    )
    try:
        from db.llm_provider import LLMProvider
        llm = LLMProvider()
        # 超时必须比默认 60s 大（2026-10-20 实测）：本调用实测 64.2s（返回仅 2461 字符，
        # 慢在免费档生成速度而非输出长度），60s 会稳定 ReadTimeout ⇒ 静默退回规则兜底，
        # 而页面只显示"规则评估"标签、不报错 —— 是那种最难发现的退化。
        # 终评已后台异步（不受发布平台 ~60s 网关超时约束），故这里可以给到 150s。
        raw = await llm.text_completion(
            CAREER_ASSESS_SYSTEM, user, temperature=0.2, max_tokens=2000, timeout=ASSESS_TIMEOUT,
        )
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("dimensions"):
            return _normalize_assessment(data, script)
        logger.warning("六维评估 JSON 解析失败，使用规则评估")
    except Exception as e:
        logger.warning(f"六维评估失败，规则兜底: {e}")
    return _rule_based_assessment(turns, script)


def _derive_risk_flags(assessment: dict) -> list[str]:
    """规则兜底：从评估结果派生风险预警（LLM 未输出 risk_flags 时）。

    只依据可反查的结构性事实（证据不足/套模板/低分维度），不做能力定性。
    """
    flags = []
    dims = assessment.get("dimensions") or {}
    for d, v in dims.items():
        label = DIMENSION_LABELS.get(d, d)
        score = v.get("score") if isinstance(v, dict) else None
        conf = v.get("confidence") if isinstance(v, dict) else None
        if score is None:
            flags.append(f"「{label}」维度证据不足，未评分")
        elif conf is not None and conf < 0.5:
            flags.append(f"「{label}」维度评分置信度偏低（{round(float(conf), 2)}）")
        elif isinstance(score, (int, float)) and score <= 2.0:
            flags.append(f"「{label}」维度得分偏低（{score}），建议重点训练")
    if assessment.get("template_detected"):
        flags.append("对话中存在疑似套模板/套话，需结合原话复核")
    return flags


def _normalize_assessment(data: dict, script: dict) -> dict:
    """规整评估结果：非法/中文维度键归一、补 overall"""
    # 维度键归一（兼容中文）
    raw_dims = data.get("dimensions") or {}
    norm_raw = {}
    for k, v in raw_dims.items():
        dk = norm_dimension(k)
        if dk:
            norm_raw[dk] = v
    dims = {}
    weights = script.get("dimension_weights", {})
    weighted_sum, weight_total = 0.0, 0.0
    for d in DIMENSIONS:
        item = norm_raw.get(d) or {}
        score = item.get("score")
        if score is not None:
            try:
                score = max(1.0, min(5.0, float(score)))
            except (TypeError, ValueError):
                score = None
        dims[d] = {
            "score": score,
            "label": DIMENSION_LABELS[d],
            "level": item.get("level", "insufficient" if score is None else "average"),
            "confidence": float(item.get("confidence", 0.5) or 0.5),
            "evidence_turns": [int(x) for x in item.get("evidence_turns", []) if str(x).isdigit()],
            "evidence_quotes": [q for q in (item.get("evidence_quotes") or []) if isinstance(q, str) and q.strip()][:3],
            "rationale": item.get("rationale", ""),
        }
        if score is not None:
            w = float(weights.get(d, 1.0))
            weighted_sum += score * w
            weight_total += w
    overall = round(weighted_sum / weight_total, 2) if weight_total else None
    data["dimensions"] = dims
    data["overall"] = overall
    data.setdefault("strength", "")
    data.setdefault("weaknesses", [])
    data.setdefault("template_detected", False)
    data.setdefault("summary", "")
    data.setdefault("highlights", [])
    # 风险预警：LLM 输出优先，缺失/空则规则兜底（只据结构性事实，不做能力定性）
    rf = data.get("risk_flags")
    if not isinstance(rf, list) or not rf:
        data["risk_flags"] = _derive_risk_flags(data)
    data["assessment_source"] = "llm"
    return data


def _rule_based_assessment(turns: list[dict], script: dict) -> dict:
    """LLM 不可用时的诚实兜底：按证据命中数与信息密度给粗分，标注规则来源"""
    weights = script.get("dimension_weights", {})
    dim_evidence = {d: [] for d in DIMENSIONS}
    # 同时记录每个维度被直接考察（probe）的轮次，供无结构化命中时保守评分
    dim_probed = {d: [] for d in DIMENSIONS}
    for t in turns:
        dens = float((t.get("evidence") or {}).get("density", 0.5))
        for h in (t.get("evidence") or {}).get("dimension_hits", []):
            if h.get("dimension") in DIMENSIONS:
                dim_evidence[h["dimension"]].append((t.get("turn_index"), h.get("polarity"), dens, h.get("note", "")))
        pd = t.get("probe_dimension")
        ans_len = len((t.get("answer") or "").strip())
        if pd in DIMENSIONS and ans_len > 0:
            dim_probed[pd].append((t.get("turn_index"), dens))
    dims, ws, wt = {}, 0.0, 0.0
    for d in DIMENSIONS:
        ev = dim_evidence[d]
        if ev:
            pos = sum(1 for _, p, _, _ in ev if p == "positive")
            neg = sum(1 for _, p, _, _ in ev if p == "negative")
            dens = sum(x for _, _, x, _ in ev) / len(ev)
            score = round(max(1.0, min(5.0, 2.5 + (pos - neg) * 0.6 + dens)), 1)
            rationale = "【规则评估】基于单轮证据正负向与信息密度粗估，建议启用LLM复评"
            turns_used = [i for i, _, _, _ in ev]
            quotes = [n for _, _, _, n in ev if n and isinstance(n, str)][:3]
            conf = 0.4
        elif dim_probed[d]:
            # 被考察但结构化取证缺失：按答案信息密度给保守中性分，明确低置信
            dens = sum(x for _, x in dim_probed[d]) / len(dim_probed[d])
            score = round(max(1.5, min(4.0, 2.2 + dens * 0.8)), 1)
            rationale = "【规则评估·保守】缺少结构化取证，仅依据被考察轮次的作答信息量给中性分，建议启用LLM复评"
            turns_used = [i for i, _ in dim_probed[d]]
            # 从被考察轮次的学生回答中截取片段作为弱证据引用
            quotes = []
            for ti, _ in dim_probed[d]:
                for t in turns:
                    if t.get("turn_index") == ti and t.get("answer"):
                        quotes.append(t["answer"][:50])
                        break
            quotes = quotes[:3]
            conf = 0.25
        else:
            dims[d] = {"score": None, "label": DIMENSION_LABELS[d], "level": "insufficient",
                       "confidence": 0.0, "evidence_turns": [], "evidence_quotes": [],
                       "rationale": "无有效证据，不予评分"}
            continue
        dims[d] = {"score": score, "label": DIMENSION_LABELS[d],
                   "level": "average", "confidence": conf,
                   "evidence_turns": turns_used, "evidence_quotes": quotes,
                   "rationale": rationale}
        w = float(weights.get(d, 1.0)); ws += score * w; wt += w
    result = {
        "dimensions": dims,
        "overall": round(ws / wt, 2) if wt else None,
        "strength": "（规则评估，请以教师复核为准）",
        "weaknesses": [], "template_detected": any((t.get("evidence") or {}).get("template_suspect") for t in turns),
        "summary": f"共完成{len(turns)}轮对抗，本结果为LLM不可用时的规则兜底评估。",
        "highlights": [],
        "assessment_source": "rule_fallback",
    }
    result["risk_flags"] = _derive_risk_flags(result)
    return result


# ────────────────────────────────────────────────────────────
# 节点 5：提升路径
# ────────────────────────────────────────────────────────────
async def build_improvement_plan(assessment: dict, scenario_label: str) -> dict:
    user = IMPROVEMENT_USER_TMPL.format(
        assessment_json=json.dumps(assessment, ensure_ascii=False)[:3000],
        scenario_label=scenario_label,
    )
    fallback = _fallback_improvement(assessment)
    try:
        from db.llm_provider import LLMProvider
        llm = LLMProvider()
        raw = await llm.text_completion(
            IMPROVEMENT_SYSTEM, user, temperature=0.5, max_tokens=700, timeout=IMPROVEMENT_TIMEOUT,
        )
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("actions"):
            # 学习资源（⑥「学」环节）：LLM 输出优先，缺失/非法则规则兜底（内置方法论卡）
            lr = data.get("learning_resources")
            if not isinstance(lr, list) or not lr:
                data["learning_resources"] = _derive_learning_resources(assessment)
            return data
    except Exception as e:
        logger.warning(f"提升路径生成失败，规则兜底: {e}")
    return fallback


# 六维方法论/知识点卡（静态通用素材，规则兜底；真实方法论，不编造）
_DIM_METHODOLOGY = {
    "expression": {"title": "结构化表达：结论先行", "points": [
        "用『结论-理由-例子』三段式复述同一问题",
        "金字塔原理：先总后分，层层递进",
        "一句话讲清核心观点，再展开论据"]},
    "stress": {"title": "抗压应变：STOP 法则", "points": [
        "被质疑先停 3 秒稳住情绪，再回应",
        "区分事实与猜测，不盲目承诺",
        "把压力问题转成可拆解的下一步动作"]},
    "decompose": {"title": "方案拆解：目标-约束-子任务", "points": [
        "先写『目标-约束-子任务-优先级』四行再作答",
        "MECE 拆分：不重不漏地切分子问题",
        "明确最小可行版本与验证点"]},
    "collab": {"title": "协作沟通：先肯定后建议", "points": [
        "先复述对方诉求，确认理解一致",
        "对事不对人，用数据/场景而非主观偏好说服",
        "给出两个可选项，推进共识而非对抗"]},
    "presentation": {"title": "技术汇报：技术降维表达", "points": [
        "先讲结论与影响，再讲实现细节",
        "把技术术语翻译成业务语言",
        "限时练习：同一方案分别讲给内行和外行"]},
    "problem_solving": {"title": "问题解决：应急-风险-备选", "points": [
        "写『应急步骤-风险-备选方案』清单并计时",
        "5Why 追根因，不只处理表象",
        "每一步都问『失败了怎么办』"]},
}


def _derive_learning_resources(assessment: dict) -> list[dict]:
    """规则兜底：为最弱 1-2 个维度生成方法论/知识点卡（静态素材，不编造）。"""
    dims = assessment.get("dimensions", {})
    scored = [
        (d, v.get("score") or 0) for d, v in dims.items()
        if isinstance(v, dict) and v.get("score") is not None
    ]
    scored.sort(key=lambda x: x[1])
    priority = [d for d, _ in scored[:2]]
    if not priority:
        priority = ["expression"]
    out = []
    for d in priority:
        card = _DIM_METHODOLOGY.get(d)
        if card:
            out.append({"dimension": d, "title": card["title"], "points": list(card["points"])})
    return out


def _fallback_improvement(assessment: dict) -> dict:
    dims = assessment.get("dimensions", {})
    scored = [(d, v.get("score") or 0) for d, v in dims.items() if v.get("score") is not None]
    scored.sort(key=lambda x: x[1])
    priority = [d for d, _ in scored[:2]]
    actions = []
    coach = {
        "expression": "用『结论-理由-例子』结构复述同一问题并录音回听",
        "stress": "每天做1次限时90秒高压问答，刻意练习先稳住再回应",
        "decompose": "面对问题先写『目标-约束-子任务-优先级』四行再作答",
        "collab": "练习先复述对方诉求、再给两个可选项的沟通句式",
        "presentation": "把一个技术方案分别讲给外行和内行听，各限时2分钟",
        "problem_solving": "针对场景写『应急步骤-风险-备选方案』清单并计时",
    }
    for d in priority:
        actions.append({"dimension": d, "do": coach.get(d, "针对性重复演练"), "frequency": "每周3次"})
    return {
        "priority_dimensions": priority,
        "actions": actions or [{"dimension": "expression", "do": "完成下一场不同类型情景演练", "frequency": "每周2次"}],
        "learning_resources": _derive_learning_resources(assessment),
        "next_scenario": "建议轮换到尚未演练的情景类型，补齐维度",
        "encouragement": "完成一次完整对抗本身就是进步，针对最弱维度刻意练习即可。",
    }
