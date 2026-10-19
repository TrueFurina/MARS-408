# ============================================================
# career_service — 芒得很职·对抗实训编排服务（P0 简化备选）
#
# 不依赖 LangGraph interrupt：状态落库（career_sessions.state），
# 每个 HTTP 请求推进一轮，节点为 agents/career_nodes.py 中的 async 纯函数。
# 后续 P5 可平滑替换为 LangGraph checkpointer，业务节点不变。
# ============================================================

import asyncio
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
                        task_id: Optional[str] = None,
                        phase: Optional[str] = None) -> dict:
    seed = nodes.get_scenario(scenario_id)
    if not seed:
        raise ValueError(f"情景不存在: {scenario_id}")

    max_turns = max(MIN_TURNS, min(int(max_turns or DEFAULT_MAX_TURNS), 12))
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else seed.get("difficulty_default", "medium")
    # F5: 前后测阶段标记（pre/post 白名单；其余值一律视为未标记，不猜）
    phase = phase if phase in ("pre", "post") else None

    state = new_state(
        session_id="", user_id=user_id,
        scenario_type=seed.get("type", ""),
        scenario_subtype=seed.get("subtype", ""),
        difficulty=difficulty, max_turns=max_turns, task_id=task_id,
    )
    state["scenario_id"] = scenario_id
    state["title"] = seed.get("title", "")
    state["scenario_label"] = seed.get("type_label", SCENARIO_TYPE_LABELS.get(seed.get("type", ""), ""))
    # ⑤ 回溯重评：记录会话开始时的 rubric 版本（改标准后可与当前版本对比）
    state["rubric_version"] = seed.get("rubric_version", "1.0")
    if phase:
        state["phase"] = phase

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
        "phase": phase,
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
        # 终评异步化：与 end_session 同理，同步跑两轮 LLM 必然撞上公网网关超时。
        if state.get("status") == "finished" and store.get_assessment_by_session(session_id):
            return _finished_payload(state, turn_index)
        if state.get("report_status") != "generating":
            state["report_status"] = "generating"
            state["report_error"] = ""
            store.save_session_state(state, status="ongoing")
            asyncio.create_task(_finish_background(session_id))
        return {
            "status": "finished_pending",
            "turns_done": turn_index,
            "message": _GENERATING_MSG,
        }

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

    # ── 报告已生成过：直接回放，不重复烧 token（幂等重入）──
    if state.get("status") == "finished" and store.get_assessment_by_session(session_id):
        return _finished_payload(state, len(turns))

    # ── 已在生成中：不要并发再起一次（否则同一会话两份评估）──
    if state.get("report_status") == "generating":
        return {
            "status": "generating",
            "turns_done": len(turns),
            "message": _GENERATING_MSG,
        }

    # ── 异步出报告（关键改动，见下方 _finish_background 注释）──
    state["report_status"] = "generating"
    state["report_error"] = ""
    store.save_session_state(state, status=state.get("status") or "ongoing")
    asyncio.create_task(_finish_background(session_id))
    return {
        "status": "generating",
        "turns_done": len(turns),
        "message": _GENERATING_MSG,
    }


# 免费档 LLM 实测：六维评估单次 ~64s + 提升路径 ~15s ⇒ 提示必须写实，别承诺 30 秒
_GENERATING_MSG = "评估报告生成中（六维 ECD 评估 + 提升路径），约需 1–2 分钟，请稍后查看报告"


def _finished_payload(state: dict, turns_done: int) -> dict:
    """已完成的会话：直接用落库内容组装响应（不再调用 LLM）。"""
    record = store.get_assessment_by_session(state["session_id"]) or {}
    return {
        "status": "finished",
        "turns_done": turns_done,
        "assessment": record.get("dimension_scores") or state.get("assessment_report", {}),
        "improvement": record.get("improvement_plan") or state.get("improvement_plan", {}),
        "evidence_chain": record.get("evidence_chain", []),
    }


