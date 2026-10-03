# ============================================================
# 证据校验 Agent 节点（INC-01 / INC-05）
#
# 薄封装节点：从 AgentState 收集 8 类资源文本 → 调既有
# engines.gomarl_conflict.ConflictResolutionEngine（不重写引擎）→
# 映射 severity/disposition、计算 consistency_score → 写 state["evidence_report"]。
#
# 设计硬约束：
#   - 全节点 try/except 降级：任何异常都返回 state，绝不中断
#     critic → path_planner 既有链路（设计 §7.5）。
#   - 冲突类型→严重度：factual→high, semantic→medium, keyword→low。
#   - disposition 由 resolution 字符串映射：adopt/reject/human_review。
#   - 收集顺序固定（设计 §7.4），保证 Conflict.id 稳定可复现。
#   - LLM 通道沿用既有 LLMProvider（auto 优先级：DeepSeek→讯飞 X2），不接 Qwen。
#
# 防幻觉增强（F）：在原有「跨 Agent 一致性」之外，新增「知识支撑度」校验——
#   将讲解文档（teacher_doc）逐句与检索知识库（retrieved_chunks）做余弦相似度，
#   支撑度过低则标记为疑似幻觉（potential_hallucination），写入 evidence_report。
# ============================================================

import logging
import re
import time

import numpy as np

from agents.state import AgentState
from engines.gomarl_conflict import conflict_engine

logger = logging.getLogger("netlearn.evidence_check")

# 固定收集顺序（设计 §7.4）：field → (agent_name, 展示名)
_AGENT_FIELD_MAP = [
    ("teacher_doc", "teacher", "讲解文档"),
    ("quiz", "quiz", "题库"),
    ("code_practice", "code_practice", "代码实操"),
    ("ppt_outline", "ppt", "PPT大纲"),
    ("extension", "extension", "拓展阅读"),
    ("mindmap", "mindmap", "思维导图"),
    ("video_script", "video", "视频脚本"),
    ("media_plan", "media", "多媒体方案"),
]

# 冲突类型 → 严重度（设计 §3.2）
_TYPE_SEVERITY = {
    "factual": "high",
    "semantic": "medium",
    "keyword": "low",
}

# 知识支撑度阈值（按 E5-base-v2 余弦分布经验调参）
_GROUNDING_FLAG_SCORE = 0.30       # 讲解文档平均最大相似度低于此值 → 疑似幻觉
_GROUNDING_FLAG_FRACTION = 0.50   # 支撑句占比低于此值 → 疑似幻觉


# ── 知识支撑度（防幻觉）辅助函数 ──

def _chunk_text(chunk) -> str:
    """从检索分块中抽取文本（兼容多种字段名）。"""
    if isinstance(chunk, dict):
        for k in ("content", "text", "chunk", "chunk_text", "page_content"):
            v = chunk.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return ""
    if isinstance(chunk, str):
        return chunk
    return ""


def _split_sentences(text: str) -> list[str]:
    """按中英文句末标点切分讲解文档为句子（过滤过短句）。"""
    parts = re.split(r"(?<=[。！？!?；;\n])", text or "")
    sents = [p.strip() for p in parts if p and p.strip()]
    return [s for s in sents if len(s) >= 8]


def _compute_embeddings_and_grounding(
    combined: list[str], texts: list[str], chunk_texts: list[str], teacher_sents: list[str],
) -> tuple:
    """在单个线程中完成 E5 嵌入推理 + numpy matmul 支撑度计算。
    作为 asyncio.to_thread 的 target，避免阻塞事件循环。"""
    from db.embedder import embed_batch  # 必须在本线程函数内导入（to_thread 跨线程，外层作用域不可见）
    emb = np.array(embed_batch(combined), dtype=np.float32)
    n_chunk = len(chunk_texts)
    n_agent = len(texts)
    grounding = {}
    if n_chunk and teacher_sents:
        chunk_emb = emb[n_agent:n_agent + n_chunk]
        teacher_emb = emb[n_agent + n_chunk:]
        grounding = _grounding_from_embeddings(teacher_emb, chunk_emb, chunk_texts)
    return emb, grounding


