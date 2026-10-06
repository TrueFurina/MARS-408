# ============================================================
# career_service — 芒得很职·对抗实训编排服务（P0 简化备选）
#
# 不依赖 LangGraph interrupt：状态落库（career_sessions.state），
# 每个 HTTP 请求推进一轮，节点为 agents/career_nodes.py 中的 async 纯函数。
# 后续 P5 可平滑替换为 LangGraph checkpointer，业务节点不变。
# ============================================================

import logging
from typing import Optional

from agents.career_state import (
    new_state, DIMENSION_LABELS, SCENARIO_TYPE_LABELS,
    DEFAULT_MAX_TURNS, MIN_TURNS,
)
from agents import career_nodes as nodes
from db import career_store as store

logger = logging.getLogger("netlearn.career.service")


# ────────────────────────────────────────────────────────────
# 场景列表
# ────────────────────────────────────────────────────────────
def list_scenarios() -> list[dict]:
    return nodes.list_scenarios()


# ────────────────────────────────────────────────────────────
# 启动一场实训：生成脚本 + 第一问
# ────────────────────────────────────────────────────────────
async def start_session(user_id: str, scenario_id: str,
                        difficulty: str = "medium",
                        max_turns: int = DEFAULT_MAX_TURNS,
                        task_id: Optional[str] = None) -> dict:
    seed = nodes.get_scenario(scenario_id)
    if not seed:
        raise ValueError(f"情景不存在: {scenario_id}")

    max_turns = max(MIN_TURNS, min(int(max_turns or DEFAULT_MAX_TURNS), 12))
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else seed.get("difficulty_default", "medium")

    state = new_state(
        session_id="", user_id=user_id,
        scenario_type=seed.get("type", ""),
        scenario_subtype=seed.get("subtype", ""),
        difficulty=difficulty, max_turns=max_turns, task_id=task_id,
    )
    state["scenario_id"] = scenario_id
    state["title"] = seed.get("title", "")
    state["scenario_label"] = seed.get("type_label", SCENARIO_TYPE_LABELS.get(seed.get("type", ""), ""))

    # 1) 生成对抗脚本
    script = await nodes.build_scenario_script(seed, difficulty)
    state["scenario_script"] = script

    # 2) 第一问（开场），登记为待回答问题
    opening = script.get("opening_question") or seed.get("opening_question", "请先做个自我介绍。")
    state["pending"] = {"question": opening, "mode": "normal", "probe_dimension": "expression", "intent": "开场"}

    # 3) 落库
    sid = store.create_session(state)
    state["session_id"] = sid
    store.save_session_state(state, status="ongoing")

    return {
        "session_id": sid,
        "scenario_id": scenario_id,
        "title": state["title"],
        "scenario_label": state["scenario_label"],
        "setting": script.get("setting", ""),
        "student_role": script.get("student_role", ""),
        "interviewer_role": script.get("interviewer_role", ""),
        "max_turns": max_turns,
        "next_question": {"question": opening, "mode": "normal", "probe_dimension": "expression"},
        "turns_done": 0,
        "status": "ongoing",
    }


# ────────────────────────────────────────────────────────────
# 推进一轮：学生作答 → 取证 → 决定下一问或终评
# ────────────────────────────────────────────────────────────
async def answer_turn(session_id: str, answer_text: str) -> dict:
    state = store.get_session_state(session_id)
    if not state:
        raise KeyError(f"实训会话不存在: {session_id}")
    if state.get("status") in ("finished", "abandoned"):
        return {"status": state["status"], "message": "本场实训已结束，请查看报告", "turns_done": len(state.get("dialogue_turns", []))}

    answer_text = (answer_text or "").strip()
    if not answer_text:
        raise ValueError("回答不能为空")

    pending = state.get("pending") or {}
    question = pending.get("question", "")
    mode = pending.get("mode", "normal")
    probe_dimension = pending.get("probe_dimension", "problem_solving")
    turns = state.setdefault("dialogue_turns", [])
    turn_index = len(turns) + 1

    # 1) 单轮取证
    evidence = await nodes.collect_evidence(
        state.get("scenario_label", ""), question, answer_text,
    )
    turn = {
        "turn_index": turn_index,
        "mode": mode,
        "question": question,
        "answer": answer_text,
        "probe_dimension": probe_dimension,
        "evidence": evidence,
    }
    turns.append(turn)
    store.add_turn(session_id, turn)

    # 2) 是否达到轮数上限 → 终评
    if turn_index >= int(state.get("max_turns", DEFAULT_MAX_TURNS)):
        return await _finish(state)

    # 3) 决定对抗模式（鲶鱼/加压），生成下一问
    new_mode, triggered, catfish_cont = nodes.decide_adversary_mode(
        turns, state.get("adversary_mode", "normal"), state.get("catfish_continuous", 0),
    )
    state["adversary_mode"] = new_mode
    state["catfish_continuous"] = catfish_cont
    if triggered and new_mode == "catfish":
        state["catfish_triggered"] = True

    nxt = await nodes.generate_adversary_question(
        state.get("scenario_script", {}), turns, answer_text, new_mode,
    )
    state["pending"] = {
        "question": nxt["question"],
        "mode": nxt.get("mode", new_mode),
        "probe_dimension": nxt.get("probe_dimension", "problem_solving"),
        "intent": nxt.get("intent", ""),
    }
    store.save_session_state(state, status="ongoing")

    return {
        "status": "ongoing",
        "turns_done": turn_index,
        "max_turns": state.get("max_turns"),
        "mode": state["pending"]["mode"],
        "catfish_triggered": state.get("catfish_triggered", False),
        "last_evidence": {
            "template_suspect": evidence.get("template_suspect", False),
            "density": evidence.get("density", 0.5),
            "dimension_hits": evidence.get("dimension_hits", []),
        },
        "next_question": {
            "question": state["pending"]["question"],
            "mode": state["pending"]["mode"],
            "probe_dimension": state["pending"]["probe_dimension"],
            "intent": state["pending"].get("intent", ""),
        },
    }


