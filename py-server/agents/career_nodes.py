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
    DEFAULT_MAX_TURNS, CATFISH_MAX_CONTINUE,
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


def list_scenarios() -> list[dict]:
    """返回前端可选场景列表（只给展示字段，不泄露完整脚本）"""
    out = []
    for s in _load_scenario_file().get("scenarios", []):
        out.append({
            "id": s["id"], "type": s["type"], "subtype": s.get("subtype", ""),
            "type_label": s.get("type_label", s["type"]),
            "subtype_label": s.get("subtype_label", ""),
            "title": s["title"],
            "difficulty_default": s.get("difficulty_default", "medium"),
        })
    return out


def get_scenario(scenario_id: str) -> Optional[dict]:
    for s in _load_scenario_file().get("scenarios", []):
        if s["id"] == scenario_id:
            return s
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
            return data
        logger.warning("情景脚本 JSON 解析失败，使用种子兜底")
    except Exception as e:
        logger.warning(f"情景脚本生成失败，使用种子兜底: {e}")
    return fallback


# ────────────────────────────────────────────────────────────
# 节点 2：单轮证据采集
# ────────────────────────────────────────────────────────────
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
            return data
    except Exception as e:
        logger.warning(f"证据采集失败，规则兜底: {e}")
    return fallback


# ────────────────────────────────────────────────────────────
# 对抗模式决策（鲶鱼机制，规则驱动，稳定可控）
# ────────────────────────────────────────────────────────────
def decide_adversary_mode(turns: list[dict], current_mode: str, catfish_continuous: int) -> tuple[str, bool, int]:
    """返回 (mode, 本轮是否新触发鲶鱼, 更新后的catfish_continuous)"""
    n = len(turns)
    if n == 0:
        return "normal", False, 0

    recent = turns[-2:]
    template_cnt = sum(1 for t in recent if (t.get("evidence") or {}).get("template_suspect"))
    avg_density = sum(float((t.get("evidence") or {}).get("density", 0.5)) for t in recent) / len(recent)

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


# ────────────────────────────────────────────────────────────
# 节点 3：生成下一轮对抗问题
# ────────────────────────────────────────────────────────────
def _dialogue_brief(turns: list[dict], keep: int = 4) -> str:
    brief = []
    for t in turns[-keep:]:
        brief.append(f"第{t.get('turn_index')}轮 对手：{t.get('question','')}")
        brief.append(f"第{t.get('turn_index')}轮 学生：{t.get('answer','')}")
    return "\n".join(brief) if brief else "（这是第一轮，尚无历史）"


async def generate_adversary_question(script: dict, turns: list[dict], last_answer: str,
                                      mode: str, probe_dimension: str = "") -> dict:
    catfish_hint = ""
    if mode == "catfish":
        catfish_hint = "【特别提示】判定学生疑似套模板，请务必用反事实极端假设逼其给出具体取舍。"
    user = ADVERSARY_USER_TMPL.format(
        setting=script.get("setting", ""),
        interviewer_role=script.get("interviewer_role", ""),
        mode_label=ADVERSARY_MODE_LABELS.get(mode, mode),
        dialogue_brief=_dialogue_brief(turns),
        last_answer=last_answer or "（学生未作答）",
        probe_plan="；".join(script.get("probe_plan", [])),
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
        raw = await llm.text_completion(CAREER_ASSESS_SYSTEM, user, temperature=0.2, max_tokens=2000)
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("dimensions"):
            return _normalize_assessment(data, script)
        logger.warning("六维评估 JSON 解析失败，使用规则评估")
    except Exception as e:
        logger.warning(f"六维评估失败，规则兜底: {e}")
    return _rule_based_assessment(turns, script)


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
        hit_dim = False
        for h in (t.get("evidence") or {}).get("dimension_hits", []):
            if h.get("dimension") in DIMENSIONS:
                dim_evidence[h["dimension"]].append((t.get("turn_index"), h.get("polarity"), dens, h.get("note", "")))
                hit_dim = True
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
    return {
        "dimensions": dims,
        "overall": round(ws / wt, 2) if wt else None,
        "strength": "（规则评估，请以教师复核为准）",
        "weaknesses": [], "template_detected": any((t.get("evidence") or {}).get("template_suspect") for t in turns),
        "summary": f"共完成{len(turns)}轮对抗，本结果为LLM不可用时的规则兜底评估。",
        "assessment_source": "rule_fallback",
    }


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
        raw = await llm.text_completion(IMPROVEMENT_SYSTEM, user, temperature=0.5, max_tokens=700)
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("actions"):
            return data
    except Exception as e:
        logger.warning(f"提升路径生成失败，规则兜底: {e}")
    return fallback


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
        "next_scenario": "建议轮换到尚未演练的情景类型，补齐维度",
        "encouragement": "完成一次完整对抗本身就是进步，针对最弱维度刻意练习即可。",
    }