def _grounding_from_embeddings(teacher_emb, chunk_emb, chunk_texts) -> dict:
    """计算讲解文档相对检索知识库的支撑度（防幻觉核心）。

    返回 {score, grounded_fraction, flagged, best_sim, evidence}。
      - score            = 各句与知识库最大余弦相似度的均值
      - grounded_fraction= 最大相似度≥阈值的句子占比
      - flagged          = score<阈值 或 支撑句占比<阈值
    evidence 取相似度最高的分块文本，供前端/审阅溯源。
    """
    def _norm(m):
        n = np.linalg.norm(m, axis=1, keepdims=True)
        return m / np.where(n == 0, 1, n)

    t = _norm(np.asarray(teacher_emb, dtype=np.float32))
    c = _norm(np.asarray(chunk_emb, dtype=np.float32))
    sims = t @ c.T                       # (n_sent, n_chunk)
    max_sims = sims.max(axis=1)
    score = float(max_sims.mean())
    grounded_fraction = float((max_sims >= _GROUNDING_FLAG_SCORE).mean())
    flagged = bool(score < _GROUNDING_FLAG_SCORE or grounded_fraction < _GROUNDING_FLAG_FRACTION)
    best_idx = int(max_sims.argmax())
    best_sim = float(max_sims[best_idx])
    best_text = chunk_texts[best_idx] if 0 <= best_idx < len(chunk_texts) else ""
    evidence = [{"text": best_text[:500], "score": round(best_sim, 3), "source": "retrieved_kb"}]
    return {
        "score": score,
        "grounded_fraction": grounded_fraction,
        "flagged": flagged,
        "best_sim": best_sim,
        "evidence": evidence,
    }


def _map_disposition(resolution: str) -> str:
    """将消解结论字符串映射为处置类型（adopt/reject/human_review）。"""
    r = (resolution or "").lower()
    if any(k in r for k in ("正确", "综合修正", "采纳", "adopt")):
        return "adopt"
    if any(k in r for k in ("否决", "错误", "不成立", "reject")):
        return "reject"
    # 默认人工复核（含「需人工审核」「无法判断」等）
    return "human_review"


# ── 防幻觉可演示：修正回写 + diff + 引用 + 置信度（F-enhance）──

_CORRECTION_MARKERS = ["修正内容：", "修正内容:", "corrected_content"]


def _extract_corrected_content(resolution: str) -> str:
    """从消解结论字符串中提取修正后内容。

    冲突引擎 EvidenceConflictResolver._llm_resolve 返回的 JSON 含 corrected_content，
    但 resolve() 将其追加到 resolution 字符串（"\\n\\n修正内容：xxx"）。
    本函数解析出修正文本，供回写最终交付。
    """
    if not resolution:
        return ""
    for marker in _CORRECTION_MARKERS:
        idx = resolution.find(marker)
        if idx >= 0:
            return resolution[idx + len(marker):].strip()
    return ""


def _apply_corrections_to_state(state: AgentState, conflicts: list[dict]) -> list[dict]:
    """将 adoptable 冲突的修正内容回写最终交付（teacher_doc），返回 corrections diff。

    防幻觉硬核演示：检出冲突 → 提取修正 → 回写 state["teacher_doc"] →
    生成 before/after diff 供前端高亮展示「系统在校错」。

    仅对 disposition=adopt 且涉及 teacher 的冲突做回写（讲解文档是核心交付）。
    无修正内容时跳过（不阻断）。
    """
    corrections: list[dict] = []
    teacher_doc = state.get("teacher_doc") or ""
    if not teacher_doc:
        return corrections

    corrected = teacher_doc
    for c in conflicts:
        disp = c.get("disposition", "")
        if disp != "adopt":
            continue
        # 涉及 teacher 的冲突才回写讲解文档
        involved = {c.get("agent_a", ""), c.get("agent_b", "")}
        if "teacher" not in involved:
            continue
        fixed = _extract_corrected_content(c.get("resolution", ""))
        if not fixed or len(fixed) < 4:
            continue
        # 回写：将修正内容追加为「✅ 证据校验修正」段落（保留原文做 diff）
        before_snippet = corrected[-300:] if len(corrected) > 300 else corrected
        corrected = corrected.rstrip() + f"\n\n---\n✅ **证据校验修正**（冲突 {c.get('id', '')}）：\n{fixed}\n"
        corrections.append({
            "field": "teacher_doc",
            "conflict_id": c.get("id", ""),
            "description": c.get("description", ""),
            "before": before_snippet,
            "after": fixed,
            "applied": True,
        })

    if corrections:
        state["teacher_doc"] = corrected
        state["evidence_corrected"] = True
    return corrections