# ────────────────────────────────────────────────────────────
# 学生主动结束（至少 MIN_TURNS 轮才出报告，否则提示）
# ────────────────────────────────────────────────────────────
async def end_session(session_id: str, force: bool = False) -> dict:
    state = store.get_session_state(session_id)
    if not state:
        raise KeyError(f"实训会话不存在: {session_id}")
    turns = state.get("dialogue_turns", [])
    if len(turns) < MIN_TURNS and not force:
        return {
            "status": "insufficient",
            "turns_done": len(turns),
            "min_turns": MIN_TURNS,
            "message": f"证据不足，至少完成 {MIN_TURNS} 轮才能生成评估报告（可 force=true 强制结束）",
        }
    return await _finish(state)


# ────────────────────────────────────────────────────────────
# 终评：六维 ECD 评估 + 提升路径，落库
# ────────────────────────────────────────────────────────────
async def _finish(state: dict) -> dict:
    sid = state["session_id"]
    turns = state.get("dialogue_turns", [])
    script = state.get("scenario_script", {})

    assessment = await nodes.assess_session(
        script, state.get("scenario_label", ""), state.get("title", ""), turns,
    )
    improvement = await nodes.build_improvement_plan(assessment, state.get("scenario_label", ""))

    # 证据链：维度 → 支撑轮次 + 原话引用 + 逐轮证据聚合（ECD Claim-Evidence 对齐）
    # 先从每轮 collect_evidence 的 dimension_hits 聚合该维度的所有证据 note
    per_dim_turn_evidence = {}
    for t in turns:
        ev = t.get("evidence") or {}
        for h in ev.get("dimension_hits", []) or []:
            dk = h.get("dimension")
            if dk:
                per_dim_turn_evidence.setdefault(dk, []).append({
                    "turn": t.get("turn_index"),
                    "polarity": h.get("polarity", "neutral"),
                    "note": h.get("note", ""),
                })
    evidence_chain = []
    for dim, item in (assessment.get("dimensions") or {}).items():
        evidence_chain.append({
            "dimension": dim,
            "label": DIMENSION_LABELS.get(dim, dim),
            "score": item.get("score"),
            "level": item.get("level"),
            "confidence": item.get("confidence"),
            "evidence_turns": item.get("evidence_turns", []),
            "evidence_quotes": item.get("evidence_quotes", []),
            "rationale": item.get("rationale", ""),
            "per_turn_evidence": per_dim_turn_evidence.get(dim, []),
        })

    overall = assessment.get("overall")
    store.save_assessment(
        session_id=sid, user_id=state.get("user_id", ""),
        assessment=assessment, improvement=improvement,
        evidence_chain=evidence_chain,
        consistency_score=overall, task_id=state.get("task_id"),
    )

    state["dimension_scores"] = assessment.get("dimensions", {})
    state["assessment_report"] = assessment
    state["improvement_plan"] = improvement
    state["status"] = "finished"
    state["pending"] = None
    store.save_session_state(state, status="finished")

    return {
        "status": "finished",
        "turns_done": len(turns),
        "assessment": assessment,
        "improvement": improvement,
        "evidence_chain": evidence_chain,
    }


def get_report(session_id: str) -> dict:
    state = store.get_session_state(session_id)
    if not state:
        raise KeyError(f"实训会话不存在: {session_id}")
    record = store.get_assessment_by_session(session_id)
    return {
        "session_id": session_id,
        "title": state.get("title", ""),
        "scenario_label": state.get("scenario_label", ""),
        "status": state.get("status"),
        "turns": [
            {"turn_index": t.get("turn_index"), "mode": t.get("mode"),
             "probe_dimension": t.get("probe_dimension"),
             "question": t.get("question"), "answer": t.get("answer"),
             "evidence": t.get("evidence", {})}
            for t in state.get("dialogue_turns", [])
        ],
        "assessment": (record or {}).get("dimension_scores") or state.get("assessment_report", {}),
        "improvement": (record or {}).get("improvement_plan") or state.get("improvement_plan", {}),
        "evidence_chain": (record or {}).get("evidence_chain", []),
    }


def list_my_sessions(user_id: str) -> list[dict]:
    return store.list_my_sessions(user_id)