async def _finish_background(session_id: str) -> None:
    """后台生成报告。

    为什么必须异步（2026-10-16 公网实测）：
        终评 = 六维评估(max_tokens=2000) + 提升路径 两次串行 LLM 调用，
        实测单轮对话 20s / 首题 26s，终评总耗时稳定超过发布平台网关的
        ~60s 超时 ⇒ 同步返回时用户侧拿到的是 **504**，而后端其实已经算完并
        落库（随后 report 接口 200）。同步接口在公网形态下本质是"必然超时"，
        故改为：end 立即回 generating，后台跑完落库，前端轮询 report。
    """
    try:
        state = store.get_session_state(session_id)
        if not state:
            logger.warning("后台终评：会话已不存在 %s", session_id)
            return
        await _finish(state)
        # _finish 内部最后一次 save 用了它自己的 state 副本，这里重读再落状态
        fresh = store.get_session_state(session_id) or state
        fresh["report_status"] = "ready"
        fresh["report_error"] = ""
        store.save_session_state(fresh, status="finished")
        logger.info("后台终评完成：%s", session_id)
    except Exception as e:  # 失败必须可读：否则前端只会永远轮询
        logger.exception("后台终评失败")
        try:
            fresh = store.get_session_state(session_id) or {}
            fresh["report_status"] = "failed"
            fresh["report_error"] = str(e)[:200]
            store.save_session_state(fresh, status=fresh.get("status") or "ongoing")
        except Exception:
            logger.exception("后台终评失败状态回写也失败")


# ────────────────────────────────────────────────────────────
# 终评：六维 ECD 评估 + 提升路径，落库
# ────────────────────────────────────────────────────────────
def _find_by_label(label: str) -> Optional[str]:
    """按情景中文标签（type_label）反查 scenario_id；找不到返回 None。

    用于 state 未携带 scenario_id 时仍能定位情景种子（取 BARS 锚点做真实溯源）。
    """
    if not label:
        return None
    for s in (nodes.list_scenarios() or []):
        if s.get("type_label") == label:
            return s.get("id")
    return None
def _build_evidence_chain(state: dict, assessment: dict) -> list[dict]:
    """构建 ECD 证据链（维度 → 支撑轮次 + 原话引用 + 逐轮证据聚合）。

    真实溯源：BARS 锚点与重点考察取自情景种子；逐轮证据取自 dialogue_turns 的
    collect_evidence.dimension_hits 与六维评估的 evidence_turns，绝不伪造检索来源。
    本实训链路无 KB/向量库检索（career_nodes 全链路无 retrieve/FrugalRAG 调用），
    故 chunk_ref 仅作「情景 rubric 段落 id」，source_type 恒为 "rule"。

    供 _finish 与 reassess_session 共用：重评时 evidence_chain 的 score/rubric_text
    必须与重评后的 assessment 同源，避免「分数更新了但证据链还挂旧分」的漂移。
    """
    seed = nodes.get_scenario(
        state.get("scenario_id") or _find_by_label(state.get("scenario_label", ""))
    )
    bars = (seed or {}).get("bars_anchor", {})
    seed_focus = (seed or {}).get("focus_points", [])
    turns = state.get("dialogue_turns", [])

    # 逐轮学生原话映射（turn_index → 前 80 字），供溯源引用（取自真实 dialogue_turns）
    answer_by_turn = {
        t.get("turn_index"): (t.get("answer") or "")[:80] for t in turns
    }

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
                    "answer_snippet": (t.get("answer") or "")[:80],
                })
    evidence_chain = []
    for dim, item in (assessment.get("dimensions") or {}).items():
        # 逐轮证据：优先用单轮 collect_evidence 的 dimension_hits（含原话 note），
        # 规则兜底模式（无 LLM collect_evidence）下用六维评估的 evidence_turns 补全，
        # 确保"学生第 N 轮说"真实可溯（全部取自 dialogue_turns，绝不编造）。
        pte = list(per_dim_turn_evidence.get(dim, []))
        seen_turns = {e.get("turn") for e in pte}
        for ti in (item.get("evidence_turns") or []):
            if ti not in seen_turns and ti in answer_by_turn:
                pte.append({
                    "turn": ti,
                    "polarity": "neutral",
                    "note": "",
                    "answer_snippet": answer_by_turn[ti],
                })
        evidence_chain.append({
            "dimension": dim,
            "label": DIMENSION_LABELS.get(dim, dim),
            "score": item.get("score"),
            "level": item.get("level"),
            "confidence": item.get("confidence"),
            "evidence_turns": item.get("evidence_turns", []),
            "evidence_quotes": item.get("evidence_quotes", []),
            "rationale": item.get("rationale", ""),
            "per_turn_evidence": pte,
            "source_type": "rule",
            "source_agent": "CAREER_ASSESS(ECD六维)",
            "chunk_ref": f"scenario:{state.get('scenario_id', '?')}#BARS:{dim}",
            "snippet": (item.get("evidence_quotes") or [""])[0],
            "rubric_text": (bars.get(dim) or {}).get("5") or (bars.get(dim) or {}).get("3") or "",
            "focus_points": seed_focus,
        })
    return evidence_chain