def _build_citations(state: AgentState, conflicts: list[dict], grounding: dict = None) -> list[dict]:
    """收集引用章节（知识库来源），供前端展示溯源证据。

    来源：
      1. retrieved_chunks（检索知识库分块）— 提取 source/chapter
      2. 冲突 evidence（FrugalRAG 检索证据）
      3. grounding evidence（支撑度最佳匹配分块）
    去重后按 score 降序，取 top 8。
    """
    citations: list[dict] = []
    seen: set[str] = set()

    # 1. 检索知识库分块
    for chunk in (state.get("retrieved_chunks") or []):
        if isinstance(chunk, dict):
            text = _chunk_text(chunk)[:200]
            source = chunk.get("source") or chunk.get("chapter_name") or chunk.get("metadata", {}).get("chapter_name", "") if isinstance(chunk.get("metadata"), dict) else ""
            if isinstance(chunk.get("metadata"), dict):
                source = source or chunk["metadata"].get("chapter_name", "") or chunk["metadata"].get("source", "")
        else:
            text = str(chunk)[:200]
            source = ""
        key = text[:60]
        if key and key not in seen:
            seen.add(key)
            citations.append({"text": text, "source": source or "知识库", "score": float(chunk.get("score", 0.0)) if isinstance(chunk, dict) else 0.0})

    # 2. 冲突 evidence
    for c in conflicts:
        for e in (c.get("evidence") or []):
            text = (e.get("text") or "")[:200]
            key = text[:60]
            if key and key not in seen:
                seen.add(key)
                citations.append({"text": text, "source": e.get("source", "") or "FrugalRAG", "score": float(e.get("score", 0.0) or 0.0)})

    # 3. grounding evidence
    if grounding and grounding.get("evidence"):
        for e in grounding["evidence"]:
            text = (e.get("text") or "")[:200]
            key = text[:60]
            if key and key not in seen:
                seen.add(key)
                citations.append({"text": text, "source": e.get("source", "") or "知识库", "score": float(e.get("score", 0.0) or 0.0)})

    citations.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return citations[:8]


def _compute_confidence_score(overall_consistency: float, grounding: dict = None, total_conflicts: int = 0) -> float:
    """计算防幻觉置信度（0-1）。

    综合：
      - 跨 Agent 一致性（overall_consistency）
      - 知识支撑度 grounding（若有）
      - 冲突数量惩罚
    """
    base = float(overall_consistency or 1.0)
    if grounding:
        g = float(grounding.get("score", 0.5) or 0.5)
        base = base * 0.5 + g * 0.5
    # 冲突惩罚：每个冲突扣 0.05，下限 0.1
    penalty = min(total_conflicts * 0.05, 0.4)
    return round(max(0.1, base - penalty), 3)


def _collect_agent_results(state: AgentState) -> list[dict]:
    """按固定顺序从 state 收集各 Agent 产出文本，过滤空内容。"""
    results: list[dict] = []
    for field, agent_name, _label in _AGENT_FIELD_MAP:
        val = state.get(field)
        if field == "mindmap" and isinstance(val, dict):
            content = val.get("mermaid", "")
        else:
            content = val or ""
        if isinstance(content, str) and content.strip():
            results.append({"agent_name": agent_name, "content": content})
    return results


def _build_report(state: AgentState, engine_result: dict, elapsed_ms: float, status: str = "ok", grounding: dict = None) -> dict:
    """将引擎返回映射为前端契约 EvidenceReport（含知识支撑度）。"""
    conflicts_raw = engine_result.get("conflicts", []) or []
    conflicts = []
    for idx, c in enumerate(conflicts_raw):
        conflicts.append({
            "id": f"{c.get('agent_a')}__{c.get('agent_b')}__{c.get('type')}__{idx}",
            "type": c.get("type", "semantic"),
            "agent_a": c.get("agent_a", ""),
            "agent_b": c.get("agent_b", ""),
            "description": c.get("description", ""),
            "severity": _TYPE_SEVERITY.get(c.get("type", ""), "low"),
            "evidence": [
                {
                    "text": e.get("text", ""),
                    "score": float(e.get("score", 0.0) or 0.0),
                    "source": e.get("source", ""),
                }
                for e in (c.get("evidence", []) or [])
            ],
            "resolution": c.get("resolution", ""),
            "confidence": float(c.get("confidence", 0.0) or 0.0),
            "disposition": _map_disposition(c.get("resolution", "")),
        })

    # 知识支撑度（防幻觉）：讲解文档与检索知识库支撑度低 → 疑似幻觉
    total_conflicts = int(engine_result.get("total_conflicts", len(conflicts)) or 0)
    unresolved = int(engine_result.get("unresolved", 0) or 0)
    if grounding and grounding.get("flagged"):
        conflicts.append({
            "id": "teacher__knowledge_base__grounding__hallucination",
            "type": "factual",
            "agent_a": "teacher",
            "agent_b": "knowledge_base",
            "description": (
                f"讲解文档与检索知识库支撑度偏低（grounding={grounding.get('score'):.2f}），"
                f"存在未由知识库支撑的疑似幻觉内容，建议人工复核或补充检索。"
            ),
            "severity": "high",
            "evidence": grounding.get("evidence", []),
            "resolution": "需人工复核",
            "confidence": float(grounding.get("score", 0.0) or 0.0),
            "disposition": "human_review",
        })
        total_conflicts += 1
        unresolved += 1

    overall = float(engine_result.get("overall_consistency", 1.0) or 1.0)
    # 防幻觉可演示：引用章节 + 置信度（corrections 由节点回写后追加）
    citations = _build_citations(state, conflicts, grounding)
    confidence_score = _compute_confidence_score(overall, grounding, total_conflicts)
    return {
        "status": status,
        "overall_consistency": overall,
        "consistency_score": round(overall * 100, 1),
        "confidence_score": confidence_score,
        "total_conflicts": total_conflicts,
        "resolved": int(engine_result.get("resolved", 0) or 0),
        "unresolved": unresolved,
        "conflicts": conflicts,
        "citations": citations,
        "corrections": [],
        "grounding_score": round(float(grounding.get("score", 0.0)) * 100, 1) if grounding else None,
        "grounding_flagged": bool(grounding.get("flagged")) if grounding else False,
        "checked_agents": [r["agent_name"] for r in _collect_agent_results(state)],
        "course": state.get("course", ""),
        "elapsed_ms": int(elapsed_ms),
    }


