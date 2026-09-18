# ============================================================
# smoke_repro.py — 离线复现 LangGraph SSE 流水线 int+bytes 崩溃
# 用桩 LLM 替换真实调用，完整跑 agent_graph.astream + event_stream 处理逻辑，
# 捕获首个异常的完整 traceback，定位 int + bytes 真实来源。
# ============================================================
import asyncio
import json
import os
import sys
import traceback
import types

# 让 Python 不把 bytes 静默 repr，便于观察
os.environ.setdefault("NETLEARN_ENV", "development")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 1. 桩 LLM：替换 db.llm_provider.LLMProvider 的所有生成方法 ──
import db.llm_provider as llm_mod

_FAKE = "这是一段用于冒烟测试的讲解内容。TCP 是面向连接的传输层协议，UDP 是无连接的。" \
        "交换机工作在数据链路层，路由器工作在网络层。HTTP 端口是 80，HTTPS 端口是 443。" \
        "三次握手顺序为 SYN -> SYN+ACK -> ACK。"

async def _fake_text_completion(self, system_prompt, user_prompt, **kwargs):
    return _FAKE

async def _fake_chat(self, messages, **kwargs):
    return _FAKE

llm_mod.LLMProvider.text_completion = _fake_text_completion
llm_mod.LLMProvider.chat = _fake_chat

# ── 2. 导入真实 graph 与 SSE 处理辅助函数 ──
from api.langgraph import _sse, _node_summary
from shared.content_safety import audit_output
from shared.metrics import record_langgraph_node_seconds
from agents.graph import agent_graph