async def _finish(state: dict) -> dict:
    sid = state["session_id"]
    turns = state.get("dialogue_turns", [])
    script = state.get("scenario_script", {})

    assessment = await nodes.assess_session(
        script, state.get("scenario_label", ""), state.get("title", ""), turns,
    )
    improvement = await nodes.build_improvement_plan(assessment, state.get("scenario_label", ""))

    evidence_chain = _build_evidence_chain(state, assessment)

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


def _overall_of(assessment) -> Optional[float]:
    """从 assessment（可能为 None/非 dict）稳健取 overall，供重评对比。"""
    if not isinstance(assessment, dict):
        return None
    return assessment.get("overall")


async def reassess_session(session_id: str) -> dict:
    """⑤ 回溯重评：用当前情景的 rubric（bars_anchor）对已完成会话重新跑六维评估，保留旧分对比。

    诚实边界：
    - 仅对 status=finished 且有对话的会话生效；重评是幂等纯函数调用（assess_session）；
    - save_assessment 追加新记录，旧分仍可查（list_assessments_by_session），绝不覆盖历史；
    - 只替换 script 的 bars_anchor（评分量表依据），对话与逐轮证据不变；
    - 重评后的 evidence_chain 与新 assessment 同源重建（_build_evidence_chain），避免分/证据漂移。
    """
    state = store.get_session_state(session_id)
    if not state:
        raise KeyError(f"实训会话不存在: {session_id}")
    turns = state.get("dialogue_turns", [])
    if state.get("status") != "finished" or not turns:
        raise ValueError("仅可对已完成的实训会话回溯重评")

    seed = nodes.get_scenario(
        state.get("scenario_id") or _find_by_label(state.get("scenario_label", ""))
    )
    if not seed:
        raise ValueError("情景种子不存在，无法回溯重评")

    current_version = seed.get("rubric_version", "1.0")
    old_version = state.get("rubric_version", current_version)

    # 用当前 rubric 重跑评估：只替换 script 的 bars_anchor，其余脚本不变
    script = dict(state.get("scenario_script", {}))
    script["bars_anchor"] = seed.get("bars_anchor", {})

    new_assessment = await nodes.assess_session(
        script, state.get("scenario_label", ""), state.get("title", ""), turns,
    )
    new_evidence_chain = _build_evidence_chain(state, new_assessment)

    # 重评前的全部历史评估（正序）：list_assessments_by_session 让「旧分可查」落地
    history = store.list_assessments_by_session(session_id)
    old_record = history[-1] if history else {}
    old_assessment = old_record.get("dimension_scores") or {}

    # 追加新评估（不覆盖旧分）；improvement 沿用旧记录（提升路径不因 rubric 变化而失效）
    store.save_assessment(
        session_id=session_id, user_id=state.get("user_id", ""),
        assessment=new_assessment,
        improvement=old_record.get("improvement_plan") or {},
        evidence_chain=new_evidence_chain,
        consistency_score=new_assessment.get("overall"),
        task_id=state.get("task_id"),
    )
    state["rubric_version"] = current_version
    state["assessment_report"] = new_assessment
    store.save_session_state(state, status="finished")

    return {
        "session_id": session_id,
        "rubric_version_before": old_version,
        "rubric_version_after": current_version,
        "previous_overall": _overall_of(old_assessment),
        "history_overalls": [_overall_of(r.get("dimension_scores")) for r in history],
        "new_overall": new_assessment.get("overall"),
        "assessment": new_assessment,
        "evidence_chain": new_evidence_chain,
        "reassessed": True,
    }


def get_report(session_id: str) -> dict:
    state = store.get_session_state(session_id)
    if not state:
        raise KeyError(f"实训会话不存在: {session_id}")
    record = store.get_assessment_by_session(session_id)
    # 终评已异步化：报告尚未落库时，如实回「生成中 / 失败」，让前端轮询或重试，
    # 而不是给一份空报告把"还没算完"伪装成"算完了但没分"。
    if not record and state.get("report_status") == "generating":
        return {"session_id": session_id, "status": "generating", "message": _GENERATING_MSG}
    if not record and state.get("report_status") == "failed":
        return {
            "session_id": session_id, "status": "failed",
            "message": f"报告生成失败：{state.get('report_error') or '未知原因'}（可重新结束会话重试）",
        }
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