def _empty_report(state: AgentState, elapsed_ms: float, status: str, error: str = "") -> dict:
    """降级/空结果报告（设计 §7.5：不抛异常，给出 status 字段）。"""
    return {
        "status": status,
        "overall_consistency": 1.0,
        "consistency_score": 100.0,
        "confidence_score": 1.0,
        "total_conflicts": 0,
        "resolved": 0,
        "unresolved": 0,
        "conflicts": [],
        "citations": [],
        "corrections": [],
        "grounding_score": None,
        "grounding_flagged": False,
        "checked_agents": [],
        "course": state.get("course", ""),
        "elapsed_ms": int(elapsed_ms),
        "error": error,
    }


async def evidence_check_node(state: AgentState) -> AgentState:
    """证据校验 LangGraph 节点（critic 之后、path_planner 之前）。

    不修改既有冲突引擎；仅做编排 + 调用 + 报告映射。任何异常均降级返回，
    保证 critic → path_planner 链路不破（设计 §7.5）。
    """
    state["status"] = "evidence_checking"
    state["current_agent"] = "evidence_check"

    start = time.time()
    try:
        agent_results = _collect_agent_results(state)
        if not agent_results:
            state["evidence_report"] = _empty_report(state, (time.time() - start) * 1000, "ok")
            return state

        # 1. 计算 E5 嵌入（语义一致性 + 知识支撑度/防幻觉共用）；失败则降级
        embeddings = None
        grounding = None  # {score, grounded_fraction, flagged, best_sim, evidence}
        try:
            texts = [r["content"] for r in agent_results]
            chunks = state.get("retrieved_chunks") or []
            chunk_texts = [_chunk_text(c) for c in chunks]
            teacher_doc = state.get("teacher_doc") or ""
            teacher_sents = _split_sentences(teacher_doc) if teacher_doc.strip() else []

            combined = texts + chunk_texts + teacher_sents
            if combined:
                # 在 thread 中执行 E5 推理 + numpy matmul，避免阻塞事件循环
                import asyncio as _asyncio
                emb, grounding = await _asyncio.to_thread(
                    _compute_embeddings_and_grounding,
                    combined, texts, chunk_texts, teacher_sents,
                )
                n_agent = len(texts)
                embeddings = emb[:n_agent] if n_agent else None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"证据校验嵌入/支撑度计算失败，降级为仅事实/关键词检测: {e}")
            embeddings = None
            grounding = None

        # 2. 调用既有冲突引擎（不修改引擎内部）
        course = state.get("course", "computer_network") or "computer_network"
        engine_result = await conflict_engine.check_and_resolve(
            agent_results, course=course, agent_embeddings=embeddings
        )

        state["evidence_report"] = _build_report(
            state, engine_result, (time.time() - start) * 1000, status="ok",
            grounding=grounding,
        )
        report = state["evidence_report"]
        # 防幻觉可演示：将 adoptable 冲突修正回写最终交付（teacher_doc），
        # 生成 before/after diff 写入 report["corrections"]，供前端高亮展示「系统在校错」
        try:
            corrections = _apply_corrections_to_state(state, report.get("conflicts", []))
            if corrections:
                report["corrections"] = corrections
                logger.info(f"证据校验修正回写: {len(corrections)} 处修正已应用至讲解文档")
        except Exception as ce:  # noqa: BLE001
            logger.warning(f"修正回写失败，不影响主流程: {ce}")
        if grounding:
            logger.info(f"知识支撑度(防幻觉): grounding={grounding['score']:.3f}, "
                        f"flagged={grounding['flagged']}")
        logger.info(
            f"证据校验完成: 检出 {report['total_conflicts']} 冲突，已消解 {report['resolved']} 个"
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"证据校验节点异常，降级返回: {e}")
        state["evidence_report"] = _empty_report(
            state, (time.time() - start) * 1000, "error", error=str(e)
        )

    return state