# ── 3. 完整复刻 event_stream 的处理逻辑（与 api/langgraph.py 一致）──
async def replay_event_stream(state):
    print("[repro] astream 开始...", flush=True)
    _ait = agent_graph.astream(state, stream_mode="updates").__aiter__()
    while True:
        try:
            event = await _ait.__anext__()
        except StopAsyncIteration:
            break
        except Exception as e:
            print("\n[repro] !!! 节点执行内部抛出异常（astream.__anext__）:", flush=True)
            traceback.print_exc()
            raise

        for node_name, node_state in event.items():
            try:
                record_langgraph_node_seconds(node_name, 0.1)
                _sse("node_done", node_name, _node_summary(node_name, node_state))

                if node_name == "coordinator":
                    _sse("status", "coordinating", f"请求解析完成: 主题={node_state.get('topic', '')}, 难度={node_state.get('difficulty', '')}")
                elif node_name == "diagnostician":
                    diag = node_state.get("diagnosis", {}) or {}
                    _sse("status", "diagnosing", f"诊断完成: 薄弱点={diag.get('weak_areas', [])}, 建议深度={diag.get('recommended_depth', '')}")
                elif node_name == "planner":
                    _sse("status", "planning", "规划完成")
                elif node_name == "retriever":
                    chunks = node_state.get("retrieved_chunks", []) or []
                    _sse("node_done", "retriever", f"检索完成: 命中 {len(chunks)} 个相关知识点")
                    for i, c in enumerate(chunks[:3]):
                        _sse("retrieval", f"chunk_{i}", c.get("content", "")[:200] + "...")
                elif node_name == "generator_cluster":
                    _sse("status", "generating", "Generator Cluster 正在并行生成资源...")
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
                            _sse("safety_alert", _sse_field, "; ".join(_notes))
                        _sse("content", _sse_field, _safe)
                    mindmap_data = node_state.get("mindmap") or {}
                    if mindmap_data:
                        _mermaid = mindmap_data.get("mermaid", "") or ""
                        _mermaid, _m_notes = await audit_output(_mermaid, "langgraph/stream/mindmap")
                        if _m_notes:
                            _sse("safety_alert", "mindmap", "; ".join(_m_notes))
                        _sse("content", "mindmap", _mermaid)
                        _sse("data", "mindmap_stats", json.dumps(mindmap_data.get("stats", {}), ensure_ascii=False))
                        _sse("data", "mindmap_weak_points", json.dumps(mindmap_data.get("weak_points", []), ensure_ascii=False))
                    ppt_file = node_state.get("ppt_file")
                    if ppt_file and ppt_file.get("ok"):
                        _sse("content", "ppt_file", json.dumps(ppt_file, ensure_ascii=False))
                    _sse("content", "video_script", node_state.get("video_script", "") or "")
                elif node_name == "assessor":
                    _sse("status", "assessing", "评估反馈完成")
                elif node_name == "critic":
                    critic_report = node_state.get("critic_report", "") or ""
                    consensus = node_state.get("consensus", {}) or {}
                    if critic_report:
                        critic_report, _cr_notes = await audit_output(critic_report, "langgraph/stream/critic")
                        if _cr_notes:
                            _sse("safety_alert", "critic", "; ".join(_cr_notes))
                        _sse("content", "critic", critic_report)
                    if consensus.get("status") == "rejected":
                        _sse("warning", "gomarl", f"GOMARL 共识警告: {consensus.get('flagged_issues', [])}")
                elif node_name == "evidence_check":
                    report = node_state.get("evidence_report") or {}
                    _sse("status", "evidence_checking", "证据校验 Agent 正在检测冲突...")
                    total = report.get("total_conflicts", 0)
                    resolved = report.get("resolved", 0)
                    _sse("node_done", "evidence_check", f"证据校验完成: 检出 {total} 个冲突，已消解 {resolved} 个")
                    _sse("evidence", "report", json.dumps(report, ensure_ascii=False))
                    corrections = report.get("corrections") or []
                    if corrections:
                        corrected_doc = node_state.get("teacher_doc") or ""
                        if corrected_doc:
                            _cdoc, _cnotes = await audit_output(corrected_doc, "langgraph/stream/teacher_corrected")
                            _sse("content", "teacher_corrected", _cdoc)
                        _sse("status", "evidence_corrected", f"防幻觉修正: {len(corrections)} 处冲突已回写最终交付")
                elif node_name == "quality_gate":
                    verdict = node_state.get("gate_verdict", "pass")
                    reasons = node_state.get("gate_reasons") or []
                    gate_result = node_state.get("gate_result") or {}
                    if verdict == "pass":
                        _sse("gate_pass", "quality_gate", json.dumps({"verdict": "pass", "reasons": reasons, "consistency_score": gate_result.get("consistency_score")}, ensure_ascii=False))
                    elif verdict == "fix":
                        _sse("gate_fix", "quality_gate", json.dumps({"verdict": "fix", "reasons": reasons, "retry_count": gate_result.get("gate_retry_count", 0), "consistency_score": gate_result.get("consistency_score")}, ensure_ascii=False))
                    elif verdict == "reject":
                        _sse("gate_rejected", "quality_gate", json.dumps({"verdict": "reject", "reasons": reasons, "hard_failures": gate_result.get("hard_failures", []), "consistency_score": gate_result.get("consistency_score")}, ensure_ascii=False))
                        _sse("status", "rejected", "产物验收不通过，流水线已终止")
                        return
                elif node_name == "path_planner":
                    _sse("status", "path_planning", "路径规划完成")
            except Exception as e:
                print(f"\n[repro] !!! event_stream 处理节点 '{node_name}' 时抛出 int+bytes 类异常:", flush=True)
                traceback.print_exc()
                raise

    print("[repro] astream 全部节点完成", flush=True)


def build_state():
    return {
        "messages": [],
        "user_request": "讲解 TCP 三次握手",
        "student_profile": {"learning_style": "reading", "knowledge_base": "beginner", "weak_points": "网络层"},
        "topic": "TCP 三次握手",
        "difficulty": "medium",
        "course": "computer_network",
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


if __name__ == "__main__":
    st = build_state()
    try:
        asyncio.run(replay_event_stream(st))
        print("\n[repro] ✅ 未复现 int+bytes，流水线完整通过", flush=True)
    except Exception as e:
        print(f"\n[repro] ❌ 捕获异常: {type(e).__name__}: {e}", flush=True)
        sys.exit(1)
