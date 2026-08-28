# ============================================================
# API — LangGraph 多智能体 SSE 流式端点（新架构核心）
# 已迁移：手动顺序 await → agent_graph.astream
# ============================================================

import json
import logging
import asyncio
import time
import os
import traceback

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from shared.sse_guard import sse_disconnect_guard

from models import LangGraphStreamRequest
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from shared.content_safety import audit_output  # P1-7：流式输出内容安全审核
from shared.metrics import record_langgraph_node_seconds  # P1-4：节点耗时指标

logger = logging.getLogger("netlearn.langgraph")
# F-011：LangGraph 流式学习端点统一鉴权 + 每用户 LLM 配额（429）
router = APIRouter(prefix="/agents", tags=["langgraph"], dependencies=[Depends(require_llm_quota)])


@router.post("/langgraph/stream")
async def langgraph_stream(req: LangGraphStreamRequest, request: Request, user: dict = Depends(get_current_user)):
    """LangGraph 10-Agent 流式学习端点。

    使用 agent_graph.astream 替代手动顺序 await 各节点。
    条件边（route_after_retriever, route_after_critic, route_after_quality_gate）自动执行。
    循环重试（critic→retriever, quality_gate→generator_cluster）前端需处理重复节点事件。
    产物验收闸门（quality_gate）REJECT 时直接终止流。
    """

    async def event_stream():
        try:
            from agents.graph import agent_graph
            from agents.state import AgentState

            # 构建初始状态
            user_id = user.get("user_id") or user.get("id") or ""
            memory_context = ""
            if user_id:
                try:
                    from services.memory_service import build_memory_context
                    memory_context = build_memory_context(
                        user_id,
                        session_id=getattr(req, "session_id", None) or None,
                        max_episodes=8,
                    )
                except Exception as e:
                    logger.debug(f"记忆上下文组装失败(降级为空): {e}")

            state = {
                "messages": [],
                "user_request": req.message,
                "student_profile": req.profile or {},
                "memory_context": memory_context,
                "topic": req.topic or req.message,
                "difficulty": req.difficulty,
                "course": req.course,
                "diagnosis": None,
                "plan": None,
                "retrieved_chunks": None,
                "teacher_doc": None,
                "quiz": None,
                "media_plan": None,
                "extension": None,
                "mindmap": None,
                "code_practice": None,
                "ppt_outline": None,
                "video_script": None,
                "consensus": None,
                "critic_report": None,
                "evidence_report": None,
                "gate_result": None,
                "gate_verdict": "",
                "gate_reasons": [],
                "gate_retry_count": 0,
                "current_agent": "coordinator",
                "error": None,
                "status": "coordinating",
                "regenerate_round": 0,
            }

            yield _sse("status", "coordinating", "Coordinator 正在解析请求...")

            # 使用 graph.astream 遍历所有节点（带超时保护，防止单个 LLM 调用挂起导致流水线阻塞）
            # P0-B：单节点超时由 30s 提至 120s。真实节点最长约 277s 发生在「限流级联」下
            # （7 路并发轰单 key → 11202/11203 → 反复回退重试）；X2 主通道修复 + 每通道并发
            # 信号量(4) + 退避重试后，正常节点耗时远低于此。若个别节点仍超时，仅该流水线降级。
            NODE_TIMEOUT = 120  # 单节点超时 120s
            _ait = agent_graph.astream(state, stream_mode="updates").__aiter__()
            while True:
                _node_start = time.perf_counter()
                try:
                    event = await asyncio.wait_for(_ait.__anext__(), timeout=NODE_TIMEOUT)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.error(f"LangGraph 节点执行超时（{NODE_TIMEOUT}s），流水线降级终止")
                    yield _sse("error", "timeout", f"节点执行超时（{NODE_TIMEOUT}s），流水线已降级终止")
                    yield "data: [DONE]\n\n"
                    return
                # event = {node_name: updated_state_dict}
                _node_elapsed = time.perf_counter() - _node_start
                for node_name, node_state in event.items():
                    # P1-4：记录节点耗时指标
                    record_langgraph_node_seconds(node_name, _node_elapsed)
                    # 推送 node_done SSE
                    yield _sse("node_done", node_name, _node_summary(node_name, node_state))

                    # 按 node_name 推送具体内容事件
                    if node_name == "coordinator":
                        yield _sse("status", "coordinating", f"请求解析完成: 主题={node_state.get('topic', '')}, 难度={node_state.get('difficulty', '')}")

                    elif node_name == "diagnostician":
                        diag = node_state.get("diagnosis", {}) or {}
                        yield _sse("status", "diagnosing", f"诊断完成: 薄弱点={diag.get('weak_areas', [])}, 建议深度={diag.get('recommended_depth', '')}")

                    elif node_name == "planner":
                        yield _sse("status", "planning", "规划完成")

                    elif node_name == "retriever":
                        chunks = node_state.get("retrieved_chunks", []) or []
                        yield _sse("node_done", "retriever", f"检索完成: 命中 {len(chunks)} 个相关知识点")
                        for i, c in enumerate(chunks[:3]):
                            yield _sse("retrieval", f"chunk_{i}", c.get("content", "")[:200] + "...")

                    elif node_name == "generator_cluster":
                        yield _sse("status", "generating", "Generator Cluster (7 Agents) 正在并行生成资源...")
                        # P1-7：生成内容输出安全审核（敏感词 + 讯飞合规 + 幻觉检查）
                        for _state_key, _sse_field in [
                            ("teacher_doc", "teacher"), ("quiz", "quiz"),
                            ("media_plan", "media"), ("extension", "extension"),
                            ("code_practice", "code_practice"),
                            ("ppt_outline", "ppt_outline"),
                            ("video_script", "video_script"),
                        ]:
                            _raw = node_state.get(_state_key, "") or ""
                            _safe, _notes = await audit_output(_raw, f"langgraph/stream/{_sse_field}")
                            if _notes:
                                yield _sse("safety_alert", _sse_field, "; ".join(_notes))
                            yield _sse("content", _sse_field, _safe)
                        # 新增资源类型
                        mindmap_data = node_state.get("mindmap") or {}
                        if mindmap_data:
                            _mermaid = mindmap_data.get("mermaid", "") or ""
                            _mermaid, _m_notes = await audit_output(_mermaid, "langgraph/stream/mindmap")
                            if _m_notes:
                                yield _sse("safety_alert", "mindmap", "; ".join(_m_notes))
                            yield _sse("content", "mindmap", _mermaid)
                            yield _sse("data", "mindmap_stats", json.dumps(mindmap_data.get("stats", {}), ensure_ascii=False))
                            yield _sse("data", "mindmap_weak_points", json.dumps(mindmap_data.get("weak_points", []), ensure_ascii=False))
                        # 真实 .pptx 文件（多模态产出，可下载）
                        ppt_file = node_state.get("ppt_file")
                        if ppt_file and ppt_file.get("ok"):
                            yield _sse("content", "ppt_file", json.dumps(ppt_file, ensure_ascii=False))
                        yield _sse("content", "video_script", node_state.get("video_script", "") or "")

                    elif node_name == "assessor":
                        yield _sse("status", "assessing", "评估反馈完成")

                    elif node_name == "critic":
                        critic_report = node_state.get("critic_report", "") or ""
                        consensus = node_state.get("consensus", {}) or {}
                        if critic_report:
                            # P1-7：审阅报告输出安全审核
                            critic_report, _cr_notes = await audit_output(critic_report, "langgraph/stream/critic")
                            if _cr_notes:
                                yield _sse("safety_alert", "critic", "; ".join(_cr_notes))
                            yield _sse("content", "critic", critic_report)
                        if consensus.get("status") == "rejected":
                            yield _sse("warning", "gomarl", f"GOMARL 共识警告: {consensus.get('flagged_issues', [])}")

                    elif node_name == "evidence_check":
                        report = node_state.get("evidence_report") or {}
                        yield _sse("status", "evidence_checking", "证据校验 Agent 正在检测冲突...")
                        total = report.get("total_conflicts", 0)
                        resolved = report.get("resolved", 0)
                        yield _sse("node_done", "evidence_check", f"证据校验完成: 检出 {total} 个冲突，已消解 {resolved} 个")
                        try:
                            yield _sse("evidence", "report", json.dumps(report, ensure_ascii=False))
                        except (TypeError, ValueError):
                            pass
                        # 防幻觉可演示：修正回写后推送修正后讲解文档 + diff
                        corrections = report.get("corrections") or []
                        if corrections:
                            corrected_doc = node_state.get("teacher_doc") or ""
                            if corrected_doc:
                                _cdoc, _cnotes = await audit_output(corrected_doc, "langgraph/stream/teacher_corrected")
                                yield _sse("content", "teacher_corrected", _cdoc)
                            yield _sse("status", "evidence_corrected", f"防幻觉修正: {len(corrections)} 处冲突已回写最终交付")

                    elif node_name == "quality_gate":
                        verdict = node_state.get("gate_verdict", "pass")
                        reasons = node_state.get("gate_reasons") or []
                        gate_result = node_state.get("gate_result") or {}

                        if verdict == "pass":
                            yield _sse("gate_pass", "quality_gate", json.dumps({
                                "verdict": "pass",
                                "reasons": reasons,
                                "consistency_score": gate_result.get("consistency_score"),
                            }, ensure_ascii=False))
                        elif verdict == "fix":
                            yield _sse("gate_fix", "quality_gate", json.dumps({
                                "verdict": "fix",
                                "reasons": reasons,
                                "retry_count": gate_result.get("gate_retry_count", 0),
                                "consistency_score": gate_result.get("consistency_score"),
                            }, ensure_ascii=False))
                        elif verdict == "reject":
                            yield _sse("gate_rejected", "quality_gate", json.dumps({
                                "verdict": "reject",
                                "reasons": reasons,
                                "hard_failures": gate_result.get("hard_failures", []),
                                "consistency_score": gate_result.get("consistency_score"),
                            }, ensure_ascii=False))
                            yield _sse("status", "rejected", "产物验收不通过，流水线已终止")
                            yield "data: [DONE]\n\n"
                            return

                    elif node_name == "path_planner":
                        yield _sse("status", "path_planning", "路径规划完成")

            # ── 完成 ──
            yield _sse("status", "done", "所有 Agent 流水线执行完毕")
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("LangGraph pipeline error")
            # Sanitized: no internal paths or tracebacks leaked to client
            yield _sse("error", "pipeline_error", "Pipeline execution failed, please retry")
            yield "data: [DONE]\n\n"

    return StreamingResponse(sse_disconnect_guard(request, event_stream()), media_type="text/event-stream")


def _sse(event_type: str, field: str, content: str) -> str:
    """构建 SSE 格式的事件消息"""
    return f"data: {json.dumps({'type': event_type, 'field': field, 'content': content}, ensure_ascii=False)}\n\n"


def _node_summary(node_name: str, state: dict) -> str:
    """为各节点生成简短摘要"""
    summaries = {
        "coordinator": f"主题={state.get('topic', '')}, 难度={state.get('difficulty', '')}",
        "diagnostician": f"诊断: 薄弱点={((state.get('diagnosis') or {}).get('weak_areas', []))}",
        "planner": "学习计划已生成",
        "retriever": f"命中 {len(state.get('retrieved_chunks') or [])} 个知识点",
        "generator_cluster": "7种资源已生成",
        "assessor": "评估反馈完成",
        "critic": "质量审阅完成",
        "evidence_check": "证据校验完成",
        "quality_gate": "产物验收闸门完成",
        "path_planner": "学习路径已规划",
    }
    return summaries.get(node_name, f"{node_name} 完成")